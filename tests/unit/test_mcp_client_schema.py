from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.core.agent.mcp_client import (
    MCPTool,
    _normalize_mcp_input_schema,
    validate_mcp_stdio_config,
)


class TestNormalizeMcpInputSchema:
    def test_lifts_property_level_required_booleans_to_parent_required_array(self):
        schema = {
            "type": "object",
            "properties": {
                "stock_code": {"type": "string", "required": True},
                "market": {"type": "string", "required": False},
            },
        }

        normalized = _normalize_mcp_input_schema(schema)

        assert normalized["required"] == ["stock_code"]
        assert "required" not in normalized["properties"]["stock_code"]
        assert "required" not in normalized["properties"]["market"]
        assert schema["properties"]["stock_code"]["required"] is True

    def test_preserves_existing_required_arrays_while_fixing_nested_objects(self):
        schema = {
            "type": "object",
            "required": ["server"],
            "properties": {
                "server": {
                    "type": "object",
                    "required": ["transport"],
                    "properties": {
                        "transport": {"type": "string"},
                        "stock_code": {"type": "string", "required": True},
                        "market": {"type": "string", "required": False},
                    },
                }
            },
        }

        normalized = _normalize_mcp_input_schema(schema)

        assert normalized["required"] == ["server"]
        assert normalized["properties"]["server"]["required"] == [
            "transport",
            "stock_code",
        ]
        assert (
            "required"
            not in normalized["properties"]["server"]["properties"]["stock_code"]
        )
        assert (
            "required" not in normalized["properties"]["server"]["properties"]["market"]
        )

    def test_preserves_parent_required_flag_for_nested_object_properties(self):
        schema = {
            "type": "object",
            "properties": {
                "server": {
                    "type": "object",
                    "required": True,
                    "properties": {
                        "transport": {"type": "string", "required": True},
                    },
                }
            },
        }

        normalized = _normalize_mcp_input_schema(schema)

        assert normalized["required"] == ["server"]
        assert normalized["properties"]["server"]["required"] == ["transport"]
        assert (
            "required"
            not in normalized["properties"]["server"]["properties"]["transport"]
        )

    def test_ignores_non_boolean_required_values_and_non_dict_properties(self):
        schema = {
            "type": "object",
            "properties": {
                "server": "invalid-property-schema",
                "market": {"type": "string", "required": "yes"},
                "stock_code": {"type": "string", "required": True},
            },
        }

        normalized = _normalize_mcp_input_schema(schema)

        assert normalized["required"] == ["stock_code"]
        assert normalized["properties"]["server"] == "invalid-property-schema"
        assert normalized["properties"]["market"]["required"] == "yes"
        assert "required" not in normalized["properties"]["stock_code"]
        assert schema["properties"]["server"] == "invalid-property-schema"
        assert schema["properties"]["market"]["required"] == "yes"


class TestMCPToolSchemaNormalization:
    def test_mcp_tool_accepts_property_level_required_booleans(self):
        mcp_tool = SimpleNamespace(
            name="quote_lookup",
            description="Lookup a quote",
            inputSchema={
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string", "required": True},
                    "market": {"type": "string", "required": False},
                },
            },
        )

        tool = MCPTool(mcp_tool, MagicMock(), "gf-securities")

        assert tool.parameters["required"] == ["stock_code"]
        assert "required" not in tool.parameters["properties"]["stock_code"]
        assert "required" not in tool.parameters["properties"]["market"]


class TestValidateMcpStdioConfig:
    @pytest.mark.parametrize("suffix", [".py", ".pyw", ".pyc", ".pyo", ".pyz"])
    def test_rejects_python_local_script_targets(self, suffix: str) -> None:
        config = {"command": "python", "args": [f"./payload{suffix}"]}

        with pytest.raises(ValueError, match="local Python script/archive"):
            validate_mcp_stdio_config(config)

    def test_rejects_windows_python_archive_target_case_insensitively(self) -> None:
        config = {
            "command": "python3",
            "args": ["-I", "-u", "C:\\Users\\Public\\payload.PYZ"],
        }

        with pytest.raises(ValueError, match="local Python script/archive"):
            validate_mcp_stdio_config(config)

    def test_rejects_python_script_target_after_option_separator(self) -> None:
        config = {"command": "python", "args": ["--", "payload.py"]}

        with pytest.raises(ValueError, match="local Python script/archive"):
            validate_mcp_stdio_config(config)

    def test_rejects_python_local_target_without_known_suffix(self) -> None:
        config = {"command": "python", "args": ["./payload"]}

        with pytest.raises(ValueError, match="local Python script/archive"):
            validate_mcp_stdio_config(config)

    @pytest.mark.parametrize(
        "config",
        [
            {"command": "python", "args": ["-m", "mcp_server"]},
            {"command": "python3", "args": ["-I", "-m", "package.module"]},
            {"command": "python3", "args": ["-mmcp_server"]},
            {"command": "py", "args": ["-3.12", "-m", "mcp_server"]},
            {
                "command": "python",
                "args": ["-m", "mcp_server", "--config", "server.py"],
            },
            {
                "mcpServers": {
                    "demo": {"command": "python", "args": ["-m", "mcp_server"]}
                }
            },
        ],
    )
    def test_allows_python_module_launches(self, config: dict) -> None:
        validate_mcp_stdio_config(config)

    def test_rejects_python_inline_code_flags(self) -> None:
        config = {"command": "python", "args": ["-c", "print('x')"]}

        with pytest.raises(ValueError, match="inline code flags"):
            validate_mcp_stdio_config(config)

    def test_rejects_python_compact_inline_code_flags(self) -> None:
        config = {"command": "python", "args": ["-Ic", "print('x')"]}

        with pytest.raises(ValueError, match="inline code flags"):
            validate_mcp_stdio_config(config)

    def test_rejects_python_missing_module_name(self) -> None:
        config = {"command": "python", "args": ["-m"]}

        with pytest.raises(ValueError, match="module or package"):
            validate_mcp_stdio_config(config)

    def test_rejects_python_option_only_launch(self) -> None:
        config = {"command": "python", "args": ["-I", "-u"]}

        with pytest.raises(ValueError, match="module or package"):
            validate_mcp_stdio_config(config)

    def test_rejects_python_launch_without_args(self) -> None:
        config = {"command": "python"}

        with pytest.raises(ValueError, match="module or package"):
            validate_mcp_stdio_config(config)

    def test_allows_module_owned_dash_c_argument(self) -> None:
        config = {
            "command": "python",
            "args": ["-m", "mcp_server", "-c", "config.toml"],
        }

        validate_mcp_stdio_config(config)
