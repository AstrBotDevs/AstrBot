"""Compatibility re-exports for experimental context-memory backend hooks.

The protocol definitions and global hook state live in
`context_memory_experimental_backends.py` to keep experimental extension points
explicitly isolated from stable context-memory config logic.
"""

from astrbot.core import context_memory_experimental_backends as _exp

__all__ = list(_exp.__all__)
globals().update({name: getattr(_exp, name) for name in __all__})
