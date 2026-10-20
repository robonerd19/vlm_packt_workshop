"""Single-owner navigation orchestration with timestamped RGB-D snapshots."""
import json
import math
import threading
import time

import message_filters
import numpy as np
import rclpy
from action_msgs.msg import GoalStatus
from cv_bridge import CvBridge
from geometry_msgs.msg import PointStamped, PoseStamped
from lifecycle_msgs.srv import GetState
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import Odometry, OccupancyGrid
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.duration import Duration
from rclpy.clock import Clock, ClockType
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo, Image
from tf2_geometry_msgs import do_transform_point
from tf2_ros import Buffer, TransformListener
from vlm_nav_msgs.action import VlmNavigate
from vlm_nav_msgs.srv import GetReadiness

from .perception import InferenceClient, PerceptionError, ObjectNotFound, UnusableDetection, description_matches, require_complete_box, approach_goal, project_box
from .search import viewpoints


class SearchCancelled(Exception):
    pass


class Navigator(Node):
    def __init__(self):
        super().__init__('vlm_navigator')
        defaults = {'inference_url': 'http://127.0.0.1:8081', 'inference_timeout': 120.0,
                    'color_topic': '/camera/color/image_raw',
                    'depth_topic': '/camera/aligned_depth/image_raw',
                    'info_topic': '/camera/color/camera_info', 'odom_topic': '/odom',
                    'map_frame': 'map', 'base_frame': 'base_link', 'approach_distance': 1.0,
                    'sensor_max_age': 2.0, 'image_width': 320, 'max_new_tokens': 128,
                    'nav_timeout': 120.0, 'max_capture_displacement': 0.10,
                    'lifecycle_nodes': ['amcl', 'planner_server', 'controller_server', 'bt_navigator'],
                    'require_lifecycle': True, 'home_x': 0.0, 'home_y': 0.0,
                    'search_enabled': True, 'search_map_enabled': True,
                    'search_timeout': 900.0, 'search_headings': 36, 'search_rotation_delay': 1.0,
                    'verify_detection': True,
                    'search_locations': 3, 'search_spacing': 3.0, 'search_clearance': 0.45,
                    'frame_description_tokens': 96}
        for key, value in defaults.items():
            self.declare_parameter(key, value)
        self.p = lambda key: self.get_parameter(key).value
        self.cb = ReentrantCallbackGroup()
        self.bridge = CvBridge()
        self.lock = threading.Lock()
        self.busy = False
        self.snapshot = None
        self.map = None
        self.info = None
        self.odom = None
        self.odom_received = 0.0
        self.clock_value = 0
        self.clock_advanced = 0.0
        self.model_ok = False
        self.frame_number = 0
        self.lifecycle = {name: False for name in (self.p('lifecycle_nodes') if self.p('require_lifecycle') else [])}
        self.lifecycle_clients = {name: self.create_client(GetState, '/' + name + '/get_state',
                                                         callback_group=self.cb)
                                  for name in self.lifecycle}
        self.pending_lifecycle = {}
        self.lifecycle_seen = {}
        self.backend = InferenceClient(self.p('inference_url'), self.p('inference_timeout'),
                                       self.p('image_width'))
        self.tf = Buffer(cache_time=Duration(seconds=180))
        self.listener = TransformListener(self.tf, self)
        self.rgb_sub = message_filters.Subscriber(self, Image, self.p('color_topic'),
                                                  qos_profile=qos_profile_sensor_data)
        self.depth_sub = message_filters.Subscriber(self, Image, self.p('depth_topic'),
                                                    qos_profile=qos_profile_sensor_data)
        self.sync = message_filters.ApproximateTimeSynchronizer(
            [self.rgb_sub, self.depth_sub], queue_size=3, slop=0.05)
        self.sync.registerCallback(self.on_images)
        self.create_subscription(CameraInfo, self.p('info_topic'), self.on_info,
                                 qos_profile_sensor_data)
        self.create_subscription(Odometry, self.p('odom_topic'), self.on_odom,
                                 qos_profile_sensor_data)
        self.create_subscription(OccupancyGrid, '/map', self.on_map,
                                 QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                                            reliability=ReliabilityPolicy.RELIABLE))
        self.nav = ActionClient(self, NavigateToPose, '/navigate_to_pose', callback_group=self.cb)
        self.target_pub = self.create_publisher(PoseStamped, '/vlm_nav/target_pose', 1)
        self.action = ActionServer(self, VlmNavigate, '/vlm_navigate',
                                   execute_callback=self.execute, goal_callback=self.goal,
                                   cancel_callback=lambda _: CancelResponse.ACCEPT,
                                   callback_group=self.cb)
        self.create_service(GetReadiness, '/vlm_nav/readiness', self.readiness, callback_group=self.cb)
        self.create_timer(1.0, self.poll, callback_group=self.cb,
                          clock=Clock(clock_type=ClockType.STEADY_TIME))
        self.get_logger().info('VLM navigator started; readiness is checked before each goal.')

    def on_map(self, msg):
        with self.lock:
            self.map = msg

    def on_info(self, msg):
        with self.lock:
            self.info = msg

    def on_odom(self, msg):
        with self.lock:
            self.odom, self.odom_received = msg, time.monotonic()

    def on_images(self, rgb, depth):
        try:
            bgr = self.bridge.imgmsg_to_cv2(rgb, 'bgr8')
            if depth.encoding not in ('32FC1', '16UC1'):
                raise PerceptionError('Unsupported depth encoding: ' + depth.encoding)
            array = self.bridge.imgmsg_to_cv2(depth, 'passthrough').astype(np.float32)
            if depth.encoding == '16UC1':
                array /= 1000.0
            if bgr.shape[:2] != array.shape:
                raise PerceptionError('RGB and registered depth dimensions differ.')
            if rgb.header.frame_id != depth.header.frame_id:
                raise PerceptionError('RGB and registered depth optical frames differ.')
            with self.lock:
                self.snapshot = (bgr, array, rgb.header, time.monotonic())
        except Exception as exc:
            self.get_logger().warning(str(exc), throttle_duration_sec=5)

    def poll(self):
        now = self.get_clock().now().nanoseconds
        if now > self.clock_value:
            self.clock_advanced = time.monotonic()
        self.clock_value = now
        self.model_ok = self.backend.healthy()
        for name, client in self.lifecycle_clients.items():
            pending = self.pending_lifecycle.get(name)
            if pending and not pending.done():
                continue
            if not client.service_is_ready():
                self.lifecycle[name] = False
                continue
            future = client.call_async(GetState.Request())
            self.pending_lifecycle[name] = future
            def done(f, key=name):
                try:
                    self.lifecycle[key] = f.result().current_state.id == 3
                    self.lifecycle_seen[key] = time.monotonic()
                except Exception:
                    self.lifecycle[key] = False
            future.add_done_callback(done)

    def status(self):
        with self.lock:
            snap, info, odom, received, busy = (self.snapshot, self.info, self.odom,
                                              self.odom_received, self.busy)
        camera = snap is not None and time.monotonic() - snap[3] < self.p('sensor_max_age')
        calibration = bool(info and snap and info.width == snap[0].shape[1]
                           and info.height == snap[0].shape[0]
                           and info.header.frame_id == snap[2].frame_id
                           and info.k[0] > 0 and info.k[4] > 0)
        tf_ok = bool(snap and self.tf.can_transform(self.p('map_frame'), snap[2].frame_id,
                                                    Time.from_msg(snap[2].stamp)))
        odom_ok = bool(odom and time.monotonic() - received < 2)
        stationary = bool(odom_ok and abs(odom.twist.twist.linear.x) < 0.02
                          and abs(odom.twist.twist.linear.y) < 0.02
                          and abs(odom.twist.twist.angular.z) < 0.02)
        checks = {'model': self.model_ok, 'camera': camera, 'calibration': calibration,
                  'tf': tf_ok, 'clock': time.monotonic()-self.clock_advanced < 3,
                  'odometry': odom_ok, 'nav2': self.nav.server_is_ready()
                  and all(ok and time.monotonic()-self.lifecycle_seen.get(name, 0) < 3
                          for name, ok in self.lifecycle.items())}
        return {'ready': all(checks.values()), 'checks': checks,
                'reasons': [name + ' not ready' for name, ok in checks.items() if not ok],
                'busy': busy, 'stationary': stationary,
                'backend': self.p('inference_url')}

    def readiness(self, request, response):
        status = self.status()
        response.ready = status['ready']
        response.status_json = json.dumps(status)
        return response

    def goal(self, request):
        if not request.prompt.strip() or len(request.prompt) > 512:
            return GoalResponse.REJECT
        with self.lock:
            if self.busy:
                return GoalResponse.REJECT
            self.busy = True
        return GoalResponse.ACCEPT

    def feedback(self, handle, state, token='', distance=0.0):
        if handle.is_active:
            feedback = VlmNavigate.Feedback()
            feedback.status, feedback.token = state, token
            feedback.nav_distance_remaining = float(distance)
            handle.publish_feedback(feedback)

    def wait(self, future, seconds):
        event = threading.Event()
        future.add_done_callback(lambda _: event.set())
        deadline = time.monotonic() + seconds
        while rclpy.ok() and time.monotonic() < deadline:
            if event.wait(0.1):
                return future.result()
        raise TimeoutError('ROS action response timed out.')

    def robot_xy(self, stamp=None):
        transform = self.tf.lookup_transform(self.p('map_frame'), self.p('base_frame'),
                                             stamp or Time(), timeout=Duration(seconds=1))
        t = transform.transform.translation
        q = transform.transform.rotation
        yaw = math.atan2(2*(q.w*q.z + q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
        return np.array([t.x, t.y]), yaw

    def check_cancel(self, handle):
        if handle.is_cancel_requested:
            raise SearchCancelled('Cancelled; no active navigation goal.')

    def navigate(self, handle, motion, gx, gy, yaw, state='navigating', until=float('inf')):
        if not self.nav.server_is_ready() or not all(self.lifecycle.values()):
            raise PerceptionError('Nav2 became unavailable during inference.')
        pose = PoseStamped()
        pose.header.frame_id = self.p('map_frame')
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x, pose.pose.position.y = float(gx), float(gy)
        pose.pose.orientation.z, pose.pose.orientation.w = math.sin(yaw/2), math.cos(yaw/2)
        self.target_pub.publish(pose)
        nav_goal = NavigateToPose.Goal()
        nav_goal.pose = pose
        future = self.nav.send_goal_async(nav_goal, feedback_callback=lambda fb:
            self.feedback(handle, state, distance=fb.feedback.distance_remaining))
        try:
            nav_handle = self.wait(future, 10)
            motion['handle'] = nav_handle
        except TimeoutError:
            # A late acceptance must not leave an unowned navigation goal running.
            motion['release_busy'] = False
            def late_goal(f):
                try:
                    late = f.result()
                    if late and late.accepted:
                        late.cancel_goal_async()
                        late.get_result_async().add_done_callback(lambda _: self.clear_busy())
                    else:
                        self.clear_busy()
                except Exception as exc:
                    self.get_logger().error('Unconfirmed late Nav2 goal: ' + str(exc))
            future.add_done_callback(late_goal)
            raise
        if not nav_handle.accepted:
            raise PerceptionError('Nav2 rejected the target pose.')
        nav_result = nav_handle.get_result_async()
        motion['result'] = nav_result
        deadline = min(time.monotonic() + self.p('nav_timeout'), until)
        while not nav_result.done():
            if handle.is_cancel_requested or time.monotonic() > deadline or not rclpy.ok():
                self.wait(nav_handle.cancel_goal_async(), 5)
                terminal = self.wait(nav_result, 10)
                if handle.is_cancel_requested and terminal.status == GoalStatus.STATUS_CANCELED:
                    raise SearchCancelled('Navigation cancellation confirmed.')
                if terminal.status != GoalStatus.STATUS_SUCCEEDED:
                    raise PerceptionError('Navigation stopped or timed out.')
                break
            time.sleep(0.1)
        terminal = nav_result.result()
        if handle.is_cancel_requested:
            raise SearchCancelled('Navigation stopped; cancellation confirmed.')
        if terminal.status != GoalStatus.STATUS_SUCCEEDED or terminal.result.error_code != 0:
            raise PerceptionError('Navigation failed.')

    def capture(self, handle):
        # Never reuse an image from before the preceding turn/translation.
        deadline = time.monotonic() + 5.0
        settled = None
        while time.monotonic() < deadline:
            self.check_cancel(handle)
            status = self.status()
            now = time.monotonic()
            if status['ready'] and status['stationary']:
                settled = settled or now
                with self.lock:
                    snap, info = self.snapshot, self.info
                if now-settled >= 0.5 and snap[3] > settled:
                    return snap, info
            else:
                settled = None
            time.sleep(0.1)
        raise PerceptionError('Fresh stationary RGB-D capture unavailable.')

    def detect_target(self, handle, result):
        (bgr, depth, header, _), info = self.capture(handle)
        stamp = Time.from_msg(header.stamp)
        robot_xy, robot_yaw = self.robot_xy(stamp)
        optical_tf = self.tf.lookup_transform(self.p('map_frame'), header.frame_id,
                                               stamp, timeout=Duration(seconds=1))
        self.frame_number += 1
        frame_number = self.frame_number
        description = ''
        try:
            description = self.backend.describe(bgr, self.p('frame_description_tokens'))
            self.feedback(handle, 'seeing', f'Frame {frame_number}: {description}')
        except Exception as exc:
            # The caption informs the UI; it never controls robot motion.
            self.feedback(handle, 'seeing', f'Frame {frame_number}: description unavailable ({exc}).')
        self.check_cancel(handle)
        self.feedback(handle, 'thinking')
        try:
            box, raw = self.backend.detect(bgr, handle.request.prompt,
                                           handle.request.max_new_tokens or self.p('max_new_tokens'))
        except ObjectNotFound:
            self.check_cancel(handle)
            result.full_vlm_response = '{"found":false}'
            raise
        self.check_cancel(handle)
        result.full_vlm_response = raw
        self.feedback(handle, 'validating', token=raw)
        require_complete_box(box, bgr.shape[1], bgr.shape[0])
        if self.p('verify_detection'):
            self.feedback(handle, 'confirming')
            try:
                self.backend.confirm(bgr, box, handle.request.prompt)
            except ObjectNotFound:
                self.check_cancel(handle)
                if not description_matches(description, handle.request.prompt):
                    raise
                # The detector box and independent scene description agree; the
                # narrow crop can be ambiguous beside warehouse shelving.
                self.feedback(handle, 'confirming', 'Full-frame description confirms the detected target.')
            self.check_cancel(handle)
        xyz = project_box(box, depth, (info.k[0], info.k[4], info.k[2], info.k[5]))
        point = PointStamped()
        point.header = header
        point.point.x, point.point.y, point.point.z = map(float, xyz)
        mapped = do_transform_point(point, optical_tf)
        current, current_yaw = self.robot_xy()
        delta_yaw = math.atan2(math.sin(current_yaw-robot_yaw), math.cos(current_yaw-robot_yaw))
        if np.linalg.norm(current-robot_xy) > self.p('max_capture_displacement') or abs(delta_yaw) > 0.1:
            raise PerceptionError('Robot moved during inference; capture again.')
        if not self.status()['stationary']:
            raise PerceptionError('Robot is moving; detection snapshot invalidated.')
        return approach_goal((mapped.point.x, mapped.point.y), robot_xy, self.p('approach_distance'))

    def find_target(self, handle, result, motion):
        deadline = time.monotonic() + self.p('search_timeout')
        # Each view includes an independent, target-free visual description for the UI.
        inference_budget = 2 * self.p('inference_timeout')
        if self.p('verify_detection'):
            inference_budget += self.p('inference_timeout') + min(self.p('inference_timeout'), 15.0)
        start, heading = self.robot_xy()
        locations = [(float(start[0]), float(start[1]))]
        map_note = ''
        if self.p('search_enabled') and self.p('search_map_enabled'):
            with self.lock:
                grid = self.map
            if grid is not None and grid.header.frame_id == self.p('map_frame'):
                origin = grid.info.origin
                q = origin.orientation
                yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
                locations += viewpoints(np.asarray(grid.data).reshape(grid.info.height, grid.info.width),
                                        grid.info.resolution,
                                        (origin.position.x, origin.position.y, yaw), start,
                                        self.p('search_spacing'), self.p('search_clearance'),
                                        self.p('search_locations'))
            else:
                map_note = ' No matching map available; searched local views only.'
        headings = max(1, min(360, self.p('search_headings'))) if self.p('search_enabled') else 1
        views = 0
        for location, (x, y) in enumerate(locations):
            for index in range(headings):
                self.check_cancel(handle)
                # Do not start inference if it could exceed the remaining budget.
                if time.monotonic()+inference_budget > deadline:
                    raise PerceptionError(f'Object not found within search time limit ({views} views).'+map_note)
                if location or index:
                    self.feedback(handle, 'searching', f'Viewpoint {location+1}/{len(locations)}, view {index+1}/{headings}')
                    try:
                        self.navigate(handle, motion, x, y, heading+index*2*math.pi/headings,
                                      state='searching_navigation', until=deadline)
                        # Let the robot and camera settle before taking the next view.
                        settle_deadline = time.monotonic() + max(0.0, self.p('search_rotation_delay'))
                        while time.monotonic() < settle_deadline:
                            self.check_cancel(handle)
                            time.sleep(min(0.1, settle_deadline-time.monotonic()))
                    except PerceptionError:
                        # A terminal Nav2 failure may skip an obstructed viewpoint.
                        # An unconfirmed cancellation/timeout never starts another goal.
                        active = motion.get('result')
                        if active is None or not active.done():
                            raise
                        self.feedback(handle, 'searching', 'Viewpoint navigation failed; skipping location.')
                        break
                if time.monotonic()+inference_budget+5.0 > deadline:
                    raise PerceptionError(f'Object not found within search time limit ({views} views).'+map_note)
                views += 1
                try:
                    return self.detect_target(handle, result)
                except (ObjectNotFound, UnusableDetection) as exc:
                    self.feedback(handle, 'searching', f'{exc} View {views}; continuing search.')
        raise PerceptionError(f'Object not found after {views} views at {len(locations)} bounded viewpoints.'+map_note)

    def execute(self, handle):
        result = VlmNavigate.Result()
        motion = {'handle': None, 'result': None, 'release_busy': True}
        try:
            self.frame_number = 0
            status = self.status()
            if not status['ready']:
                raise PerceptionError('; '.join(status['reasons']))
            self.check_cancel(handle)
            prompt = handle.request.prompt.strip()
            if prompt.lower() in ('home', 'go home', 'go to home'):
                gx, gy, yaw = self.p('home_x'), self.p('home_y'), 0.0
                result.nav_intent = 'home'
            else:
                gx, gy, yaw = self.find_target(handle, result, motion)
                result.nav_intent = 'object'
            self.check_cancel(handle)
            self.navigate(handle, motion, gx, gy, yaw)
            result.success = True
            result.description = 'Navigation complete.'
            self.feedback(handle, 'done')
            handle.succeed()
        except SearchCancelled as exc:
            result.description = str(exc)
            if handle.is_active:
                handle.canceled()
        except Exception as exc:
            self.get_logger().error(str(exc))
            result.description = str(exc)
            nav_handle = motion['handle']
            nav_result = motion['result']
            if nav_handle and nav_handle.accepted and nav_result is not None and not nav_result.done():
                nav_handle.cancel_goal_async()
            if handle.is_active:
                handle.abort()
        finally:
            nav_result = motion['result']
            if nav_result is not None and not nav_result.done():
                nav_result.add_done_callback(lambda _: self.clear_busy())
            elif motion['release_busy']:
                self.clear_busy()
        return result

    def clear_busy(self):
        with self.lock:
            self.busy = False


def main(args=None):
    rclpy.init(args=args)
    node = Navigator()
    executor = MultiThreadedExecutor(num_threads=6)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
