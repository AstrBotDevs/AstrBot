"""Tests for runtime-owned LLM metadata catalog refresh."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.utils.llm_metadata import LLMMetadataCatalog


def _catalog_payload(model_id: str) -> dict:
    return {
        "openai": {
            "models": {
                model_id: {
                    "id": model_id,
                    "reasoning": True,
                    "tool_call": True,
                    "knowledge": "2024-01",
                    "release_date": "2024-01-01",
                    "modalities": {"input": ["text"], "output": ["text"]},
                    "open_weights": False,
                    "limit": {"context": 8, "output": 2},
                }
            }
        }
    }


def _mock_response(payload: object, *, status: int = 200) -> AsyncMock:
    response = AsyncMock()
    response.raise_for_status = MagicMock()
    if status >= 400:
        response.raise_for_status.side_effect = Exception("unused")
    response.json = AsyncMock(return_value=payload)
    response.__aenter__.return_value = response
    response.__aexit__.return_value = False
    return response


def _mock_session(responses: list[AsyncMock]) -> MagicMock:
    session = MagicMock()
    session.get = MagicMock(side_effect=responses)
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False
    return session


@pytest.mark.asyncio
async def test_refresh_uses_fallback_endpoint_after_primary_failure():
    catalog = LLMMetadataCatalog()
    primary = _mock_response([])
    fallback = _mock_response(_catalog_payload("fallback-model"))
    session = _mock_session([primary, fallback])

    with (
        patch(
            "astrbot.core.utils.proxy_route.create_aiohttp_session",
            return_value=session,
        ),
        patch(
            "astrbot.core.utils.proxy_route.current_aiohttp_proxy",
            return_value=None,
        ),
    ):
        await catalog.refresh()

    assert catalog.get("fallback-model") is not None
    assert catalog.get("fallback-model")["reasoning"] is True
    assert session.get.call_count == 2
    assert session.get.call_args_list[0].args[0] == "https://models.dev/api.json"
    assert (
        session.get.call_args_list[1].args[0] == "https://models.opencode.ai/api.json"
    )


@pytest.mark.asyncio
async def test_refresh_uses_fallback_endpoint_after_malformed_provider_payload():
    catalog = LLMMetadataCatalog()
    primary = _mock_response({"broken-provider": {"models": None}})
    fallback = _mock_response(_catalog_payload("fallback-model"))
    session = _mock_session([primary, fallback])

    with (
        patch(
            "astrbot.core.utils.proxy_route.create_aiohttp_session",
            return_value=session,
        ),
        patch(
            "astrbot.core.utils.proxy_route.current_aiohttp_proxy",
            return_value=None,
        ),
    ):
        await catalog.refresh()

    assert catalog.get("fallback-model") is not None
    assert session.get.call_count == 2


@pytest.mark.asyncio
async def test_refresh_keeps_catalog_empty_when_all_endpoints_fail():
    catalog = LLMMetadataCatalog()
    catalog.replace(
        {
            "stale-model": {
                "id": "stale-model",
                "reasoning": False,
                "tool_call": False,
                "knowledge": "none",
                "release_date": "",
                "modalities": {"input": ["text"], "output": ["text"]},
                "open_weights": False,
                "limit": {"context": 1, "output": 1},
            }
        }
    )
    session = _mock_session([_mock_response([]), _mock_response("not-an-object")])

    with (
        patch(
            "astrbot.core.utils.proxy_route.create_aiohttp_session",
            return_value=session,
        ),
        patch(
            "astrbot.core.utils.proxy_route.current_aiohttp_proxy",
            return_value=None,
        ),
    ):
        await catalog.refresh()

    assert catalog.get("stale-model") is not None
    assert catalog.get("fallback-model") is None
    assert session.get.call_count == 2
