"""Version utility module to dynamically retrieve version from package metadata."""

from importlib.metadata import PackageNotFoundError, version


def get_version() -> str:
    """
    Get the version from package metadata.
    
    This version is dynamically set by uv-dynamic-versioning from VCS (git tags).
    Falls back to "0.0.0.dev0" if the package is not installed (e.g., during development).
    
    Returns:
        str: The version string (e.g., "4.5.1")
    """
    try:
        return version("AstrBot")
    except PackageNotFoundError:
        # Fallback for development environment where package is not installed
        return "0.0.0.dev0"
