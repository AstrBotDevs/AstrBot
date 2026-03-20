from astrbot.core.prompt_assembly_router import assemble_system_prompt


def test_assemble_system_prompt_omits_empty_sections() -> None:
    prompt = assemble_system_prompt(base_system_prompt="Base")
    assert prompt == "Base"


def test_assemble_system_prompt_orders_sections() -> None:
    prompt = assemble_system_prompt(
        base_system_prompt="Base",
        retrieved_long_term_facts=["Fact A", "Fact B"],
        summarized_history="Summary C",
        pinned_memory_block="<top_level_memory>\nPinned D\n</top_level_memory>",
    )

    assert "Base" in prompt
    assert "<long_term_facts>" in prompt
    assert "<summarized_history>" in prompt
    assert "<top_level_memory>" in prompt
    assert prompt.index("Base") < prompt.index("<long_term_facts>")
    assert prompt.index("<long_term_facts>") < prompt.index("<summarized_history>")
    assert prompt.index("<summarized_history>") < prompt.index("<top_level_memory>")
