"""Read-only prerequisite check; never installs system packages."""
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys


def main():
    missing = []
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        missing.append("Ubuntu 22.04 x86_64 is the supported deployment platform")
    for command in ("git", "cmake", "c++", "make"):
        if not shutil.which(command):
            missing.append(f"missing executable: {command}")
    if shutil.which("cmake"):
        version = subprocess.check_output(["cmake", "--version"], text=True).splitlines()[0]
        match = re.search(r"(\d+)\.(\d+)", version)
        if not match or tuple(map(int, match.groups())) < (3, 19):
            missing.append("CMake >= 3.19 is required")
    ros = Path(os.environ.get("ROS_PREFIX") or f'/opt/ros/{os.environ.get("ROS_DISTRO") or "humble"}')
    for relative in ("setup.bash", "share/ament_cmake/cmake/ament_cmakeConfig.cmake",
                     "share/rclcpp/cmake/rclcppConfig.cmake",
                     "share/rosidl_default_generators/cmake/rosidl_default_generatorsConfig.cmake",
                     "share/rmw_fastrtps_cpp/cmake/rmw_fastrtps_cppConfig.cmake"):
        if not (ros / relative).is_file():
            missing.append(f"missing ROS dependency: {ros / relative}")
    unitree = Path(os.environ.get("UNITREE_SDK2_PREFIX") or "/usr/local")
    if not any((unitree / relative).is_file() for relative in (
        "lib/cmake/unitree_sdk2/unitree_sdk2Config.cmake",
        "lib64/cmake/unitree_sdk2/unitree_sdk2Config.cmake")):
        missing.append(f"missing Unitree SDK2 installation under {unitree}")
    for library, candidates in {
        "yaml-cpp": ("/usr/lib/x86_64-linux-gnu/cmake/yaml-cpp/yaml-cpp-config.cmake", "/usr/local/lib/cmake/yaml-cpp/yaml-cpp-config.cmake"),
        "SDL2": ("/usr/lib/x86_64-linux-gnu/cmake/SDL2/sdl2-config.cmake", "/usr/local/lib/cmake/SDL2/sdl2-config.cmake"),
        "X11": ("/usr/include/X11/Xlib.h", "/usr/local/include/X11/Xlib.h"),
    }.items():
        if not any(Path(candidate).is_file() for candidate in candidates):
            missing.append(f"missing system development dependency: {library}")
    try:
        import yaml  # noqa: F401
    except ImportError:
        missing.append("missing Python PyYAML (Ubuntu package python3-yaml)")
    if missing:
        print("Missing deployment prerequisites:\n" + "\n".join(f"  - {item}" for item in missing), file=sys.stderr)
        print("See README.md for manual installation; no system changes were made.", file=sys.stderr)
        return 2
    print(f"System prerequisites ready: ROS={ros}, Unitree SDK2={unitree}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
