import pytest

import astrbot.core.utils.llm_metadata as llm_metadata

METADATA = {
    "test-provider": {
        "models": {
            "test-model": {
                "id": "test-model",
                "limit": {"context": 4096, "output": 1024},
            }
        }
    }
}


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Response:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    async def json(self):
        return self.data


class _Session:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requested_urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def get(self, url):
        self.requested_urls.append(url)
        return _AsyncContext(self.outcomes.pop(0))


@pytest.mark.asyncio
async def test_update_llm_metadata_uses_primary_url(monkeypatch):
    session = _Session([_Response(METADATA)])
    monkeypatch.setattr(
        llm_metadata.aiohttp,
        "ClientSession",
        lambda **_kwargs: session,
    )
    monkeypatch.setattr(llm_metadata, "build_tls_connector", lambda: None)
    llm_metadata.LLM_METADATAS.clear()

    await llm_metadata.update_llm_metadata()

    assert session.requested_urls == [llm_metadata.LLM_METADATA_URLS[0]]
    assert llm_metadata.LLM_METADATAS["test-model"]["limit"]["context"] == 4096


@pytest.mark.asyncio
async def test_update_llm_metadata_falls_back_to_opencode_domain(monkeypatch):
    session = _Session([ConnectionError("primary unavailable"), _Response(METADATA)])
    monkeypatch.setattr(
        llm_metadata.aiohttp,
        "ClientSession",
        lambda **_kwargs: session,
    )
    monkeypatch.setattr(llm_metadata, "build_tls_connector", lambda: None)
    llm_metadata.LLM_METADATAS.clear()

    await llm_metadata.update_llm_metadata()

    assert session.requested_urls == list(llm_metadata.LLM_METADATA_URLS)
    assert "test-model" in llm_metadata.LLM_METADATAS
