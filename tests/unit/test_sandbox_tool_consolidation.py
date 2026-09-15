from astrbot.core.tools.computer_tools import sandbox as sandbox_tools


def _actions(tool_cls) -> set[str]:
    return set(tool_cls().parameters["properties"]["action"]["enum"])


def test_generic_sandbox_tools_are_grouped_by_intent():
    assert sandbox_tools.SandboxQueryTool().name == "astrbot_sandbox_query"
    assert sandbox_tools.SandboxLifecycleTool().name == "astrbot_sandbox_lifecycle"
    assert sandbox_tools.SandboxOperationTool().name == "astrbot_sandbox_operation"

    assert _actions(sandbox_tools.SandboxQueryTool) == {
        "list_sandboxes",
        "get_current",
        "list_providers",
    }
    assert _actions(sandbox_tools.SandboxLifecycleTool) == {
        "create",
        "switch",
        "release",
        "renew_lease",
        "set_retention",
        "takeover",
        "destroy",
    }
    assert _actions(sandbox_tools.SandboxOperationTool) == {
        "capture_screenshot",
        "copy_file",
    }
    operation_params = sandbox_tools.SandboxOperationTool().parameters["properties"]
    assert "return_image_to_llm" in operation_params
    assert (
        "copy_file requires source_sandbox_id"
        in sandbox_tools.SandboxOperationTool().description
    )


def test_legacy_generic_sandbox_tools_are_not_registered():
    legacy_names = {
        "ListSandboxesTool",
        "ListSandboxProvidersTool",
        "GetCurrentSandboxTool",
        "CreateSandboxTool",
        "SwitchSandboxTool",
        "ReleaseSandboxTool",
        "SetSandboxRetentionPolicyTool",
        "KeepAliveSandboxTool",
        "TakeoverSandboxTool",
        "DestroySandboxTool",
        "ScreenshotSandboxTool",
        "CopyFileBetweenSandboxesTool",
    }

    assert not any(hasattr(sandbox_tools, name) for name in legacy_names)
