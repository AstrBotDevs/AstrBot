"""Tests for astrbot.core.provider.manager.

Covers ProviderManager __init__, callbacks/hooks, get_provider_by_id,
get_using_provider, _resolve_env_key_list, get_provider_config_by_id,
and related helper methods.
"""

from unittest.mock import MagicMock, patch

import pytest

from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.provider import (
    DecisionProvider,
    EmbeddingProvider,
    Provider,
    RerankProvider,
    STTProvider,
    TTSProvider,
)

# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def mock_acm():
    """Create a mock AstrBotConfigManager with valid nested config structure."""
    acm = MagicMock()
    acm.confs = {
        "default": {
            "provider": [],
            "provider_sources": [],
            "agent": {"runtime": "astrbot", "config": {"model": {"provider_id": ""}}},
            "provider_settings": {"default_provider_id": ""},
            "provider_stt_settings": {},
            "provider_tts_settings": {},
        }
    }
    acm.default_conf = acm.confs["default"]
    acm.get_conf.return_value = acm.confs["default"]
    return acm


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_persona_mgr():
    pm = MagicMock()
    pm.default_persona = "default"
    pm.persona_v3_config = []
    pm.personas_v3 = []
    pm.selected_default_persona_v3 = None
    return pm


@pytest.fixture
def manager(mock_acm, mock_db, mock_persona_mgr):
    with patch("astrbot.core.provider.manager.llm_tools"):
        mgr = ProviderManager(
            acm=mock_acm,
            db_helper=mock_db,
            persona_mgr=mock_persona_mgr,
        )
        yield mgr


# =========================================================================
# __init__
# =========================================================================


class TestProviderManagerInit:
    def test_construction(self, manager):
        assert manager.reload_lock is not None
        assert manager.resource_lock is not None
        assert manager.providers_config == []
        assert manager.provider_sources_config == []
        assert manager.provider_settings == {"default_provider_id": ""}
        assert manager.provider_insts == []
        assert manager.stt_provider_insts == []
        assert manager.tts_provider_insts == []
        assert manager.embedding_provider_insts == []
        assert manager.rerank_provider_insts == []
        assert manager.decision_provider_insts == []
        assert manager.inst_map == {}
        assert manager.curr_provider_inst is None
        assert manager._provider_change_callback is None
        assert manager._provider_change_hooks == []
        assert manager._mcp_init_task is None

    def test_default_persona_name_from_mgr(self, manager):
        assert manager.default_persona_name == "default"

    def test_persona_configs_property(self, manager):
        assert manager.persona_configs == []

    def test_personas_property(self, manager):
        assert manager.personas == []

    def test_selected_default_persona_property(self, manager):
        assert manager.selected_default_persona is None


# =========================================================================
# Callbacks / Hooks
# =========================================================================


class TestProviderManagerCallbacks:
    def test_set_provider_change_callback(self, manager):
        cb = MagicMock()
        manager.set_provider_change_callback(cb)
        assert manager._provider_change_callback is cb

    def test_set_provider_change_callback_none(self, manager):
        manager.set_provider_change_callback(None)
        assert manager._provider_change_callback is None

    def test_register_provider_change_hook(self, manager):
        hook = MagicMock()
        manager.register_provider_change_hook(hook)
        assert hook in manager._provider_change_hooks

    def test_register_provider_change_hook_duplicate(self, manager):
        hook = MagicMock()
        manager.register_provider_change_hook(hook)
        manager.register_provider_change_hook(hook)
        assert len(manager._provider_change_hooks) == 1

    def test_unregister_provider_change_hook(self, manager):
        hook = MagicMock()
        manager.register_provider_change_hook(hook)
        manager.unregister_provider_change_hook(hook)
        assert hook not in manager._provider_change_hooks

    def test_unregister_provider_change_hook_not_registered(self, manager):
        hook = MagicMock()
        # Should not raise
        manager.unregister_provider_change_hook(hook)

    def test_notify_provider_changed_calls_callback(self, manager):
        cb = MagicMock()
        manager.set_provider_change_callback(cb)
        manager._notify_provider_changed("p1", ProviderType.CHAT_COMPLETION, "umo_1")
        cb.assert_called_once_with("p1", ProviderType.CHAT_COMPLETION, "umo_1")

    def test_notify_provider_changed_swallows_callback_error(self, manager):
        callback = MagicMock(side_effect=ValueError("callback failed"))
        hook = MagicMock()
        manager.set_provider_change_callback(callback)
        manager.register_provider_change_hook(hook)

        manager._notify_provider_changed("p1", ProviderType.CHAT_COMPLETION, None)

        callback.assert_called_once_with("p1", ProviderType.CHAT_COMPLETION, None)
        hook.assert_called_once_with("p1", ProviderType.CHAT_COMPLETION, None)

    def test_notify_provider_changed_calls_hooks(self, manager):
        hook1 = MagicMock()
        hook2 = MagicMock()
        manager.register_provider_change_hook(hook1)
        manager.register_provider_change_hook(hook2)
        manager._notify_provider_changed("p1", ProviderType.SPEECH_TO_TEXT, None)
        hook1.assert_called_once_with("p1", ProviderType.SPEECH_TO_TEXT, None)
        hook2.assert_called_once_with("p1", ProviderType.SPEECH_TO_TEXT, None)

    def test_notify_provider_changed_skips_callback_in_hooks(self, manager):
        """When the same callable is both callback and hook, it should only be invoked once."""
        fn = MagicMock()
        manager.set_provider_change_callback(fn)
        manager.register_provider_change_hook(fn)
        manager._notify_provider_changed("p1", ProviderType.CHAT_COMPLETION, None)
        assert fn.call_count == 1

    def test_notify_provider_changed_swallows_hook_error(self, manager):
        first = MagicMock(side_effect=RuntimeError("hook failed"))
        second = MagicMock()
        manager.register_provider_change_hook(first)
        manager.register_provider_change_hook(second)

        manager._notify_provider_changed("p1", ProviderType.CHAT_COMPLETION, None)

        first.assert_called_once_with("p1", ProviderType.CHAT_COMPLETION, None)
        second.assert_called_once_with("p1", ProviderType.CHAT_COMPLETION, None)


# =========================================================================
# get_provider_by_id / get_using_provider
# =========================================================================


class TestProviderManagerLookups:
    @pytest.mark.asyncio
    async def test_get_provider_by_id_not_found(self, manager):
        result = await manager.get_provider_by_id("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_provider_by_id_found(self, manager):
        fake_inst = MagicMock(spec=Provider)
        manager.inst_map["p1"] = fake_inst
        result = await manager.get_provider_by_id("p1")
        assert result is fake_inst

    def test_get_using_provider_chat_completion_default(self, manager, mock_acm):
        fake_provider = MagicMock(spec=Provider)
        manager.provider_insts = [fake_provider]
        mock_acm.get_conf.return_value = {
            "provider_settings": {"default_provider_id": None}
        }
        result = manager.get_using_provider(ProviderType.CHAT_COMPLETION)
        assert result is fake_provider

    @pytest.mark.asyncio
    async def test_get_using_provider_chat_completion_by_id(self, manager, mock_acm):
        fake_provider = MagicMock(spec=Provider)
        manager.inst_map["default_prov"] = fake_provider
        mock_acm.get_conf.return_value = {
            "agent": {
                "runtime": "astrbot",
                "config": {"model": {"provider_id": "default_prov"}},
            }
        }

        result = await manager.get_using_provider_async(ProviderType.CHAT_COMPLETION)

        assert result is fake_provider
        mock_acm.get_conf.assert_called_once_with(None)

    def test_get_using_provider_chat_completion_no_instances(self, manager, mock_acm):
        mock_acm.get_conf.return_value = {
            "provider_settings": {"default_provider_id": None}
        }
        result = manager.get_using_provider(ProviderType.CHAT_COMPLETION)
        assert result is None

    def test_get_using_provider_stt_disabled_returns_none(self, manager, mock_acm):
        mock_acm.get_conf.return_value = {"provider_stt_settings": {"enable": False}}
        result = manager.get_using_provider(ProviderType.SPEECH_TO_TEXT)
        assert result is None

    def test_get_using_provider_tts_disabled_returns_none(self, manager, mock_acm):
        mock_acm.get_conf.return_value = {"provider_tts_settings": {"enable": False}}
        result = manager.get_using_provider(ProviderType.TEXT_TO_SPEECH)
        assert result is None

    def test_get_using_provider_unknown_type(self, manager, mock_acm):
        with pytest.raises(ValueError, match="Unknown provider type"):
            manager.get_using_provider(ProviderType.EMBEDDING)

    @pytest.mark.asyncio
    async def test_get_using_provider_with_umo(self, manager, mock_acm):
        fake_provider = MagicMock(spec=Provider)
        manager.inst_map["umo_prov"] = fake_provider
        mock_acm.get_conf.return_value = {
            "agent": {
                "runtime": "astrbot",
                "config": {"model": {"provider_id": "umo_prov"}},
            }
        }

        result = await manager.get_using_provider_async(
            ProviderType.CHAT_COMPLETION, umo="session_1"
        )

        assert result is fake_provider
        mock_acm.get_conf.assert_called_once_with("session_1")


# =========================================================================
# _resolve_env_key_list
# =========================================================================


class TestResolveEnvKeyList:
    def test_no_env_vars(self, manager):
        config = {"key": ["sk-abc", "sk-def"]}
        result = manager._resolve_env_key_list(config)
        assert result["key"] == ["sk-abc", "sk-def"]

    def test_env_var_resolved(self, manager, monkeypatch):
        monkeypatch.setenv("PROVIDER_TEST_API_KEY", "sk-from-env")
        config = {"key": ["$PROVIDER_TEST_API_KEY"], "id": "prov1"}

        result = manager._resolve_env_key_list(config)

        assert result["key"] == ["sk-from-env"]

    def test_env_var_braces(self, manager, monkeypatch):
        monkeypatch.setenv("PROVIDER_TEST_SECRET", "very_secret")
        config = {"key": ["${PROVIDER_TEST_SECRET}"], "id": "prov1"}

        result = manager._resolve_env_key_list(config)

        assert result["key"] == ["very_secret"]

    def test_env_var_not_set_logs_warning(self, manager, monkeypatch):
        monkeypatch.delenv("PROVIDER_TEST_MISSING", raising=False)
        config = {"key": ["$PROVIDER_TEST_MISSING"], "id": "prov1"}
        with patch("astrbot.core.provider.manager.logger") as logger:
            result = manager._resolve_env_key_list(config)

        assert result["key"] == [""]
        logger.warning.assert_called_once()

    def test_env_var_mixed_list(self, manager, monkeypatch):
        monkeypatch.setenv("PROVIDER_TEST_MIXED", "val1")
        config = {"key": ["$PROVIDER_TEST_MIXED", "static_key"], "id": "prov1"}

        result = manager._resolve_env_key_list(config)

        assert result["key"] == ["val1", "static_key"]

    def test_non_list_key_passthrough(self, manager):
        config = {"key": "not_a_list"}
        result = manager._resolve_env_key_list(config)
        assert result["key"] == "not_a_list"

    def test_empty_env_var_name(self, manager):
        config = {"key": ["$"], "id": "prov1"}
        result = manager._resolve_env_key_list(config)
        assert result["key"] == ["$"]

    def test_missing_key_field(self, manager):
        config = {"id": "prov1"}
        result = manager._resolve_env_key_list(config)
        assert result == config


# =========================================================================
# get_provider_config_by_id
# =========================================================================


class TestGetProviderConfigById:
    def test_found(self, manager):
        manager.providers_config = [
            {"id": "p1", "type": "openai"},
            {"id": "p2", "type": "anthropic"},
        ]
        result = manager.get_provider_config_by_id("p1")
        assert result == {"id": "p1", "type": "openai"}

    def test_not_found(self, manager):
        manager.providers_config = [{"id": "p1", "type": "openai"}]
        result = manager.get_provider_config_by_id("nonexistent")
        assert result is None

    def test_deep_copy_returned(self, manager):
        manager.providers_config = [{"id": "p1", "type": "openai", "key": ["secret"]}]
        result = manager.get_provider_config_by_id("p1")
        # Mutating the result should not affect the source
        result["key"].append("new_key")
        assert manager.providers_config[0]["key"] == ["secret"]

    def test_merged_flag(self, manager):
        manager.providers_config = [
            {"id": "p1", "provider_source_id": "src1", "model": "chosen-model"}
        ]
        manager.provider_sources_config = [
            {
                "id": "src1",
                "type": "openai",
                "model": "source-model",
                "base_url": "https://provider.invalid",
            }
        ]

        result = manager.get_provider_config_by_id("p1", merged=True)

        assert result == {
            "id": "p1",
            "provider_source_id": "src1",
            "type": "openai",
            "model": "chosen-model",
            "base_url": "https://provider.invalid",
        }
        result["model"] = "caller-mutation"
        assert manager.providers_config[0]["model"] == "chosen-model"
        assert manager.provider_sources_config[0]["model"] == "source-model"

    def test_empty_configs(self, manager):
        result = manager.get_provider_config_by_id("p1")
        assert result is None


# =========================================================================
# _get_all_provider_instances / _clear_loaded_instances / get_insts
# =========================================================================


class TestProviderManagerInstances:
    def test_get_insts(self, manager):
        fp = MagicMock(spec=Provider)
        manager.provider_insts = [fp]
        assert manager.get_insts() == [fp]

    def test_get_all_provider_instances_deduplicates(self, manager):
        fp = MagicMock(spec=Provider)
        manager.provider_insts = [fp]
        manager.inst_map = {"p1": fp}
        all_insts = manager._get_all_provider_instances()
        # fp appears in both lists but should only be returned once
        assert len(all_insts) == 1
        assert all_insts[0] is fp

    def test_get_all_provider_instances_returns_all_types(self, manager):
        pairs = [
            ("provider_insts", Provider),
            ("stt_provider_insts", STTProvider),
            ("tts_provider_insts", TTSProvider),
            ("embedding_provider_insts", EmbeddingProvider),
            ("rerank_provider_insts", RerankProvider),
            ("decision_provider_insts", DecisionProvider),
        ]
        expected = []
        for index, (attribute, base) in enumerate(pairs):
            instance = MagicMock(spec=base)
            setattr(manager, attribute, [instance])
            manager.inst_map[str(index)] = instance
            expected.append(instance)

        assert manager._get_all_provider_instances() == expected

    def test_clear_loaded_instances(self, manager):
        manager.provider_insts = [MagicMock(spec=Provider)]
        manager.stt_provider_insts = [MagicMock(spec=STTProvider)]
        manager.inst_map = {"p1": MagicMock()}
        manager.curr_provider_inst = MagicMock()

        manager._clear_loaded_instances()
        assert manager.provider_insts == []
        assert manager.stt_provider_insts == []
        assert manager.tts_provider_insts == []
        assert manager.embedding_provider_insts == []
        assert manager.rerank_provider_insts == []
        assert manager.decision_provider_insts == []
        assert manager.inst_map == {}
        assert manager.curr_provider_inst is None
        assert manager.curr_stt_provider_inst is None
        assert manager.curr_tts_provider_inst is None
