import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from astrbot.core.provider.sources.dashscope_stt_api_source import (
    ProviderDashScopeSTT,
    DashScopeAPIError,
    build_headers,
    build_api_url,
    normalize_timeout,
)
from astrbot.core.provider.entities import ProviderType
from astrbot.core.utils.media_utils import MediaResolver


@pytest.fixture
def mock_media_resolver():
    """Mock MediaResolver to return a fake base64 data URI."""
    with patch("astrbot.core.provider.sources.dashscope_stt_api_source.MediaResolver") as mock:
        instance = mock.return_value
        resolved_mock = MagicMock()
        resolved_mock.base64_data = "SUQzBAAAAA..."
        resolved_mock.mime_type = "audio/wav"
        resolved_mock.to_data_url.return_value = "data:audio/wav;base64,SUQzBAAAAA..."
        instance.to_base64_data = AsyncMock(return_value=resolved_mock)
        yield mock


@pytest.fixture
def provider_config():
    return {
        "id": "dashscope_stt_test",
        "api_key": "sk-test123",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3-asr-flash",
        "language": "zh",
        "enable_itn": True,
        "timeout": 30,
        "proxy": "",
    }


@pytest.fixture
def provider(provider_config):
    return ProviderDashScopeSTT(provider_config, {})


@pytest.mark.asyncio
async def test_build_headers():
    headers = build_headers("sk-abc")
    assert headers["Authorization"] == "Bearer sk-abc"
    assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_build_api_url():
    # With trailing slash
    assert build_api_url("https://api.example.com/v1/") == "https://api.example.com/v1/chat/completions"
    # Without trailing slash
    assert build_api_url("https://api.example.com/v1") == "https://api.example.com/v1/chat/completions"
    # Already ends with /chat/completions
    assert build_api_url("https://api.example.com/v1/chat/completions") == "https://api.example.com/v1/chat/completions"


@pytest.mark.asyncio
async def test_normalize_timeout():
    assert normalize_timeout(None) is None
    assert normalize_timeout("") is None
    assert normalize_timeout(30) == 30
    assert normalize_timeout("30") == 30


@pytest.mark.asyncio
async def test_get_text_success(provider, mock_media_resolver):
    """Test successful transcription."""
    # Mock HTTP response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "欢迎使用阿里云。"
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider, "_get_client") as mock_client:
        client = AsyncMock()
        client.post = AsyncMock(return_value=mock_response)
        mock_client.return_value = client

        result = await provider.get_text("https://example.com/audio.mp3")

        assert result == "欢迎使用阿里云。"
        # Verify correct payload was sent
        call_args = client.post.call_args
        assert call_args[0][0] == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        payload = call_args[1]["json"]
        assert payload["model"] == "qwen3-asr-flash"
        assert payload["messages"][0]["content"][0]["type"] == "input_audio"
        assert payload["messages"][0]["content"][0]["input_audio"]["data"].startswith("data:audio/wav;base64,")
        assert payload["asr_options"]["language"] == "zh"
        assert payload["asr_options"]["enable_itn"] is True
        assert payload["stream"] is False


@pytest.mark.asyncio
async def test_get_text_with_empty_language(provider_config, mock_media_resolver):
    """Test that language is omitted when not provided."""
    provider_config["language"] = ""
    provider = ProviderDashScopeSTT(provider_config, {})
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Hello world."}}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider, "_get_client") as mock_client:
        client = AsyncMock()
        client.post = AsyncMock(return_value=mock_response)
        mock_client.return_value = client

        await provider.get_text("https://example.com/audio.mp3")
        payload = client.post.call_args[1]["json"]
        assert "language" not in payload["asr_options"]


@pytest.mark.asyncio
async def test_get_text_http_error(provider, mock_media_resolver):
    """Test HTTP error handling (e.g., 400 Bad Request)."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = '{"error":{"message":"Invalid parameter"}}'
    mock_response.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError(
        "Bad Request", request=MagicMock(), response=mock_response
    ))

    with patch.object(provider, "_get_client") as mock_client:
        client = AsyncMock()
        client.post = AsyncMock(return_value=mock_response)
        mock_client.return_value = client

        with pytest.raises(DashScopeAPIError) as excinfo:
            await provider.get_text("https://example.com/audio.mp3")
        assert "DashScope STT request failed" in str(excinfo.value)
        assert "400" in str(excinfo.value)


@pytest.mark.asyncio
async def test_get_text_empty_response(provider, mock_media_resolver):
    """Test when API returns empty choices or content."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": []}
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider, "_get_client") as mock_client:
        client = AsyncMock()
        client.post = AsyncMock(return_value=mock_response)
        mock_client.return_value = client

        with pytest.raises(DashScopeAPIError) as excinfo:
            await provider.get_text("https://example.com/audio.mp3")
        assert "No choices" in str(excinfo.value)


@pytest.mark.asyncio
async def test_get_text_media_resolver_failure(provider):
    """Test when MediaResolver fails to convert audio."""
    with patch("astrbot.core.provider.sources.dashscope_stt_api_source.MediaResolver") as mock:
        instance = mock.return_value
        instance.to_base64_data = AsyncMock(return_value=None)

        with pytest.raises(ValueError) as excinfo:
            await provider.get_text("invalid_audio")
        assert "Failed to parse audio source" in str(excinfo.value)


@pytest.mark.asyncio
async def test_terminate(provider):
    """Test terminate closes the client."""
    client = AsyncMock()
    provider._client = client
    await provider.terminate()
    client.aclose.assert_called_once()
    assert provider._client is None


@pytest.mark.asyncio
async def test_terminate_no_client(provider):
    """Test terminate when client is None."""
    provider._client = None
    await provider.terminate()  # Should not raise
