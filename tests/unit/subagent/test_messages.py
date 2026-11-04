import pytest
from pydantic import TypeAdapter, ValidationError

from astrbot.core.agent.input import (
    FileInput,
    ImageInput,
    InputComponent,
    PlainInput,
    format_input_content,
    parse_input_content,
)
from astrbot.core.astr_agent_runtime.tools.subagent import (
    SendAgentMessageTool,
    SpawnAgentTool,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "messages",
    [
        [],
        "text",
        ["text"],
        [{"type": "plain", "text": " "}],
        [{"type": "image"}],
        [{"type": "mention_user", "mention_user_id": "alice"}],
    ],
)
async def test_invalid_components_do_not_create_or_message_agents(
    environment, messages
):
    env = environment
    with pytest.raises(ValueError):
        await SpawnAgentTool().call(env.wrapper, messages=messages)
    with pytest.raises(ValueError):
        await SendAgentMessageTool().call(env.wrapper, "unknown", messages=messages)
    assert not env.store.agents


def test_typed_content_preserves_wire_semantics_order_and_references():
    wire = [
        {"type": "plain", "text": "  Analyze  "},
        {"type": "image", "path": "chart.png", "url": "unused", "text": " Chart "},
        {"type": "file", "url": "https://example.com/report.pdf"},
    ]
    content = parse_input_content(wire)
    wire[0]["text"] = "Changed"
    assert isinstance(content[0], PlainInput)
    assert isinstance(content[1], ImageInput)
    assert isinstance(content[2], FileInput)
    assert [item.model_dump(exclude_none=True) for item in content] == [
        {"type": "plain", "text": "Analyze"},
        {"type": "image", "path": "chart.png", "text": "Chart"},
        {"type": "file", "url": "https://example.com/report.pdf"},
    ]
    assert format_input_content(content) == (
        "Analyze\n[image] Chart chart.png\n[file] https://example.com/report.pdf"
    )
    adapter = TypeAdapter(list[InputComponent])
    assert (
        adapter.validate_json(adapter.dump_json(content, exclude_none=True)) == content
    )
    with pytest.raises(ValidationError, match="frozen"):
        content[0].text = "Changed"


@pytest.mark.parametrize("component", [ImageInput, FileInput])
@pytest.mark.parametrize(
    "references", [{}, {"path": "a", "url": "b"}, {"path": " "}, {"url": 123}]
)
def test_input_attachments_require_an_unambiguous_nonempty_reference(
    component, references
):
    with pytest.raises(ValueError):
        component(**references)
