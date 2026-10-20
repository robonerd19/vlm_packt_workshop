"""Browser bridge; ROS stays in an executor thread, HTTP in bounded workers."""
import json
import queue
import threading
import time

import cv2
import rclpy
from ament_index_python.packages import get_package_share_directory
from cv_bridge import CvBridge
from flask import Flask, Response, jsonify, render_template, request
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from geometry_msgs.msg import PoseStamped
from vlm_nav_msgs.action import VlmNavigate
from vlm_nav_msgs.srv import GetReadiness
from werkzeug.serving import make_server


class WebBridge(Node):
    def __init__(self):
        super().__init__('vlm_web')
        for key, value in {'bind': '127.0.0.1', 'port': 8000,
                           'color_topic': '/camera/color/image_raw',
                           'request_timeout': 300.0}.items():
            self.declare_parameter(key, value)
        self.cb = ReentrantCallbackGroup()
        self.bridge = CvBridge()
        self.condition = threading.Condition()
        self.jpeg = None
        self.target = None
        self.version = 0
        self.goal_lock = threading.Lock()
        self.goal = None
        self.pending = False
        self.cancel_pending = False
        self.active_token = None
        self.action = ActionClient(self, VlmNavigate, '/vlm_navigate', callback_group=self.cb)
        self.readiness = self.create_client(GetReadiness, '/vlm_nav/readiness', callback_group=self.cb)
        self.create_subscription(Image, self.get_parameter('color_topic').value,
                                 self.on_image, qos_profile_sensor_data)
        self.create_subscription(PoseStamped, '/vlm_nav/target_pose', self.on_target, 1)

    def on_target(self, msg):
        self.target = {'frame': msg.header.frame_id, 'x': msg.pose.position.x,
                       'y': msg.pose.position.y}

    def on_image(self, msg):
        try:
            image = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
            ok, jpeg = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                with self.condition:
                    self.jpeg = jpeg.tobytes()
                    self.version += 1
                    self.condition.notify_all()
        except Exception as exc:
            self.get_logger().warning(str(exc), throttle_duration_sec=5)

    def status(self):
        if not self.readiness.service_is_ready():
            return {'ready': False, 'reasons': ['Navigator readiness service unavailable.']}
        event = threading.Event()
        future = self.readiness.call_async(GetReadiness.Request())
        future.add_done_callback(lambda _: event.set())
        if not event.wait(2):
            self.readiness.remove_pending_request(future)
            return {'ready': False, 'reasons': ['Navigator readiness timed out.']}
        try:
            status = json.loads(future.result().status_json)
            status['target'] = self.target
            return status
        except Exception:
            return {'ready': False, 'reasons': ['Invalid readiness response.']}

    def submit(self, prompt):
        with self.goal_lock:
            if self.pending:
                return None
            self.pending = True
            self.cancel_pending = False
            token = object()
            self.active_token = token
        events = queue.Queue(maxsize=64)
        def put(item):
            try:
                events.put_nowait(item)
            except queue.Full:
                # Keep bounded memory while ensuring terminal results are retained.
                try:
                    events.get_nowait()
                except queue.Empty:
                    pass
                events.put_nowait(item)
        if not self.action.server_is_ready():
            with self.goal_lock:
                self.pending = False
            put({'type': 'error', 'message': 'VLM action server unavailable.'})
            return events, token
        goal = VlmNavigate.Goal()
        goal.prompt, goal.max_new_tokens = prompt, 128
        def feedback(msg):
            put({'type': 'feedback', 'status': msg.feedback.status,
                 'text': msg.feedback.token,
                 'distance': msg.feedback.nav_distance_remaining})
        def result_done(future):
            try:
                outcome = future.result()
                result = outcome.result
                put({'type': 'done', 'success': result.success, 'message': result.description,
                     'response': result.full_vlm_response, 'action_status': outcome.status})
            except Exception as exc:
                put({'type': 'error', 'message': str(exc)})
            finally:
                with self.goal_lock:
                    self.goal = None
                    self.pending = False
        def accepted(future):
            try:
                handle = future.result()
                if not handle.accepted:
                    put({'type': 'error', 'message': 'Goal rejected: navigator busy or invalid request.'})
                    with self.goal_lock:
                        self.pending = False
                    return
                with self.goal_lock:
                    self.goal = handle
                    cancel = self.cancel_pending
                handle.get_result_async().add_done_callback(result_done)
                if cancel:
                    handle.cancel_goal_async()
            except Exception as exc:
                put({'type': 'error', 'message': str(exc)})
                with self.goal_lock:
                    self.pending = False
        self.action.send_goal_async(goal, feedback_callback=feedback).add_done_callback(accepted)
        return events, token

    def cancel(self, token=None):
        with self.goal_lock:
            if not self.pending or (token is not None and token is not self.active_token):
                return False
            self.cancel_pending = True
            handle = self.goal
        if handle:
            handle.cancel_goal_async()
        return True


def create_app(node):
    share = get_package_share_directory('vlm_nav_web')
    app = Flask(__name__, template_folder=share + '/web/templates', static_folder=share + '/web/static')
    app.config['MAX_CONTENT_LENGTH'] = 4096

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/status')
    def status():
        return jsonify(node.status())

    @app.get('/video_feed')
    def video():
        def frames():
            version = -1
            while rclpy.ok():
                with node.condition:
                    node.condition.wait_for(lambda: node.version != version, timeout=2)
                    jpeg, version = node.jpeg, node.version
                if jpeg:
                    yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n'
        return Response(frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

    @app.post('/infer')
    def infer():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get('prompt'), str):
            return jsonify(error='A string prompt is required.'), 400
        prompt = payload['prompt'].strip()
        if not prompt or len(prompt) > 512:
            return jsonify(error='Prompt must contain 1–512 characters.'), 400
        submission = node.submit(prompt)
        if submission is None:
            return jsonify(error='A request is already active.'), 409
        events, token = submission
        def stream():
            deadline = time.monotonic() + node.get_parameter('request_timeout').value
            try:
                while time.monotonic() < deadline:
                    try:
                        item = events.get(timeout=1)
                    except queue.Empty:
                        yield json.dumps({'type': 'heartbeat'}) + '\n'
                        continue
                    yield json.dumps(item) + '\n'
                    if item['type'] in ('done', 'error'):
                        return
                node.cancel(token)
                yield json.dumps({'type': 'error', 'message': 'Request timed out; cancellation requested.'}) + '\n'
            finally:
                # Closing the browser stream requests cancellation of the active goal.
                node.cancel(token)
        return Response(stream(), mimetype='application/x-ndjson', headers={'Cache-Control': 'no-store'})

    @app.post('/cancel')
    def cancel():
        return jsonify(cancellation_requested=node.cancel())

    return app


def main(args=None):
    rclpy.init(args=args)
    node = WebBridge()
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    worker = threading.Thread(target=executor.spin, daemon=True)
    worker.start()
    server = make_server(node.get_parameter('bind').value, node.get_parameter('port').value,
                         create_app(node), threaded=True)
    node.get_logger().info(f'Browser UI: http://{node.get_parameter("bind").value}:{node.get_parameter("port").value}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
