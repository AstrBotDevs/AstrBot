import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.provider.decision import DecisionService
from astrbot.core.provider.entities import (
    DecisionBooleanQuestion,
    ProviderMetaData,
    ProviderType,
)
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.provider import DecisionProvider
from astrbot.core.provider.register import provider_cls_map
from astrbot.dashboard.services.config_service import ProviderConfigService


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "http", "initialize", "cancel"])
async def test_decision_source_discovery_closes_temporary_provider(
    monkeypatch, failure
):
    from astrbot.core.utils.llm_metadata import LLM_METADATAS

    monkeypatch.setitem(
        LLM_METADATAS, "unknown-a", {"limit": {"context": 128000}, "tool_call": True}
    )
    instances = []

    class DirectoryDecisionProvider(DecisionProvider):
        def __init__(self, config, settings):
            super().__init__(config, settings)
            instances.append(self)
            self.client = httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        503 if failure == "http" else 200,
                        json={"data": [{"id": "unknown-a"}, {"id": "unknown-b"}]},
                    )
                )
            )

        async def initialize(self):
            if failure == "initialize":
                raise RuntimeError("initialization failed")
            if failure == "cancel":
                raise asyncio.CancelledError

        async def get_models(self):
            response = await self.client.get("https://decision.test/prefix/v1/models")
            response.raise_for_status()
            return [item["id"] for item in response.json()["data"]]

        async def ask(self, questions, state=None, *, request_max_retries=0):
            return {}

        async def terminate(self):
            await self.client.aclose()

    monkeypatch.setitem(
        provider_cls_map,
        "test_decision_directory",
        ProviderMetaData(
            id="directory",
            model=None,
            type="test_decision_directory",
            desc="Test directory",
            provider_type=ProviderType.DECISION,
            cls_type=DirectoryDecisionProvider,
        ),
    )
    source = {"id": "directory", "type": "test_decision_directory"}
    manager = SimpleNamespace(dynamic_import_provider=lambda _: None, inst_map={})
    service = ProviderConfigService(
        SimpleNamespace(
            astrbot_config={"provider_sources": [source]},
            provider_manager=manager,
        )
    )
    if failure:
        expected = {
            "http": httpx.HTTPStatusError,
            "initialize": RuntimeError,
            "cancel": asyncio.CancelledError,
        }[failure]
        with pytest.raises(expected):
            await service.list_provider_source_models("directory")
    else:
        result = await service.list_provider_source_models("directory")
        assert result["models"] == ["unknown-a", "unknown-b"]
        assert result["model_metadata"] == {}
    assert len(instances) == 1
    assert instances[0].client.is_closed

    if not failure:
        instance = DirectoryDecisionProvider(source, {})
        manager.inst_map["decision-instance"] = instance
        try:
            result = await service.list_provider_models("decision-instance")
            assert result["models"] == ["unknown-a", "unknown-b"]
            assert result["model_metadata"] == {}
            assert not instance.client.is_closed
        finally:
            await instance.terminate()


@pytest.mark.asyncio
async def test_model_discovery_rejects_other_capabilities():
    service = ProviderConfigService(
        SimpleNamespace(
            astrbot_config={},
            provider_manager=SimpleNamespace(inst_map={"stt": MagicMock()}),
        )
    )
    with pytest.raises(ValueError, match="stt"):
        await service.list_provider_models("stt")


@pytest.mark.asyncio
async def test_native_decision_source_multiple_models_and_service_chain(monkeypatch):
    from astrbot.core.provider.sources.openai_decision_source import (
        OpenAIDecisionProvider,
    )

    requests = []
    clients = []
    original_client = httpx.AsyncClient

    def handler(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer test-key"
        assert request.headers["x-gateway"] == "configured"
        if request.method == "GET":
            assert request.url.path == "/gateway/v1/models"
            return httpx.Response(
                200, json={"data": [{"id": "unknown-a"}, {"id": "unknown-b"}]}
            )
        assert request.url.path == "/gateway/v1/decisions"
        body = json.loads(request.content)
        assert body["model"] == "unknown-b"
        return httpx.Response(
            200,
            json={
                "model": "unknown-b",
                "answers": [{"name": "ok", "type": "predicate", "probability": 0.7}],
                "usage": {"input_tokens": 4, "output_tokens": 0, "total_tokens": 4},
            },
        )

    def client_factory(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        client = original_client(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)

    class MemoryConfig(dict):
        def save_config(self, config=None):
            if config is not None:
                self.update(config)

    config = MemoryConfig(copy.deepcopy(DEFAULT_CONFIG))
    config.update(provider=[], provider_sources=[], provider_settings={})
    monkeypatch.setattr("astrbot.core.provider.manager.astrbot_config", config)
    acm = MagicMock()
    acm.confs = {"default": config}
    acm.default_conf = config
    acm.get_conf.return_value = config
    persona = SimpleNamespace(default_persona="")
    manager = ProviderManager(acm, MagicMock(), persona)
    service = ProviderConfigService(
        SimpleNamespace(astrbot_config=config, provider_manager=manager)
    )
    await service.upsert_provider_source(
        "native",
        {
            "id": "native",
            "type": "openai_decision",
            "provider_type": "decision",
            "enable": True,
            "api_base": "https://decisions.test/gateway/v1",
            "key": ["test-key"],
            "custom_headers": {"X-Gateway": "configured"},
        },
    )
    try:
        directory = await service.list_provider_source_models("native")
        assert directory["models"] == ["unknown-a", "unknown-b"]
        assert clients[0].is_closed
        for model in directory["models"]:
            await service.create_provider(
                {"id": f"native/{model}", "enable": True, "model": model},
                source_id="native",
            )
        assert len(manager.decision_provider_insts) == 2
        assert manager.provider_insts == []
        assert all(
            isinstance(p, OpenAIDecisionProvider)
            for p in manager.decision_provider_insts
        )
        assert {
            p["id"] for p in service.list_providers(capability="decision")["providers"]
        } == {
            "native/unknown-a",
            "native/unknown-b",
        }
        assert service.list_providers(capability="chat")["providers"] == []
        instance_directory = await service.list_provider_models("native/unknown-b")
        assert instance_directory["models"] == directory["models"]
        result = await DecisionService(manager).ask(
            {"ok": DecisionBooleanQuestion("Is the task ready?")},
            {"ready": True},
            provider_id="native/unknown-b",
        )
        assert result["ok"].probability == 0.7
        assert result.model == "unknown-b"
        assert result.usage.input_tokens == 4
        assert result.usage.output_tokens == 0
        assert [request.method for request in requests] == ["GET", "GET", "POST"]
    finally:
        for provider in manager.decision_provider_insts:
            await provider.terminate()
    assert all(client.is_closed for client in clients)
