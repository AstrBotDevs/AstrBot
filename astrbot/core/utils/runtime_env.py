import os
import sys


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_packaged_desktop_runtime() -> bool:
    return os.environ.get("ASTRBOT_DESKTOP_CLIENT") == "1"


_faiss_importable_cache: bool | None = None


def is_faiss_importable() -> bool:
    """Checks if faiss-cpu is installable and importable on the current CPU without crashing.

    Standard faiss-cpu wheels on PyPI are compiled with AVX2 instruction set requirements.
    Importing it on a CPU without AVX2 raises a SIGILL (Illegal Instruction) signal, which
    cannot be caught by python try-except blocks and crashes the entire process.
    This helper uses NumPy CPU feature detection and a subprocess fallback import check
    to determine if FAISS is safely available.

    Returns:
        bool: True if faiss can be imported safely, False otherwise.
    """
    global _faiss_importable_cache
    if _faiss_importable_cache is not None:
        return _faiss_importable_cache

    # 1. NumPy-based fast check.
    try:
        import numpy as np

        # NumPy >= 2.0
        if hasattr(np, "_core") and hasattr(np._core, "_multiarray_umath"):
            features = getattr(np._core._multiarray_umath, "__cpu_features__", {})
        # NumPy < 2.0 fallback
        elif hasattr(np, "core") and hasattr(np.core, "_multiarray_umath"):
            features = getattr(np.core._multiarray_umath, "__cpu_features__", {})
        else:
            features = {}

        if features and not features.get("AVX2", False):
            _faiss_importable_cache = False
            return False
    except Exception:
        pass

    # 2. Subprocess fallback check.
    try:
        import subprocess

        result = subprocess.run(
            [sys.executable, "-c", "import faiss"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        _faiss_importable_cache = result.returncode == 0
    except Exception:
        _faiss_importable_cache = False

    return _faiss_importable_cache
