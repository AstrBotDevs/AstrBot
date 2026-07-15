from types import SimpleNamespace

from astrbot.core.star.filter.command import CommandFilter, GreedyStr


def _run_filter(command_name: str, alias: set, message: str):
    cmd_filter = CommandFilter(command_name=command_name, alias=set(alias))
    # A single greedy parameter captures everything after the command name.
    cmd_filter.handler_params = {"query": GreedyStr}
    extras: dict = {}
    event = SimpleNamespace(
        is_at_or_wake_command=True,
        get_message_str=lambda: message,
        set_extra=lambda key, value: extras.__setitem__(key, value),
    )
    ok = cmd_filter.filter(event, None)
    return ok, extras.get("parsed_params")


def test_command_filter_keeps_argument_matching_an_alias():
    # Invoking a command by one name with a first argument that happens to equal
    # another alias of the same command must not strip that argument a second time.
    ok, params = _run_filter("search", {"find"}, "search find keyword")
    assert ok
    assert params == {"query": "find keyword"}


def test_command_filter_keeps_sole_argument_matching_an_alias():
    ok, params = _run_filter("add", {"new"}, "add new")
    assert ok
    assert params == {"query": "new"}


def test_command_filter_normal_argument_unaffected():
    ok, params = _run_filter("search", {"find"}, "search cat photo")
    assert ok
    assert params == {"query": "cat photo"}
