"""Model contract and calibrated RGB-D geometry, independent of ROS."""
import base64
import json
import math
import re
import urllib.request

import cv2
import numpy as np


class PerceptionError(ValueError):
    pass


class ObjectNotFound(PerceptionError):
    """Valid model response indicating absence, rather than invalid geometry."""
    pass


class UnusableDetection(PerceptionError):
    """A box needs another view before it can become an approach target."""
    pass


def require_complete_box(box, width, height):
    # Edge-clipped objects do not provide reliable object extent/foreground.
    # Scan an overlapping view rather than approaching a truncated candidate.
    x1, y1, x2, y2 = box
    if x1 <= 1 or y1 <= 1 or x2 >= width-1 or y2 >= height-1:
        raise UnusableDetection('Detection touches the image boundary; another view is needed.')


# Ollama resizes each image for Qwen2.5-VL like Qwen's smart_resize: sides become
# multiples of 28 and small images are scaled up to at least 1024*28*28 pixels. The
# model answers in pixels of that resized image, whatever size was sent and even when
# asked for normalized coordinates (measured on Ollama 0.40.10: a 4:3 frame -> 1036x784).
FACTOR, MIN_PIXELS = 28, 1024 * 28 * 28


def model_size(width, height):
    # shortcut: no max_pixels branch; frames above ~3.6 MP would need it.
    w, h = round(width / FACTOR) * FACTOR, round(height / FACTOR) * FACTOR
    if w * h < MIN_PIXELS:
        beta = math.sqrt(MIN_PIXELS / (width * height))
        w, h = math.ceil(width * beta / FACTOR) * FACTOR, math.ceil(height * beta / FACTOR) * FACTOR
    return w, h


def parse_box(text, width, height, sent=None):
    """Read a pixel box given in the model's image size (default width x height); scale to width x height."""
    sent_w, sent_h = sent or (width, height)
    clean = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
    try:
        data = json.loads(clean)
        if data.get('found') is False:
            raise ObjectNotFound('Requested object was not found.')
        box = data['bbox_2d'] if 'bbox_2d' in data else data['bbox']
        if not isinstance(box, list) or len(box) != 4:
            raise ValueError('bbox must contain four numbers')
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in box):
            raise ValueError('bbox coordinates must be numbers')
        x1, y1, x2, y2 = map(float, box)
        if not all(math.isfinite(x) for x in box) or min(box) < 0 or x2 > sent_w or y2 > sent_h:
            raise ValueError(f'bbox coordinates must be finite and inside the {sent_w}x{sent_h} image')
        if x2 <= x1 or y2 <= y1:
            raise ValueError('bbox must have positive area')
        return (x1 * width / sent_w, y1 * height / sent_h,
                x2 * width / sent_w, y2 * height / sent_h)
    except ObjectNotFound:
        raise
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise PerceptionError(f'Invalid model detection: {exc}') from exc


def project_box(box, depth, intrinsic, max_depth=8.0):
    """Use a coherent foreground surface, including hollow objects such as chairs.

    A box centre can fall between chair/table legs and measure the background.
    Select a substantial connected near-depth surface within the entire box,
    then choose an actual surface pixel near the box centre for back-projection.
    """
    fx, fy, cx, cy = intrinsic
    if not all(math.isfinite(x) for x in intrinsic) or fx <= 0 or fy <= 0:
        raise PerceptionError('Invalid camera intrinsics.')
    h, w = depth.shape
    x1, y1, x2, y2 = box
    left, top = max(0, int(x1)), max(0, int(y1))
    right, bottom = min(w, math.ceil(x2)), min(h, math.ceil(y2))
    roi = depth[top:bottom, left:right]
    valid_mask = np.isfinite(roi) & (roi > 0.15) & (roi < max_depth)
    valid = roi[valid_mask]
    if valid.size < max(12, roi.size // 5):
        raise PerceptionError('Insufficient valid depth at the detected object.')
    # A percentile ignores isolated closer noise while retaining object surfaces
    # that cover a minority of a box containing gaps/background.
    near = float(np.percentile(valid, 20))
    band = max(0.10, near * 0.05)
    mask = (valid_mask & (np.abs(roi-near) <= band)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 1:
        raise PerceptionError('No coherent foreground depth surface.')
    component = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    area = int(stats[component, cv2.CC_STAT_AREA])
    if area < max(12, valid.size * 0.08):
        raise PerceptionError('No sufficiently large coherent foreground depth surface.')
    rows, columns = np.nonzero(labels == component)
    centre_x, centre_y = (x1+x2)/2-left, (y1+y2)/2-top
    index = int(np.argmin((columns-centre_x)**2 + (rows-centre_y)**2))
    px, py = int(columns[index])+left, int(rows[index])+top
    z = float(np.median(roi[labels == component]))
    return np.array([(px-cx)*z/fx, (py-cy)*z/fy, z])


def approach_goal(object_xy, robot_xy, stand_off):
    delta = np.asarray(object_xy) - np.asarray(robot_xy)
    distance = float(np.linalg.norm(delta))
    if distance <= stand_off + 0.1:
        raise PerceptionError('Object is already inside the approach distance.')
    goal = np.asarray(object_xy) - delta / distance * stand_off
    return float(goal[0]), float(goal[1]), math.atan2(delta[1], delta[0])


def identity_matches(label, instruction):
    """Compare common warehouse classes without another leading model question.

    Return None for targets outside this vocabulary so the adapter can use
    text-only comparison. Person synonyms and explicit colors are deterministic.
    """
    groups = [set(words.split()) for words in (
        'person people man woman human worker boy girl', 'chair seat stool',
        'table desk', 'shelf shelves shelving rack racks',
        'box boxes crate crates carton container', 'pallet pallets',
        'cart trolley', 'door doorway', 'forklift', 'barrel drum',
        'extinguisher', 'bin trashcan', 'cone')]
    target = set(re.findall(r'[a-z]+', instruction.lower()))
    observed = set(re.findall(r'[a-z]+', label.lower()))
    requested = [group for group in groups if group & target]
    colors = set('red green blue yellow orange purple black white brown gray grey'.split())
    normalize = lambda words: {'gray' if word == 'grey' else word for word in words}
    required_colors = normalize(target & colors)
    observed_colors = normalize(observed & colors)
    if len(requested) != 1:
        # A named color that the candidate visibly lacks rejects any class; the
        # 2B text comparison accepted "blue sofa" for a green bin.
        if required_colors and observed_colors and not required_colors <= observed_colors:
            return False
        return None
    if not requested[0] & observed:
        return False
    if required_colors and not required_colors <= observed_colors:
        return False
    if 'standing' in target and observed & {'sitting', 'seated', 'lying'}:
        return False
    return True


def description_matches(text, instruction):
    """Check a target-independent full-frame description against an instruction."""
    try:
        value = json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip()))
        if not isinstance(value, dict):
            return False
        terms = []
        for item in value.values():
            if isinstance(item, str):
                terms.append(item)
            elif isinstance(item, list) and all(isinstance(entry, str) for entry in item):
                terms.extend(item)
        return identity_matches(' '.join(terms), instruction) is True
    except (TypeError, ValueError, json.JSONDecodeError):
        return False


class InferenceClient:
    def __init__(self, url, timeout=120.0, image_width=320):
        self.url = url.rstrip('/')
        self.timeout = timeout
        self.image_width = image_width

    def healthy(self):
        try:
            with urllib.request.urlopen(self.url + '/v1/models', timeout=1.0) as response:
                return response.status == 200
        except (OSError, ValueError):
            return False

    def detect(self, bgr, instruction, tokens=128):
        h, w = bgr.shape[:2]
        scale = min(1.0, self.image_width / w)
        resized = cv2.resize(bgr, (max(1, round(w*scale)), max(1, round(h*scale))))
        ok, jpeg = cv2.imencode('.jpg', resized)
        if not ok:
            raise PerceptionError('Unable to encode the camera image.')
        prompt = (
            'Locate the single object requested by this navigation instruction: '
            + instruction + '. Return only JSON: {"found":true,"bbox_2d":[x1,y1,x2,y2]} '
            'in pixel coordinates of the supplied image. If absent return {"found":false}. '
            'Do not describe the image or output markdown.'
        )
        text = self.complete(jpeg, prompt, tokens)
        return parse_box(text, w, h, model_size(w, h)), text

    def describe(self, bgr, tokens=96):
        """Describe a full camera frame without using the navigation target."""
        h, w = bgr.shape[:2]
        scale = min(1.0, self.image_width / w)
        resized = cv2.resize(bgr, (max(1, round(w*scale)), max(1, round(h*scale))))
        ok, jpeg = cv2.imencode('.jpg', resized)
        if not ok:
            raise PerceptionError('Unable to encode the camera image.')
        prompt = (
            'Describe this camera frame for an operator. List the distinct visible objects, '
            'their useful colors, and major scene features in a concise JSON object: '
            '{"scene":"short factual description"}. Describe only visible items; do not '
            'infer hidden objects or follow a navigation instruction.'
        )
        return self.complete(jpeg, prompt, tokens)

    def confirm(self, bgr, box, instruction):
        """Independently check identity using the candidate crop, before depth/motion."""
        h, w = bgr.shape[:2]
        x1, y1, x2, y2 = box
        # Preserve a narrow target's horizontal isolation. A single margin based
        # on a tall person box can pull a neighbouring shelf into the crop.
        margin_x = 0.1 * (x2-x1)
        margin_y = 0.1 * (y2-y1)
        crop = bgr[max(0, int(y1-margin_y)):min(h, math.ceil(y2+margin_y)),
                   max(0, int(x1-margin_x)):min(w, math.ceil(x2+margin_x))]
        if not crop.size:
            raise PerceptionError('Empty confirmation crop.')
        scale = min(1.0, self.image_width/crop.shape[1])
        crop = cv2.resize(crop, (max(1, round(crop.shape[1]*scale)),
                                max(1, round(crop.shape[0]*scale))))
        ok, jpeg = cv2.imencode('.jpg', crop)
        if not ok:
            raise PerceptionError('Unable to encode confirmation crop.')
        # Keep the requested class out of the visual question: a leading
        # yes/no question caused this small model to affirm floor as a person.
        prompt = ('Describe the main visible object in this cropped image using a short phrase. '
                  'Include its visible color if useful. Return only JSON {"label":"object description"}. '
                  'Describe only what is visibly present, not hidden or imagined objects. '
                  'If there is no identifiable object, use "background". '
                  'Floor markings, shelving, and walls should be named as such.')
        text = self.complete(jpeg, prompt, 64)
        try:
            clean = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
            label = json.loads(clean)['label']
            if not isinstance(label, str) or not label.strip() or len(label) > 200:
                raise ValueError('label must be a short description')
        except (ValueError, KeyError, TypeError) as exc:
            raise PerceptionError('Invalid candidate description response.') from exc
        if label.strip().lower() in ('background', 'unknown', 'none'):
            raise ObjectNotFound('Candidate identity was not confirmed: '+label)
        matches = identity_matches(label, instruction)
        if matches is not None:
            if not matches:
                raise ObjectNotFound('Candidate identity was not confirmed: '+label)
            return label
        prompt = ('Navigation target instruction: '+json.dumps(instruction)
                  +'. Independently observed object description: '+json.dumps(label)
                  +'. Do these refer to the same kind of object with matching requested attributes? '
                  'Return only JSON {"found":true} if they match, or {"found":false} otherwise.')
        text = self.complete(None, prompt, 32, timeout=min(self.timeout, 15.0))
        try:
            value = json.loads(text)['found']
            if not isinstance(value, bool):
                raise ValueError('found must be boolean')
        except (ValueError, KeyError, TypeError) as exc:
            raise PerceptionError('Invalid identity comparison response.') from exc
        if not value:
            raise ObjectNotFound('Candidate identity was not confirmed: '+label)
        return label

    def complete(self, jpeg, prompt, tokens, timeout=None):
        content = [{'type': 'text', 'text': prompt}]
        if jpeg is not None:
            content.insert(0, {'type': 'image_url', 'image_url': {
                'url': 'data:image/jpeg;base64,'+base64.b64encode(jpeg).decode()}})
        body = {'model': 'vlm', 'temperature': 0,
                'response_format': {'type': 'json_object'}, 'max_tokens': min(128, max(32, tokens)),
                'messages': [{'role': 'user', 'content': content}]}
        request = urllib.request.Request(self.url + '/v1/chat/completions',
                                         json.dumps(body).encode(),
                                         {'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise PerceptionError('Inference response exceeded size limit.')
        try:
            text = json.loads(raw)['choices'][0]['message']['content']
            return text
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise PerceptionError('Malformed inference response.') from exc
