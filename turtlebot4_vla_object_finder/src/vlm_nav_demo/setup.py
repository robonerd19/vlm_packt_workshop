from setuptools import find_packages, setup
from pathlib import Path
name = 'vlm_nav_demo'
data = [('share/ament_index/resource_index/packages', ['resource/' + name]),
        ('share/' + name, ['package.xml'])]
for folder in ('launch', 'config', 'web'):
    for p in Path(folder).rglob('*'):
        if p.is_file() and '__pycache__' not in str(p):
            data.append(('share/' + name + '/' + str(p.parent), [str(p)]))
setup(name=name, version='0.1.0', packages=find_packages(), data_files=data,
      install_requires=['setuptools'], zip_safe=False, license='Apache-2.0',
      maintainer='Workshop maintainers', maintainer_email='maintainer@example.com',
      description='CPU-only RGB-D VLM navigation workshop',
      entry_points={'console_scripts':['fixture = vlm_nav_demo.fixture:main', 'mock_inference = vlm_nav_demo.mock_inference:main', 'check_ros = vlm_nav_demo.check_ros:main']})
