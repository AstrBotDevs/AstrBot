"""
FFmpeg utility functions for finding the FFmpeg executable.
"""

import os
import shutil
from typing import Optional


def get_ffmpeg_path() -> str:
    """
    Get the FFmpeg executable path.

    First tries to find ffmpeg in PATH, then falls back to known locations.

    Returns:
        str: Path to the FFmpeg executable

    Raises:
        FileNotFoundError: If ffmpeg is not found in any location
    """
    # First try to find ffmpeg in PATH
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return "ffmpeg"

    # Common fallback locations
    fallback_paths = [
        "/root/.pyffmpeg/bin/ffmpeg",  # Docker pyffmpeg location
        "/usr/local/bin/ffmpeg",  # Common installation path
        "/usr/bin/ffmpeg",  # System installation path
        "/opt/bin/ffmpeg",  # Alternative installation path
    ]

    for path in fallback_paths:
        if os.path.exists(path) and os.access(path, os.X_OK):
            return path

    # If not found, return "ffmpeg" and let the caller handle the error
    return "ffmpeg"


def get_ffmpeg_path_or_none() -> Optional[str]:
    """
    Get the FFmpeg executable path or None if not found.

    Returns:
        Optional[str]: Path to the FFmpeg executable, or None if not found
    """
    try:
        path = get_ffmpeg_path()
        # Verify the path actually works
        if path == "ffmpeg":
            # Check if it's in PATH
            return path if shutil.which("ffmpeg") else None
        else:
            # Check if the file exists and is executable
            return path if os.path.exists(path) and os.access(path, os.X_OK) else None
    except Exception:
        return None
