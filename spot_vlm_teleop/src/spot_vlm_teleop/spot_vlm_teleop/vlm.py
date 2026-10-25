"""Ollama chat API calls and bounding-box drawing for OpenCV frames. No ROS here."""
import base64
import json
import math
import re
import urllib.request

import cv2

# Labels that start with the color worked best with qwen2.5vl:3b in the Go2 warehouse tests.
DETECT_PROMPT = ('What objects are in this image? Give each object a bounding box and a short '
                 'label that starts with its color. Output JSON '
                 '{"objects":[{"label":"...","bbox_2d":[x1,y1,x2,y2]}]} in pixel coordinates of the image.')
SEND_SIZE = (640, 480)  # frames are resized to this before they go to the model


def ask(url, image_bgr, prompt, max_tokens=256, timeout=120.0, model='vlm'):
    """Send one frame and a prompt to Ollama's /api/chat; return the reply text."""
    ok, jpeg = cv2.imencode('.jpg', cv2.resize(image_bgr, SEND_SIZE))
    if not ok:
        raise RuntimeError('JPEG encoding failed')
    body = {'model': model, 'stream': False,
            'options': {'temperature': 0, 'num_predict': max_tokens},
            'messages': [{'role': 'user', 'content': prompt,
                          'images': [base64.b64encode(jpeg).decode()]}]}
    request = urllib.request.Request(url + '/api/chat', json.dumps(body).encode(),
                                     {'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())['message']['content']


def model_size(width, height, factor=28, min_pixels=1024 * 28 * 28):
    """Image size Qwen2.5-VL works in (and gives boxes in) after Ollama resizes a width x height frame."""
    w, h = round(width / factor) * factor, round(height / factor) * factor
    if w * h < min_pixels:
        beta = math.sqrt(min_pixels / (width * height))
        w, h = math.ceil(width * beta / factor) * factor, math.ceil(height * beta / factor) * factor
    return w, h


def parse_objects(text, frame_width, frame_height):
    """Read {"label", "bbox_2d"} entries from the reply and scale the boxes to the frame.

    The model may stop mid-list at the token limit, so each complete flat {...} entry is read
    on its own instead of parsing the whole reply as JSON.
    """
    model_w, model_h = model_size(*SEND_SIZE)
    sx, sy = frame_width / model_w, frame_height / model_h
    objects = []
    for chunk in re.findall(r'\{[^{}]*\}', text):
        try:
            item = json.loads(chunk)
            label, box = str(item['label']).strip(), [float(v) for v in item['bbox_2d']]
        except (ValueError, KeyError, TypeError):
            continue
        if len(box) != 4 or not label:
            continue
        x1, y1, x2, y2 = (min(max(v, 0.0), limit) for v, limit in
                          zip((box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy),
                              (frame_width, frame_height) * 2))
        if x2 - x1 > 2 and y2 - y1 > 2 and (label, (x1, y1, x2, y2)) not in objects:
            objects.append((label, (x1, y1, x2, y2)))
    return objects


def draw_objects(image_bgr, objects):
    """Return a copy of the frame with a labelled box per object."""
    out = image_bgr.copy()
    scale = max(0.5, out.shape[1] / 1000)  # readable after the page shrinks the 960 px frame
    for label, (x1, y1, x2, y2) in objects:
        p1, p2 = (int(x1), int(y1)), (int(x2), int(y2))
        cv2.rectangle(out, p1, p2, (0, 255, 255), 2)
        (tw, th), base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
        top = max(p1[1] - th - base - 4, 0)
        cv2.rectangle(out, (p1[0], top), (p1[0] + tw + 6, top + th + base + 4), (0, 255, 255), -1)
        cv2.putText(out, label, (p1[0] + 3, top + th + 2), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 2)
    return out
