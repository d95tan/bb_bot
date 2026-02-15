"""Package version from pyproject.toml (when installed) or BUILD_VERSION env."""

import os
from importlib.metadata import PackageNotFoundError, version


def get_version() -> str:
    """
    Return deployed version.
    Uses BUILD_VERSION env if set (e.g. from Docker build-arg when building from a git tag),
    otherwise the installed package version from pyproject.toml.
    """
    env_version = os.environ.get("BUILD_VERSION", "").strip()
    if env_version:
        return env_version
    try:
        return version("bb_bot")
    except PackageNotFoundError:
        return "0.0.0.dev"
