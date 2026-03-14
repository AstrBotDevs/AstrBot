"""Tests for HTTPClient and MetadataClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot_sdk.clients.http import HTTPClient
from astrbot_sdk.clients.metadata import MetadataClient, PluginMetadata
from astrbot_sdk.clients._proxy import CapabilityProxy
from astrbot_sdk.decorators import provide_capability
from astrbot_sdk.errors import AstrBotError


class TestHTTPClient:
    """Tests for HTTPClient."""

    @pytest.fixture
    def mock_proxy(self):
        """Create a mock CapabilityProxy."""
        proxy = MagicMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})
        return proxy

    @pytest.fixture
    def http_client(self, mock_proxy):
        """Create HTTPClient with mock proxy."""
        return HTTPClient(mock_proxy)

    @pytest.mark.asyncio
    async def test_register_api_calls_proxy_with_correct_args(
        self, http_client, mock_proxy
    ):
        """register_api should call proxy with correct arguments."""
        await http_client.register_api(
            route="/test-api",
            handler_capability="test_plugin.http_handler",
            methods=["GET", "POST"],
            description="Test API",
        )

        mock_proxy.call.assert_called_once_with(
            "http.register_api",
            {
                "route": "/test-api",
                "methods": ["GET", "POST"],
                "handler_capability": "test_plugin.http_handler",
                "description": "Test API",
            },
        )

    @pytest.mark.asyncio
    async def test_register_api_defaults_to_get(self, http_client, mock_proxy):
        """register_api should default to GET method."""
        await http_client.register_api(
            route="/test-api",
            handler_capability="test_plugin.http_handler",
        )

        call_args = mock_proxy.call.call_args
        assert call_args[0][1]["methods"] == ["GET"]

    @pytest.mark.asyncio
    async def test_register_api_accepts_capability_handler_reference(
        self, http_client, mock_proxy
    ):
        class DemoPlugin:
            @provide_capability(
                "demo.http_handler",
                description="handle http requests",
            )
            async def http_handler(self, payload):
                return payload

        plugin = DemoPlugin()
        await http_client.register_api(
            route="/test-api",
            handler=plugin.http_handler,
            methods=["POST"],
        )

        mock_proxy.call.assert_called_once_with(
            "http.register_api",
            {
                "route": "/test-api",
                "methods": ["POST"],
                "handler_capability": "demo.http_handler",
                "description": "",
            },
        )

    @pytest.mark.asyncio
    async def test_register_api_rejects_conflicting_handler_inputs(
        self, http_client, mock_proxy
    ):
        class DemoPlugin:
            @provide_capability(
                "demo.http_handler",
                description="handle http requests",
            )
            async def http_handler(self, payload):
                return payload

        plugin = DemoPlugin()
        with pytest.raises(AstrBotError, match="不能同时提供"):
            await http_client.register_api(
                route="/test-api",
                handler_capability="demo.http_handler",
                handler=plugin.http_handler,
            )
        mock_proxy.call.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_api_rejects_non_capability_handler(
        self, http_client, mock_proxy
    ):
        class DemoPlugin:
            async def plain_method(self, payload):
                return payload

        plugin = DemoPlugin()
        with pytest.raises(
            AstrBotError, match="需要传入使用 @provide_capability 声明的方法"
        ):
            await http_client.register_api(
                route="/test-api",
                handler=plugin.plain_method,
            )
        mock_proxy.call.assert_not_called()

    @pytest.mark.asyncio
    async def test_unregister_api_calls_proxy(self, http_client, mock_proxy):
        """unregister_api should call proxy with correct arguments."""
        await http_client.unregister_api("/test-api", methods=["GET"])

        mock_proxy.call.assert_called_once_with(
            "http.unregister_api",
            {"route": "/test-api", "methods": ["GET"]},
        )

    @pytest.mark.asyncio
    async def test_unregister_api_defaults_to_all_methods(
        self, http_client, mock_proxy
    ):
        """unregister_api should pass empty methods list for all methods."""
        await http_client.unregister_api("/test-api")

        call_args = mock_proxy.call.call_args
        assert call_args[0][1]["methods"] == []

    @pytest.mark.asyncio
    async def test_list_apis_returns_apis_from_proxy(self, http_client, mock_proxy):
        """list_apis should return apis from proxy response."""
        mock_proxy.call.return_value = {
            "apis": [
                {"route": "/api1", "methods": ["GET"], "description": "API 1"},
                {"route": "/api2", "methods": ["POST"], "description": "API 2"},
            ]
        }

        result = await http_client.list_apis()

        assert len(result) == 2
        assert result[0]["route"] == "/api1"
        assert result[1]["route"] == "/api2"

    @pytest.mark.asyncio
    async def test_list_apis_returns_empty_list_when_no_apis(
        self, http_client, mock_proxy
    ):
        """list_apis should return empty list when no apis."""
        mock_proxy.call.return_value = {}

        result = await http_client.list_apis()

        assert result == []


class TestMetadataClient:
    """Tests for MetadataClient."""

    @pytest.fixture
    def mock_proxy(self):
        """Create a mock CapabilityProxy."""
        proxy = MagicMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})
        return proxy

    @pytest.fixture
    def metadata_client(self, mock_proxy):
        """Create MetadataClient with mock proxy."""
        return MetadataClient(mock_proxy, "current_plugin")

    @pytest.mark.asyncio
    async def test_get_plugin_returns_metadata(self, metadata_client, mock_proxy):
        """get_plugin should return PluginMetadata when plugin exists."""
        mock_proxy.call.return_value = {
            "plugin": {
                "name": "test_plugin",
                "display_name": "Test Plugin",
                "desc": "A test plugin",
                "author": "test_author",
                "version": "1.0.0",
                "enabled": True,
            }
        }

        result = await metadata_client.get_plugin("test_plugin")

        assert result is not None
        assert result.name == "test_plugin"
        assert result.display_name == "Test Plugin"
        assert result.author == "test_author"
        assert result.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_plugin_returns_none_when_not_found(
        self, metadata_client, mock_proxy
    ):
        """get_plugin should return None when plugin not found."""
        mock_proxy.call.return_value = {}

        result = await metadata_client.get_plugin("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_plugins_returns_list(self, metadata_client, mock_proxy):
        """list_plugins should return list of PluginMetadata."""
        mock_proxy.call.return_value = {
            "plugins": [
                {
                    "name": "plugin1",
                    "display_name": "Plugin 1",
                    "author": "a1",
                    "version": "1.0",
                },
                {
                    "name": "plugin2",
                    "display_name": "Plugin 2",
                    "author": "a2",
                    "version": "2.0",
                },
            ]
        }

        result = await metadata_client.list_plugins()

        assert len(result) == 2
        assert result[0].name == "plugin1"
        assert result[1].name == "plugin2"

    @pytest.mark.asyncio
    async def test_list_plugins_returns_empty_list(self, metadata_client, mock_proxy):
        """list_plugins should return empty list when no plugins."""
        mock_proxy.call.return_value = {}

        result = await metadata_client.list_plugins()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_plugin_config_returns_config_for_current_plugin(
        self, metadata_client, mock_proxy
    ):
        """get_plugin_config should return config for current plugin."""
        mock_proxy.call.return_value = {"config": {"key": "value"}}

        result = await metadata_client.get_plugin_config()

        mock_proxy.call.assert_called_once_with(
            "metadata.get_plugin_config",
            {"name": "current_plugin"},
        )
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_get_plugin_config_returns_none_for_other_plugin(
        self, metadata_client, mock_proxy
    ):
        """get_plugin_config should return None when querying other plugin's config."""
        # Mock proxy.call should not be called
        result = await metadata_client.get_plugin_config("other_plugin")

        # Should not call proxy for other plugin
        mock_proxy.call.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_current_plugin_returns_current_plugin_metadata(
        self, metadata_client, mock_proxy
    ):
        """get_current_plugin should return current plugin's metadata."""
        mock_proxy.call.return_value = {
            "plugin": {
                "name": "current_plugin",
                "display_name": "Current Plugin",
                "author": "test_author",
                "version": "1.0.0",
            }
        }

        result = await metadata_client.get_current_plugin()

        assert result is not None
        assert result.name == "current_plugin"

    @pytest.mark.asyncio
    async def test_get_plugin_uses_business_payload_only(
        self, metadata_client, mock_proxy
    ):
        """Metadata request payload should not expose runtime caller identity."""
        mock_proxy.call.return_value = {"plugin": None}

        await metadata_client.get_plugin("other_plugin")

        mock_proxy.call.assert_called_once_with(
            "metadata.get_plugin",
            {"name": "other_plugin"},
        )

    @pytest.mark.asyncio
    async def test_list_plugins_uses_empty_payload(self, metadata_client, mock_proxy):
        """list_plugins should not expose runtime caller identity in payload."""
        mock_proxy.call.return_value = {"plugins": []}

        await metadata_client.list_plugins()

        mock_proxy.call.assert_called_once_with(
            "metadata.list_plugins",
            {},
        )


class TestPluginMetadata:
    """Tests for PluginMetadata dataclass."""

    def test_from_dict_creates_metadata(self):
        """from_dict should create PluginMetadata from dict."""
        data = {
            "name": "test_plugin",
            "display_name": "Test Plugin",
            "desc": "A test plugin",
            "author": "test_author",
            "version": "1.0.0",
            "enabled": True,
        }

        result = PluginMetadata.from_dict(data)

        assert result.name == "test_plugin"
        assert result.display_name == "Test Plugin"
        assert result.description == "A test plugin"
        assert result.author == "test_author"
        assert result.version == "1.0.0"
        assert result.enabled is True

    def test_from_dict_uses_name_as_display_name_fallback(self):
        """from_dict should use name as display_name fallback."""
        data = {"name": "test_plugin"}

        result = PluginMetadata.from_dict(data)

        assert result.display_name == "test_plugin"

    def test_from_dict_uses_description_as_desc_fallback(self):
        """from_dict should use description field as fallback for desc."""
        data = {"name": "test", "description": "Test description"}

        result = PluginMetadata.from_dict(data)

        assert result.description == "Test description"

    def test_from_dict_defaults_version(self):
        """from_dict should default version to 0.0.0."""
        data = {"name": "test_plugin"}

        result = PluginMetadata.from_dict(data)

        assert result.version == "0.0.0"

    def test_from_dict_defaults_enabled(self):
        """from_dict should default enabled to True."""
        data = {"name": "test_plugin"}

        result = PluginMetadata.from_dict(data)

        assert result.enabled is True
