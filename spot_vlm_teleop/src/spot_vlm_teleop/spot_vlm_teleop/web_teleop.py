"""Drive Spot from a web page, stream its camera, and ask Ollama about what it sees.

ROS side:  /inspection_camera/image -> cv_bridge -> OpenCV frame
           /cmd_vel (Twist) from the page's drive buttons
           /vlm/question, /vlm/answer (String) and /vlm/annotated (Image with boxes)
Web side:  GET /  page,  GET /video  MJPEG stream,  GET /snapshot.jpg  last frame sent to the model,
           POST /drive {"vx","wz"},  POST /ask {"question"},  POST /detect
"""
import os
import threading
import time

import cv2
import rclpy
from ament_index_python.packages import get_package_share_directory
from cv_bridge import CvBridge
from flask import Flask, Response, jsonify, request, send_from_directory
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

from spot_vlm_teleop import vlm

MAX_VX, MAX_WZ = 0.6, 0.6  # m/s and rad/s; CHAMP walks Spot steadily up to these
DEADMAN = 0.5              # s without a drive request -> stop
OVERLAY_TIME = 10.0        # s the detection boxes stay on the live stream while Spot stands still
SETTLE = 1.5               # s after the last drive command before a frame goes to the model


class WebTeleop(Node):
    def __init__(self):
        super().__init__('spot_web_teleop')
        self.url = self.declare_parameter('ollama_url', 'http://127.0.0.1:8081').value
        topic = self.declare_parameter('image_topic', '/inspection_camera/image').value
        self.bridge = CvBridge()
        self.lock = threading.Lock()
        self.frame = None                      # latest camera frame (BGR)
        self.frame_id = 0
        self.snapshot = None                   # frame the model last saw, with boxes if any
        self.overlay = ([], 0.0)               # (objects, time) drawn on the live stream
        self.busy = threading.Lock()           # one model request at a time
        self.cmd, self.cmd_time, self.moving = (0.0, 0.0), 0.0, False
        self.move_time = 0.0                   # last non-zero drive command
        self.create_subscription(Image, topic, self.on_image, 1)
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 1)
        self.question_pub = self.create_publisher(String, '/vlm/question', 1)
        self.answer_pub = self.create_publisher(String, '/vlm/answer', 1)
        self.annotated_pub = self.create_publisher(Image, '/vlm/annotated', 1)
        self.create_timer(0.1, self.publish_cmd)

    def on_image(self, msg):
        frame = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
        with self.lock:
            self.frame, self.frame_id = frame, self.frame_id + 1

    def drive(self, vx, wz):
        vx, wz = max(-MAX_VX, min(MAX_VX, vx)), max(-MAX_WZ, min(MAX_WZ, wz))
        with self.lock:
            self.cmd, self.cmd_time = (vx, wz), time.monotonic()
            if vx or wz:
                self.move_time = self.cmd_time
                self.overlay = ([], 0.0)  # boxes no longer match the view once Spot moves

    def publish_cmd(self):
        with self.lock:
            fresh = time.monotonic() - self.cmd_time < DEADMAN
            vx, wz = self.cmd if fresh else (0.0, 0.0)
        # Publish while driving and once on stop, so keyboard teleop still works when the page is idle.
        if vx or wz or self.moving:
            twist = Twist()
            twist.linear.x, twist.angular.z = vx, wz
            self.cmd_pub.publish(twist)
            self.moving = bool(vx or wz)

    def ask(self, question, detect):
        """Run one model request on the current frame; returns a dict for the page."""
        # Spot keeps moving briefly after the last command; wait so the boxes match the view.
        with self.lock:
            wait = self.move_time + SETTLE - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        with self.lock:
            frame = None if self.frame is None else self.frame.copy()
        if frame is None:
            return {'error': 'No camera image yet.'}
        prompt = vlm.DETECT_PROMPT if detect else question + ' Answer briefly.'
        self.question_pub.publish(String(data='[detect objects]' if detect else question))
        start = time.monotonic()
        try:
            text = vlm.ask(self.url, frame, prompt, max_tokens=384 if detect else 160)
        except Exception as exc:  # network, timeout or bad reply: report it on the page
            return {'error': f'Ollama request failed: {exc}'}
        seconds = round(time.monotonic() - start, 1)
        result = {'seconds': seconds}
        if detect:
            objects = vlm.parse_objects(text, frame.shape[1], frame.shape[0])
            snapshot = vlm.draw_objects(frame, objects)
            result['objects'] = [label for label, _ in objects]
            result['answer'] = ', '.join(result['objects']) or 'No objects found.'
            with self.lock:
                self.overlay = (objects, time.monotonic())
            self.annotated_pub.publish(self.bridge.cv2_to_imgmsg(snapshot, 'bgr8'))
        else:
            snapshot, result['answer'] = frame, text.strip()
        with self.lock:
            self.snapshot = snapshot
        self.answer_pub.publish(String(data=result['answer']))
        return result

    def live_jpeg(self, last_id):
        """Next camera frame (with fresh boxes drawn) as JPEG, or None if there is no new one."""
        with self.lock:
            if self.frame is None or self.frame_id == last_id:
                return None, last_id
            frame, frame_id = self.frame, self.frame_id
            objects, when = self.overlay
        if objects and time.monotonic() - when < OVERLAY_TIME:
            frame = vlm.draw_objects(frame, objects)
        return cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes(), frame_id


def create_app(node):
    web = os.path.join(get_package_share_directory('spot_vlm_teleop'), 'web')
    app = Flask(__name__)

    @app.get('/')
    def index():
        return send_from_directory(web, 'index.html')

    @app.get('/video')
    def video():
        def frames():
            last = 0
            while rclpy.ok():
                jpeg, last = node.live_jpeg(last)
                if jpeg is None:
                    time.sleep(0.03)
                    continue
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n'
        return Response(frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

    @app.get('/snapshot.jpg')
    def snapshot():
        with node.lock:
            image = node.snapshot
        if image is None:
            return '', 404
        return Response(cv2.imencode('.jpg', image)[1].tobytes(), mimetype='image/jpeg',
                        headers={'Cache-Control': 'no-store'})

    @app.post('/drive')
    def drive():
        data = request.get_json(silent=True) or {}
        try:
            node.drive(float(data.get('vx', 0)), float(data.get('wz', 0)))
        except (TypeError, ValueError):
            return jsonify(error='vx and wz must be numbers'), 400
        return jsonify(ok=True)

    def model_request(detect):
        question = str((request.get_json(silent=True) or {}).get('question', '')).strip()
        if not detect and not 0 < len(question) <= 300:
            return jsonify(error='Type a question (1-300 characters).'), 400
        if not node.busy.acquire(blocking=False):
            return jsonify(error='The model is still answering the previous request.'), 409
        try:
            result = node.ask(question, detect)
        finally:
            node.busy.release()
        return jsonify(result), (502 if 'error' in result else 200)

    app.add_url_rule('/ask', 'ask', lambda: model_request(False), methods=['POST'])
    app.add_url_rule('/detect', 'detect', lambda: model_request(True), methods=['POST'])
    return app


def main():
    rclpy.init()
    node = WebTeleop()
    port = node.declare_parameter('port', 8000).value
    threading.Thread(target=rclpy.spin, args=(node,), daemon=True).start()
    node.get_logger().info(f'Open http://127.0.0.1:{port}')
    try:
        create_app(node).run(host='127.0.0.1', port=port, threaded=True)
    finally:
        node.cmd_pub.publish(Twist())
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
