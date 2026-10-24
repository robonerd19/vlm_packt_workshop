"""Explicit deterministic mock HTTP backend; never used in real-model mode."""
import base64
import cv2
import numpy as np
import json
import math
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.reply(200, {'status': 'ok', 'backend': 'MOCK'})

    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        if length > 1024 * 1024:
            self.reply(413, {'error': 'Request too large'})
            return
        try:
            payload = json.loads(self.rfile.read(length))
            content = payload['messages'][0]['content']
            prompt = next(item['text'] for item in content if item['type'] == 'text').lower()
            time.sleep(float(os.getenv('MOCK_DELAY', '0.2')))
            image_content = next((item for item in content if item['type'] == 'image_url'), None)
            if image_content:
                encoded = image_content['image_url']['url'].split(',', 1)[1]
                image = cv2.imdecode(np.frombuffer(base64.b64decode(encoded), np.uint8), cv2.IMREAD_COLOR)
                hidden_visible = np.count_nonzero(image[:, :, 0].astype(float)-image[:, :, 2] > 80) > 1000
                absent = 'missing' in prompt or ('hidden' in prompt and not hidden_visible)
                # Answer like Ollama: pixels of its resize to >= 1024*28*28 pixels (vlm_nav.perception.model_size).
                beta = math.sqrt(1024 * 28 * 28 / (image.shape[0] * image.shape[1]))
                mw, mh = (math.ceil(side * beta / 28) * 28 for side in (image.shape[1], image.shape[0]))
                value = {'label': 'blue chair' if hidden_visible else 'red chair'} if 'describe the main visible' in prompt else (
                    {'found': False} if absent else {'found': True, 'bbox_2d': [
                        round(mw*0.35), round(mh*0.3), round(mw*0.65), round(mh*0.7)]})
            else:
                value = {'found': 'missing' not in prompt}
            text = json.dumps(value)
            self.reply(200, {'choices': [{'message': {'content': text}}]})
        except Exception as exc:
            self.reply(400, {'error': str(exc)})

    def reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass


def main():
    print('MOCK inference backend; detections are deterministic fixtures.', flush=True)
    ThreadingHTTPServer(('127.0.0.1', int(os.getenv('MOCK_PORT', '8081'))), Handler).serve_forever()
