"""Import smoke tests for DifyAPIClient."""

from unittest.mock import patch

import pytest

from astrbot.core.agent.runners.dify.dify_api_client import DifyAPIClient, _stream_sse


class TestDifyAPIClientImport:
    """Verify DifyAPIClient can be imported and instantiated."""

    def test_class_importable(self):
        """DifyAPIClient should be importable."""
        assert DifyAPIClient is not None

    def test_instantiation_with_defaults(self):
        """DifyAPIClient should be instantiatable with only api_key."""
        with patch("astrbot.core.agent.runners.dify.dify_api_client.ClientSession"):
            client = DifyAPIClient(api_key="test-key")
        assert isinstance(client, DifyAPIClient)
        assert client.api_key == "test-key"
        assert client.api_base == "https://api.dify.ai/v1"

    def test_instantiation_with_custom_base(self):
        """DifyAPIClient should accept a custom api_base."""
        with patch("astrbot.core.agent.runners.dify.dify_api_client.ClientSession"):
            client = DifyAPIClient(api_key="test-key", api_base="https://custom.dify.com/v1")
        assert isinstance(client, DifyAPIClient)
        assert client.api_base == "https://custom.dify.com/v1"

    def test_session_created_on_init(self):
        """DifyAPIClient creates a ClientSession on init."""
        import aiohttp

        with patch("astrbot.core.agent.runners.dify.dify_api_client.ClientSession", spec=aiohttp.ClientSession):
            client = DifyAPIClient(api_key="test-key")
        assert isinstance(client.session, aiohttp.ClientSession)

    def test_headers_include_bearer_token(self):
        """Headers should include the Authorization bearer token."""
        with patch("astrbot.core.agent.runners.dify.dify_api_client.ClientSession"):
            client = DifyAPIClient(api_key="my-secret-key")
        assert client.headers["Authorization"] == "Bearer my-secret-key"

    @pytest.mark.asyncio
    async def test_close_cleans_up_session(self):
        """close() should close the underlying session."""
        client = DifyAPIClient(api_key="test-key")
        assert not client.session.closed
        await client.close()
        assert client.session.closed

    def test_stream_sse_is_callable(self):
        """_stream_sse helper should be importable and callable."""
        assert callable(_stream_sse)
