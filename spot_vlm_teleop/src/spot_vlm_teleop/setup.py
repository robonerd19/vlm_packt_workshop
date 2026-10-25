import os
from glob import glob
from setuptools import setup

# The world's model folders are nested (meshes, materials), so install them file by file.
models = [(os.path.join('share/spot_vlm_teleop', root), [os.path.join(root, f) for f in files])
          for root, _, files in os.walk('worlds/models') if files]

setup(
    name='spot_vlm_teleop',
    version='0.1.0',
    packages=['spot_vlm_teleop'],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/spot_vlm_teleop']),
        ('share/spot_vlm_teleop', ['package.xml']),
        ('share/spot_vlm_teleop/launch', glob('launch/*')),
        ('share/spot_vlm_teleop/web', glob('web/*')),
        ('share/spot_vlm_teleop/worlds', ['worlds/room.sdf']),
        *models,
    ],
    install_requires=['setuptools'],
    entry_points={'console_scripts': ['web_teleop = spot_vlm_teleop.web_teleop:main']},
)
