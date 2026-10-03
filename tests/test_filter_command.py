"""Import smoke tests for astrbot.core.star.filter.command."""
from astrbot.core.star.filter.command import CommandFilter, GreedyStr


def test_command_filter_class():
    """CommandFilter is importable and is a class."""
    assert isinstance(CommandFilter, type)


def test_greedy_str_class():
    """GreedyStr is importable and is a subclass of str."""
    assert issubclass(GreedyStr, str)
