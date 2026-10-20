from glob import glob
from setuptools import setup

package_name = "go2_warehouse_slam"

setup(
    name=package_name,
    version="0.1.0",
    packages=[],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Go2 VLM Navigation maintainers",
    maintainer_email="maintainers@example.org",
    description="Online SLAM launch configuration for the Unitree Go2 warehouse simulation.",
    license="MIT",
    entry_points={"console_scripts": []},
)
