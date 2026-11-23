"""Persona commands render current selections and persist explicit changes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.builtin_stars.builtin_commands.commands.persona import PersonaCommands


@pytest.fixture
def persona_command():
    conversation = SimpleNamespace(persona_id="Writer", title="Current topic")
    conversations = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value="abcd-conversation"),
        get_conversation=AsyncMock(return_value=conversation),
        update_conversation_persona_id=AsyncMock(),
    )
    personas = SimpleNamespace(
        get_default_persona_v3=AsyncMock(return_value={"name": "Default"}),
        resolve_selected_persona=AsyncMock(
            return_value=("Writer", {"name": "Writer"}, None)
        ),
        get_folder_tree=AsyncMock(return_value=[]),
        get_personas=AsyncMock(return_value=[]),
        personas_v3=[{"name": "Writer", "prompt": "Write clearly."}],
    )
    context = SimpleNamespace(
        conversation_manager=conversations,
        persona_manager=personas,
        provider_manager=SimpleNamespace(
            personas=[{"name": "Writer", "prompt": "Write clearly."}]
        ),
        get_config=Mock(return_value={"provider_settings": {}}),
    )
    event = SimpleNamespace(
        message_str="persona",
        unified_msg_origin="test:FriendMessage:alice",
        get_platform_name=Mock(return_value="test"),
        set_result=Mock(),
    )
    return PersonaCommands(context), context, event


def test_persona_tree_keeps_folder_membership_and_nested_order(persona_command):
    command, _, _ = persona_command
    folders = [
        {
            "folder_id": "root",
            "name": "Work",
            "children": [{"folder_id": "child", "name": "Drafts", "children": []}],
        }
    ]
    personas = [
        SimpleNamespace(persona_id="Writer", folder_id="root"),
        SimpleNamespace(persona_id="Editor", folder_id="child"),
        SimpleNamespace(persona_id="Unfiled", folder_id=None),
    ]
    assert command._build_tree_output(folders, personas) == [
        "├ 📁 Work/",
        "￨ ├ 👤 Writer",
        "￨ ├ 📁 Drafts/",
        "￨ ￨ ├ 👤 Editor",
    ]


@pytest.mark.asyncio
async def test_persona_displays_canonical_three_value_resolution(persona_command):
    command, context, event = persona_command
    context.persona_manager.resolve_selected_persona.return_value = (
        "Writer",
        {"name": "Writer"},
        False,
    )

    await command.persona(event)

    reply = event.set_result.call_args.args[0].chain[0].text
    assert "Default" in reply
    assert "Current topic(abcd)" in reply
    assert "人格情景: Writer" in reply
    context.persona_manager.resolve_selected_persona.assert_awaited_once_with(
        umo=event.unified_msg_origin, platform_name="test"
    )


@pytest.mark.asyncio
async def test_persona_unset_persists_explicit_disabled_selection(persona_command):
    command, context, event = persona_command
    event.message_str = "persona unset"

    await command.persona(event)

    context.conversation_manager.update_conversation_persona_id.assert_awaited_once_with(
        event.unified_msg_origin, "[%None]"
    )
    assert "取消人格成功" in event.set_result.call_args.args[0].chain[0].text


@pytest.mark.asyncio
async def test_unknown_persona_does_not_replace_current_selection(persona_command):
    command, context, event = persona_command
    event.message_str = "persona Missing"

    await command.persona(event)

    context.conversation_manager.update_conversation_persona_id.assert_not_awaited()
    assert "不存在" in event.set_result.call_args.args[0].chain[0].text


@pytest.mark.asyncio
async def test_persona_unset_without_conversation_does_not_write(persona_command):
    command, context, event = persona_command
    event.message_str = "persona unset"
    context.conversation_manager.get_curr_conversation_id.return_value = None

    await command.persona(event)

    context.conversation_manager.update_conversation_persona_id.assert_not_awaited()
    assert "当前没有对话" in event.set_result.call_args.args[0].chain[0].text
