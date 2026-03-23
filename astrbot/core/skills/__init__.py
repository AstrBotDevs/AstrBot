"""
AstrBot skills module - DEPRECATED

.. deprecated::
    This module has been moved to :mod:`astrbot._internal.skills`.
    Please update your imports accordingly.

    Old import (deprecated):
        from astrbot.core.skills import SkillManager, SkillInfo

    New import:
        from astrbot._internal.skills import SkillManager, SkillInfo

This file exists solely for backward compatibility and will be removed in a future version.
"""

import warnings

warnings.warn(
    "astrbot.core.skills has been moved to astrbot._internal.skills. "
    "Please update your imports.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from new location for backward compatibility
from astrbot._internal.skills import (
    SkillInfo,
    SkillManager,
    build_skills_prompt,
    SkillToToolConverter,
)

__all__ = [
    "SkillInfo",
    "SkillManager",
    "build_skills_prompt",
    "SkillToToolConverter",
]
