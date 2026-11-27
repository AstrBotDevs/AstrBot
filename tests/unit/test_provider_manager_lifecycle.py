"""Tests for ProviderManager lifecycle, cleanup, and config synchronization."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.provider.entities import ProviderMetaData, ProviderType
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.provider import (
    DecisionProvider,
    EmbeddingProvider,
    Provider,
    RerankProvider,
    STTProvider,
    TTSProvider,
)


class _FakeConfig(dict):
    """Dictionary-backed config stub with a no-op save_config method."""

    def save_config(self) -> None:
        return None


def _make_manager(default_conf: _FakeConfig | None = None) -> ProviderManager:
    """Create a ProviderManager backed by an isolated in-memory config.

    Args:
        default_conf: Optional configuration dictionary to attach as default_conf.

    Returns:
        Configured ProviderManager instance.
    """
    if default_conf is None:
        default_conf = _FakeConfig(
            {
                "provider": [],
                "provider_sources": [],
                "provider_settings": {},
                "provider_stt_settings": {},
                "provider_tts_settings": {},
                "agent": {},
            }
        )
    acm = SimpleNamespace(confs={"default": default_conf}, default_conf=default_conf)
    persona_mgr = SimpleNamespace(
        default_persona="default",
        persona_v3_config=[],
        personas_v3=[],
        selected_default_persona_v3=None,
    )
    manager = ProviderManager(acm, MagicMock(), persona_mgr)
    manager.llm_tools = MagicMock()
    manager.llm_tools.disable_mcp_server = AsyncMock()
    return manager


@pytest.mark.asyncio
async def test_terminate_provider_removes_embedding_and_rerank_instances() -> None:
    """Ensure terminate_provider removes embedding and rerank instances."""
    manager = _make_manager()

    emb = MagicMock(spec=EmbeddingProvider)
    emb.terminate = AsyncMock()
    rerank = MagicMock(spec=RerankProvider)
    rerank.terminate = AsyncMock()

    manager.embedding_provider_insts.append(emb)
    manager.rerank_provider_insts.append(rerank)
    manager.inst_map["emb_1"] = emb
    manager.inst_map["rerank_1"] = rerank

    await manager.terminate_provider("emb_1")
    assert emb not in manager.embedding_provider_insts
    assert "emb_1" not in manager.inst_map
    emb.terminate.assert_awaited_once()

    await manager.terminate_provider("rerank_1")
    assert rerank not in manager.rerank_provider_insts
    assert "rerank_1" not in manager.inst_map
    rerank.terminate.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminate_closes_all_provider_types_once_and_continues_on_error() -> (
    None
):
    """Ensure terminate() shuts down every provider type without aborting on errors."""
    manager = _make_manager()

    chat = MagicMock(spec=Provider)
    chat.provider_config = {"id": "chat_1"}
    chat.terminate = AsyncMock(side_effect=RuntimeError("boom"))

    stt = MagicMock(spec=STTProvider)
    stt.provider_config = {"id": "stt_1"}
    stt.terminate = AsyncMock()

    tts = MagicMock(spec=TTSProvider)
    tts.provider_config = {"id": "tts_1"}
    tts.terminate = AsyncMock()

    emb = MagicMock(spec=EmbeddingProvider)
    emb.provider_config = {"id": "emb_1"}
    emb.terminate = AsyncMock()

    rerank = MagicMock(spec=RerankProvider)
    rerank.provider_config = {"id": "rerank_1"}
    rerank.terminate = AsyncMock()

    decision = MagicMock(spec=DecisionProvider)
    decision.provider_config = {"id": "dec_1"}
    decision.terminate = AsyncMock()

    map_only = MagicMock(spec=Provider)
    map_only.provider_config = {"id": "map_only_1"}
    map_only.terminate = AsyncMock()

    manager.provider_insts.append(chat)
    manager.stt_provider_insts.append(stt)
    manager.tts_provider_insts.append(tts)
    manager.embedding_provider_insts.append(emb)
    manager.rerank_provider_insts.append(rerank)
    manager.decision_provider_insts.append(decision)
    manager.inst_map = {
        "chat_1": chat,
        "stt_1": stt,
        "tts_1": tts,
        "emb_1": emb,
        "rerank_1": rerank,
        "dec_1": decision,
        "map_only_1": map_only,
    }

    await manager.terminate()

    chat.terminate.assert_awaited_once()
    stt.terminate.assert_awaited_once()
    tts.terminate.assert_awaited_once()
    emb.terminate.assert_awaited_once()
    rerank.terminate.assert_awaited_once()
    decision.terminate.assert_awaited_once()
    map_only.terminate.assert_awaited_once()
    manager.llm_tools.disable_mcp_server.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_provider_uses_tts_settings_and_keeps_registry_metadata_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify TTS selection uses provider_tts_settings and metadata.id is unmutated."""

    class _FakeTTS(TTSProvider):
        def __init__(self, provider_config: dict, provider_settings: dict) -> None:
            super().__init__(provider_config, provider_settings)

        async def get_audio(self, text: str) -> str:
            return text

    conf = _FakeConfig(
        {
            "provider": [],
            "provider_sources": [],
            "provider_settings": {"provider_id": "chat_only"},
            "provider_stt_settings": {},
            "provider_tts_settings": {"provider_id": "tts_2"},
            "agent": {},
        }
    )
    manager = _make_manager(conf)

    meta = ProviderMetaData(
        id="default",
        model="tts-model",
        type="fake_tts",
        provider_type=ProviderType.TEXT_TO_SPEECH,
        cls_type=_FakeTTS,
    )
    monkeypatch.setattr(
        "astrbot.core.provider.manager.provider_cls_map",
        {"fake_tts": meta},
    )
    monkeypatch.setattr(manager, "dynamic_import_provider", lambda _type: None)

    await manager.load_provider(
        {"id": "tts_1", "type": "fake_tts", "enable": True},
    )
    await manager.load_provider(
        {"id": "tts_2", "type": "fake_tts", "enable": True},
    )
    await manager.load_provider(
        {"id": "tts_3", "type": "fake_tts", "enable": True},
    )

    assert manager.curr_tts_provider_inst is manager.inst_map["tts_2"]
    assert meta.id == "default"


@pytest.mark.asyncio
async def test_reload_and_create_provider_sync_from_acm_default_conf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify reload() and create_provider() sync config from self.acm.default_conf."""
    new_provider = {"id": "p1", "type": "fake_chat", "enable": True}
    default_conf = _FakeConfig(
        {
            "provider": [],
            "provider_sources": [{"id": "src1"}],
            "provider_settings": {},
            "provider_stt_settings": {},
            "provider_tts_settings": {},
            "agent": {},
        }
    )
    manager = _make_manager(default_conf)
    manager.providers_config = [{"id": "stale"}]
    monkeypatch.setattr(manager, "load_provider", AsyncMock())

    await manager.create_provider(new_provider)
    assert manager.providers_config is default_conf["provider"]
    assert manager.providers_config == [new_provider]

    default_conf["provider_sources"] = [{"id": "src2"}]
    await manager.reload({"id": "p1", "type": "fake_chat", "enable": False})
    assert manager.providers_config is default_conf["provider"]
    assert manager.provider_sources_config == [{"id": "src2"}]


@pytest.mark.asyncio
async def test_terminate_provider_removes_inst_map_when_terminate_raises() -> None:
    """Failed terminate() in terminate_provider must still clear inst_map."""
    manager = _make_manager()

    emb = MagicMock(spec=EmbeddingProvider)
    emb.terminate = AsyncMock(side_effect=RuntimeError("cleanup failed"))
    manager.embedding_provider_insts.append(emb)
    manager.inst_map["emb_err"] = emb

    await manager.terminate_provider("emb_err")

    assert emb not in manager.embedding_provider_insts
    assert "emb_err" not in manager.inst_map
    emb.terminate.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminate_bounds_stalled_provider_and_prevents_new_loads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shutdown times out stalled providers and blocks new provider registration."""

    class _FakeChat(Provider):
        def __init__(self, provider_config: dict, provider_settings: dict) -> None:
            super().__init__(provider_config, provider_settings)
            self.terminated = False

        def get_current_key(self) -> str:
            return ""

        async def text_chat(self, *args, **kwargs):
            raise NotImplementedError

        async def terminate(self) -> None:
            self.terminated = True

    manager = _make_manager()
    manager._PROVIDER_TERMINATE_TIMEOUT_S = 0.05

    gate = asyncio.Event()

    async def stalled_terminate() -> None:
        await gate.wait()

    stalled = MagicMock(spec=Provider)
    stalled.provider_config = {"id": "stalled_1"}
    stalled.terminate = stalled_terminate

    trailing = MagicMock(spec=Provider)
    trailing.provider_config = {"id": "trailing_1"}
    trailing.terminate = AsyncMock()

    manager.provider_insts.extend([stalled, trailing])
    manager.inst_map = {"stalled_1": stalled, "trailing_1": trailing}

    try:
        await asyncio.wait_for(manager.terminate(), timeout=1.0)
        trailing.terminate.assert_awaited_once()
        manager.llm_tools.disable_mcp_server.assert_awaited_once()
        assert manager.inst_map == {}
        assert manager.provider_insts == []

        meta = ProviderMetaData(
            id="default",
            model="m",
            type="fake_chat",
            provider_type=ProviderType.CHAT_COMPLETION,
            cls_type=_FakeChat,
        )
        monkeypatch.setattr(
            "astrbot.core.provider.manager.provider_cls_map",
            {"fake_chat": meta},
        )
        monkeypatch.setattr(manager, "dynamic_import_provider", lambda _type: None)

        await manager.load_provider(
            {"id": "late_1", "type": "fake_chat", "enable": True}
        )
        assert "late_1" not in manager.inst_map

        with pytest.raises(RuntimeError, match="shutting down"):
            await manager.create_provider(
                {"id": "late_2", "type": "fake_chat", "enable": True}
            )
    finally:
        gate.set()


@pytest.mark.asyncio
async def test_reload_refreshes_provider_sources_before_load_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload must refresh provider_sources_config before merging sources in load_provider."""
    default_conf = _FakeConfig(
        {
            "provider": [
                {
                    "id": "p1",
                    "type": "fake_chat",
                    "enable": True,
                    "provider_source_id": "src1",
                }
            ],
            "provider_sources": [{"id": "src1", "api_base": "https://old.example"}],
            "provider_settings": {},
            "provider_stt_settings": {},
            "provider_tts_settings": {},
            "agent": {},
        }
    )
    manager = _make_manager(default_conf)
    default_conf["provider_sources"] = [
        {"id": "src1", "api_base": "https://new.example"}
    ]

    merged_bases: list[str | None] = []

    async def capture_load(provider_config: dict) -> None:
        merged = manager.get_merged_provider_config(provider_config)
        merged_bases.append(merged.get("api_base"))

    monkeypatch.setattr(manager, "load_provider", capture_load)

    await manager.reload(
        {
            "id": "p1",
            "type": "fake_chat",
            "enable": True,
            "provider_source_id": "src1",
        }
    )

    assert merged_bases == ["https://new.example"]
