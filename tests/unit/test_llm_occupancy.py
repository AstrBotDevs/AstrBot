"""LLM prefix occupancy rejects command-root collisions."""

from astrbot.core.command import CommandCatalog, CommandGroupRegistration
from astrbot.core.command.occupancy import collect_command_roots, llm_prefix_conflict


def test_llm_prefix_llm_is_rejected_when_root_occupied():
    catalog = CommandCatalog(
        groups=[CommandGroupRegistration((("llm",),), "builtin.llm")]
    )
    error = llm_prefix_conflict(
        ["/llm"],
        ["/"],
        collect_command_roots(catalog),
        config_id="default",
    )
    assert error is not None
    assert error["error_code"] == "llm_prefix_occupied"
    assert error["config_id"] == "default"
    assert error["public_path"] == "llm"


def test_bare_slash_prefix_is_not_an_occupancy_conflict():
    catalog = CommandCatalog(
        groups=[CommandGroupRegistration((("llm",),), "builtin.llm")]
    )
    assert (
        llm_prefix_conflict(
            ["/"],
            ["/"],
            collect_command_roots(catalog),
            config_id="default",
        )
        is None
    )
