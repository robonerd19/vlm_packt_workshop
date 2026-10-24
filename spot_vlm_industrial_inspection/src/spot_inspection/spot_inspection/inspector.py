"""Walk Spot through an inspection route and ask a VLM about each asset.

At every station Spot stops, faces the asset, grabs an inspection-camera frame and
sends it with the station's short question to an OpenAI-compatible VLM endpoint
(llama.cpp + Qwen2-VL); a per-station rule turns the answer into OK/ANOMALY.
Findings go to /inspection/report and a Markdown report.
"""
import base64
import json
import math
import re
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

DESCRIBE = 'Describe what you see in one short sentence.'


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def drive_command(x, y, yaw, gx, gy, max_v=0.4, max_w=0.5):
    """Point-to-point walk: turn toward the goal, then walk while steering. Returns (vx, wz, arrived)."""
    dist = math.hypot(gx - x, gy - y)
    if dist < 0.15:
        return 0.0, 0.0, True
    err = wrap(math.atan2(gy - y, gx - x) - yaw)
    wz = max(-max_w, min(max_w, 1.5 * err))
    if abs(err) > 0.35:  # turn in place first; CHAMP drifts if asked to arc tightly
        return 0.0, wz, False
    return min(max_v, 0.6 * dist), wz, False


def zoom(bgr, factor):
    """Centre crop so small assets (gauges) fill more of the VLM's view."""
    if factor <= 1:
        return bgr
    h, w = bgr.shape[:2]
    ch, cw = int(h / factor), int(w / factor)
    return bgr[(h - ch) // 2:(h + ch) // 2, (w - cw) // 2:(w + cw) // 2]


def judge(answer, station):
    """Turn the VLM's short answer into a verdict using the station's rule.

    Returns (anomaly, value): anomaly is None when the answer does not fit the rule.
    """
    if 'max_value' in station:
        number = re.search(r'-?\d+(?:\.\d+)?', answer)
        if not number:
            return None, None
        value = float(number.group(0))
        return value > station['max_value'], value
    word = re.sub(r'[^a-z]', '', answer.strip().lower().split()[0]) if answer.strip() else ''
    if word not in ('yes', 'no'):
        return None, None
    return word == station['anomaly_if'], word


class Inspector(Node):
    def __init__(self):
        super().__init__('inspector')
        share = Path(get_package_share_directory('spot_inspection'))
        self.url = self.declare_parameter('inference_url', 'http://127.0.0.1:8081').value.rstrip('/')
        route = self.declare_parameter('route_file', str(share / 'config' / 'route.yaml')).value
        self.report_dir = Path(self.declare_parameter('report_dir', '/tmp/spot_inspection').value)
        self.return_home = self.declare_parameter('return_home', True).value
        self.stations = yaml.safe_load(Path(route).read_text())['stations']

        self.pose = None
        self.frame = None
        self.frame_time = 0.0
        self.lock = threading.Lock()
        self.cmd = self.create_publisher(Twist, '/cmd_vel', 10)
        self.report = self.create_publisher(String, '/inspection/report', 10)
        self.create_subscription(Odometry, '/odom/ground_truth', self.on_odom, 10)
        self.create_subscription(Image, '/inspection_camera/image', self.on_image, 1)

    def on_odom(self, msg):
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        self.pose = (p.x, p.y, yaw)

    def on_image(self, msg):
        if msg.encoding not in ('rgb8', 'bgr8'):
            return
        img = np.frombuffer(msg.data, np.uint8).reshape(msg.height, msg.step // 3, 3)[:, :msg.width]
        with self.lock:
            self.frame = cv2.cvtColor(img, cv2.COLOR_RGB2BGR) if msg.encoding == 'rgb8' else img.copy()
            self.frame_time = self.now()

    def now(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def sleep(self, seconds):
        end = self.now() + seconds
        while rclpy.ok() and self.now() < end:
            time.sleep(0.02)

    def publish(self, vx=0.0, wz=0.0):
        t = Twist()
        t.linear.x, t.angular.z = float(vx), float(wz)
        self.cmd.publish(t)

    def walk_to(self, gx, gy, gyaw, timeout=180.0):
        """Returns True once at the pose, False if the timeout ran out first."""
        start = self.now()
        arrived = reached = False
        while rclpy.ok() and self.now() - start < timeout:
            x, y, yaw = self.pose
            if not arrived:
                vx, wz, arrived = drive_command(x, y, yaw, gx, gy)
            else:
                err = wrap(gyaw - yaw)
                if abs(err) < 0.05:
                    reached = True
                    break
                vx, wz = 0.0, max(-0.5, min(0.5, 1.5 * err))
            self.publish(vx, wz)
            self.sleep(0.1)
        else:
            self.get_logger().warn(f'Timed out walking to ({gx:.1f}, {gy:.1f})')
        self.publish()
        return reached

    def capture(self):
        """Wait for a frame taken after the robot stopped and settled."""
        self.sleep(2.0)
        stopped = self.now()
        while rclpy.ok():
            with self.lock:
                if self.frame is not None and self.frame_time > stopped:
                    return self.frame.copy()
            time.sleep(0.05)

    def ask_vlm(self, bgr, prompt, max_tokens=64):
        ok, jpeg = cv2.imencode('.jpg', cv2.resize(bgr, (640, 480)))
        if not ok:
            raise RuntimeError('JPEG encoding failed')
        body = {'model': 'vlm', 'temperature': 0, 'max_tokens': max_tokens,
                'messages': [{'role': 'user', 'content': [
                    {'type': 'image_url', 'image_url': {
                        'url': 'data:image/jpeg;base64,' + base64.b64encode(jpeg).decode()}},
                    {'type': 'text', 'text': prompt}]}]}
        req = urllib.request.Request(self.url + '/v1/chat/completions', json.dumps(body).encode(),
                                     {'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=180) as response:
            return json.loads(response.read())['choices'][0]['message']['content']

    def run(self):
        while rclpy.ok() and self.pose is None:
            self.get_logger().info('Waiting for /odom/ground_truth ...', throttle_duration_sec=5)
            time.sleep(0.5)
        run_dir = self.report_dir / datetime.now().strftime('%Y%m%d_%H%M%S')
        run_dir.mkdir(parents=True, exist_ok=True)
        home = self.pose
        results = []
        for i, st in enumerate(self.stations, 1):
            self.get_logger().info(f'[{i}/{len(self.stations)}] Walking to {st["name"]}')
            reached = self.walk_to(st['x'], st['y'], math.radians(st['yaw']))
            image = self.capture()
            image_file = f'station_{i}.jpg'
            cv2.imwrite(str(run_dir / image_file), image)
            t0 = time.monotonic()
            if not reached:  # the camera may be pointing at something else: no verdict
                answer, anomaly, value, finding = '', None, None, 'Did not reach the station; not inspected.'
            else:
                try:
                    answer = self.ask_vlm(zoom(image, st.get('zoom', 1)), st['question'], 16).strip()
                    anomaly, value = judge(answer, st)
                    finding = self.ask_vlm(image, DESCRIBE).strip()
                except (OSError, ValueError, KeyError, RuntimeError) as exc:
                    answer, anomaly, value, finding = '', None, None, f'VLM request failed: {exc}'
            result = {'station': st['name'], 'x': st['x'], 'y': st['y'], 'image': image_file,
                      'question': st['question'], 'answer': answer, 'value': value, 'anomaly': anomaly,
                      'finding': finding, 'inference_s': round(time.monotonic() - t0, 1)}
            results.append(result)
            self.report.publish(String(data=json.dumps(result)))
            status = {True: 'ANOMALY', False: 'OK', None: 'UNKNOWN'}[anomaly]
            self.get_logger().info(f'{st["name"]}: {status} (answer: {answer!r}) - {finding}')
            (run_dir / 'results.json').write_text(json.dumps(results, indent=2))
        write_markdown(run_dir, results)
        self.get_logger().info(f'Inspection complete. Report: {run_dir / "report.md"}')
        if self.return_home:
            self.get_logger().info('Returning to start')
            self.walk_to(home[0], home[1], home[2])


def write_markdown(run_dir, results):
    lines = ['# Spot inspection report', '', f'Generated {datetime.now():%Y-%m-%d %H:%M}', '',
             '| Station | Status | VLM answer | VLM description |', '|---|---|---|---|']
    for r in results:
        status = {True: '**ANOMALY**', False: 'OK', None: 'UNKNOWN'}[r['anomaly']]
        cells = [r['station'], status, r['answer'], r['finding']]
        lines.append('| ' + ' | '.join(c.replace('|', '/').replace('\n', ' ') for c in cells) + ' |')
    lines.append('')
    for r in results:
        lines += [f"## {r['station']}", '', f"![{r['station']}]({r['image']})", '',
                  f"Q: {r['question']}  ", f"A: `{r['answer']}` ({r['inference_s']} s)", '']
    (run_dir / 'report.md').write_text('\n'.join(lines))


def main():
    rclpy.init()
    node = Inspector()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    threading.Thread(target=executor.spin, daemon=True).start()
    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.publish()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
