"""Failed speech and knowledge-base model calls are shown in ChatUI."""

import copy
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.astr_agent_runtime.main_agent import (
    knowledge_base as knowledge_base_build,
)
from astrbot.core.astr_agent_runtime.main_agent.config import MainAgentBuildConfig
from astrbot.core.auxiliary_model_errors import (
    AUXILIARY_MODEL_ERROR_CODE,
    notify_auxiliary_model_failure,
)
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.knowledge_base.retrieval.manager import RetrievalManager
from astrbot.core.knowledge_base.retrieval.rank_fusion import FusedResult
from astrbot.core.message.components import Plain, Record
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.preprocess_stage.stage import PreProcessStage
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage
from astrbot.core.provider.entities import ProviderRequest


def _event(platform="webchat"):
    event = MagicMock()
    event.get_platform_name.return_value = platform
    event.unified_msg_origin = f"{platform}:FriendMessage:user"
    event.send = AsyncMock()
    event.get_extra.return_value = None
    event.is_stopped.return_value = False
    event.plugins_name = None
    return event


def _cards(event):
    """The ChatUI error cards an event sent, as their JSON payloads."""
    return [
        call.args[0].chain[0].data
        for call in event.send.await_args_list
        if call.args[0].type == "chatui_error"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["webchat", "aiocqhttp"])
async def test_card_is_shown_in_chatui_only(platform):
    event = _event(platform)
    await notify_auxiliary_model_failure(event, "Text-to-speech (tts)", "timeout")
    assert _cards(event) == (
        [
            {
                "code": AUXILIARY_MODEL_ERROR_CODE,
                "message": "Text-to-speech (tts): timeout",
            }
        ]
        if platform == "webchat"
        else []
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("send_fails", [False, True])
async def test_a_card_does_not_stop_the_reply(send_fails):
    event = _event()
    event._has_send_oper = False

    async def send(_chain):
        # Like AstrMessageEvent.send, which the pipeline checks before
        # running the model.
        event._has_send_oper = True
        if send_fails:
            raise RuntimeError("stream closed")

    event.send = AsyncMock(side_effect=send)
    await notify_auxiliary_model_failure(event, "Speech-to-text (whisper)", "down")
    event.send.assert_awaited_once()
    assert event._has_send_oper is False


def _voice(tmp_path):
    path = tmp_path / "voice.wav"
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * 160)
    return path


async def _preprocess(provider, message):
    config = {"provider_stt_settings": {"enable": True, "provider_id": "stt"}}
    context = SimpleNamespace(
        get_config=lambda **_: config,
        get_using_stt_provider_async=AsyncMock(return_value=provider),
    )
    stage = PreProcessStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config=config, plugin_manager=SimpleNamespace(context=context)
        )
    )
    event = _event()
    event.message_obj = SimpleNamespace(message=message, message_str="")
    event.message_str = ""
    event.get_messages.return_value = message
    await stage.process(event)
    return event


@pytest.mark.asyncio
async def test_failed_speech_to_text_shows_the_provider_and_cause(tmp_path):
    provider = SimpleNamespace(
        provider_config={"id": "whisper"},
        get_text=AsyncMock(side_effect=RuntimeError("model whisper-9 not found")),
    )
    event = await _preprocess(provider, [Record(file=str(_voice(tmp_path)))])
    assert _cards(event) == [
        {
            "code": AUXILIARY_MODEL_ERROR_CODE,
            "message": "Speech-to-text (whisper): model whisper-9 not found",
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("has_voice", [True, False])
async def test_missing_speech_to_text_provider_is_shown_only_for_voice(
    tmp_path, has_voice
):
    message = [Record(file=str(_voice(tmp_path)))] if has_voice else [Plain("hi")]
    event = await _preprocess(None, message)
    assert len(_cards(event)) == (1 if has_voice else 0)


@pytest.mark.asyncio
async def test_failed_text_to_speech_sends_text_and_one_card():
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["provider_tts_settings"]["enable"] = True
    provider = SimpleNamespace(
        provider_config={"id": "edge"},
        get_audio=AsyncMock(side_effect=RuntimeError("401 invalid key")),
    )
    context = SimpleNamespace(
        get_config=lambda **_: config,
        get_using_tts_provider_async=AsyncMock(return_value=provider),
    )
    stage = ResultDecorateStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config=config, plugin_manager=SimpleNamespace(context=context)
        )
    )
    event = _event()
    result = MessageEventResult(
        chain=[Plain("first part"), Plain("second part")],
        result_content_type=ResultContentType.LLM_RESULT,
    )
    event.get_result.return_value = result
    async for _ in stage.process(event):
        pass
    # The reply falls back to text; both failed segments share one card.
    assert [comp.text for comp in result.chain] == ["first part", "second part"]
    assert _cards(event) == [
        {
            "code": AUXILIARY_MODEL_ERROR_CODE,
            "message": "Text-to-speech (edge): 401 invalid key",
        }
    ]


@pytest.mark.asyncio
async def test_retrieval_collects_skipped_embedding_and_rerank_failures():
    vec_db = SimpleNamespace(
        retrieve=AsyncMock(side_effect=RuntimeError("embedding 404")),
        rerank_provider=SimpleNamespace(
            rerank=AsyncMock(side_effect=RuntimeError("rerank 401"))
        ),
    )
    helper = SimpleNamespace(
        kb=SimpleNamespace(
            top_k_dense=5, top_k_sparse=5, top_m_final=5, rerank_provider_id="r"
        ),
        vec_db=vec_db,
    )
    fused = FusedResult(
        chunk_id="c", chunk_index=0, doc_id="d", kb_id="kb", content="text", score=1
    )
    manager = RetrievalManager(
        sparse_retriever=SimpleNamespace(retrieve=AsyncMock(return_value=[])),
        rank_fusion=SimpleNamespace(fuse=AsyncMock(return_value=[fused])),
        kb_db=SimpleNamespace(
            get_documents_with_metadata_batch=AsyncMock(
                return_value={
                    "d": {
                        "document": SimpleNamespace(doc_name="doc"),
                        "knowledge_base": SimpleNamespace(kb_name="KB"),
                    }
                }
            )
        ),
    )
    errors: list[str] = []
    results = await manager.retrieve(
        query="q", kb_ids=["kb"], kb_id_helper_map={"kb": helper}, errors=errors
    )
    # Retrieval still answers from what worked.
    assert [result.content for result in results] == ["text"]
    assert errors == [
        "Embedding search in knowledge base kb failed: RuntimeError: embedding 404",
        "Rerank failed: RuntimeError: rerank 401",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("raises", [False, True])
async def test_knowledge_base_failures_are_shown_without_dropping_results(
    monkeypatch, raises
):
    async def retrieve(query, umo, context, errors):
        if raises:
            raise ValueError("all knowledge bases are unavailable")
        errors.append("Rerank failed: timeout")
        return "fact"

    monkeypatch.setattr(knowledge_base_build, "retrieve_knowledge_base", retrieve)
    event = _event()
    req = ProviderRequest(prompt="question")
    await knowledge_base_build.apply_knowledge_base(
        event,
        req,
        MagicMock(),
        MainAgentBuildConfig(tool_call_timeout=60, kb_agentic_mode=False),
    )
    detail = (
        "all knowledge bases are unavailable" if raises else "Rerank failed: timeout"
    )
    assert _cards(event) == [
        {"code": AUXILIARY_MODEL_ERROR_CODE, "message": f"Knowledge base: {detail}"}
    ]
    assert len(req.extra_user_content_parts) == (0 if raises else 1)


@pytest.mark.asyncio
async def test_knowledge_base_tool_shows_failures_and_still_answers(monkeypatch):
    from astrbot.core.astr_agent_runtime.tools import knowledge_base_tools

    async def retrieve(query, umo, context, errors):
        errors.append("Knowledge base docs is unavailable: no embedding provider")
        return "fact"

    monkeypatch.setattr(knowledge_base_tools, "retrieve_knowledge_base", retrieve)
    event = _event()
    wrapper = SimpleNamespace(context=SimpleNamespace(event=event, context=None))
    result = await knowledge_base_tools.KnowledgeBaseQueryTool().call(
        wrapper, query="q"
    )
    assert result == "fact"
    assert [card["message"] for card in _cards(event)] == [
        "Knowledge base: Knowledge base docs is unavailable: no embedding provider"
    ]
