from glob import glob
from setuptools import setup

package_name = "go2_warehouse_nav2"

setup(
    name=package_name,
    version="0.1.0",
    packages=[],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        ("share/" + package_name + "/maps/warehouse", glob("maps/warehouse/*")),
        ("lib/" + package_name, glob("scripts/*.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Go2 VLM Navigation maintainers",
    maintainer_email="maintainers@example.org",
    description="Warehouse 2D map and Nav2 configuration for the Unitree Go2 simulation.",
    license="MIT",
    entry_points={"console_scripts": []},
)
