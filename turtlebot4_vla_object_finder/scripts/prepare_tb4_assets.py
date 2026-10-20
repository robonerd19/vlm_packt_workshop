#!/usr/bin/env python3
"""Bake official TurtleBot 4 warehouse assets into the image for offline use."""
import hashlib
import json
import subprocess
import shutil
import re
from urllib.parse import unquote
import xml.etree.ElementTree as ET
from pathlib import Path
from ament_index_python.packages import get_package_share_directory


def prepare_world(output):
    upstream = Path(get_package_share_directory('turtlebot4_gz_bringup'))
    root = ET.parse(upstream/'worlds/warehouse.sdf')
    manifest = []
    resolved = {}
    locked = {entry['url']: entry for entry in json.loads(
        Path(__file__).with_name('warehouse_assets.lock.json').read_text())}
    for uri in root.findall('.//include/uri'):
        url = uri.text.strip()
        if url not in resolved:
            entry = locked[url]
            owner, _, name = url.split('/1.0/')[1].split('/', 2)
            cache = Path.home()/'.gz/fuel/fuel.gazebosim.org'/owner.lower()/'models'/name.lower()
            model = cache/entry['version']
            if not (model/'model.sdf').is_file():
                print(f'Downloading {url} version {entry["version"]}', flush=True)
                subprocess.run(['gz', 'fuel', 'download', '-u', url+'/'+entry['version']],
                               check=True, timeout=180)
            digest = hashlib.sha256((model/'model.sdf').read_bytes()).hexdigest()
            if digest != entry['model_sdf_sha256']:
                raise RuntimeError(f'Fuel model checksum mismatch: {url}')
            target = output/'models'/owner.lower()/name.lower()/entry['version']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(model, target, dirs_exist_ok=True)
            resolved[url] = target
            manifest.append({'url': url, 'version': model.name,
                             'model_sdf_sha256': hashlib.sha256((model/'model.sdf').read_bytes()).hexdigest()})
        uri.text = str(resolved[url])
    # Replace Fuel file URLs embedded in model SDFs with baked local paths.
    # Human meshes in the upstream world use absolute URLs even after download.
    for sdf in (output/'models').rglob('*.sdf'):
        tree = ET.parse(sdf)
        for uri in tree.findall('.//uri'):
            value = (uri.text or '').strip()
            if value.startswith('https://'):
                match = re.fullmatch(r'https://fuel\.gazebosim\.org/1\.0/([^/]+)/models/(.+?)/(\d+)/files/(.+)', value)
                if not match:
                    raise RuntimeError(f'Unresolved remote model resource: {value}')
                owner, name, version, relative = map(unquote, match.groups())
                local = output/'models'/owner.lower()/name.lower()/version/relative
                if not local.is_file():
                    raise RuntimeError(f'Missing model file: {local}')
                uri.text = str(local)
        tree.write(sdf, encoding='utf-8', xml_declaration=True)
    world = root.getroot().find('world')
    ET.SubElement(world, 'plugin', {'name': 'gz::sim::systems::Sensors',
                                  'filename': 'gz-sim-sensors-system'}).append(ET.fromstring('<render_engine>ogre2</render_engine>'))
    root.write(output/'worlds/warehouse.sdf', encoding='utf-8', xml_declaration=True)
    (output/'worlds/warehouse-assets.json').write_text(json.dumps(manifest, indent=2)+'\n')


def prepare_robot(output):
    desc = Path(get_package_share_directory('turtlebot4_description'))
    text = subprocess.check_output(['xacro', str(desc/'urdf/standard/turtlebot4.urdf.xacro'),
                                    'gazebo:=ignition', 'namespace:='], text=True)
    root = ET.fromstring(text)
    # Keep official geometry, collision, mass, joints, and optical calibration.
    # This mobile navigation demo does not emulate Create3 docking, buttons,
    # floor/cliff detection, battery, or wheel-drop hardware.
    for parent in root.iter():
        for child in list(parent):
            if child.tag in ('plugin', 'ros2_control'):
                parent.remove(child)
            elif child.tag == 'sensor' and child.attrib.get('name') not in ('rgbd_camera', 'rplidar'):
                parent.remove(child)
    sensors = root.findall('.//sensor')
    if {sensor.attrib['name'] for sensor in sensors} != {'rgbd_camera', 'rplidar'}:
        raise RuntimeError('Expected exactly the TurtleBot 4 OAK-D and RPLIDAR sensors.')
    for sensor in sensors:
        kind = sensor.attrib['type']
        for tag, value in [('update_rate', '2' if kind == 'rgbd_camera' else '5'), ('visualize', 'false'),
                           ('topic', '/camera' if kind == 'rgbd_camera' else '/scan'),
                           ('gz_frame_id', 'oakd_rgb_camera_optical_frame' if kind == 'rgbd_camera' else 'rplidar_link')]:
            element = sensor.find(tag)
            if element is None:
                element = ET.SubElement(sensor, tag)
            element.text = value
        if kind == 'rgbd_camera':
            sensor.find('camera/clip/far').text = '20'
        if kind == 'gpu_lidar':
            scan = sensor.find('.//scan/horizontal/samples')
            if scan is not None:
                scan.text = '180'
    # Resolve meshes to installed package paths; no network resource lookup.
    for mesh in root.findall('.//mesh'):
        uri = mesh.attrib.get('filename', '')
        if uri.startswith('package://'):
            package, rel = uri[len('package://'):].split('/', 1)
            mesh.set('filename', str(Path(get_package_share_directory(package))/rel))
    gazebo = ET.SubElement(root, 'gazebo')
    gazebo.append(ET.fromstring('''<plugin filename="gz-sim-diff-drive-system" name="gz::sim::systems::DiffDrive">
      <left_joint>left_wheel_joint</left_joint><right_joint>right_wheel_joint</right_joint>
      <wheel_separation>0.233</wheel_separation><wheel_radius>0.03575</wheel_radius>
      <topic>/cmd_vel</topic><odom_topic>/odom</odom_topic><tf_topic>/odom_tf</tf_topic>
      <frame_id>odom</frame_id><child_frame_id>base_link</child_frame_id>
      <odom_publish_frequency>20</odom_publish_frequency>
      <max_linear_acceleration>0.4</max_linear_acceleration><max_angular_acceleration>0.6</max_angular_acceleration>
    </plugin>'''))
    gazebo.append(ET.fromstring('''<plugin filename="gz-sim-joint-state-publisher-system" name="gz::sim::systems::JointStatePublisher">
      <topic>/joint_states</topic>
    </plugin>'''))
    ET.indent(root)
    ET.ElementTree(root).write(output/'urdf/turtlebot4.urdf', encoding='utf-8', xml_declaration=True)


if __name__ == '__main__':
    import sys
    output = Path(sys.argv[1]).resolve()
    for directory in ('worlds', 'urdf', 'maps'):
        (output/directory).mkdir(parents=True, exist_ok=True)
    navigation = Path(get_package_share_directory('turtlebot4_navigation'))
    for name in ('warehouse.yaml', 'warehouse.pgm'):
        shutil.copy2(navigation/'maps'/name, output/'maps'/name)
    prepare_world(output)
    prepare_robot(output)
