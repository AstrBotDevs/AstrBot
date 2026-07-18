import pytest

from astrbot.core.star.filter.command import CommandFilter


class FakeCommandEvent:
    def __init__(self, message_str: str):
        self.message_str = message_str
        self.is_at_or_wake_command = True
        self.extras = {}

    def get_message_str(self) -> str:
        return self.message_str

    def set_extra(self, key: str, value) -> None:
        self.extras[key] = value


@pytest.mark.parametrize(
    ("command_name", "message_str", "handler_params", "expected_params"),
    [
        (
            "修改好感度",
            "修改好感度 @Heaven Whisper(488267082) 64",
            {"target": str, "value": int},
            {"target": "@Heaven Whisper(488267082)", "value": 64},
        ),
        (
            "修改好感度",
            "修改好感度 @Jane Doe(U01ABC-DEF) 64",
            {"target": str, "value": int},
            {"target": "@Jane Doe(U01ABC-DEF)", "value": 64},
        ),
        (
            "修改好感度",
            "修改好感度 488267082 64",
            {"target": str, "value": int},
            {"target": "488267082", "value": 64},
        ),
        (
            "修改关系",
            "修改关系 @Alice One(U1) @Bob Two(U2)",
            {"source": str, "target": str},
            {"source": "@Alice One(U1)", "target": "@Bob Two(U2)"},
        ),
    ],
)
def test_command_filter_keeps_at_mentions_with_spaces_as_single_params(
    command_name,
    message_str,
    handler_params,
    expected_params,
):
    command_filter = CommandFilter(command_name)
    command_filter.handler_params = handler_params
    event = FakeCommandEvent(message_str)

    assert command_filter.filter(event, cfg=None)
    assert event.extras["parsed_params"] == expected_params
