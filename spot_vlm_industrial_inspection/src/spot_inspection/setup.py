from glob import glob
from setuptools import setup

setup(
    name='spot_inspection',
    version='0.1.0',
    packages=['spot_inspection'],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/spot_inspection']),
        ('share/spot_inspection', ['package.xml']),
        ('share/spot_inspection/config', glob('config/*')),
        ('share/spot_inspection/launch', glob('launch/*')),
    ],
    install_requires=['setuptools'],
    entry_points={'console_scripts': ['inspector = spot_inspection.inspector:main']},
)
