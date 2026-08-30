import asyncio
import contextlib
import copy
import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from astrbot.core.provider.catalog import ProviderAdapterDescriptor, ProviderCatalog
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.provider import (
    EmbeddingProvider,
    Provider,
    RerankProvider,
    STTProvider,
    TTSProvider,
)
from astrbot.core.tools.function_tool_manager import FunctionToolManager

pytestmark = pytest.mark.provider

_original_persona_mgr = sys.modules.get("astrbot.core.persona_mgr")
_stub_persona_mgr = types.ModuleType("astrbot.core.persona_mgr")


class PersonaManager: ...


setattr(_stub_persona_mgr, "PersonaManager", PersonaManager)
sys.modules["astrbot.core.persona_mgr"] = _stub_persona_mgr

provider_manager_module = importlib.import_module("astrbot.core.provider.manager")
ProviderManager = provider_manager_module.ProviderManager

if _original_persona_mgr is not None:
    sys.modules["astrbot.core.persona_mgr"] = _original_persona_mgr
else:
    sys.modules.pop("astrbot.core.persona_mgr", None)


class DummyChatProvider(Provider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.initialized = False
        self.set_model(provider_config.get("model", "dummy-model"))

    def get_current_key(self) -> str:
        return self.provider_config.get("key", [""])[0]

    def set_key(self, key: str) -> None:
        self.provider_config["key"] = [key]

    async def get_models(self) -> list[str]:
        return [self.get_model()]

    async def text_chat(self, **kwargs):
        raise NotImplementedError

    async def initialize(self) -> None:
        self.initialized = True


class DummySTTProvider(STTProvider):
    async def get_text(self, audio_url: str) -> str:
        return audio_url


class DummyTTSProvider(TTSProvider):
    async def get_audio(self, text: str) -> str:
        return text


class DummyEmbeddingProvider(EmbeddingProvider):
    async def get_embedding(self, text: str) -> list[float]:
        return [0.1]

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        return [[0.1] for _ in text]

    def get_dim(self) -> int:
        return 1


class DummyRerankProvider(RerankProvider):
    async def rerank(self, query: str, documents: list[str], top_n: int | None = None):
        return []


class _ConfigWithAsyncSave(dict):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.save_config_async = AsyncMock(return_value=True)


def _build_manager(config: dict | None = None) -> ProviderManager:
    default_config = config or {
        "provider": [],
        "provider_sources": [],
        "provider_settings": {},
        "agent_runner": {
            "runner_type": "local",
            "config": {"model": {"provider_id": "default-provider"}},
        },
        "provider_stt_settings": {"enable": False, "provider_id": None},
        "provider_tts_settings": {"enable": False, "provider_id": None},
    }
    default_conf = _ConfigWithAsyncSave(default_config)
    acm = SimpleNamespace(
        confs={"default": default_conf},
        get_conf=lambda umo=None: default_conf,
        default_conf=default_conf,
    )
    persona_mgr = SimpleNamespace(default_persona="default")
    return ProviderManager(
        acm,
        persona_mgr=persona_mgr,
        preferences=AsyncMock(),
        catalog=ProviderCatalog(),
        tools=FunctionToolManager(),
    )


def _register_provider(
    manager: ProviderManager,
    adapter_type: str,
    provider_class: type,
    provider_type: ProviderType,
) -> None:
    manager.catalog.register(
        ProviderAdapterDescriptor.create(
            type=adapter_type,
            desc="test adapter",
            provider_type=provider_type,
            default_config_tmpl=None,
            provider_display_name=None,
        ),
        provider_class,
    )


def test_register_provider_change_hook_deduplicates_and_notify_swallows_failures(
    monkeypatch,
):
    manager = _build_manager()
    warning = MagicMock()
    hook_ok = MagicMock()
    hook_fail = MagicMock(side_effect=RuntimeError("hook failed"))

    manager.register_provider_change_hook(hook_ok)
    manager.register_provider_change_hook(hook_ok)
    manager.register_provider_change_hook(hook_fail)

    monkeypatch.setattr(provider_manager_module.logger, "warning", warning)

    manager._notify_provider_changed(
        "provider-1",
        ProviderType.CHAT_COMPLETION,
        "umo-1",
    )

    assert manager._provider_change_hooks == [hook_ok, hook_fail]
    hook_ok.assert_called_once_with(
        "provider-1",
        ProviderType.CHAT_COMPLETION,
        "umo-1",
    )
    hook_fail.assert_called_once_with(
        "provider-1",
        ProviderType.CHAT_COMPLETION,
        "umo-1",
    )
    warning.assert_called_once()
    assert "调用 provider 变更钩子失败" in warning.call_args.args[0]


@pytest.mark.asyncio
async def test_load_session_provider_overrides_ignores_invalid_records(monkeypatch):
    manager = _build_manager()
    monkeypatch.setattr(
        manager.preferences,
        "session_get",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    key="provider_perf_chat_completion",
                    value={"val": "provider-a"},
                    scope_id="session-1",
                ),
                SimpleNamespace(
                    key="provider_perf_unknown",
                    value={"val": "provider-b"},
                    scope_id="session-2",
                ),
                SimpleNamespace(
                    key="provider_perf_chat_completion",
                    value={"val": ""},
                    scope_id="session-3",
                ),
                SimpleNamespace(
                    key="other_key",
                    value={"val": "provider-c"},
                    scope_id="session-4",
                ),
            ],
        ),
    )

    await manager._load_session_provider_overrides()

    assert manager._session_provider_overrides == {
        "session-1": {ProviderType.CHAT_COMPLETION: "provider-a"},
    }


def test_get_using_provider_prefers_override_and_falls_back_to_default():
    manager = _build_manager()
    default_provider = DummyChatProvider(
        {
            "id": "default-provider",
            "type": "fake_chat_default",
            "enable": True,
        },
        manager.provider_settings,
    )
    session_provider = DummyChatProvider(
        {
            "id": "session-provider",
            "type": "fake_chat_session",
            "enable": True,
        },
        manager.provider_settings,
    )
    manager.provider_insts = [default_provider]
    manager.inst_map = {
        "default-provider": default_provider,
        "session-provider": session_provider,
    }
    manager._session_provider_overrides = {
        "umo-ok": {ProviderType.CHAT_COMPLETION: "session-provider"},
        "umo-missing": {ProviderType.CHAT_COMPLETION: "missing-provider"},
    }

    assert (
        manager.get_using_provider(ProviderType.CHAT_COMPLETION, "umo-ok")
        is session_provider
    )
    assert (
        manager.get_using_provider(ProviderType.CHAT_COMPLETION, "umo-missing")
        is default_provider
    )
    assert manager.get_using_provider(ProviderType.SPEECH_TO_TEXT) is None


@pytest.mark.asyncio
async def test_set_provider_session_override_persists_and_notifies(monkeypatch):
    manager = _build_manager()
    provider = DummyChatProvider(
        {
            "id": "session-provider",
            "type": "fake_chat_session_override",
            "enable": True,
        },
        manager.provider_settings,
    )
    manager.inst_map["session-provider"] = provider
    hook = MagicMock()
    manager.register_provider_change_hook(hook)

    monkeypatch.setattr(manager.preferences, "session_put", AsyncMock())

    await manager.set_provider(
        "session-provider",
        ProviderType.CHAT_COMPLETION,
        umo="umo-1",
    )

    assert manager._session_provider_overrides == {
        "umo-1": {ProviderType.CHAT_COMPLETION: "session-provider"},
    }
    manager.preferences.session_put.assert_awaited_once_with(
        "umo-1",
        "provider_perf_chat_completion",
        "session-provider",
    )
    hook.assert_called_once_with(
        "session-provider",
        ProviderType.CHAT_COMPLETION,
        "umo-1",
    )


@pytest.mark.asyncio
async def test_set_provider_raises_for_unknown_provider_id():
    manager = _build_manager()

    with pytest.raises(ValueError, match="提供商 missing-provider 不存在"):
        await manager.set_provider(
            "missing-provider",
            ProviderType.CHAT_COMPLETION,
        )


@pytest.mark.asyncio
async def test_set_provider_updates_global_defaults_for_chat_stt_and_tts(monkeypatch):
    manager = _build_manager()
    chat_provider = DummyChatProvider(
        {"id": "chat-global", "type": "fake_chat_global", "enable": True},
        manager.provider_settings,
    )
    stt_provider = DummySTTProvider(
        {"id": "stt-global", "type": "fake_stt_global", "enable": True},
        manager.provider_settings,
    )
    tts_provider = DummyTTSProvider(
        {"id": "tts-global", "type": "fake_tts_global", "enable": True},
        manager.provider_settings,
    )
    manager.inst_map = {
        "chat-global": chat_provider,
        "stt-global": stt_provider,
        "tts-global": tts_provider,
    }
    hook = MagicMock()
    manager.register_provider_change_hook(hook)
    monkeypatch.setattr(manager.preferences, "put_async", AsyncMock())

    await manager.set_provider("chat-global", ProviderType.CHAT_COMPLETION)
    await manager.set_provider("stt-global", ProviderType.SPEECH_TO_TEXT)
    await manager.set_provider("tts-global", ProviderType.TEXT_TO_SPEECH)

    assert (
        manager.acm.default_conf["agent_runner"]["config"]["model"]["provider_id"]
        == "chat-global"
    )
    assert (
        manager.acm.default_conf["provider_stt_settings"]["provider_id"] == "stt-global"
    )
    assert (
        manager.acm.default_conf["provider_tts_settings"]["provider_id"] == "tts-global"
    )
    manager.preferences.put_async.assert_not_awaited()
    assert manager.acm.default_conf.save_config_async.await_count == 3
    assert hook.call_args_list == [
        call("chat-global", ProviderType.CHAT_COMPLETION, None),
        call("stt-global", ProviderType.SPEECH_TO_TEXT, None),
        call("tts-global", ProviderType.TEXT_TO_SPEECH, None),
    ]


@pytest.mark.asyncio
async def test_set_provider_rolls_back_global_selection_when_persistence_fails():
    manager = _build_manager()
    provider = DummyChatProvider(
        {"id": "chat-new", "type": "fake_chat_new", "enable": True},
        manager.provider_settings,
    )
    manager.inst_map["chat-new"] = provider
    previous_config = copy.deepcopy(dict(manager.acm.default_conf))
    hook = MagicMock()
    manager.register_provider_change_hook(hook)
    manager.acm.default_conf.save_config_async.side_effect = OSError("disk unavailable")

    with pytest.raises(OSError, match="disk unavailable"):
        await manager.set_provider("chat-new", ProviderType.CHAT_COMPLETION)

    assert dict(manager.acm.default_conf) == previous_config
    hook.assert_not_called()


@pytest.mark.asyncio
async def test_set_provider_does_not_roll_back_a_newer_global_selection():
    manager = _build_manager()
    provider = DummyChatProvider(
        {"id": "chat-new", "type": "fake_chat_new", "enable": True},
        manager.provider_settings,
    )
    manager.inst_map["chat-new"] = provider
    hook = MagicMock()
    manager.register_provider_change_hook(hook)

    async def superseded_by_newer_selection() -> bool:
        manager.acm.default_conf["agent_runner"]["config"]["model"]["provider_id"] = (
            "chat-newer"
        )
        return False

    manager.acm.default_conf.save_config_async.side_effect = (
        superseded_by_newer_selection
    )

    with pytest.raises(RuntimeError, match="superseded"):
        await manager.set_provider("chat-new", ProviderType.CHAT_COMPLETION)

    assert (
        manager.acm.default_conf["agent_runner"]["config"]["model"]["provider_id"]
        == "chat-newer"
    )
    hook.assert_not_called()


@pytest.mark.asyncio
async def test_set_provider_keeps_session_override_unpublished_when_persistence_fails():
    manager = _build_manager()
    provider = DummyChatProvider(
        {"id": "chat-session", "type": "fake_chat_session", "enable": True},
        manager.provider_settings,
    )
    manager.inst_map["chat-session"] = provider
    hook = MagicMock()
    manager.register_provider_change_hook(hook)
    manager.preferences.session_put.side_effect = OSError("preferences unavailable")

    with pytest.raises(OSError, match="preferences unavailable"):
        await manager.set_provider(
            "chat-session",
            ProviderType.CHAT_COMPLETION,
            umo="umo-1",
        )

    assert manager._session_provider_overrides == {}
    hook.assert_not_called()


def test_resolve_env_key_list_expands_env_references(monkeypatch):
    manager = _build_manager()
    monkeypatch.setenv("ASTRBOT_PROVIDER_KEY", "resolved-key")
    monkeypatch.delenv("ASTRBOT_MISSING_KEY", raising=False)

    resolved = manager._resolve_env_key_list(
        {
            "id": "provider-1",
            "key": ["$ASTRBOT_PROVIDER_KEY", "${ASTRBOT_MISSING_KEY}", "plain-key"],
        },
    )

    assert resolved["key"] == ["resolved-key", "", "plain-key"]


def test_dynamic_import_provider_unknown_type_returns_without_error():
    manager = _build_manager()

    manager.dynamic_import_provider("unknown_provider_type")


def test_dynamic_import_provider_registers_both_openai_protocols():
    manager = _build_manager()

    manager.dynamic_import_provider("openai_chat_completions")
    manager.dynamic_import_provider("openai_responses")

    assert manager.catalog.get("openai_chat_completions").cls_type.__name__ == (
        "ProviderOpenAIChatCompletions"
    )
    assert manager.catalog.get("openai_responses").cls_type.__name__ == (
        "ProviderOpenAIResponses"
    )


def test_get_provider_config_by_id_can_merge_provider_source():
    manager = _build_manager(
        {
            "provider": [
                {
                    "id": "chat-1",
                    "type": "fake_chat",
                    "provider_source_id": "shared-source",
                    "enable": True,
                    "base_url": "https://provider.test",
                }
            ],
            "provider_sources": [
                {
                    "id": "shared-source",
                    "key": ["source-key"],
                    "timeout": 30,
                }
            ],
            "provider_settings": {},
            "agent_runner": {
                "runner_type": "local",
                "config": {"model": {"provider_id": "chat-1"}},
            },
            "provider_stt_settings": {"enable": False, "provider_id": None},
            "provider_tts_settings": {"enable": False, "provider_id": None},
        }
    )

    merged = manager.get_provider_config_by_id("chat-1", merged=True)
    raw = manager.get_provider_config_by_id("chat-1", merged=False)

    assert raw == {
        "id": "chat-1",
        "type": "fake_chat",
        "provider_source_id": "shared-source",
        "enable": True,
        "base_url": "https://provider.test",
    }
    assert merged == {
        "id": "chat-1",
        "type": "fake_chat",
        "provider_source_id": "shared-source",
        "enable": True,
        "base_url": "https://provider.test",
        "key": ["source-key"],
        "timeout": 30,
    }
    assert manager.get_provider_config_by_id("missing") is None


def test_get_using_provider_warns_when_configured_provider_is_missing(monkeypatch):
    manager = _build_manager(
        {
            "provider": [],
            "provider_sources": [],
            "provider_settings": {},
            "agent_runner": {
                "runner_type": "local",
                "config": {"model": {"provider_id": "missing-chat"}},
            },
            "provider_stt_settings": {"enable": True, "provider_id": "missing-stt"},
            "provider_tts_settings": {"enable": True, "provider_id": "missing-tts"},
        }
    )
    warning = MagicMock()
    monkeypatch.setattr(provider_manager_module.logger, "warning", warning)

    assert manager.get_using_provider(ProviderType.CHAT_COMPLETION) is None
    assert manager.get_using_provider(ProviderType.SPEECH_TO_TEXT) is None
    assert manager.get_using_provider(ProviderType.TEXT_TO_SPEECH) is None
    assert warning.call_count == 3


def test_get_using_provider_raises_for_unknown_provider_type():
    manager = _build_manager()

    with pytest.raises(ValueError, match="Unknown provider type"):
        manager.get_using_provider("bad-type")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_load_provider_merges_source_initializes_and_selects_default(
    monkeypatch,
):
    manager = _build_manager(
        {
            "provider": [],
            "provider_sources": [
                {
                    "id": "shared-source",
                    "key": ["source-key"],
                    "base_url": "https://example.test",
                },
            ],
            "provider_settings": {},
            "agent_runner": {
                "runner_type": "local",
                "config": {"model": {"provider_id": "chat-1"}},
            },
            "provider_stt_settings": {"enable": False, "provider_id": None},
            "provider_tts_settings": {"enable": False, "provider_id": None},
        },
    )
    monkeypatch.setenv("ASTRBOT_CHAT_KEY", "chat-key")
    monkeypatch.setattr(manager, "dynamic_import_provider", lambda provider_type: None)
    _register_provider(
        manager,
        "fake_chat_load",
        DummyChatProvider,
        ProviderType.CHAT_COMPLETION,
    )

    await manager.load_provider(
        {
            "id": "chat-1",
            "type": "fake_chat_load",
            "provider_type": "chat_completion",
            "provider_source_id": "shared-source",
            "key": ["$ASTRBOT_CHAT_KEY"],
            "enable": True,
            "model": "dummy-chat-model",
        },
    )

    inst = manager.inst_map["chat-1"]
    assert isinstance(inst, DummyChatProvider)
    assert inst.initialized is True
    assert inst.provider_config["id"] == "chat-1"
    assert inst.provider_config["base_url"] == "https://example.test"
    assert inst.provider_config["key"] == ["chat-key"]
    assert manager.get_using_provider(ProviderType.CHAT_COMPLETION) is inst


@pytest.mark.asyncio
async def test_load_provider_selects_default_tts_from_tts_settings(monkeypatch):
    manager = _build_manager(
        {
            "provider": [],
            "provider_sources": [],
            "provider_settings": {},
            "agent_runner": {
                "runner_type": "local",
                "config": {"model": {"provider_id": "chat-default"}},
            },
            "provider_stt_settings": {"enable": False, "provider_id": None},
            "provider_tts_settings": {"enable": True, "provider_id": "tts-1"},
        },
    )
    monkeypatch.setattr(manager, "dynamic_import_provider", lambda provider_type: None)
    _register_provider(
        manager,
        "fake_tts_load",
        DummyTTSProvider,
        ProviderType.TEXT_TO_SPEECH,
    )

    await manager.load_provider(
        {
            "id": "tts-1",
            "type": "fake_tts_load",
            "provider_type": "text_to_speech",
            "enable": True,
        },
    )

    inst = manager.inst_map["tts-1"]
    assert isinstance(inst, DummyTTSProvider)
    assert manager.get_using_provider(ProviderType.TEXT_TO_SPEECH) is inst


@pytest.mark.asyncio
async def test_load_provider_replaces_existing_current_tts_when_configured_default_matches(
    monkeypatch,
):
    manager = _build_manager(
        {
            "provider": [],
            "provider_sources": [],
            "provider_settings": {},
            "agent_runner": {
                "runner_type": "local",
                "config": {"model": {"provider_id": "chat-default"}},
            },
            "provider_stt_settings": {"enable": False, "provider_id": None},
            "provider_tts_settings": {"enable": True, "provider_id": "tts-target"},
        },
    )
    existing = DummyTTSProvider(
        {"id": "tts-existing", "type": "fake_tts_existing", "enable": True},
        manager.provider_settings,
    )
    manager.tts_provider_insts = [existing]

    monkeypatch.setattr(manager, "dynamic_import_provider", lambda provider_type: None)
    _register_provider(
        manager,
        "fake_tts_target",
        DummyTTSProvider,
        ProviderType.TEXT_TO_SPEECH,
    )

    await manager.load_provider(
        {
            "id": "tts-target",
            "type": "fake_tts_target",
            "provider_type": "text_to_speech",
            "enable": True,
        },
    )

    assert (
        manager.get_using_provider(ProviderType.TEXT_TO_SPEECH)
        is manager.inst_map["tts-target"]
    )


@pytest.mark.asyncio
async def test_load_provider_skips_disabled_and_agent_runner_records(monkeypatch):
    manager = _build_manager()
    dynamic_import = MagicMock()
    monkeypatch.setattr(manager, "dynamic_import_provider", dynamic_import)

    await manager.load_provider(
        {
            "id": "disabled-chat",
            "type": "fake_chat_disabled",
            "provider_type": "chat_completion",
            "key": [],
            "enable": False,
        },
    )
    await manager.load_provider(
        {
            "id": "runner-only",
            "type": "fake_runner",
            "provider_type": "agent_runner",
            "enable": True,
        },
    )

    dynamic_import.assert_not_called()
    assert manager.inst_map == {}


@pytest.mark.asyncio
async def test_load_provider_returns_cleanly_when_provider_metadata_is_missing(
    monkeypatch,
):
    manager = _build_manager()
    monkeypatch.setattr(manager, "dynamic_import_provider", lambda provider_type: None)

    await manager.load_provider(
        {
            "id": "missing-meta",
            "type": "fake_missing_meta",
            "provider_type": "chat_completion",
            "key": [],
            "enable": True,
        },
    )

    assert manager.inst_map == {}


@pytest.mark.asyncio
async def test_load_provider_returns_cleanly_on_import_error(monkeypatch):
    manager = _build_manager()
    monkeypatch.setattr(
        manager,
        "dynamic_import_provider",
        MagicMock(side_effect=ModuleNotFoundError("missing dependency")),
    )

    await manager.load_provider(
        {
            "id": "broken-provider",
            "type": "fake_broken",
            "provider_type": "chat_completion",
            "key": [],
            "enable": True,
        },
    )

    assert manager.inst_map == {}


@pytest.mark.asyncio
async def test_load_provider_returns_cleanly_on_unknown_dynamic_import_failure(
    monkeypatch,
):
    manager = _build_manager()
    monkeypatch.setattr(
        manager,
        "dynamic_import_provider",
        MagicMock(side_effect=RuntimeError("unexpected import failure")),
    )

    await manager.load_provider(
        {
            "id": "broken-provider",
            "type": "fake_broken",
            "provider_type": "chat_completion",
            "key": [],
            "enable": True,
        },
    )

    assert manager.inst_map == {}


@pytest.mark.asyncio
async def test_load_provider_wraps_type_mismatch(monkeypatch):
    manager = _build_manager()
    monkeypatch.setattr(manager, "dynamic_import_provider", lambda provider_type: None)
    _register_provider(
        manager,
        "fake_type_mismatch",
        DummySTTProvider,
        ProviderType.CHAT_COMPLETION,
    )

    with pytest.raises(
        Exception, match="实例化 fake_type_mismatch\\(mismatch\\) 提供商适配器失败"
    ):
        await manager.load_provider(
            {
                "id": "mismatch",
                "type": "fake_type_mismatch",
                "provider_type": "chat_completion",
                "key": [],
                "enable": True,
            },
        )

    assert "mismatch" not in manager.inst_map


@pytest.mark.asyncio
async def test_clear_provider_overrides_remove_cached_and_persisted_entries(
    monkeypatch,
):
    manager = _build_manager()
    manager._session_provider_overrides = {
        "umo-1": {
            ProviderType.CHAT_COMPLETION: "chat-1",
            ProviderType.TEXT_TO_SPEECH: "tts-1",
        }
    }
    monkeypatch.setattr(manager.preferences, "session_remove", AsyncMock())

    await manager.clear_provider_override("umo-1", ProviderType.CHAT_COMPLETION)

    assert manager._session_provider_overrides == {
        "umo-1": {ProviderType.TEXT_TO_SPEECH: "tts-1"}
    }
    manager.preferences.session_remove.assert_awaited_once_with(
        "umo-1",
        "provider_perf_chat_completion",
    )

    await manager.clear_all_provider_overrides("umo-1")

    assert manager._session_provider_overrides == {}
    assert manager.preferences.session_remove.await_args_list[1:] == [
        (("umo-1", "provider_perf_text_to_speech"), {})
    ]


@pytest.mark.asyncio
async def test_initialize_selects_defaults_and_starts_mcp_init(monkeypatch):
    manager = _build_manager(
        {
            "provider": [
                {"id": "chat-a", "enable": True},
                {"id": "chat-b", "enable": True},
            ],
            "provider_sources": [],
            "provider_settings": {},
            "agent_runner": {
                "runner_type": "local",
                "config": {"model": {"provider_id": "chat-a"}},
            },
            "provider_stt_settings": {"enable": True, "provider_id": "stt-a"},
            "provider_tts_settings": {"enable": True, "provider_id": "tts-a"},
        }
    )
    chat_a = DummyChatProvider(
        {"id": "chat-a", "type": "fake_chat_a", "enable": True},
        manager.provider_settings,
    )
    chat_b = DummyChatProvider(
        {"id": "chat-b", "type": "fake_chat_b", "enable": True},
        manager.provider_settings,
    )
    stt_a = DummySTTProvider(
        {"id": "stt-a", "type": "fake_stt_a", "enable": True},
        manager.provider_settings,
    )

    async def fake_load_provider(provider_config: dict) -> None:
        provider_id = provider_config["id"]
        if provider_id == "chat-a":
            manager.provider_insts.append(chat_a)
            manager.inst_map[provider_id] = chat_a
        elif provider_id == "chat-b":
            manager.provider_insts.append(chat_b)
            manager.inst_map[provider_id] = chat_b

    monkeypatch.setattr(manager, "_load_session_provider_overrides", AsyncMock())
    monkeypatch.setattr(manager, "load_provider", fake_load_provider)
    monkeypatch.setattr(
        manager.preferences,
        "get_async",
        AsyncMock(side_effect=["missing-chat", "stt-a", None]),
    )
    manager.stt_provider_insts = [stt_a]
    manager.inst_map["stt-a"] = stt_a
    manager.tool_manager.init_mcp_clients = AsyncMock()

    await manager.initialize()
    if manager._mcp_init_task is not None:
        await manager._mcp_init_task

    manager._load_session_provider_overrides.assert_awaited_once()
    assert manager.get_using_provider(ProviderType.CHAT_COMPLETION) is chat_a
    assert manager.get_using_provider(ProviderType.SPEECH_TO_TEXT) is stt_a
    assert manager.get_using_provider(ProviderType.TEXT_TO_SPEECH) is None
    manager.preferences.get_async.assert_not_awaited()
    manager.tool_manager.init_mcp_clients.assert_awaited_once()


@pytest.mark.asyncio
async def test_initialize_continues_after_load_provider_failure(monkeypatch):
    manager = _build_manager(
        {
            "provider": [
                {"id": "broken-chat", "enable": True},
                {"id": "chat-ok", "enable": True},
            ],
            "provider_sources": [],
            "provider_settings": {},
            "agent_runner": {
                "runner_type": "local",
                "config": {"model": {"provider_id": "chat-ok"}},
            },
            "provider_stt_settings": {"enable": False, "provider_id": None},
            "provider_tts_settings": {"enable": False, "provider_id": None},
        }
    )
    chat_ok = DummyChatProvider(
        {"id": "chat-ok", "type": "fake_chat_ok", "enable": True},
        manager.provider_settings,
    )

    async def fake_load_provider(provider_config: dict) -> None:
        if provider_config["id"] == "broken-chat":
            raise RuntimeError("broken provider")
        manager.provider_insts.append(chat_ok)
        manager.inst_map["chat-ok"] = chat_ok

    monkeypatch.setattr(manager, "_load_session_provider_overrides", AsyncMock())
    monkeypatch.setattr(manager, "load_provider", fake_load_provider)
    monkeypatch.setattr(
        manager.preferences,
        "get_async",
        AsyncMock(side_effect=[None, None, None]),
    )
    manager.tool_manager.init_mcp_clients = AsyncMock()

    await manager.initialize()
    if manager._mcp_init_task is not None:
        await manager._mcp_init_task

    assert manager.get_using_provider(ProviderType.CHAT_COMPLETION) is chat_ok
    manager.tool_manager.init_mcp_clients.assert_awaited_once()


@pytest.mark.asyncio
async def test_initialize_falls_back_when_persisted_provider_ids_have_wrong_types(
    monkeypatch,
):
    manager = _build_manager(
        {
            "provider": [{"id": "chat-a", "enable": True}],
            "provider_sources": [],
            "provider_settings": {},
            "agent_runner": {
                "runner_type": "local",
                "config": {"model": {"provider_id": "chat-a"}},
            },
            "provider_stt_settings": {"enable": True, "provider_id": "stt-a"},
            "provider_tts_settings": {"enable": True, "provider_id": "tts-a"},
        }
    )
    chat_a = DummyChatProvider(
        {"id": "chat-a", "type": "fake_chat_a", "enable": True},
        manager.provider_settings,
    )
    stt_a = DummySTTProvider(
        {"id": "stt-a", "type": "fake_stt_a", "enable": True},
        manager.provider_settings,
    )
    tts_a = DummyTTSProvider(
        {"id": "tts-a", "type": "fake_tts_a", "enable": True},
        manager.provider_settings,
    )

    monkeypatch.setattr(manager, "_load_session_provider_overrides", AsyncMock())
    monkeypatch.setattr(manager, "load_provider", AsyncMock())
    monkeypatch.setattr(
        manager.preferences,
        "get_async",
        AsyncMock(side_effect=["stt-a", "chat-a", 123]),
    )
    manager.provider_insts = [chat_a]
    manager.stt_provider_insts = [stt_a]
    manager.tts_provider_insts = [tts_a]
    manager.inst_map = {
        "chat-a": chat_a,
        "stt-a": stt_a,
        "tts-a": tts_a,
    }
    manager.tool_manager.init_mcp_clients = AsyncMock()

    await manager.initialize()
    if manager._mcp_init_task is not None:
        await manager._mcp_init_task

    assert manager.get_using_provider(ProviderType.CHAT_COMPLETION) is chat_a
    assert manager.get_using_provider(ProviderType.SPEECH_TO_TEXT) is stt_a
    assert manager.get_using_provider(ProviderType.TEXT_TO_SPEECH) is tts_a


@pytest.mark.asyncio
async def test_initialize_reuses_pending_mcp_init_task(monkeypatch):
    manager = _build_manager()
    existing_task = asyncio.create_task(asyncio.Event().wait())

    monkeypatch.setattr(manager, "_load_session_provider_overrides", AsyncMock())
    monkeypatch.setattr(manager, "load_provider", AsyncMock())
    monkeypatch.setattr(
        manager.preferences,
        "get_async",
        AsyncMock(side_effect=[None, None, None]),
    )
    manager.tool_manager.init_mcp_clients = AsyncMock()
    manager._mcp_init_task = existing_task

    await manager.initialize()

    assert manager._mcp_init_task is existing_task
    manager.tool_manager.init_mcp_clients.assert_not_awaited()

    existing_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await existing_task


@pytest.mark.asyncio
async def test_initialize_replaces_done_mcp_task_and_logs_background_failure(
    monkeypatch,
):
    manager = _build_manager()
    done_task = asyncio.create_task(asyncio.sleep(0))
    await done_task
    error = MagicMock()

    monkeypatch.setattr(manager, "_load_session_provider_overrides", AsyncMock())
    monkeypatch.setattr(manager, "load_provider", AsyncMock())
    monkeypatch.setattr(
        manager.preferences,
        "get_async",
        AsyncMock(side_effect=[None, None, None]),
    )
    monkeypatch.setattr(provider_manager_module.logger, "error", error)
    manager.tool_manager.init_mcp_clients = AsyncMock(
        side_effect=RuntimeError("mcp boom")
    )
    manager._mcp_init_task = done_task

    await manager.initialize()
    assert manager._mcp_init_task is not done_task
    if manager._mcp_init_task is not None:
        await manager._mcp_init_task

    manager.tool_manager.init_mcp_clients.assert_awaited_once()
    assert error.call_count == 1
    assert error.call_args.args[0] == "MCP init background task failed"
    assert error.call_args.kwargs["exc_info"] is True


@pytest.mark.asyncio
async def test_reload_terminates_removed_provider_and_auto_selects_remaining(
    monkeypatch,
):
    manager = _build_manager(
        {
            "provider": [
                {"id": "chat-a", "enable": True},
                {"id": "chat-b", "enable": True},
            ],
            "provider_sources": [],
            "provider_settings": {},
            "agent_runner": {
                "runner_type": "local",
                "config": {"model": {"provider_id": "chat-a"}},
            },
            "provider_stt_settings": {"enable": False, "provider_id": None},
            "provider_tts_settings": {"enable": False, "provider_id": None},
        }
    )
    chat_a = DummyChatProvider(
        {"id": "chat-a", "type": "fake_chat_a", "enable": True},
        manager.provider_settings,
    )
    chat_b = DummyChatProvider(
        {"id": "chat-b", "type": "fake_chat_b", "enable": True},
        manager.provider_settings,
    )
    chat_a.terminate = AsyncMock()
    manager.provider_insts = [chat_a, chat_b]
    manager.inst_map = {"chat-a": chat_a, "chat-b": chat_b}
    manager.curr_provider_inst = chat_a

    manager.acm.default_conf = {
        "provider": [{"id": "chat-b", "enable": True}],
        "provider_sources": [],
    }
    _register_provider(
        manager,
        "fake_chat_b",
        DummyChatProvider,
        ProviderType.CHAT_COMPLETION,
    )
    monkeypatch.setattr(manager, "load_provider", AsyncMock())

    await manager.reload({"id": "chat-a", "enable": False})

    assert manager.load_provider.await_count == 0
    assert "chat-a" not in manager.inst_map
    assert manager.provider_insts == [chat_b]
    chat_a.terminate.assert_awaited_once()


@pytest.mark.asyncio
async def test_reload_loads_enabled_provider_and_prunes_out_of_config_instances(
    monkeypatch,
):
    manager = _build_manager(
        {
            "provider": [
                {"id": "chat-new", "enable": True},
                {"id": "chat-keep", "enable": True},
            ],
            "provider_sources": [],
            "provider_settings": {},
            "agent_runner": {
                "runner_type": "local",
                "config": {"model": {"provider_id": "chat-new"}},
            },
            "provider_stt_settings": {"enable": False, "provider_id": None},
            "provider_tts_settings": {"enable": False, "provider_id": None},
        }
    )
    chat_keep = DummyChatProvider(
        {"id": "chat-keep", "type": "fake_chat_keep", "enable": True},
        manager.provider_settings,
    )
    stale = DummyChatProvider(
        {"id": "chat-stale", "type": "fake_chat_stale", "enable": True},
        manager.provider_settings,
    )
    stale.terminate = AsyncMock()
    manager.provider_insts = [chat_keep, stale]
    manager.inst_map = {"chat-keep": chat_keep, "chat-stale": stale}
    manager.curr_provider_inst = None

    loaded_new = DummyChatProvider(
        {"id": "chat-new", "type": "fake_chat_new", "enable": True},
        manager.provider_settings,
    )
    _register_provider(
        manager,
        "fake_chat_new",
        DummyChatProvider,
        ProviderType.CHAT_COMPLETION,
    )

    async def fake_load_provider(provider_config: dict) -> None:
        if provider_config["id"] == "chat-new":
            manager.provider_insts.insert(0, loaded_new)
            manager.inst_map["chat-new"] = loaded_new

    terminate_provider = AsyncMock(side_effect=manager.terminate_provider)
    monkeypatch.setattr(manager, "load_provider", fake_load_provider)
    monkeypatch.setattr(manager, "terminate_provider", terminate_provider)
    manager.acm.default_conf = {
        "provider": [
            {"id": "chat-new", "enable": True},
            {"id": "chat-keep", "enable": True},
        ],
        "provider_sources": [],
    }

    await manager.reload({"id": "chat-new", "enable": True})

    assert terminate_provider.await_args_list[0] == call("chat-new")
    assert terminate_provider.await_args_list[1] == call("chat-stale")
    assert manager.provider_insts[0] is loaded_new
    assert "chat-stale" not in manager.inst_map
    stale.terminate.assert_awaited_once()


@pytest.mark.asyncio
async def test_reload_auto_selects_stt_and_tts_when_current_instances_are_none(
    monkeypatch,
):
    manager = _build_manager(
        {
            "provider": [
                {"id": "stt-a", "enable": True},
                {"id": "tts-a", "enable": True},
            ],
            "provider_sources": [],
            "provider_settings": {},
            "agent_runner": {
                "runner_type": "local",
                "config": {"model": {"provider_id": "chat-a"}},
            },
            "provider_stt_settings": {"enable": True, "provider_id": "stt-a"},
            "provider_tts_settings": {"enable": True, "provider_id": "tts-a"},
        }
    )
    stt_a = DummySTTProvider(
        {"id": "stt-a", "type": "fake_stt_a", "enable": True},
        manager.provider_settings,
    )
    tts_a = DummyTTSProvider(
        {"id": "tts-a", "type": "fake_tts_a", "enable": True},
        manager.provider_settings,
    )
    manager.stt_provider_insts = [stt_a]
    manager.tts_provider_insts = [tts_a]
    manager.inst_map = {"stt-a": stt_a, "tts-a": tts_a}
    _register_provider(
        manager,
        "fake_stt_a",
        DummySTTProvider,
        ProviderType.SPEECH_TO_TEXT,
    )
    _register_provider(
        manager,
        "fake_tts_a",
        DummyTTSProvider,
        ProviderType.TEXT_TO_SPEECH,
    )

    manager.acm.default_conf = {
        "provider": [
            {"id": "stt-a", "enable": True},
            {"id": "tts-a", "enable": True},
        ],
        "provider_sources": [],
    }
    monkeypatch.setattr(manager, "load_provider", AsyncMock())

    await manager.reload({"id": "missing-provider", "enable": False})

    assert manager.stt_provider_insts == [stt_a]
    assert manager.tts_provider_insts == [tts_a]


@pytest.mark.asyncio
async def test_delete_provider_by_source_id_terminates_matching_instances_and_saves():
    manager = _build_manager(
        {
            "provider": [
                {"id": "chat-a", "provider_source_id": "source-1"},
                {"id": "chat-b", "provider_source_id": "source-1"},
                {"id": "chat-c", "provider_source_id": "source-2"},
            ],
            "provider_sources": [],
            "provider_settings": {},
            "agent_runner": {
                "runner_type": "local",
                "config": {"model": {"provider_id": "chat-a"}},
            },
            "provider_stt_settings": {"enable": False, "provider_id": None},
            "provider_tts_settings": {"enable": False, "provider_id": None},
        }
    )
    manager.terminate_provider = AsyncMock()

    async def persist_after_config_is_complete() -> bool:
        manager.terminate_provider.assert_not_awaited()
        return True

    manager.acm.default_conf.save_config_async.side_effect = (
        persist_after_config_is_complete
    )

    await manager.delete_provider(provider_source_id="source-1")

    assert manager.terminate_provider.await_args_list == [
        call("chat-a"),
        call("chat-b"),
    ]
    assert manager.acm.default_conf["provider"] == [
        {"id": "chat-c", "provider_source_id": "source-2"},
    ]
    manager.acm.default_conf.save_config_async.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_provider_persists_new_config_and_reloads():
    manager = _build_manager(
        {
            "provider": [
                {"id": "chat-a", "type": "old-type", "enable": True},
            ],
            "provider_sources": [],
            "provider_settings": {},
            "agent_runner": {
                "runner_type": "local",
                "config": {"model": {"provider_id": "chat-a"}},
            },
            "provider_stt_settings": {"enable": False, "provider_id": None},
            "provider_tts_settings": {"enable": False, "provider_id": None},
        }
    )
    transitions: list[str] = []

    async def persist() -> bool:
        transitions.append("persist")
        return True

    async def reload(provider_config: dict) -> None:
        assert provider_config is new_config
        transitions.append("reload")

    manager.acm.default_conf.save_config_async.side_effect = persist
    manager.reload = AsyncMock(side_effect=reload)
    new_config = {"id": "chat-a", "type": "new-type", "enable": True}

    await manager.update_provider("chat-a", new_config)

    assert manager.acm.default_conf["provider"] == [new_config]
    manager.acm.default_conf.save_config_async.assert_awaited_once()
    manager.reload.assert_awaited_once_with(new_config)
    assert transitions == ["persist", "reload"]


@pytest.mark.asyncio
async def test_create_provider_appends_config_loads_instance_and_syncs_provider_list():
    manager = _build_manager()
    transitions: list[str] = []

    async def persist() -> bool:
        transitions.append("persist")
        return True

    async def load(provider_config: dict) -> None:
        assert provider_config is new_config
        transitions.append("load")

    manager.acm.default_conf.save_config_async.side_effect = persist
    manager.load_provider = AsyncMock(side_effect=load)
    new_config = {"id": "chat-new", "type": "fake-chat", "enable": True}
    await manager.create_provider(new_config)

    assert manager.acm.default_conf["provider"] == [new_config]
    manager.acm.default_conf.save_config_async.assert_awaited_once()
    manager.load_provider.assert_awaited_once_with(new_config)
    assert manager.providers_config == [new_config]
    assert transitions == ["persist", "load"]


@pytest.mark.asyncio
async def test_update_provider_does_not_reload_when_config_persistence_fails():
    manager = _build_manager(
        {
            "provider": [
                {"id": "chat-a", "type": "old-type", "enable": True},
            ],
            "provider_sources": [],
            "provider_settings": {},
            "agent_runner": {
                "runner_type": "local",
                "config": {"model": {"provider_id": "chat-a"}},
            },
            "provider_stt_settings": {"enable": False, "provider_id": None},
            "provider_tts_settings": {"enable": False, "provider_id": None},
        }
    )
    old_config = manager.acm.default_conf["provider"]
    manager.acm.default_conf.save_config_async.side_effect = OSError("disk unavailable")
    manager.reload = AsyncMock()

    with pytest.raises(OSError, match="disk unavailable"):
        await manager.update_provider(
            "chat-a",
            {"id": "chat-a", "type": "new-type", "enable": True},
        )

    assert manager.acm.default_conf["provider"] is old_config
    manager.reload.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_provider_does_not_load_when_write_is_superseded():
    """A stale config snapshot must not publish a live provider instance."""
    manager = _build_manager()
    old_config = manager.acm.default_conf["provider"]
    manager.acm.default_conf.save_config_async.return_value = False
    manager.load_provider = AsyncMock()
    new_config = {"id": "chat-new", "type": "fake-chat", "enable": True}

    with pytest.raises(RuntimeError, match="superseded"):
        await manager.create_provider(new_config)

    assert manager.acm.default_conf["provider"] is old_config
    assert manager.providers_config is old_config
    manager.load_provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_terminate_provider_cleans_embedding_and_rerank_instances():
    manager = _build_manager()
    embedding = DummyEmbeddingProvider(
        {"id": "embed-1", "type": "fake_embed", "enable": True},
        manager.provider_settings,
    )
    rerank = DummyRerankProvider(
        {"id": "rerank-1", "type": "fake_rerank", "enable": True},
        manager.provider_settings,
    )
    embedding.terminate = AsyncMock()
    rerank.terminate = AsyncMock()
    manager.embedding_provider_insts = [embedding]
    manager.rerank_provider_insts = [rerank]
    manager.inst_map = {
        "embed-1": embedding,
        "rerank-1": rerank,
    }

    await manager.terminate_provider("embed-1")
    await manager.terminate_provider("rerank-1")

    assert manager.embedding_provider_insts == []
    assert manager.rerank_provider_insts == []
    assert manager.inst_map == {}
    embedding.terminate.assert_awaited_once()
    rerank.terminate.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminate_provider_clears_current_stt_and_tts_instances():
    manager = _build_manager()
    stt_provider = DummySTTProvider(
        {"id": "stt-1", "type": "fake_stt", "enable": True},
        manager.provider_settings,
    )
    tts_provider = DummyTTSProvider(
        {"id": "tts-1", "type": "fake_tts", "enable": True},
        manager.provider_settings,
    )
    stt_provider.terminate = AsyncMock()
    tts_provider.terminate = AsyncMock()
    manager.stt_provider_insts = [stt_provider]
    manager.tts_provider_insts = [tts_provider]
    manager.inst_map = {"stt-1": stt_provider, "tts-1": tts_provider}

    await manager.terminate_provider("stt-1")
    await manager.terminate_provider("tts-1")

    assert manager.stt_provider_insts == []
    assert manager.tts_provider_insts == []
    assert manager.stt_provider_insts == []
    assert manager.tts_provider_insts == []
    stt_provider.terminate.assert_awaited_once()
    tts_provider.terminate.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminate_provider_is_noop_for_missing_id():
    manager = _build_manager()

    await manager.terminate_provider("missing-provider")

    assert manager.inst_map == {}
    assert manager.provider_insts == []
    assert manager.stt_provider_insts == []
    assert manager.tts_provider_insts == []


@pytest.mark.asyncio
async def test_terminate_cancels_mcp_task_and_terminates_loaded_providers(monkeypatch):
    manager = _build_manager()
    provider = DummyChatProvider(
        {"id": "chat-a", "type": "fake_chat_a", "enable": True},
        manager.provider_settings,
    )
    provider.terminate = AsyncMock()
    manager.provider_insts = [provider]
    manager.tool_manager.disable_mcp_server = AsyncMock()

    async def wait_forever() -> None:
        await asyncio.Event().wait()

    manager._mcp_init_task = asyncio.create_task(wait_forever())

    await manager.terminate()

    assert manager._mcp_init_task.cancelled()
    provider.terminate.assert_awaited_once()
    manager.tool_manager.disable_mcp_server.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminate_also_terminates_stt_tts_embedding_and_rerank(monkeypatch):
    manager = _build_manager()
    stt_provider = DummySTTProvider(
        {"id": "stt-a", "type": "fake_stt_a", "enable": True},
        manager.provider_settings,
    )
    tts_provider = DummyTTSProvider(
        {"id": "tts-a", "type": "fake_tts_a", "enable": True},
        manager.provider_settings,
    )
    embedding_provider = DummyEmbeddingProvider(
        {"id": "embed-a", "type": "fake_embed_a", "enable": True},
        manager.provider_settings,
    )
    rerank_provider = DummyRerankProvider(
        {"id": "rerank-a", "type": "fake_rerank_a", "enable": True},
        manager.provider_settings,
    )
    stt_provider.terminate = AsyncMock()
    tts_provider.terminate = AsyncMock()
    embedding_provider.terminate = AsyncMock()
    rerank_provider.terminate = AsyncMock()
    manager.stt_provider_insts = [stt_provider]
    manager.tts_provider_insts = [tts_provider]
    manager.embedding_provider_insts = [embedding_provider]
    manager.rerank_provider_insts = [rerank_provider]
    manager.tool_manager.disable_mcp_server = AsyncMock()

    await manager.terminate()

    stt_provider.terminate.assert_awaited_once()
    tts_provider.terminate.assert_awaited_once()
    embedding_provider.terminate.assert_awaited_once()
    rerank_provider.terminate.assert_awaited_once()
    manager.tool_manager.disable_mcp_server.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminate_deduplicates_shared_instance_and_swallows_disable_mcp_errors():
    manager = _build_manager()
    shared = DummyChatProvider(
        {"id": "shared", "type": "fake_chat_shared", "enable": True},
        manager.provider_settings,
    )
    shared.terminate = AsyncMock()
    manager.provider_insts = [shared]
    manager.tts_provider_insts = [shared]
    manager.tool_manager.disable_mcp_server = AsyncMock(
        side_effect=RuntimeError("disable failed")
    )

    await manager.terminate()

    shared.terminate.assert_awaited_once()
    manager.tool_manager.disable_mcp_server.assert_awaited_once()
