"""Provider lifecycle regressions without supplier network requests."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.provider import manager as module

CATEGORIES = [
    (
        module.ProviderType.CHAT_COMPLETION,
        module.Provider,
        "provider_insts",
        "curr_provider_inst",
    ),
    (
        module.ProviderType.SPEECH_TO_TEXT,
        module.STTProvider,
        "stt_provider_insts",
        "curr_stt_provider_inst",
    ),
    (
        module.ProviderType.TEXT_TO_SPEECH,
        module.TTSProvider,
        "tts_provider_insts",
        "curr_tts_provider_inst",
    ),
    (
        module.ProviderType.EMBEDDING,
        module.EmbeddingProvider,
        "embedding_provider_insts",
        None,
    ),
    (module.ProviderType.RERANK, module.RerankProvider, "rerank_provider_insts", None),
]


@pytest.fixture
def manager(monkeypatch):
    config = {"provider": [], "provider_settings": {}}
    acm = SimpleNamespace(confs={"default": config})
    manager = module.ProviderManager(acm, None, SimpleNamespace(default_persona=None))
    manager.llm_tools = SimpleNamespace(disable_mcp_server=AsyncMock())
    monkeypatch.setattr(module, "provider_cls_map", {})
    monkeypatch.setattr(module, "astrbot_config", config)
    return manager


@pytest.fixture(params=CATEGORIES, ids=lambda case: case[0].value)
def category(request):
    return request.param


def register_adapter(category, initialize_error=None):
    kind, base, _, _ = category
    created = []

    class Adapter(base):
        def __init__(self, config, settings):
            self.initialize = AsyncMock(side_effect=initialize_error)
            self.terminate = AsyncMock()
            self.meta = lambda: SimpleNamespace(id=config["id"])
            created.append(self)

    # Supplier methods are not used by lifecycle tests.
    Adapter.__abstractmethods__ = frozenset()
    module.provider_cls_map[kind.value] = SimpleNamespace(
        cls_type=Adapter, provider_type=kind, type=kind.value
    )
    return created


def config(category, provider_id="model"):
    return {"id": provider_id, "type": category[0].value, "enable": True}


@pytest.mark.asyncio
async def test_load_unload_and_reload_all_categories(manager, category):
    created = register_adapter(category)
    settings = config(category)
    module.astrbot_config["provider"] = [settings]
    collection = getattr(manager, category[2])
    await manager.load_provider(settings)
    created[0].initialize.assert_awaited_once()
    assert collection == [created[0]]
    await manager.reload(settings)
    assert collection == [created[1]]
    assert manager.inst_map["model"] is created[1]
    created[0].terminate.assert_awaited_once()
    await manager.terminate_provider("model")
    await manager.terminate_provider("model")
    assert not collection and not manager.inst_map
    created[1].terminate.assert_awaited_once()
    if category[3]:
        assert getattr(manager, category[3]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_failed_close_does_not_leave_registered_instances(
    manager, category, failure
):
    created = register_adapter(category)
    await manager.load_provider(config(category))
    created[0].terminate.side_effect = failure("close failed")
    with pytest.raises(failure):
        await manager.terminate_provider("model")
    assert not manager.inst_map and not getattr(manager, category[2])
    if category[3]:
        assert getattr(manager, category[3]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_failed_initialization_closes_unpublished_instance(
    manager, category, failure
):
    created = register_adapter(category, failure("initialization failed"))
    expected = asyncio.CancelledError if failure is asyncio.CancelledError else Exception
    with pytest.raises(expected):
        await manager.load_provider(config(category))
    assert not manager.inst_map and not getattr(manager, category[2])
    created[0].terminate.assert_awaited_once()


@pytest.mark.asyncio
async def test_configured_tts_is_selected_instead_of_chat_settings(manager):
    category = CATEGORIES[2]
    created = register_adapter(category)
    manager.provider_settings["provider_id"] = "first"
    manager.provider_tts_settings["provider_id"] = "preferred"
    await manager.load_provider(config(category, "first"))
    await manager.load_provider(config(category, "preferred"))
    assert manager.curr_tts_provider_inst is created[1]


@pytest.mark.asyncio
async def test_shutdown_closes_every_category_after_one_failure(manager):
    instances = []
    for category in CATEGORIES:
        created = register_adapter(category)
        await manager.load_provider(config(category, category[0].value))
        instances.extend(created)
    instances[0].terminate.side_effect = RuntimeError("close failed")
    await manager.terminate()
    for inst in instances:
        inst.terminate.assert_awaited_once()
    assert not manager.inst_map
    assert all(not getattr(manager, case[2]) for case in CATEGORIES)
    manager.llm_tools.disable_mcp_server.assert_awaited_once()
    await manager.terminate()
    for inst in instances:
        inst.terminate.assert_awaited_once()


@pytest.mark.asyncio
async def test_replacement_during_close_is_not_removed(manager):
    category = CATEGORIES[0]
    created = register_adapter(category)
    await manager.load_provider(config(category))
    started, release = asyncio.Event(), asyncio.Event()

    async def close():
        started.set()
        await release.wait()

    created[0].terminate.side_effect = close
    task = asyncio.create_task(manager.terminate_provider("model"))
    await started.wait()
    await manager.load_provider(config(category))
    release.set()
    await task
    assert manager.inst_map["model"] is created[1]
    assert manager.provider_insts == [created[1]]


def test_merged_config_does_not_share_nested_source_values(manager):
    source = {
        "id": "source", "key": ["original"], "custom_headers": {"x-test": "original"}
    }
    manager.provider_sources_config = [source]
    settings = {
        "id": "model", "provider_source_id": "source", "options": {"model": True}
    }
    first = manager.get_merged_provider_config(settings)
    second = manager.get_merged_provider_config(settings)
    first["key"].append("changed")
    first["custom_headers"]["x-test"] = "changed"
    first["options"]["model"] = False
    assert second["key"] == source["key"] == ["original"]
    assert second["custom_headers"] == source["custom_headers"]
    assert source["custom_headers"] == {"x-test": "original"}
    assert settings["options"] == {"model": True}
    assert second["id"] == "model"
    override = manager.get_merged_provider_config({**settings, "key": ["override"]})
    assert override["key"] == ["override"]
