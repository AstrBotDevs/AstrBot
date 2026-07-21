import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import anyio
import mcp
import pytest

from astrbot.core.agent.mcp_client import (
    MCPClient,
    MCPPromptPaginationNotSupportedError,
)


def _prompt_client(session=None):
    client = MCPClient()
    client.session = session or AsyncMock()
    client._server_capabilities = SimpleNamespace(
        prompts=SimpleNamespace(listChanged=False)
    )
    return client


class TestMCPPromptCapabilities:
    @pytest.mark.asyncio
    async def test_prompt_capability_does_not_require_list_changed(self):
        client = MCPClient()
        assert client.supports_prompts is False

        client._server_capabilities = SimpleNamespace(prompts=None)
        assert client.supports_prompts is False

        client._server_capabilities = SimpleNamespace()
        assert client.supports_prompts is False

        client._server_capabilities = SimpleNamespace(
            prompts=SimpleNamespace(listChanged=False)
        )
        assert client.supports_prompts is True

        await client.cleanup()
        assert client.supports_prompts is False

    @pytest.mark.asyncio
    async def test_prompt_operations_require_available_session(self):
        client = _prompt_client()
        client.session = None

        with pytest.raises(ValueError, match="session is not available"):
            await client.list_prompts()
        with pytest.raises(ValueError, match="session is not available"):
            await client.get_prompt("review")

    @pytest.mark.asyncio
    async def test_prompt_operations_require_advertised_capability(self):
        session = AsyncMock()
        client = MCPClient()
        client.session = session

        with pytest.raises(RuntimeError, match="does not advertise prompts"):
            await client.list_prompts()
        with pytest.raises(RuntimeError, match="does not advertise prompts"):
            await client.get_prompt("review")

        session.list_prompts.assert_not_awaited()
        session.get_prompt.assert_not_awaited()


class TestMCPPromptListing:
    @pytest.mark.asyncio
    async def test_listing_without_cursor_uses_sdk_1_8_compatible_call(self):
        session = AsyncMock()
        expected = object()
        session.list_prompts.return_value = expected
        client = _prompt_client(session)

        result = await client.list_prompts()

        assert result is expected
        session.list_prompts.assert_awaited_once_with()
        assert not hasattr(client, "prompts")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cursor", ["next-page", ""])
    async def test_listing_prefers_params_api_when_available(self, cursor):
        expected = object()

        class PaginatedRequestParams:
            def __init__(self, cursor):
                self.cursor = cursor

        class ParamsSession:
            def __init__(self):
                self.calls = []

            async def list_prompts(self, cursor=None, *, params=None):
                self.calls.append((cursor, params))
                return expected

        session = ParamsSession()
        client = _prompt_client(session)

        with patch.object(
            mcp.types,
            "PaginatedRequestParams",
            PaginatedRequestParams,
            create=True,
        ):
            result = await client.list_prompts(cursor)

        assert result is expected
        assert session.calls[0][0] is None
        assert session.calls[0][1].cursor == cursor

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cursor", ["next-page", ""])
    async def test_listing_uses_cursor_api_on_intermediate_sdks(self, cursor):
        expected = object()

        class CursorSession:
            def __init__(self):
                self.calls = []

            async def list_prompts(self, cursor=None):
                self.calls.append(cursor)
                return expected

        session = CursorSession()
        client = _prompt_client(session)

        result = await client.list_prompts(cursor)

        assert result is expected
        assert session.calls == [cursor]

    @pytest.mark.asyncio
    async def test_cursor_on_sdk_1_8_raises_clear_error_without_request(self):
        class MCP18Session:
            def __init__(self):
                self.calls = 0

            async def list_prompts(self):
                self.calls += 1
                return object()

        session = MCP18Session()
        client = _prompt_client(session)

        with pytest.raises(
            MCPPromptPaginationNotSupportedError,
            match="does not support prompt pagination",
        ):
            await client.list_prompts("next-page")

        assert session.calls == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "signature_error",
        [ValueError("unavailable"), TypeError("unsupported")],
    )
    async def test_signature_detection_failure_raises_clear_error(
        self,
        signature_error,
    ):
        session = AsyncMock()
        client = _prompt_client(session)

        with (
            patch(
                "astrbot.core.agent.mcp_client.inspect.signature",
                side_effect=signature_error,
            ),
            pytest.raises(
                MCPPromptPaginationNotSupportedError,
                match="could not be detected",
            ),
        ):
            await client.list_prompts("next-page")

        session.list_prompts.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_listing_does_not_mask_sdk_type_errors(self):
        class PaginatedRequestParams:
            def __init__(self, cursor):
                self.cursor = cursor

        class ParamsSession:
            async def list_prompts(self, cursor=None, *, params=None):
                raise TypeError("invalid response payload")

        client = _prompt_client(ParamsSession())

        with (
            patch.object(
                mcp.types,
                "PaginatedRequestParams",
                PaginatedRequestParams,
                create=True,
            ),
            pytest.raises(TypeError, match="invalid response payload"),
        ):
            await client.list_prompts("next-page")

    @pytest.mark.asyncio
    async def test_listing_propagates_cancellation(self):
        class CursorSession:
            async def list_prompts(self, cursor=None):
                raise asyncio.CancelledError()

        client = _prompt_client(CursorSession())

        with pytest.raises(asyncio.CancelledError):
            await client.list_prompts("next-page")


class TestMCPPromptRetrieval:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("arguments", [None, {}, {"topic": "MCP"}])
    async def test_get_prompt_forwards_arguments_without_caching(self, arguments):
        session = AsyncMock()
        expected = object()
        session.get_prompt.return_value = expected
        client = _prompt_client(session)

        result = await client.get_prompt("review", arguments)

        assert result is expected
        session.get_prompt.assert_awaited_once_with(
            name="review",
            arguments=arguments,
        )
        assert not hasattr(client, "prompts")

    @pytest.mark.asyncio
    async def test_get_prompt_does_not_reconnect_after_closed_transport(self):
        session = AsyncMock()
        session.get_prompt.side_effect = anyio.ClosedResourceError()
        client = _prompt_client(session)
        client._reconnect = AsyncMock()

        with pytest.raises(anyio.ClosedResourceError):
            await client.get_prompt("review", {"topic": "MCP"})

        client._reconnect.assert_not_awaited()
