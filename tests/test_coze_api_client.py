"""Import smoke tests for CozeAPIClient."""

import pytest

from astrbot.core.agent.runners.coze.coze_api_client import CozeAPIClient


class TestCozeAPIClientImport:
    """Verify CozeAPIClient can be imported and instantiated."""

    def test_class_importable(self):
        """CozeAPIClient should be importable."""
        assert CozeAPIClient is not None

    def test_instantiation_with_defaults(self):
        """CozeAPIClient should be instantiatable with only api_key."""
        client = CozeAPIClient(api_key="test-key")
        assert isinstance(client, CozeAPIClient)
        assert client.api_key == "test-key"
        assert client.api_base == "https://api.coze.cn"

    def test_instantiation_with_custom_base(self):
        """CozeAPIClient should accept a custom api_base."""
        client = CozeAPIClient(api_key="test-key", api_base="https://custom.coze.com")
        assert isinstance(client, CozeAPIClient)
        assert client.api_base == "https://custom.coze.com"

    def test_session_is_none_on_creation(self):
        """HTTP session should be None until _ensure_session is called."""
        client = CozeAPIClient(api_key="test-key")
        assert client.session is None

    @pytest.mark.asyncio
    async def test_ensure_session_creates_session(self):
        """_ensure_session() should create an aiohttp ClientSession."""
        import aiohttp

        client = CozeAPIClient(api_key="test-key")
        session = await client._ensure_session()
        assert isinstance(session, aiohttp.ClientSession)
        await client.close()

    @pytest.mark.asyncio
    async def test_close_clears_session(self):
        """close() should clear the session."""
        client = CozeAPIClient(api_key="test-key")
        await client._ensure_session()
        assert client.session is not None
        await client.close()
        assert client.session is None
