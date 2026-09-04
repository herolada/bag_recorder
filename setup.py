import os
from glob import glob
from setuptools import find_packages, setup

package_name = "bag_recorder"

setup(
    name=package_name,
    version="1.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        (os.path.join("share", package_name), ["package.xml"]),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
        (os.path.join("lib", package_name), ["scripts/record.sh"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Adam Herold",
    maintainer_email="herold.adam7@gmail.com",
    description="Config-driven ros2 bag recording plus a GUI utility to pick topics.",
    license="BSD-3-Clause",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "select_topics = bag_recorder.select_topics:main",
        ],
    },
)
