"""Instruction -> VLM scene understanding -> RGB-D 3D targets -> top-down pick and place."""
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import rclpy
from ament_index_python.packages import get_package_share_directory
from builtin_interfaces.msg import Duration
from control_msgs.action import FollowJointTrajectory
from cv_bridge import CvBridge
from flask import Flask, jsonify, request, Response
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image, JointState
from std_msgs.msg import Empty
from tf2_msgs.msg import TFMessage
from trajectory_msgs.msg import JointTrajectoryPoint

from .description import (ARM, CAMERA_RPY, CAMERA_XYZ, FINGERS, GRASPABLE, READY, TABLE_Z,
                          attach_topic, detach_topic)
from .kinematics import PandaKinematics, top_down
from .perception import InferenceClient, PerceptionError, optical_to_world, project_box

OBSERVE = [2.4] + READY[1:]  # Arm swung behind the base, out of the overhead camera view.
OPEN, CLOSED = 0.04, 0.03    # Finger positions; closed leaves clearance for a 4 cm cube.
CUBE = 0.04


class PickPlace(Node):
    def __init__(self):
        super().__init__('vlm_pick_place')
        self.declare_parameter('inference_url', 'http://127.0.0.1:8081')
        self.declare_parameter('web_port', 8000)
        self.vlm = InferenceClient(self.get_parameter('inference_url').value)
        urdf = (Path(get_package_share_directory('moveit_resources_panda_description'))/'urdf/panda.urdf')
        self.kin = PandaKinematics(urdf.read_text())
        self.bridge = CvBridge()
        self.lock = threading.Lock()
        self.color = self.depth = self.intrinsic = self.joints = None
        self.model_poses = {}
        self.state = {'busy': False, 'log': [], 'objects': [], 'plan': None}
        self.jpeg = self.detection = None
        self.create_subscription(Image, '/camera/color/image_raw', self.on_color, 2)
        self.create_subscription(Image, '/camera/depth/image_raw', self.on_depth, 2)
        self.create_subscription(CameraInfo, '/camera/color/camera_info', self.on_info, 2)
        self.create_subscription(JointState, '/joint_states', self.on_joints, 10)
        self.create_subscription(TFMessage, '/model_poses', self.on_poses, 10)
        self.arm = ActionClient(self, FollowJointTrajectory, '/arm_controller/follow_joint_trajectory')
        self.gripper = ActionClient(self, FollowJointTrajectory, '/gripper_controller/follow_joint_trajectory')
        self.attach = {m: self.create_publisher(Empty, attach_topic(m), 1) for m in GRASPABLE}
        self.detach = {m: self.create_publisher(Empty, detach_topic(m), 1) for m in GRASPABLE}
        self.started = False

    # --- ROS inputs -------------------------------------------------------------------------
    def on_color(self, msg):
        image = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
        with self.lock:
            self.color = (time.monotonic(), image)
            self.jpeg = cv2.imencode('.jpg', image)[1].tobytes()

    def on_depth(self, msg):
        with self.lock:
            self.depth = (time.monotonic(), self.bridge.imgmsg_to_cv2(msg, '32FC1'))

    def on_info(self, msg):
        self.intrinsic = (msg.k[0], msg.k[4], msg.k[2], msg.k[5])

    def on_joints(self, msg):
        positions = dict(zip(msg.name, msg.position))
        if all(n in positions for n in ARM):
            self.joints = np.array([positions[n] for n in ARM])

    def on_poses(self, msg):
        for t in msg.transforms:
            if t.child_frame_id in GRASPABLE:
                p = t.transform.translation
                self.model_poses[t.child_frame_id] = np.array([p.x, p.y, p.z])

    # --- status / UI ------------------------------------------------------------------------
    def log(self, text):
        self.get_logger().info(text)
        with self.lock:
            self.state['log'] = (self.state['log'] + [time.strftime('%H:%M:%S ') + text])[-40:]

    def ready(self):
        return (self.started and self.color is not None and self.depth is not None
                and self.intrinsic is not None and self.vlm.healthy())

    # --- motion -----------------------------------------------------------------------------
    def send(self, client, names, points, timeout=60.0):
        if not client.wait_for_server(timeout_sec=30.0):
            raise RuntimeError('Trajectory controller is not available.')
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = names
        for seconds, q in points:
            goal.trajectory.points.append(JointTrajectoryPoint(
                positions=[float(v) for v in q],
                time_from_start=Duration(sec=int(seconds), nanosec=int(seconds % 1 * 1e9))))
        handle = self.wait(client.send_goal_async(goal), timeout)
        if not handle.accepted:
            raise RuntimeError('Trajectory goal rejected.')
        result = self.wait(handle.get_result_async(), timeout).result
        if result.error_code != 0:
            raise RuntimeError(f'Trajectory failed: {result.error_string or result.error_code}')

    @staticmethod
    def wait(future, timeout):
        end = time.monotonic() + timeout
        while not future.done():
            if time.monotonic() > end:
                raise RuntimeError('Timed out waiting for the controller.')
            time.sleep(0.01)
        return future.result()

    def move_joints(self, q, speed=0.8):
        duration = max(1.0, float(np.max(np.abs(np.asarray(q) - self.joints))) / speed)
        self.send(self.arm, ARM, [(duration, q)])

    def move_tcp(self, xyz, steps=1, seed=None):
        """Move the TCP to a world point, pointing down; steps>1 gives a straight-line path."""
        target = np.asarray(xyz) - [0, 0, TABLE_Z]
        start = self.kin.forward(self.joints)[:3, 3]
        q, points = np.array(seed if seed is not None else self.joints), []
        for i in range(1, steps + 1):
            q = self.kin.inverse(start + (target - start)*i/steps, top_down(), q)
            points.append(q)
        if steps == 1:
            return self.move_joints(points[0])
        self.send(self.arm, ARM, [(0.4*(i+1), p) for i, p in enumerate(points)])

    def grip(self, position):
        self.send(self.gripper, FINGERS, [(1.0, [position, position])])

    def startup(self):
        while self.joints is None:
            time.sleep(0.2)
        # DetachableJoint starts attached; release every cube before the arm moves.
        for _ in range(5):
            for pub in self.detach.values():
                pub.publish(Empty())
            time.sleep(0.2)
        self.grip(OPEN)
        self.move_joints(OBSERVE)
        self.started = True
        self.log('Robot ready at the observe pose.')

    # --- pipeline ---------------------------------------------------------------------------
    def fresh_frames(self):
        since = time.monotonic()
        while True:
            with self.lock:
                if self.color and self.depth and self.color[0] > since + 0.3 and self.depth[0] > since + 0.3:
                    return self.color[1].copy(), self.depth[1].copy()
            if time.monotonic() > since + 10:
                raise RuntimeError('No fresh camera frames.')
            time.sleep(0.05)

    def locate(self, bgr, depth, phrase, annotated, colour):
        box = self.vlm.locate(bgr, phrase)
        x1, y1, x2, y2 = map(int, box)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), colour, 2)
        cv2.putText(annotated, phrase, (x1, max(12, y1-4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, colour, 1)
        point = optical_to_world(project_box(box, depth, self.intrinsic), CAMERA_XYZ, CAMERA_RPY)
        self.log(f'{phrase}: top surface at {np.round(point, 3).tolist()} m')
        return point

    def run(self, instruction):
        try:
            self.move_joints(OBSERVE)
            bgr, depth = self.fresh_frames()
            annotated = bgr.copy()
            self.log('Asking the VLM what is on the table...')
            objects = self.vlm.describe(bgr)
            with self.lock:
                self.state['objects'] = objects
            self.log('Scene: ' + ', '.join(objects))
            pick, place = self.vlm.plan(instruction)
            with self.lock:
                self.state['plan'] = {'pick': pick, 'place': place}
            self.log(f'Plan: pick "{pick}", place on "{place}"')
            pick_xyz = self.locate(bgr, depth, pick, annotated, (0, 255, 255))
            place_xyz = self.locate(bgr, depth, place, annotated, (255, 0, 255))
            with self.lock:
                self.detection = cv2.imencode('.jpg', annotated)[1].tobytes()
            if np.linalg.norm(pick_xyz[:2] - place_xyz[:2]) < 0.05:
                raise PerceptionError('Pick and place locations are the same object.')

            grasp = pick_xyz - [0, 0, CUBE/2]  # TCP at the cube centre, below its top face.
            self.grip(OPEN)
            self.move_tcp(grasp + [0, 0, 0.15], seed=READY)
            self.move_tcp(grasp, steps=6)
            self.grip(CLOSED)
            model = self.held_model(grasp)
            self.attach[model].publish(Empty())
            time.sleep(0.3)
            self.move_tcp(grasp + [0, 0, 0.15], steps=6)
            release = place_xyz + [0, 0, CUBE/2 + 0.01]
            self.move_tcp(release + [0, 0, 0.12])
            self.move_tcp(release, steps=5)
            self.detach[model].publish(Empty())
            time.sleep(0.3)
            self.grip(OPEN)
            self.move_tcp(release + [0, 0, 0.12], steps=5)
            self.move_joints(OBSERVE)
            self.log(f'Done: placed {model} on the {place}.')
        except Exception as exc:  # report every failure to the operator, then return to observe
            self.log(f'Failed: {exc}')
            try:
                self.move_joints(OBSERVE)
            except Exception as again:
                self.log(f'Could not return to observe pose: {again}')
        finally:
            with self.lock:
                self.state['busy'] = False

    def held_model(self, tcp):
        """Only a cube actually between the fingers may be attached (the grasp check)."""
        tcp_world = tcp
        best = min(self.model_poses.items(), key=lambda kv: np.linalg.norm(kv[1] - tcp_world),
                   default=(None, None))
        if best[0] is None or np.linalg.norm(best[1] - tcp_world) > 0.025:
            raise RuntimeError('No cube between the fingers; grasp missed.')
        return best[0]

    def start(self, instruction):
        with self.lock:
            if self.state['busy']:
                return False
            self.state.update(busy=True, objects=[], plan=None)
        threading.Thread(target=self.run, args=(instruction,), daemon=True).start()
        return True


def create_app(node):
    app = Flask(__name__)
    page = (Path(get_package_share_directory('vlm_pick_place'))/'web/index.html').read_text()

    @app.get('/')
    def index():
        return page

    @app.get('/status')
    def status():
        with node.lock:
            return jsonify(dict(node.state, ready=node.ready()))

    @app.get('/<any(image, detection):name>.jpg')
    def image(name):
        with node.lock:
            data = node.jpeg if name == 'image' else node.detection
        return Response(data or b'', mimetype='image/jpeg', status=200 if data else 404)

    @app.post('/run')
    def run():
        instruction = str((request.get_json(silent=True) or {}).get('instruction', '')).strip()
        if not 0 < len(instruction) <= 200:
            return jsonify(error='Instruction must be 1-200 characters.'), 400
        if not node.ready():
            return jsonify(error='Robot, camera or VLM not ready yet.'), 503
        if not node.start(instruction):
            return jsonify(error='A task is already running.'), 409
        return jsonify(ok=True)
    return app


def main():
    rclpy.init()
    node = PickPlace()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    threading.Thread(target=executor.spin, daemon=True).start()
    threading.Thread(target=node.startup, daemon=True).start()
    try:
        create_app(node).run(host='127.0.0.1', port=node.get_parameter('web_port').value, threaded=True)
    finally:
        rclpy.shutdown()
