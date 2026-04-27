"""Tests for prompt assembly rendering helpers."""

from unittest.mock import patch

from astrbot.core.agent.message import TextPart
from astrbot.core.prompt import (
    PromptAssembly,
    PromptMutation,
    add_context_prefix,
    add_context_suffix,
    add_system_block,
    add_user_part,
    build_prompt_trace_snapshot,
    render_prompt_assembly,
    summarize_provider_request_base,
)
from astrbot.core.provider.entities import ProviderRequest


def test_render_prompt_assembly_orders_channels():
    req = ProviderRequest(
        prompt="hello",
        system_prompt="BASE",
        contexts=[{"role": "user", "content": "history"}],
    )
    assembly = PromptAssembly()

    add_system_block(assembly, source="skills", order=300, content="\nSKILLS\n")
    add_system_block(assembly, source="persona", order=200, content="\nPERSONA\n")
    add_system_block(
        assembly,
        source="safety",
        order=100,
        content="SAFE\n",
        prepend=True,
    )
    add_user_part(
        assembly,
        source="quoted",
        order=200,
        part=TextPart(text="quoted"),
    )
    add_user_part(
        assembly,
        source="attachment",
        order=100,
        part=TextPart(text="attachment"),
    )
    add_context_prefix(
        assembly,
        source="prefix",
        order=100,
        messages=[{"role": "system", "content": "prefix"}],
    )
    add_context_suffix(
        assembly,
        source="suffix",
        order=100,
        messages=[{"role": "assistant", "content": "suffix"}],
    )

    render_prompt_assembly(req, assembly)

    assert req.system_prompt == "SAFE\nBASE\nPERSONA\n\nSKILLS\n"
    assert [part.text for part in req.extra_user_content_parts] == [
        "attachment",
        "quoted",
    ]
    assert req.contexts == [
        {"role": "system", "content": "prefix"},
        {"role": "user", "content": "history"},
        {"role": "assistant", "content": "suffix"},
    ]


def test_render_prompt_assembly_is_render_once():
    req = ProviderRequest(prompt="hello")
    assembly = PromptAssembly()
    add_system_block(assembly, source="persona", order=200, content="\nPERSONA\n")
    add_user_part(
        assembly,
        source="attachment",
        order=100,
        part=TextPart(text="attachment"),
    )

    render_prompt_assembly(req, assembly)
    render_prompt_assembly(req, assembly)

    assert req.system_prompt == "\nPERSONA\n"
    assert [part.text for part in req.extra_user_content_parts] == ["attachment"]


def test_render_prompt_assembly_empty_is_noop():
    req = ProviderRequest(
        prompt="hello",
        system_prompt="BASE",
        contexts=[{"role": "user", "content": "history"}],
    )

    render_prompt_assembly(req, PromptAssembly())

    assert req.system_prompt == "BASE"
    assert req.extra_user_content_parts == []
    assert req.contexts == [{"role": "user", "content": "history"}]


def test_build_prompt_trace_snapshot_contains_sorted_sources():
    req = ProviderRequest(
        prompt="hello",
        system_prompt="BASE",
        contexts=[{"role": "user", "content": "history"}],
    )
    assembly = PromptAssembly(
        metadata={
            "kind": "test",
            "base_request": summarize_provider_request_base(req),
        }
    )
    add_system_block(assembly, source="skills", order=300, content="\nSKILLS\n")
    add_system_block(
        assembly,
        source="persona",
        order=200,
        content="\nPERSONA\n",
        prepend=True,
    )
    add_user_part(
        assembly,
        source="attachment",
        order=100,
        part=TextPart(text="attachment"),
    )
    add_context_suffix(
        assembly,
        source="file_extract",
        order=100,
        messages=[{"role": "system", "content": "suffix"}],
    )

    snapshot = build_prompt_trace_snapshot(assembly)

    assert [item["source"] for item in snapshot["system_blocks"]] == [
        "persona",
        "skills",
    ]
    assert snapshot["user_append_parts"] == [
        {
            "source": "attachment",
            "order": 100,
            "part": {"type": "text", "char_count": 10},
        }
    ]
    assert snapshot["system_blocks"] == [
        {
            "source": "persona",
            "order": 200,
            "prepend": True,
            "char_count": 9,
        },
        {
            "source": "skills",
            "order": 300,
            "prepend": False,
            "char_count": 8,
        },
    ]
    assert snapshot["context_prefix"] == []
    assert snapshot["context_suffix"] == [
        {
            "source": "file_extract",
            "order": 100,
            "message_count": 1,
            "roles": ["system"],
            "text_char_count": 6,
            "non_text_part_count": 0,
        }
    ]
    assert snapshot["metadata"] == {
        "kind": "test",
        "base_request": {
            "system_prompt_chars": 4,
            "context_count": 1,
            "extra_user_part_count": 0,
            "image_count": 0,
            "has_prompt": True,
        },
    }
    assert "content" not in snapshot["system_blocks"][0]
    assert "messages" not in snapshot["context_suffix"][0]


def test_prompt_mutation_facade_dispatches_to_helper_functions():
    assembly = PromptAssembly()
    mutation = PromptMutation(assembly)

    with (
        patch("astrbot.core.prompt.assembly.add_system_block") as mock_add_system,
        patch("astrbot.core.prompt.assembly.add_user_text") as mock_add_user_text,
        patch(
            "astrbot.core.prompt.assembly.add_context_prefix"
        ) as mock_add_context_prefix,
        patch(
            "astrbot.core.prompt.assembly.add_context_suffix"
        ) as mock_add_context_suffix,
        patch("astrbot.core.prompt.assembly.logger.warning"),
    ):
        mutation.add_system("\nPLUGIN\n", "plugin:test", 950)
        mutation.add_user_text("plugin user", "plugin:test", 950)
        mutation.add_context_prefix(
            [{"role": "system", "content": "prefix"}], "plugin:test", 950
        )
        mutation.add_context_suffix(
            [{"role": "assistant", "content": "suffix"}], "plugin:test", 950
        )

    mock_add_system.assert_called_once_with(
        assembly,
        source="plugin:test",
        order=950,
        content="\nPLUGIN\n",
        visible_in_trace=True,
    )
    mock_add_user_text.assert_called_once_with(
        assembly,
        source="plugin:test",
        order=950,
        text="plugin user",
        visible_in_trace=True,
    )
    mock_add_context_prefix.assert_called_once_with(
        assembly,
        source="plugin:test",
        order=950,
        messages=[{"role": "system", "content": "prefix"}],
        visible_in_trace=True,
    )
    mock_add_context_suffix.assert_called_once_with(
        assembly,
        source="plugin:test",
        order=950,
        messages=[{"role": "assistant", "content": "suffix"}],
        visible_in_trace=True,
    )


def test_prompt_mutation_warns_once_for_reserved_plugin_order():
    assembly = PromptAssembly()
    mutation = PromptMutation(assembly)

    with patch("astrbot.core.prompt.assembly.logger.warning") as mock_warning:
        mutation.add_system("\nPLUGIN\n", "plugin:test", 850)
        mutation.add_user_text("plugin user", "plugin:test", 850)

    mock_warning.assert_called_once()


def test_prompt_mutation_warns_once_for_context_prefix_cache_impact():
    assembly = PromptAssembly()
    mutation = PromptMutation(assembly)

    with patch("astrbot.core.prompt.assembly.logger.warning") as mock_warning:
        mutation.add_context_prefix(
            [{"role": "system", "content": "prefix"}],
            "plugin:test",
            950,
        )
        mutation.add_context_prefix(
            [{"role": "system", "content": "prefix again"}],
            "plugin:test",
            950,
        )

    mock_warning.assert_called_once()
