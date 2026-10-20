"""Synthetic RGB-D + TF and mock navigation; no physical simulation claims."""
import math
import time

import cv2
import numpy as np
import rclpy
from geometry_msgs.msg import TransformStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import Odometry, OccupancyGrid
from rclpy.action import ActionServer, CancelResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import CameraInfo, Image
from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster


class Fixture(Node):
    def __init__(self):
        super().__init__('demo_fixture')
        self.cb = ReentrantCallbackGroup()
        self.pubs = {name: self.create_publisher(kind, topic, 10) for name, kind, topic in [
            ('rgb', Image, '/camera/color/image_raw'), ('depth', Image, '/camera/aligned_depth/image_raw'),
            ('info', CameraInfo, '/camera/color/camera_info'), ('odom', Odometry, '/odom'),
            ('clock', Clock, '/clock')]}
        self.tf = TransformBroadcaster(self)
        self.static = StaticTransformBroadcaster(self)
        transforms = []
        for parent, child, xyz, q in [
            ('map', 'odom', (0, 0, 0), (0, 0, 0, 1)),
            ('base_link', 'camera_optical_frame', (0.15, 0, 0.4), (-0.5, 0.5, -0.5, 0.5))]:
            t = TransformStamped()
            t.header.frame_id, t.child_frame_id = parent, child
            t.transform.translation.x, t.transform.translation.y, t.transform.translation.z = map(float, xyz)
            t.transform.rotation.x, t.transform.rotation.y, t.transform.rotation.z, t.transform.rotation.w = map(float, q)
            transforms.append(t)
        self.static.sendTransform(transforms)
        self.x = self.y = self.yaw = 0.0
        self.moving = False
        self.map_pub = self.create_publisher(OccupancyGrid, '/map',
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        grid = OccupancyGrid()
        grid.header.frame_id = 'map'
        grid.info.resolution, grid.info.width, grid.info.height = 0.1, 120, 120
        grid.info.origin.position.x = grid.info.origin.position.y = -6.0
        grid.info.origin.orientation.w = 1.0
        array = np.zeros((120, 120), np.int8)
        array[[0, -1], :] = 100
        array[:, [0, -1]] = 100
        grid.data = array.ravel().tolist()
        self.map_pub.publish(grid)
        self.started = time.monotonic()
        self.create_timer(0.1, self.publish)
        self.server = ActionServer(self, NavigateToPose, '/navigate_to_pose',
                                   self.navigate, cancel_callback=lambda _: CancelResponse.ACCEPT,
                                   callback_group=self.cb)
        self.get_logger().info('MOCK sensors and Nav2; no Gazebo robot motion.')

    def publish(self):
        elapsed = time.monotonic() - self.started + 1
        clock = Clock()
        clock.clock.sec = int(elapsed)
        clock.clock.nanosec = int(elapsed % 1 * 1e9)
        self.pubs['clock'].publish(clock)
        rgb = np.full((240, 320, 3), 220, np.uint8)
        cv2.rectangle(rgb, (112, 72), (208, 168), (30, 30, 210), -1)
        if abs(math.atan2(math.sin(self.yaw-math.pi/2), math.cos(self.yaw-math.pi/2))) < 0.3:
            cv2.rectangle(rgb, (112, 72), (208, 168), (210, 30, 30), -1)
        for name, arr, encoding in [('rgb', rgb, 'bgr8'),
                                    ('depth', np.full((240, 320), 3.0, np.float32), '32FC1')]:
            msg = Image()
            msg.header.frame_id, msg.header.stamp = 'camera_optical_frame', clock.clock
            msg.height, msg.width, msg.encoding = 240, 320, encoding
            msg.step = 320 * (3 if name == 'rgb' else 4)
            msg.data = arr.tobytes()
            self.pubs[name].publish(msg)
        info = CameraInfo()
        info.header.frame_id, info.header.stamp = 'camera_optical_frame', clock.clock
        info.width, info.height = 320, 240
        info.k = [280., 0., 160., 0., 280., 120., 0., 0., 1.]
        self.pubs['info'].publish(info)
        t = TransformStamped()
        t.header.frame_id, t.child_frame_id, t.header.stamp = 'odom', 'base_link', clock.clock
        t.transform.translation.x, t.transform.translation.y = self.x, self.y
        t.transform.rotation.z, t.transform.rotation.w = math.sin(self.yaw/2), math.cos(self.yaw/2)
        self.tf.sendTransform(t)
        odom = Odometry()
        odom.header.frame_id, odom.child_frame_id, odom.header.stamp = 'odom', 'base_link', clock.clock
        odom.pose.pose.position.x, odom.pose.pose.position.y = self.x, self.y
        odom.pose.pose.orientation.z, odom.pose.pose.orientation.w = math.sin(self.yaw/2), math.cos(self.yaw/2)
        odom.twist.twist.angular.z = 0.2 if self.moving else 0.0
        self.pubs['odom'].publish(odom)

    def navigate(self, handle):
        result = NavigateToPose.Result()
        self.moving = True
        for tick in range(30):
            if handle.is_cancel_requested:
                self.moving = False
                handle.canceled()
                return result
            feedback = NavigateToPose.Feedback()
            feedback.distance_remaining = float(3-tick/10)
            handle.publish_feedback(feedback)
            time.sleep(0.1)
        pose = handle.request.pose.pose
        self.x, self.y = pose.position.x, pose.position.y
        q = pose.orientation
        self.yaw = math.atan2(2*q.w*q.z, 1-2*q.z*q.z)
        self.moving = False
        handle.succeed()
        return result


def main(args=None):
    rclpy.init(args=args)
    node = Fixture()
    executor = MultiThreadedExecutor(num_threads=3)
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
