"""Public API for creating main agents from any trigger."""

from .builder import MainAgentBuildResult, build_main_agent
from .config import MainAgentBuildConfig

__all__ = ["MainAgentBuildConfig", "MainAgentBuildResult", "build_main_agent"]
