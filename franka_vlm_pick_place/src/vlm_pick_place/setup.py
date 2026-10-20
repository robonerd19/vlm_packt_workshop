from pathlib import Path
from setuptools import find_packages, setup
name = 'vlm_pick_place'
data = [('share/ament_index/resource_index/packages', ['resource/' + name]), ('share/' + name, ['package.xml'])]
for folder in ('launch', 'config', 'worlds', 'web'):
    data.append(('share/' + name + '/' + folder, [str(p) for p in Path(folder).iterdir() if p.is_file()]))
setup(name=name, version='0.1.0', packages=find_packages(), data_files=data,
      install_requires=['setuptools'], zip_safe=False, license='Apache-2.0',
      maintainer='Workshop maintainers', maintainer_email='maintainer@example.com',
      description='Franka Panda tabletop pick and place driven by a VLM',
      entry_points={'console_scripts': ['pick_place = vlm_pick_place.pick_place_node:main']})
