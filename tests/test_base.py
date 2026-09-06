"""Import smoke tests for astrbot.core.star.base."""
from astrbot.core.star.base import Star


def test_star_class():
    """Star is importable and is a class."""
    assert isinstance(Star, type)
