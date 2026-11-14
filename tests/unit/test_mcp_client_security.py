from types import SimpleNamespace

import pytest

from astrbot.core.agent import mcp_client
from astrbot.core.utils.ssrf_guard import UnsafeMcpUrlError, validate_mcp_url


class TestValidateMcpUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "http://169.254.169.254/latest/meta-data/",  # cloud metadata
            "http://127.0.0.1:8080/mcp",
            "http://localhost/mcp",
            "http://10.0.0.5/mcp",
            "http://172.16.0.5/mcp",
            "http://192.168.1.5/mcp",
            "http://0.0.0.0/mcp",
            "ftp://example.com/mcp",
        ],
    )
    def test_blocks_unsafe_urls(self, url):
        with pytest.raises(UnsafeMcpUrlError):
            validate_mcp_url(url)

    def test_allows_public_url(self):
        validate_mcp_url("https://example.com/mcp")

    def test_env_override_allows_private_urls(self, monkeypatch):
        monkeypatch.setenv("ASTRBOT_MCP_ALLOW_PRIVATE_NETWORK_URLS", "1")
        validate_mcp_url("http://127.0.0.1:8080/mcp")


class TestMergeEnvironmentVariables:
    def test_does_not_leak_secrets(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secret")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp-secret")

        merged = mcp_client._merge_environment_variables({})

        assert "OPENAI_API_KEY" not in merged
        assert "GITHUB_TOKEN" not in merged

    def test_preserves_safe_launcher_vars(self, monkeypatch):
        monkeypatch.setenv("PATH", "/system/path")

        merged = mcp_client._merge_environment_variables({})

        assert merged.get("PATH") == "/system/path"

    def test_user_supplied_env_takes_precedence_case_insensitively(self, monkeypatch):
        monkeypatch.setenv("PATH", "/system/path")

        merged = mcp_client._merge_environment_variables({"Path": "/custom/path"})

        assert merged["Path"] == "/custom/path"
        assert "PATH" not in merged


class TestNpxPackageAllowlist:
    def test_unrestricted_by_default(self, monkeypatch):
        monkeypatch.delenv("ASTRBOT_MCP_NPX_ALLOWED_PACKAGES", raising=False)
        mcp_client._validate_stdio_args("npx", ["-y", "@anything/whatever"])

    def test_blocks_disallowed_package_when_allowlist_configured(self, monkeypatch):
        monkeypatch.setenv(
            "ASTRBOT_MCP_NPX_ALLOWED_PACKAGES",
            "@modelcontextprotocol/server-filesystem",
        )
        with pytest.raises(ValueError):
            mcp_client._validate_stdio_args("npx", ["-y", "@malicious/scope@latest"])

    def test_allows_listed_package(self, monkeypatch):
        monkeypatch.setenv(
            "ASTRBOT_MCP_NPX_ALLOWED_PACKAGES",
            "@modelcontextprotocol/server-filesystem",
        )
        mcp_client._validate_stdio_args(
            "npx", ["-y", "@modelcontextprotocol/server-filesystem"]
        )


class TestCapMcpResponseSize:
    def test_truncates_oversized_text_content(self, monkeypatch):
        monkeypatch.setenv("ASTRBOT_MCP_MAX_RESPONSE_TEXT_LENGTH", "10")
        block = SimpleNamespace(text="x" * 100)
        result = SimpleNamespace(content=[block])

        mcp_client._cap_mcp_response_size(result)

        assert len(block.text) < 100
        assert block.text.startswith("x" * 10)
        assert "truncated" in block.text

    def test_leaves_normal_sized_content_untouched(self):
        block = SimpleNamespace(text="short text")
        result = SimpleNamespace(content=[block])

        mcp_client._cap_mcp_response_size(result)

        assert block.text == "short text"
