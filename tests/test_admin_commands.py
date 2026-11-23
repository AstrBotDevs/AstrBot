"""Administrator commands persist only the requested configuration changes."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from astrbot.builtin_stars.builtin_commands.commands.admin import AdminCommands


class SavedConfig(dict):
    saved = 0

    def save_config(self) -> None:
        self.saved += 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "initial", "expected", "scoped"),
    [
        ("op", [], ["42"], False),
        ("deop", ["42", "other"], ["other"], False),
        ("wl", [], ["42"], True),
        ("dwl", ["42", "other"], ["other"], True),
    ],
)
async def test_admin_and_whitelist_changes_are_persisted(
    command, initial, expected, scoped
) -> None:
    config = SavedConfig(
        admins_id=list(initial), platform_settings={"id_whitelist": list(initial)}
    )
    context = SimpleNamespace(get_config=Mock(return_value=config))
    event = SimpleNamespace(
        unified_msg_origin="test:FriendMessage:alice", set_result=Mock()
    )
    await getattr(AdminCommands(context), command)(event, "42")
    actual = (
        config["platform_settings"]["id_whitelist"] if scoped else config["admins_id"]
    )
    untouched = (
        config["admins_id"] if scoped else config["platform_settings"]["id_whitelist"]
    )
    assert actual == expected
    assert untouched == initial
    assert config.saved == 1
    if scoped:
        context.get_config.assert_called_once_with(umo=event.unified_msg_origin)
    else:
        assert all(
            call.kwargs == {} and call.args == ()
            for call in context.get_config.call_args_list
        )
    assert event.set_result.call_args.args[0].chain[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["op", "deop", "wl", "dwl"])
async def test_missing_identifier_does_not_write_config(command: str) -> None:
    context = SimpleNamespace(get_config=Mock())
    event = SimpleNamespace(set_result=Mock())
    await getattr(AdminCommands(context), command)(event)
    context.get_config.assert_not_called()
    assert event.set_result.call_args.args[0].chain[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["deop", "dwl"])
async def test_removing_an_unknown_identifier_preserves_configuration(
    command: str,
) -> None:
    config = SavedConfig(
        admins_id=["keep"], platform_settings={"id_whitelist": ["keep"]}
    )
    context = SimpleNamespace(get_config=Mock(return_value=config))
    event = SimpleNamespace(
        unified_msg_origin="test:FriendMessage:alice", set_result=Mock()
    )
    await getattr(AdminCommands(context), command)(event, "missing")
    assert config == {
        "admins_id": ["keep"],
        "platform_settings": {"id_whitelist": ["keep"]},
    }
    assert config.saved == 0
    assert event.set_result.call_args.args[0].chain[0].text
