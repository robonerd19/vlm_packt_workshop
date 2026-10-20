"""VLM contract and RGB-D geometry for tabletop pick and place, independent of ROS.

parse_box/project_box follow the TurtleBot VLM workshop (vlm_nav.perception).
"""
import base64
import json
import math
import re
import urllib.request

import cv2
import numpy as np

from .kinematics import rpy_matrix


class PerceptionError(ValueError):
    pass


def _json(text):
    return json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip()))


def parse_box(text, width, height):
    """Require normalized 0..1000 coordinates; never guess pixel conventions."""
    try:
        data = _json(text)
        if data.get('found') is False:
            raise PerceptionError('The VLM reports the object is not visible.')
        box = data['bbox']
        if not isinstance(box, list) or len(box) != 4:
            raise ValueError('bbox must contain four numbers')
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in box):
            raise ValueError('bbox coordinates must be numbers')
        x1, y1, x2, y2 = map(float, box)
        if not all(math.isfinite(x) and 0 <= x <= 1000 for x in box):
            raise ValueError('bbox coordinates must be finite and in 0..1000')
        if x2 <= x1 or y2 <= y1:
            raise ValueError('bbox must have positive area')
        return (x1*width/1000, y1*height/1000, x2*width/1000, y2*height/1000)
    except PerceptionError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise PerceptionError(f'Invalid model detection: {exc}') from exc


def project_box(box, depth, intrinsic, max_depth=3.0):
    """Back-project the nearest coherent surface in the box (an object's top face)."""
    fx, fy, cx, cy = intrinsic
    if not all(math.isfinite(x) for x in intrinsic) or fx <= 0 or fy <= 0:
        raise PerceptionError('Invalid camera intrinsics.')
    h, w = depth.shape
    x1, y1, x2, y2 = box
    left, top = max(0, int(x1)), max(0, int(y1))
    right, bottom = min(w, math.ceil(x2)), min(h, math.ceil(y2))
    roi = depth[top:bottom, left:right]
    valid_mask = np.isfinite(roi) & (roi > 0.1) & (roi < max_depth)
    valid = roi[valid_mask]
    if valid.size < max(12, roi.size // 5):
        raise PerceptionError('Insufficient valid depth at the detected object.')
    # The nearest surface is the object's top; a loose VLM box is mostly table, so use a
    # low percentile (robust to a few noisy pixels) rather than the median.
    near = float(np.percentile(valid, 2))
    mask = (valid_mask & (np.abs(roi-near) <= 0.01)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 1:
        raise PerceptionError('No coherent foreground depth surface.')
    component = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[component, cv2.CC_STAT_AREA] < 12:
        raise PerceptionError('Foreground surface too small.')
    rows, columns = np.nonzero(labels == component)
    # Centroid of the top face rather than the box centre: boxes from a 2B VLM are loose.
    px, py = float(columns.mean())+left, float(rows.mean())+top
    z = float(np.median(roi[labels == component]))
    return np.array([(px-cx)*z/fx, (py-cy)*z/fy, z])


def optical_to_world(point, camera_xyz, camera_rpy):
    """Gazebo cameras look along link +x; optical frame is x right, y down, z forward."""
    x, y, z = point
    return rpy_matrix(*camera_rpy) @ np.array([z, -x, -y]) + np.asarray(camera_xyz)


# OpenCV hue ranges (0..180) for colour words an instruction may use.
HUES = {'red': ((0, 8), (170, 180)), 'orange': ((8, 22),), 'yellow': ((22, 38),),
        'green': ((38, 85),), 'blue': ((90, 130),), 'purple': ((130, 170),), 'violet': ((130, 170),)}


def check_colour(bgr, box, phrase):
    """A 2B VLM often boxes the nearest object rather than refusing; verify the named colour."""
    names = [w for w in re.findall(r'[a-z]+', phrase.lower()) if w in HUES]
    if not names:
        return  # shortcut: colourless phrases ("bin") are not verified; add a crop re-query if needed.
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    centre = bgr[int(y1 + h/4):int(y2 - h/4) + 1, int(x1 + w/4):int(x2 - w/4) + 1]
    hsv = cv2.cvtColor(centre, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    saturated = hsv[hsv[:, 1] > 80]
    hue = float(np.median(saturated[:, 0])) if len(saturated) else None
    if hue is None or not any(lo <= hue < hi for lo, hi in HUES[names[0]]):
        raise PerceptionError(f'No {names[0]} object found for "{phrase}".')


class InferenceClient:
    def __init__(self, url, timeout=120.0, image_width=448):
        self.url = url.rstrip('/')
        self.timeout = timeout
        self.image_width = image_width

    def healthy(self):
        try:
            with urllib.request.urlopen(self.url + '/health', timeout=1.0) as response:
                return response.status == 200
        except (OSError, ValueError):
            return False

    def describe(self, bgr):
        """Scene understanding: list what is on the table before acting."""
        text = self.complete(self._jpeg(bgr), (
            'This is a top-down view of a robot work table. List every distinct object on the '
            'table with its color and type. Return only JSON: {"objects":["red cube", ...]}.'), 128)
        try:
            objects = _json(text)['objects']
            if not isinstance(objects, list) or not all(isinstance(o, str) for o in objects):
                raise ValueError
            return [o.strip()[:60] for o in objects if o.strip()][:12]
        except (ValueError, KeyError, TypeError) as exc:
            raise PerceptionError('Invalid scene description response.') from exc

    def plan(self, instruction):
        """Split an instruction into what to pick and where to place it.

        Extraction only: given the scene object list as well, the 2B model swaps in a visible object.
        """
        text = self.complete(None, (
            'Robot instruction: ' + json.dumps(instruction) + '. Copy from the instruction the object '
            'to pick up and the destination to put it on. Return only JSON: {"pick":"...","place":"..."}.'), 64)
        try:
            data = _json(text)
            pick, place = data['pick'], data['place']
            if not all(isinstance(v, str) and 0 < len(v.strip()) <= 60 for v in (pick, place)):
                raise ValueError
        except (ValueError, KeyError, TypeError) as exc:
            raise PerceptionError('Could not interpret the instruction.') from exc
        return pick.strip(), place.strip()

    def locate(self, bgr, phrase):
        h, w = bgr.shape[:2]
        text = self.complete(self._jpeg(bgr), (
            'Locate the ' + phrase + ' in this image. Return only JSON: '
            '{"found":true,"bbox":[x1,y1,x2,y2]}. Coordinates MUST be normalized integers from '
            '0 to 1000 relative to the entire image. If absent return {"found":false}.'), 64)
        box = parse_box(text, w, h)
        check_colour(bgr, box, phrase)
        return box

    def _jpeg(self, bgr):
        h, w = bgr.shape[:2]
        scale = min(1.0, self.image_width / w)
        ok, jpeg = cv2.imencode('.jpg', cv2.resize(bgr, (round(w*scale), round(h*scale))))
        if not ok:
            raise PerceptionError('Unable to encode the camera image.')
        return jpeg.tobytes()

    def complete(self, jpeg, prompt, tokens):
        content = [{'type': 'text', 'text': prompt}]
        if jpeg is not None:
            content.insert(0, {'type': 'image_url', 'image_url': {
                'url': 'data:image/jpeg;base64,' + base64.b64encode(jpeg).decode()}})
        body = {'model': 'vlm', 'temperature': 0, 'max_tokens': tokens,
                'response_format': {'type': 'json_object'},
                'messages': [{'role': 'user', 'content': content}]}
        request = urllib.request.Request(self.url + '/v1/chat/completions', json.dumps(body).encode(),
                                         {'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise PerceptionError('Inference response exceeded size limit.')
        try:
            return json.loads(raw)['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise PerceptionError('Malformed inference response.') from exc
