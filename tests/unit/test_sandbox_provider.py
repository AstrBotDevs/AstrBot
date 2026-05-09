from typing import get_type_hints

from astrbot.core.computer.sandbox_provider import SandboxProvider


def test_sandbox_provider_protocol_exposes_generic_runtime_contract():
    protocol_hints = get_type_hints(SandboxProvider)
    assert protocol_hints["provider_id"] is str
    assert protocol_hints["capabilities"] == set[str]
    assert protocol_hints["tool_names"] == set[str]
    assert protocol_hints["system_prompt"] is str

    hints = get_type_hints(SandboxProvider.create_booter)
    assert "context" in hints
    assert hints["session_id"] is str
    assert hints["sandbox_id"] is str
