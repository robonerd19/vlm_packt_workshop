"""Capture live camera data and optionally test a manual Nav2 pose."""
import argparse
import json
import time
from pathlib import Path

import cv2
import rclpy
from action_msgs.msg import GoalStatus
from cv_bridge import CvBridge
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import CameraInfo, Image
from tf2_ros import Buffer, TransformListener
from rclpy.time import Time


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', default='/tmp/workshop-camera.jpg')
    parser.add_argument('--goal', nargs=2, type=float)
    opts, ros_args = parser.parse_known_args(args)
    rclpy.init(args=ros_args)
    node = Node('live_ros_check')
    images, depths, infos, clocks = [], [], [], []
    subscriptions = [
        node.create_subscription(Image, '/camera/color/image_raw', lambda m: images.append(m) if len(images)<2 else None, qos_profile_sensor_data),
        node.create_subscription(Image, '/camera/aligned_depth/image_raw', lambda m: depths.append(m) if len(depths)<2 else None, qos_profile_sensor_data),
        node.create_subscription(CameraInfo, '/camera/color/camera_info', lambda m: infos.append(m) if len(infos)<2 else None, qos_profile_sensor_data),
        node.create_subscription(Clock, '/clock', lambda m: clocks.append(m) if len(clocks)<2 else None, 10)]
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    try:
        deadline = time.monotonic()+45
        while time.monotonic()<deadline:
            rclpy.spin_once(node, timeout_sec=.1)
            if all(len(x)>=2 for x in [images,depths,infos,clocks]) and buffer.can_transform('map', images[-1].header.frame_id, Time()):
                break
        assert all(len(x)>=2 for x in [images,depths,infos,clocks]), 'Missing live sensors or clock'
        assert clocks[0].clock != clocks[1].clock, 'Clock did not advance'
        assert images[-1].header.frame_id == depths[-1].header.frame_id == infos[-1].header.frame_id
        assert (images[-1].width,images[-1].height)==(depths[-1].width,depths[-1].height)==(infos[-1].width,infos[-1].height)
        assert buffer.can_transform('map',images[-1].header.frame_id,Time()), 'Missing map/camera TF'
        image = CvBridge().imgmsg_to_cv2(images[-1], 'bgr8')
        assert cv2.imwrite(opts.image,image)
        print(json.dumps({'image':opts.image,'frame':images[-1].header.frame_id,
                          'width':images[-1].width,'height':images[-1].height,
                          'depth_encoding':depths[-1].encoding,'clock_advances':True}),flush=True)
        if opts.goal:
            client = ActionClient(node,NavigateToPose,'/navigate_to_pose')
            assert client.wait_for_server(timeout_sec=10), 'Nav2 action unavailable'
            goal = NavigateToPose.Goal()
            goal.pose.header.frame_id='map'
            goal.pose.pose.position.x,goal.pose.pose.position.y=opts.goal
            goal.pose.pose.orientation.w=1.
            future=client.send_goal_async(goal)
            rclpy.spin_until_future_complete(node,future,timeout_sec=10)
            handle=future.result()
            assert handle and handle.accepted,'Manual goal rejected'
            future=handle.get_result_async()
            rclpy.spin_until_future_complete(node,future,timeout_sec=90)
            if not future.done():
                cancel=handle.cancel_goal_async()
                rclpy.spin_until_future_complete(node,cancel,timeout_sec=10)
                raise RuntimeError('Manual navigation timed out; cancellation requested')
            assert future.result().status==GoalStatus.STATUS_SUCCEEDED,future.result()
            print('Manual Nav2 goal succeeded.',flush=True)
    finally:
        node.destroy_node()
        rclpy.shutdown()
