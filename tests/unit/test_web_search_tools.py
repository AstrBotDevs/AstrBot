from types import SimpleNamespace

import pytest

import astrbot.core.tools.registry as tool_registry
import astrbot.core.tools.web_search_tools as web_search_tools
from astrbot.core.knowledge_base.parsers.url_parser import URLExtractor
from astrbot.core.tools.web_search_tools import ExaWebSearchTool


class _FakeResponse:
    def __init__(self, payload: dict):
        self.status = 200
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return ""


class _FakeSession:
    def __init__(self, payload: dict, captured: dict[str, object]):
        self._payload = payload
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url: str, **kwargs):
        self._captured["url"] = url
        self._captured["kwargs"] = kwargs
        return _FakeResponse(self._payload)


def _make_tool_context(provider_settings: dict) -> SimpleNamespace:
    cfg = {"provider_settings": provider_settings}
    return SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(get_config=lambda umo=None: cfg),
            event=SimpleNamespace(unified_msg_origin="test:private:session"),
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("search_type", "expected"),
    [
        ("deep-lite", "deep-lite"),
        ("deep-reasoning", "deep-reasoning"),
        ("instant", "instant"),
        ("unsupported", "auto"),
    ],
)
async def test_exa_web_search_tool_normalizes_search_type(
    monkeypatch: pytest.MonkeyPatch,
    search_type: str,
    expected: str,
):
    captured: dict[str, object] = {}

    async def fake_exa_search(provider_settings: dict, payload: dict, timeout: int):
        captured["provider_settings"] = provider_settings
        captured["payload"] = payload
        captured["timeout"] = timeout
        return []

    monkeypatch.setattr(web_search_tools, "_exa_search", fake_exa_search)

    tool = ExaWebSearchTool()
    result = await tool.call(
        _make_tool_context({"websearch_exa_key": ["test-key"]}),
        query="AstrBot",
        search_type=search_type,
    )

    assert result == "Error: Exa web searcher does not return any results."
    assert captured["payload"]["type"] == expected


def test_get_exa_base_url_rejects_endpoint_path():
    with pytest.raises(ValueError) as exc_info:
        web_search_tools._get_exa_base_url(
            {"websearch_exa_base_url": "https://api.exa.ai/search"}
        )

    assert str(exc_info.value) == (
        "Error: Exa API Base URL must be a base URL or proxy prefix, "
        "not a specific endpoint path. Received: 'https://api.exa.ai/search'."
    )


def test_url_extractor_rejects_endpoint_base_url():
    with pytest.raises(ValueError) as exc_info:
        URLExtractor(
            ["test-key"],
            tavily_base_url="https://api.tavily.com/extract",
        )

    assert str(exc_info.value) == (
        "Error: Tavily API Base URL must be a base URL or proxy prefix, "
        "not a specific endpoint path. Received: 'https://api.tavily.com/extract'."
    )


def test_bocha_builtin_config_statuses_are_registered():
    rule = tool_registry._BUILTIN_TOOL_CONFIG_RULES.get("web_search_bocha")

    assert rule is not None
    statuses = rule.evaluate(
        {
            "provider_settings": {
                "web_search": True,
                "websearch_provider": "bocha",
            }
        }
    )

    assert statuses == [
        {
            "key": "provider_settings.web_search",
            "operator": "equals",
            "expected": True,
            "actual": True,
            "matched": True,
            "message": None,
        },
        {
            "key": "provider_settings.websearch_provider",
            "operator": "equals",
            "expected": "bocha",
            "actual": "bocha",
            "matched": True,
            "message": None,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("helper_name", "payload"),
    [
        (
            "_exa_search",
            {"query": "AstrBot"},
        ),
        (
            "_exa_find_similar",
            {"url": "https://example.com"},
        ),
    ],
)
async def test_exa_helpers_preserve_favicon(
    monkeypatch: pytest.MonkeyPatch,
    helper_name: str,
    payload: dict,
):
    captured: dict[str, object] = {}
    response_payload = {
        "results": [
            {
                "title": "Example",
                "url": "https://example.com",
                "text": "Snippet",
                "favicon": "https://example.com/favicon.ico",
            }
        ]
    }

    async def fake_get(provider_settings: dict) -> str:
        return "test-key"

    monkeypatch.setattr(web_search_tools._EXA_KEY_ROTATOR, "get", fake_get)
    monkeypatch.setattr(
        web_search_tools.aiohttp,
        "ClientSession",
        lambda **kwargs: _FakeSession(response_payload, captured),
    )

    helper = getattr(web_search_tools, helper_name)
    results = await helper(
        {"websearch_exa_key": ["test-key"]},
        payload,
    )

    assert captured["url"]
    assert results[0].favicon == "https://example.com/favicon.ico"
