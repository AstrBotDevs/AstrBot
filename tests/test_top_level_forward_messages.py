"""Tests for top-level Forward/Node/Nodes message extraction, admission, and steering."""

from __future__ import annotations

import copy
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image as PILImage

from astrbot.core import agent_media
from astrbot.core.agent.message import TextPart
from astrbot.core.agent.output import PlainOutput
from astrbot.core.agent.runtime import InputReceipt, TurnResult
from astrbot.core.astr_agent_runtime import AstrAgentRuntime
from astrbot.core.astr_agent_runtime import session as native_session
from astrbot.core.astr_agent_runtime.main_agent import (
    MainAgentBuildConfig,
)
from astrbot.core.astr_agent_runtime.main_agent import (
    builder as builder_build,
)
from astrbot.core.astr_agent_runtime.main_agent import (
    knowledge_base as knowledge_base_build,
)
from astrbot.core.astr_agent_runtime.main_agent import (
    request as request_build,
)
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.message.components import (
    Forward,
    Node,
    Nodes,
    Plain,
    Reply,
)
from astrbot.core.pipeline import context_utils
from astrbot.core.pipeline.preprocess_stage import stage as preprocess
from astrbot.core.pipeline.process_stage import follow_up
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal
from astrbot.core.pipeline.process_stage.stage import ProcessStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.provider.provider import Provider
from astrbot.core.utils import image_input
from astrbot.core.utils import media_utils as media
from astrbot.core.utils.quoted_message.forward_extractor import (
    COMPANION_FORWARD_INJECTED_EXTRA_KEY,
    FORWARD_CONTENT_HEADER,
    FORWARD_CONTENT_UNAVAILABLE,
    PARSED_FORWARDS_EXTRA_KEY,
    extract_forward_messages,
    has_forward_components,
)
from astrbot.core.utils.quoted_message.settings import QuotedMessageParserSettings


class _RecordingOneBotAPI:
    def __init__(
        self,
        responses: dict[tuple[str, str], dict] | None = None,
        *,
        raise_on: set[str] | None = None,
    ) -> None:
        self.responses = responses or {}
        self.raise_on = raise_on or set()
        self.calls: list[tuple[str, dict]] = []

    async def call_action(self, action: str, **params):
        self.calls.append((action, dict(params)))
        key_id = params.get("message_id")
        if key_id is None:
            key_id = params.get("id")
        if str(key_id) in self.raise_on:
            raise RuntimeError(f"simulated failure for {action}({key_id})")
        key = (action, str(key_id))
        if key not in self.responses:
            raise RuntimeError(f"no mock response for {key}")
        return self.responses[key]


class _FailIfCalledAPI:
    async def call_action(self, action: str, **params):
        raise AssertionError(
            f"call_action should not be called, got action={action}, params={params}"
        )


def _make_event(
    parts: list,
    *,
    text: str = "",
    session: str = "fwd-session",
    platform_name: str = "aiocqhttp",
    api=None,
    message_id: str = "msg-1001",
) -> AstrMessageEvent:
    message = AstrBotMessage()
    message.message = parts
    message.message_str = text
    message.message_id = message_id
    message.type = MessageType.FRIEND_MESSAGE
    message.sender = MessageMember(user_id="user-1", nickname="UserOne")
    message.self_id = "bot-1"
    event = AstrMessageEvent(
        text,
        message,
        PlatformMetadata(name=platform_name, id=platform_name, description="test"),
        session,
    )
    event.is_at_or_wake_command = True
    event.send = AsyncMock()
    event.send_typing = AsyncMock()
    event.stop_typing = AsyncMock()
    if api is not None:
        event.bot = SimpleNamespace(api=api)  # type: ignore[attr-defined]
    return event


def _make_local_png(tmp_path, name: str = "sample.png") -> str:
    path = tmp_path / name
    PILImage.new("RGB", (16, 16), "blue").save(path, "PNG")
    return str(path)


@pytest.fixture
def pipeline_harness(tmp_path, monkeypatch):
    work = tmp_path / "work"
    for module in (media, image_input, preprocess):
        monkeypatch.setattr(module, "get_astrbot_temp_path", lambda: str(work))
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["provider_settings"].update(
        {
            "streaming_response": False,
            "image_compress_options": {"max_size": 90},
            "enable": True,
        }
    )
    context = MagicMock(spec=builder_build.Context)
    context.persona_manager = MagicMock()
    context.conversation_manager = MagicMock()
    context.get_config.return_value = config
    context.persona_manager.resolve_selected_persona = AsyncMock(
        return_value=(None, None, False)
    )
    context.persona_manager.personas_v3 = []
    context.get_llm_tool_manager.return_value.get_builtin_tool.side_effect = (
        lambda cls, **kwargs: cls(**kwargs)
    )

    conversation = SimpleNamespace(
        cid="conv-fwd",
        conversation_id="conv-fwd",
        user_id="aiocqhttp:FriendMessage:fwd-session",
        umo="aiocqhttp:FriendMessage:fwd-session",
        persona_id=None,
        history="[]",
        content=[],
        token_usage=None,
        revision=1,
    )
    context.conversation_manager.get_curr_conversation_id = AsyncMock(
        return_value="conv-fwd"
    )
    context.conversation_manager.get_conversation = AsyncMock(return_value=conversation)
    context.conversation_manager.db.get_conversation_by_id = AsyncMock(
        return_value=conversation
    )
    context.conversation_manager.db.conversation_store = SimpleNamespace(
        get_metadata=AsyncMock(return_value=conversation),
        read_for_execution=AsyncMock(return_value=(conversation, None)),
    )
    context.conversation_manager.to_legacy_conversation.side_effect = lambda record: (
        record
    )
    context.conversation_manager.update_conversation = AsyncMock()

    provider = MagicMock(spec=Provider)
    provider.provider_config = {
        "id": "primary",
        "model": "test-model",
        "modalities": ["text", "image", "tool_use"],
        "max_context_tokens": 4096,
    }
    provider.get_model.return_value = "test-model"
    provider.text_chat = AsyncMock(
        return_value=LLMResponse(role="assistant", completion_text="ok")
    )

    async def stream(**kwargs):
        yield await provider.text_chat(**kwargs)

    provider.text_chat_stream = stream
    context.get_using_provider_async = AsyncMock(return_value=provider)
    context.get_provider_by_id.return_value = provider

    subagents = MagicMock()
    subagents.store.find_native_conversation.return_value = None
    runtime = AstrAgentRuntime(
        context, agent_configs=MagicMock(), subagents=subagents
    )
    ctx = SimpleNamespace(
        astrbot_config=config,
        plugin_manager=SimpleNamespace(context=context),
        agent_runtimes={"astrbot": runtime},
    )

    captured_runners = []
    kb_mock = AsyncMock(return_value=None)

    async def hook(event, kind, *args, context_observer=None):
        return False

    monkeypatch.setattr(context_utils, "call_event_hook", hook)
    monkeypatch.setattr(builder_build, "call_event_hook", hook)
    monkeypatch.setattr(
        internal, "try_capture_follow_up", lambda event, runtime=None: None
    )
    monkeypatch.setattr(native_session, "record_agent_stats", AsyncMock())
    monkeypatch.setattr(native_session.Metric, "upload", AsyncMock())
    monkeypatch.setattr(knowledge_base_build, "retrieve_knowledge_base", kb_mock)

    async def run(runner, turn, max_steps):
        captured_runners.append(runner)
        runner._message_parts = []
        runner._message_indices = {}
        async for response in runner._iter_llm_responses_with_fallback():
            runner.final_llm_resp = response
        return TurnResult(
            content=(PlainOutput(text=runner.final_llm_resp.completion_text),)
        )

    monkeypatch.setattr(native_session, "execute_native_loop", run)
    return SimpleNamespace(
        config=config,
        context=context,
        ctx=ctx,
        provider=provider,
        captured=captured_runners,
        kb_mock=kb_mock,
    )


async def _run_process_stage(harness, event: AstrMessageEvent) -> None:
    stage = ProcessStage()
    await stage.initialize(harness.ctx)
    async for _ in stage.process(event):
        result = event.get_result()
        if result and result.async_stream:
            async for _ in result.async_stream:
                pass
    assert not event.send.await_count, event.send.await_args_list


@pytest.mark.asyncio
async def test_pure_top_level_forward_passes_internal_gate_and_reaches_llm(
    pipeline_harness,
):
    api = _RecordingOneBotAPI(
        responses={
            ("get_forward_msg", "fwd_1"): {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Alice"},
                            "message": [
                                {"type": "text", "data": {"text": "明天上午九点开会"}}
                            ],
                        },
                        {
                            "sender": {"nickname": "Bob"},
                            "message": [
                                {"type": "at", "data": {"qq": "1001", "name": "Alice"}},
                                {"type": "text", "data": {"text": " 收到"}},
                            ],
                        },
                    ]
                }
            }
        }
    )
    event = _make_event([Forward(id="fwd_1")], text="", api=api)

    await _run_process_stage(pipeline_harness, event)

    assert len(pipeline_harness.captured) == 1
    req = pipeline_harness.captured[0].req
    assert req.prompt == "<attachment>"
    assert any(
        isinstance(part, TextPart)
        and part.text.startswith(FORWARD_CONTENT_HEADER)
        and "Alice: 明天上午九点开会" in part.text
        and "Bob: @Alice 收到" in part.text
        for part in req.extra_user_content_parts
    )
    # Pure forward must not pollute KB retrieval with "<attachment>" or chat logs.
    pipeline_harness.kb_mock.assert_not_awaited()

    cached = event.get_extra(PARSED_FORWARDS_EXTRA_KEY)
    assert isinstance(cached, dict)
    assert cached["version"] == 1
    assert cached["source"] == "astrbot_core"
    assert cached["total_nodes"] == 2
    assert cached["truncated"] is False
    assert len(cached["cards"]) == 1
    assert cached["cards"][0]["forward_id"] == "fwd_1"
    assert cached["cards"][0]["message_id"] == "msg-1001"
    assert cached["cards"][0]["node_count"] == 2
    # Exactly one RPC call for fwd_1 (no duplicate fetch between stages).
    assert len(api.calls) == 1

    assembled = await req.assemble_context()
    assert assembled["role"] == "user"
    assert isinstance(assembled["content"], list)
    assert any(
        block.get("type") == "text"
        and "Alice: 明天上午九点开会" in block.get("text", "")
        for block in assembled["content"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "components",
    [
        [
            Nodes(
                nodes=[
                    Node(name="Alice", uin="1001", content=[Plain(text="第一句")]),
                    Node(name="Bob", uin="1002", content=[Plain(text="第二句")]),
                ]
            )
        ],
        [Node(name="Solo", uin="1003", content=[Plain(text="单条节点")])],
    ],
)
async def test_pure_inline_node_and_nodes_pass_internal_gate_without_rpc(
    pipeline_harness,
    components,
):
    event = _make_event(components, text="", api=_FailIfCalledAPI())

    await _run_process_stage(pipeline_harness, event)

    assert len(pipeline_harness.captured) == 1
    req = pipeline_harness.captured[0].req
    assert req.prompt == "<attachment>"
    forward_parts = [
        part.text
        for part in req.extra_user_content_parts
        if isinstance(part, TextPart) and part.text.startswith(FORWARD_CONTENT_HEADER)
    ]
    assert len(forward_parts) == 1
    if isinstance(components[0], Nodes):
        assert "Alice: 第一句\nBob: 第二句" in forward_parts[0]
        assert event.get_extra(PARSED_FORWARDS_EXTRA_KEY)["total_nodes"] == 2
    else:
        assert "Solo: 单条节点" in forward_parts[0]
        assert event.get_extra(PARSED_FORWARDS_EXTRA_KEY)["total_nodes"] == 1


@pytest.mark.asyncio
async def test_empty_message_without_forward_is_still_skipped(pipeline_harness):
    event = _make_event([], text="", api=_FailIfCalledAPI())

    await _run_process_stage(pipeline_harness, event)

    assert len(pipeline_harness.captured) == 0


@pytest.mark.asyncio
async def test_mixed_user_text_and_forward_keeps_prompt_and_kb_query_clean(
    pipeline_harness,
):
    api = _RecordingOneBotAPI(
        responses={
            ("get_forward_msg", "fwd_mix"): {
                "data": {
                    "messages": [
                        {
                            "type": "node",
                            "data": {
                                "nickname": "Charlie",
                                "user_id": "2001",
                                "content": [
                                    {
                                        "type": "text",
                                        "data": {
                                            "text": "第三方聊天内容绝不能冒充用户"
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        }
    )
    event = _make_event(
        [Plain(text="帮我总结一下他们聊了啥"), Forward(id="fwd_mix")],
        text="帮我总结一下他们聊了啥",
        api=api,
    )

    await _run_process_stage(pipeline_harness, event)

    assert len(pipeline_harness.captured) == 1
    req = pipeline_harness.captured[0].req
    assert req.prompt == "帮我总结一下他们聊了啥"
    assert "第三方聊天内容" not in req.prompt
    assert any(
        isinstance(part, TextPart)
        and part.text.startswith(FORWARD_CONTENT_HEADER)
        and "Charlie: 第三方聊天内容绝不能冒充用户" in part.text
        for part in req.extra_user_content_parts
    )
    pipeline_harness.kb_mock.assert_awaited_once()
    assert (
        pipeline_harness.kb_mock.await_args.kwargs["query"] == "帮我总结一下他们聊了啥"
    )


@pytest.mark.asyncio
async def test_nested_forwards_images_limits_and_cycle_guard(tmp_path):
    img_nested = _make_local_png(tmp_path, "nested.png")
    img_outer = _make_local_png(tmp_path, "outer.png")
    api = _RecordingOneBotAPI(
        responses={
            ("get_forward_msg", "fwd_root"): {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Alice"},
                            "message": [
                                {"type": "text", "data": {"text": "外层消息"}},
                                {"type": "image", "data": {"url": img_outer}},
                            ],
                        },
                        {
                            "sender": {"nickname": "Bob"},
                            "message": [
                                {"type": "forward", "data": {"id": "fwd_child"}}
                            ],
                        },
                    ]
                }
            },
            ("get_forward_msg", "fwd_child"): {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Carol"},
                            "message": [
                                {"type": "text", "data": {"text": "内层消息"}},
                                {"type": "image", "data": {"url": img_nested}},
                            ],
                        },
                        {
                            "sender": {"nickname": "Dave"},
                            "message": [
                                {"type": "forward", "data": {"id": "fwd_root"}},
                                {"type": "forward", "data": {"id": "fwd_leaf"}},
                            ],
                        },
                    ]
                }
            },
            ("get_forward_msg", "fwd_leaf"): {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Eve"},
                            "message": [{"type": "text", "data": {"text": "最深层"}}],
                        }
                    ]
                }
            },
        }
    )

    # Full depth expansion with cycle guard (fwd_child -> fwd_root does not loop).
    event = _make_event([Forward(id="fwd_root")], api=api)
    parsed = await extract_forward_messages(event)
    assert parsed is not None
    assert parsed["truncated"] is False
    assert parsed["total_nodes"] == 5
    assert "Alice: 外层消息[Image]" in parsed["combined_text"]
    assert "  Carol: 内层消息[Image]" in parsed["combined_text"]
    assert "    Eve: 最深层" in parsed["combined_text"]
    assert parsed["image_urls"] == [img_outer, img_nested]
    assert len(api.calls) == 3

    # Depth cap (max_forward_node_depth=1 stops before fwd_leaf at depth 2).
    event_depth = _make_event([Forward(id="fwd_root")], api=api)
    parsed_depth = await extract_forward_messages(
        event_depth,
        settings=QuotedMessageParserSettings(max_forward_node_depth=1),
    )
    assert parsed_depth is not None
    assert parsed_depth["truncated"] is True
    assert "Carol: 内层消息" in parsed_depth["combined_text"]
    assert "Eve: 最深层" not in parsed_depth["combined_text"]

    # Fetch cap (max_forward_fetch=1 stops before fetching fwd_child).
    api_limited = _RecordingOneBotAPI(responses=api.responses)
    event_fetch = _make_event([Forward(id="fwd_root")], api=api_limited)
    parsed_fetch = await extract_forward_messages(
        event_fetch,
        settings=QuotedMessageParserSettings(max_forward_fetch=1),
    )
    assert parsed_fetch is not None
    assert parsed_fetch["truncated"] is True
    assert len(api_limited.calls) == 1
    assert "Alice: 外层消息" in parsed_fetch["combined_text"]
    assert "Carol: 内层消息" not in parsed_fetch["combined_text"]

    # Character limit truncation.
    event_chars = _make_event([Forward(id="fwd_root")], api=api)
    parsed_chars = await extract_forward_messages(
        event_chars,
        settings=QuotedMessageParserSettings(max_forward_chars=30),
    )
    assert parsed_chars is not None
    assert parsed_chars["truncated"] is True
    assert len(parsed_chars["combined_text"]) <= 30
    assert "已截断" in parsed_chars["combined_text"]


@pytest.mark.asyncio
async def test_forward_image_limit_and_multiple_cards_partial_failure():
    api = _RecordingOneBotAPI(
        responses={
            ("get_forward_msg", "card_ok"): {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Alice"},
                            "message": [
                                {"type": "image", "data": {"url": "https://img/1.jpg"}},
                                {"type": "image", "data": {"url": "https://img/2.jpg"}},
                                {"type": "image", "data": {"url": "https://img/3.jpg"}},
                            ],
                        }
                    ]
                }
            }
        },
        raise_on={"card_bad"},
    )
    event = _make_event([Forward(id="card_ok"), Forward(id="card_bad")], api=api)
    req = ProviderRequest(prompt="")

    added = await agent_media.append_forward_content(
        event,
        req,
        max_fallback_images=2,
    )
    assert added == 2
    assert req.image_urls == ["https://img/1.jpg", "https://img/2.jpg"]
    assert len(req.extra_user_content_parts) == 1
    text = req.extra_user_content_parts[0].text
    assert "[转发记录 1]" in text
    assert "Alice: [Image][Image][Image]" in text
    assert "[转发记录 2]" in text
    assert FORWARD_CONTENT_UNAVAILABLE in text


@pytest.mark.asyncio
async def test_non_onebot_and_failed_fetch_graceful_degradation_and_warn_flag(caplog):
    # Non-OneBot platform (no event.bot).
    non_onebot_event = _make_event(
        [Forward(id="ext_1")],
        platform_name="telegram",
        api=None,
    )
    req_non_onebot = ProviderRequest(prompt="")
    await agent_media.append_forward_content(non_onebot_event, req_non_onebot)
    assert [p.text for p in req_non_onebot.extra_user_content_parts] == [
        FORWARD_CONTENT_UNAVAILABLE
    ]

    # OneBot failure with warn_on_action_failure=False -> no warning.
    failing_api = _RecordingOneBotAPI(raise_on={"bad_id"})
    event_quiet = _make_event([Forward(id="bad_id")], api=failing_api)
    with caplog.at_level(logging.WARNING):
        caplog.clear()
        parsed_quiet = await extract_forward_messages(
            event_quiet,
            settings=QuotedMessageParserSettings(warn_on_action_failure=False),
        )
    assert parsed_quiet is not None
    assert parsed_quiet["combined_text"] == FORWARD_CONTENT_UNAVAILABLE
    assert not any("get_forward_msg" in rec.message for rec in caplog.records)

    # OneBot empty payload with warn_on_action_failure=True -> emits warning + degrades.
    empty_api = _RecordingOneBotAPI(
        responses={("get_forward_msg", "empty_id"): {"status": "failed", "data": {}}}
    )
    event_warn = _make_event([Forward(id="empty_id")], api=empty_api)
    with patch(
        "astrbot.core.utils.quoted_message.forward_extractor.logger.warning"
    ) as warn:
        parsed_empty = await extract_forward_messages(
            event_warn,
            settings=QuotedMessageParserSettings(warn_on_action_failure=True),
        )
    assert parsed_empty is not None
    assert parsed_empty["combined_text"] == FORWARD_CONTENT_UNAVAILABLE
    warn.assert_called_once()


@pytest.mark.asyncio
async def test_cached_astrbot_parsed_forwards_reused_with_zero_rpc(pipeline_harness):
    event = _make_event(
        [Forward(id="fwd_cached")],
        text="",
        api=_FailIfCalledAPI(),
    )
    cached_payload = {
        "version": 1,
        "source": "private_companion",
        "cards": [
            {
                "forward_id": "fwd_cached",
                "message_id": "msg-999",
                "node_count": 3,
                "truncated": False,
                "summary_text": "Alice: 来自缓存的转发",
            }
        ],
        "combined_text": "Alice: 来自缓存的转发",
        "total_nodes": 3,
        "image_urls": [],
        "truncated": False,
    }
    event.set_extra(PARSED_FORWARDS_EXTRA_KEY, cached_payload)

    await _run_process_stage(pipeline_harness, event)

    assert len(pipeline_harness.captured) == 1
    req = pipeline_harness.captured[0].req
    assert any(
        isinstance(part, TextPart) and "Alice: 来自缓存的转发" in part.text
        for part in req.extra_user_content_parts
    )
    # Original plugin cache metadata is preserved untouched.
    assert event.get_extra(PARSED_FORWARDS_EXTRA_KEY)["source"] == "private_companion"


@pytest.mark.asyncio
async def test_companion_forward_injected_skips_rpc_and_duplicate_injection(
    pipeline_harness,
):
    event = _make_event(
        [Forward(id="fwd_plugin")],
        text="",
        api=_FailIfCalledAPI(),
    )
    plugin_req = ProviderRequest(
        prompt="请看我刚刚转发的内容",
        extra_user_content_parts=[
            TextPart(text="[合并转发聊天记录 · 共2条]\nAlice: 插件已注入")
        ],
    )
    event.set_extra("provider_request", plugin_req)
    event.set_extra(COMPANION_FORWARD_INJECTED_EXTRA_KEY, True)

    await _run_process_stage(pipeline_harness, event)

    assert len(pipeline_harness.captured) == 1
    req = pipeline_harness.captured[0].req
    assert req.prompt == "请看我刚刚转发的内容"
    forward_parts = [
        part.text
        for part in req.extra_user_content_parts
        if isinstance(part, TextPart) and "转发" in part.text
    ]
    assert forward_parts == ["[合并转发聊天记录 · 共2条]\nAlice: 插件已注入"]
    assert event.get_extra(PARSED_FORWARDS_EXTRA_KEY) is None


@pytest.mark.asyncio
async def test_append_forward_content_is_idempotent():
    api = _RecordingOneBotAPI(
        responses={
            ("get_forward_msg", "fwd_idem"): {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Alice"},
                            "message": [{"type": "text", "data": {"text": "once"}}],
                        }
                    ]
                }
            }
        }
    )
    event = _make_event([Forward(id="fwd_idem")], api=api)
    req = ProviderRequest(prompt="")

    await agent_media.append_forward_content(event, req)
    await agent_media.append_forward_content(event, req)

    assert len(api.calls) == 1
    assert len(req.extra_user_content_parts) == 1


@pytest.mark.asyncio
async def test_follow_up_does_not_collapse_forward_components_to_plain_steering():
    assert Forward in follow_up._NON_PLAIN_STEERING_COMPONENTS
    assert Node in follow_up._NON_PLAIN_STEERING_COMPONENTS
    assert Nodes in follow_up._NON_PLAIN_STEERING_COMPONENTS

    active_turn = MagicMock()
    active_turn.id = "turn-1"
    active_turn.steer.return_value = InputReceipt()

    for components, text in [
        ([Forward(id="f1")], ""),
        ([Plain(text="看看这个"), Forward(id="f2")], "看看这个"),
        ([Node(name="Alice", uin="1", content=[Plain(text="hi")])], ""),
        ([Nodes(nodes=[Node(name="Bob", uin="2", content=[Plain(text="yo")])])], ""),
    ]:
        event = _make_event(components, text=text)
        capture = follow_up.try_capture_follow_up(event, active_turn)
        assert capture is None
    active_turn.steer.assert_not_called()

    # Plain text follow-up continues to steer normally.
    plain_event = _make_event([Plain(text="追问一下")], text="追问一下")
    capture = follow_up.try_capture_follow_up(plain_event, active_turn)
    assert capture is not None
    active_turn.steer.assert_called_once()
    capture.monitor_task.cancel()
    await follow_up.finalize_follow_up_capture(
        capture,
        activated=False,
        consumed_marked=False,
    )


@pytest.mark.asyncio
async def test_reply_with_nested_forward_is_not_top_level_and_coexists_with_top_level():
    reply_only = _make_event(
        [Reply(id="100", chain=[Forward(id="nested_in_reply")], message_str="")],
        text="引用了转发",
    )
    assert has_forward_components(reply_only) is False

    # Combined Reply + top-level Forward coexist cleanly.
    api = _RecordingOneBotAPI(
        responses={
            ("get_forward_msg", "top_fwd"): {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "TopUser"},
                            "message": [{"type": "text", "data": {"text": "顶层转发"}}],
                        }
                    ]
                }
            }
        }
    )
    combined_event = _make_event(
        [
            Reply(
                id="200", chain=[Plain(text="被引用的内容")], message_str="被引用的内容"
            ),
            Forward(id="top_fwd"),
        ],
        text="顺便看下转发",
        api=api,
    )
    cfg = MainAgentBuildConfig(tool_call_timeout=30)
    req, _ = await request_build.collect_initial_request(
        combined_event,
        MagicMock(),
        cfg,
    )
    assert req is not None
    assert req.prompt == "顺便看下转发"
    assert any(
        isinstance(part, TextPart) and "TopUser: 顶层转发" in part.text
        for part in req.extra_user_content_parts
    )


@pytest.mark.asyncio
async def test_pure_forward_with_valid_and_unavailable_images_end_to_end(
    pipeline_harness,
    tmp_path,
):
    valid_img = _make_local_png(tmp_path, "fwd_ok.png")
    api = _RecordingOneBotAPI(
        responses={
            ("get_forward_msg", "fwd_img"): {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Alice"},
                            "message": [
                                {"type": "text", "data": {"text": "看这张图"}},
                                {"type": "image", "data": {"url": valid_img}},
                            ],
                        }
                    ]
                }
            },
            ("get_forward_msg", "fwd_bad_img"): {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Bob"},
                            "message": [
                                {
                                    "type": "text",
                                    "data": {"text": "图过期了但文字还在"},
                                },
                                {
                                    "type": "image",
                                    "data": {"url": "http://127.0.0.1:1/missing.png"},
                                },
                            ],
                        }
                    ]
                }
            },
        }
    )

    event_ok = _make_event([Forward(id="fwd_img")], text="", api=api)
    await _run_process_stage(pipeline_harness, event_ok)
    req_ok = pipeline_harness.captured[-1].req
    assert len(req_ok.image_urls) == 1
    assert any(
        isinstance(part, TextPart) and "Alice: 看这张图[Image]" in part.text
        for part in req_ok.extra_user_content_parts
    )
    pipeline_harness.kb_mock.assert_not_awaited()

    # Even when a forward image fails preparation, prompt must not become [Image unavailable].
    event_bad = _make_event([Forward(id="fwd_bad_img")], text="", api=api)
    with patch.object(
        image_input,
        "prepare_model_image",
        AsyncMock(return_value=None),
    ):
        await _run_process_stage(pipeline_harness, event_bad)
    req_bad = pipeline_harness.captured[-1].req
    assert req_bad.prompt == "<attachment>"
    assert req_bad.image_urls == []
    assert any(
        isinstance(part, TextPart) and "Bob: 图过期了但文字还在[Image]" in part.text
        for part in req_bad.extra_user_content_parts
    )


@pytest.mark.asyncio
async def test_inline_forward_content_nested_inline_and_special_segments():
    # Inline Forward with dict content needs zero RPC and renders special segments safely.
    inline_fwd = Forward(id="inline_1")
    object.__setattr__(
        inline_fwd,
        "content",
        [
            {
                "sender": {"nickname": "Alice"},
                "message": [
                    {"type": "at", "data": {"qq": "all"}},
                    {"type": "text", "data": {"text": " 通知 "}},
                    {"type": "face", "data": {"id": "14"}},
                    {"type": "mface", "data": {"summary": "[动画表情]"}},
                    {"type": "record", "data": {"file": "voice.amr"}},
                    {"type": "video", "data": {"file": "clip.mp4"}},
                    {"type": "file", "data": {"name": "report.pdf"}},
                ],
            }
        ],
    )
    event_inline = _make_event([inline_fwd], api=_FailIfCalledAPI())
    parsed = await extract_forward_messages(event_inline)
    assert parsed is not None
    assert parsed["total_nodes"] == 1
    assert (
        "Alice: @all 通知 [Face][动画表情][Audio][Video][File:report.pdf]"
        == parsed["combined_text"]
    )

    # Inline Nodes containing a nested remote Forward expands both seamlessly.
    api = _RecordingOneBotAPI(
        responses={
            ("get_forward_msg", "sub_1"): {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Inner"},
                            "message": [
                                {"type": "text", "data": {"text": "远程子转发"}}
                            ],
                        }
                    ]
                }
            }
        }
    )
    nested_nodes = Nodes(
        nodes=[
            Node(
                name="Outer",
                uin="1001",
                content=[Plain(text="请看嵌套"), Forward(id="sub_1")],
            )
        ]
    )
    event_nested = _make_event([nested_nodes], api=api)
    parsed_nested = await extract_forward_messages(event_nested)
    assert parsed_nested is not None
    assert parsed_nested["total_nodes"] == 2
    assert "Outer: 请看嵌套" in parsed_nested["combined_text"]
    assert "  Inner: 远程子转发" in parsed_nested["combined_text"]
    assert len(api.calls) == 1

    # max_forward_fetch=0 makes zero RPC calls and degrades gracefully with truncated=True.
    event_zero = _make_event([Forward(id="blocked")], api=_FailIfCalledAPI())
    parsed_zero = await extract_forward_messages(
        event_zero,
        settings=QuotedMessageParserSettings(max_forward_fetch=0),
    )
    assert parsed_zero is not None
    assert parsed_zero["truncated"] is True
    assert parsed_zero["combined_text"] == FORWARD_CONTENT_UNAVAILABLE


@pytest.mark.asyncio
async def test_shared_fallback_image_budget_between_reply_and_top_level_forward():
    api = _RecordingOneBotAPI(
        responses={
            ("get_msg", "r1"): {
                "data": {
                    "message": [
                        {"type": "image", "data": {"url": "https://img/q1.jpg"}},
                        {"type": "image", "data": {"url": "https://img/q2.jpg"}},
                    ]
                }
            },
            ("get_forward_msg", "f1"): {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Alice"},
                            "message": [
                                {
                                    "type": "image",
                                    "data": {"url": "https://img/f1.jpg"},
                                },
                                {
                                    "type": "image",
                                    "data": {"url": "https://img/f2.jpg"},
                                },
                            ],
                        }
                    ]
                }
            },
        }
    )
    event = _make_event(
        [Reply(id="r1", chain=None, message_str=""), Forward(id="f1")],
        text="对比一下",
        api=api,
    )
    cfg = MainAgentBuildConfig(
        tool_call_timeout=30,
        max_quoted_fallback_images=3,
        provider_settings={
            "quoted_message_parser": {
                "max_forward_chars": 4000,
                "max_forward_fetch": 8,
            }
        },
    )
    req, _ = await request_build.collect_initial_request(event, MagicMock(), cfg)
    assert req is not None
    assert req.image_urls == [
        "https://img/q1.jpg",
        "https://img/q2.jpg",
        "https://img/f1.jpg",
    ]
