import os
import pathlib
import sys
import warnings


def is_docker() -> bool:
    """
    Determines if the application is running inside a Docker container.

    Returns:
        bool: True if running in Docker, False otherwise.
    """
    cgroup_path = "/proc/self/cgroup"
    if os.path.exists("/.dockerenv"):
        return True

    if os.path.isfile(cgroup_path):
        try:
            with open(cgroup_path, "r", encoding="utf-8") as stream:
                if any("docker" in line for line in stream):
                    return True
        except OSError:
            pass

    return os.getenv("CONTAINERIZED", "False").lower() == "true"


def get_platform_app_directory(app_name: str):
    """
    Returns the platform-specific application directory.

    Args:
        app_name (str): Application name to append to the platform base path.

    Returns:
        str | None: Platform-specific app directory path, or None when unsupported
        or when running in Docker.
    """
    if is_docker():
        return None

    home = pathlib.Path.home()

    if sys.platform == "win32":
        return str(home / f"AppData/Roaming/{app_name}")
    if sys.platform.startswith("linux"):
        return str(home / f".local/share/{app_name}")
    if sys.platform == "darwin":
        return str(home / f"Library/Application Support/{app_name}")
    if sys.platform.startswith("freebsd"):
        return str(home / f".local/share/{app_name}")

    warnings.warn("Warning: Unsupported Operating System!")
    return None
