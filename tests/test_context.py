"""Import smoke tests for astrbot.core.star.context."""
from astrbot.core.star.context import Context


def test_context_class():
    """Context is importable and is a class."""
    assert isinstance(Context, type)
