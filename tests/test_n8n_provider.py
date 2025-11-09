"""Test n8n provider implementation"""

import pytest

from astrbot.core.provider.sources.n8n_source import ProviderN8n


class TestN8nProvider:
    """Test suite for n8n provider"""

    def test_provider_registration(self):
        """Test that n8n provider is properly registered"""
        from astrbot.core.provider.register import provider_cls_map

        assert "n8n" in provider_cls_map
        assert provider_cls_map["n8n"].type == "n8n"
        assert provider_cls_map["n8n"].cls_type == ProviderN8n

    def test_provider_initialization_missing_url(self):
        """Test that provider raises error when webhook URL is missing"""
        config = {
            "type": "n8n",
            "id": "test_n8n",
            "enable": True,
        }
        with pytest.raises(Exception, match="n8n Webhook URL 不能为空"):
            ProviderN8n(config, {}, None)

    def test_provider_initialization_invalid_method(self):
        """Test that provider raises error for invalid HTTP method"""
        config = {
            "type": "n8n",
            "id": "test_n8n",
            "enable": True,
            "n8n_webhook_url": "https://example.com/webhook",
            "n8n_http_method": "PUT",
        }
        with pytest.raises(Exception, match="n8n HTTP 方法必须是 GET 或 POST"):
            ProviderN8n(config, {}, None)

    def test_provider_initialization_success(self):
        """Test successful provider initialization"""
        config = {
            "type": "n8n",
            "id": "test_n8n",
            "enable": True,
            "n8n_webhook_url": "https://example.com/webhook",
            "n8n_http_method": "POST",
            "n8n_auth_header": "Authorization",
            "n8n_auth_value": "Bearer test_token",
            "n8n_output_key": "result",
            "n8n_input_key": "query",
            "timeout": 60,
        }
        provider = ProviderN8n(config, {}, None)

        assert provider.webhook_url == "https://example.com/webhook"
        assert provider.http_method == "POST"
        assert provider.auth_header == "Authorization"
        assert provider.auth_value == "Bearer test_token"
        assert provider.output_key == "result"
        assert provider.input_key == "query"
        assert provider.timeout == 60
        assert provider.model_name == "n8n"

    def test_provider_default_values(self):
        """Test provider initialization with default values"""
        config = {
            "type": "n8n",
            "id": "test_n8n",
            "enable": True,
            "n8n_webhook_url": "https://example.com/webhook",
        }
        provider = ProviderN8n(config, {}, None)

        assert provider.http_method == "POST"
        assert provider.auth_header == ""
        assert provider.auth_value == ""
        assert provider.output_key == "output"
        assert provider.input_key == "input"
        assert provider.session_id_key == "sessionId"
        assert provider.image_urls_key == "imageUrls"
        assert provider.streaming is False
        assert provider.timeout == 120

    @pytest.mark.asyncio
    async def test_get_models(self):
        """Test get_models method"""
        config = {
            "type": "n8n",
            "id": "test_n8n",
            "enable": True,
            "n8n_webhook_url": "https://example.com/webhook",
        }
        provider = ProviderN8n(config, {}, None)
        models = await provider.get_models()

        assert models == ["n8n"]

    @pytest.mark.asyncio
    async def test_get_current_key(self):
        """Test get_current_key method"""
        config = {
            "type": "n8n",
            "id": "test_n8n",
            "enable": True,
            "n8n_webhook_url": "https://example.com/webhook",
            "n8n_auth_value": "test_auth_value",
        }
        provider = ProviderN8n(config, {}, None)
        key = await provider.get_current_key()

        assert key == "test_auth_value"

    @pytest.mark.asyncio
    async def test_set_key_raises_exception(self):
        """Test that set_key raises an exception"""
        config = {
            "type": "n8n",
            "id": "test_n8n",
            "enable": True,
            "n8n_webhook_url": "https://example.com/webhook",
        }
        provider = ProviderN8n(config, {}, None)

        with pytest.raises(Exception, match="n8n 适配器不支持设置 API Key"):
            await provider.set_key("new_key")

    @pytest.mark.asyncio
    async def test_forget(self):
        """Test forget method"""
        config = {
            "type": "n8n",
            "id": "test_n8n",
            "enable": True,
            "n8n_webhook_url": "https://example.com/webhook",
        }
        provider = ProviderN8n(config, {}, None)
        result = await provider.forget("test_session")

        assert result is True

    @pytest.mark.asyncio
    async def test_terminate(self):
        """Test terminate method"""
        config = {
            "type": "n8n",
            "id": "test_n8n",
            "enable": True,
            "n8n_webhook_url": "https://example.com/webhook",
        }
        provider = ProviderN8n(config, {}, None)
        # Should not raise an exception
        await provider.terminate()

    @pytest.mark.asyncio
    async def test_parse_n8n_result_string(self):
        """Test parsing string result"""
        config = {
            "type": "n8n",
            "id": "test_n8n",
            "enable": True,
            "n8n_webhook_url": "https://example.com/webhook",
        }
        provider = ProviderN8n(config, {}, None)
        result = await provider.parse_n8n_result("Hello, world!")

        assert len(result.chain) == 1
        assert result.chain[0].type == "Plain"
        assert result.chain[0].text == "Hello, world!"

    @pytest.mark.asyncio
    async def test_parse_n8n_result_dict_with_output(self):
        """Test parsing dict result with output key"""
        config = {
            "type": "n8n",
            "id": "test_n8n",
            "enable": True,
            "n8n_webhook_url": "https://example.com/webhook",
            "n8n_output_key": "result",
        }
        provider = ProviderN8n(config, {}, None)
        result = await provider.parse_n8n_result({"result": "Test response"})

        assert len(result.chain) == 1
        assert result.chain[0].type == "Plain"
        assert result.chain[0].text == "Test response"

    @pytest.mark.asyncio
    async def test_parse_n8n_result_dict_without_output_key(self):
        """Test parsing dict result without configured output key"""
        config = {
            "type": "n8n",
            "id": "test_n8n",
            "enable": True,
            "n8n_webhook_url": "https://example.com/webhook",
            "n8n_output_key": "custom_output",
        }
        provider = ProviderN8n(config, {}, None)
        # Should fall back to common keys like 'data', 'result', etc.
        result = await provider.parse_n8n_result({"data": "Fallback response"})

        assert len(result.chain) == 1
        assert result.chain[0].type == "Plain"
        assert result.chain[0].text == "Fallback response"
