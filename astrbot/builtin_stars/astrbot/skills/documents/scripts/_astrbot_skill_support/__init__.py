"""Locate shared utilities from a source checkout or an uploaded skill bundle."""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parents[3] / "_astrbot_skill_support")]
