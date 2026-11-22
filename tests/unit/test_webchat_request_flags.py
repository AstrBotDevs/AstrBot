from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.core.astr_agent_runtime.main_agent.config import MainAgentBuildConfig
from astrbot.core.astr_agent_runtime.main_agent.request import collect_initial_request
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.webchat.request_flags import (
    resolve_webchat_request_flags,
)
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils import llm_metadata


def _make_event(**extras) -> AstrMessageEvent:
    msg = AstrBotMessage()
    msg.type = MessageType.FRIEND_MESSAGE
    msg.message_str = "hello"
    msg.message = []
    msg.sender = SimpleNamespace(user_id="u1", nickname="User")
    msg.self_id = "bot"
    msg.session_id = "s1"
    event = AstrMessageEvent(
        message_str="hello",
        message_obj=msg,
        platform_meta=PlatformMetadata(
            name="webchat", description="webchat", id="webchat"
        ),
        session_id="s1",
    )
    for key, value in extras.items():
        event.set_extra(key, value)
    return event


def test_webchat_request_flags_use_defaults():
    flags = resolve_webchat_request_flags({})

    assert flags == {
        "enable_inline_genui": True,
        "enable_default_system_prompt": True,
        "enable_streaming": True,
        "enable_reasoning": True,
        "reasoning_effort": None,
    }


def test_webchat_request_flags_prefer_nested_flags():
    flags = resolve_webchat_request_flags(
        {
            "enable_streaming": False,
            "reasoning_effort": "low",
            "flags": {
                "enable_inline_genui": False,
                "enable_default_system_prompt": False,
                "enable_streaming": True,
                "reasoning_effort": "high",
            },
        }
    )

    assert flags == {
        "enable_inline_genui": False,
        "enable_default_system_prompt": False,
        "enable_streaming": True,
        "enable_reasoning": True,
        "reasoning_effort": "high",
    }


def test_webchat_request_flags_keep_legacy_streaming_fallback():
    flags = resolve_webchat_request_flags(
        {"enable_streaming": False, "reasoning_effort": "high"}
    )

    assert flags["enable_streaming"] is False
    # reasoning_effort has no legacy top-level fallback and is read only from flags.
    assert flags["reasoning_effort"] is None


@pytest.mark.parametrize(
    ("raw_effort", "expected"),
    [
        ("none", "none"),
        ("minimal", "minimal"),
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
        ("xhigh", "xhigh"),
        ("max", "max"),
        (" HIGH ", "high"),
        ("XHigh", "xhigh"),
        ("auto", None),
        ("invalid", None),
        ("", None),
        (None, None),
        (123, None),
        (True, None),
    ],
)
def test_webchat_request_flags_resolve_reasoning_effort(raw_effort, expected):
    flags = resolve_webchat_request_flags({"flags": {"reasoning_effort": raw_effort}})

    assert flags["reasoning_effort"] == expected


@pytest.mark.asyncio
async def test_collect_initial_request_populates_extra_body_from_webchat_flag():
    config = MagicMock(spec=MainAgentBuildConfig)
    config.provider_wake_prefix = ""
    config.provider_settings = {}

    webchat_event = _make_event(reasoning_effort="xhigh")
    req, _ = await collect_initial_request(webchat_event, MagicMock(), config)
    assert req is not None
    assert req.extra_body == {"reasoning_effort": "xhigh"}

    # Pre-built requests (e.g. messages with image/file attachments) must still
    # inherit the WebChat reasoning_effort flag unless already overridden.
    prebuilt_req = ProviderRequest(prompt="with attachment")
    collected, _ = await collect_initial_request(
        webchat_event, MagicMock(), config, req=prebuilt_req
    )
    assert collected is not None
    assert collected.extra_body == {"reasoning_effort": "xhigh"}

    explicit_req = ProviderRequest(
        prompt="explicit", extra_body={"reasoning_effort": "low"}
    )
    collected_explicit, _ = await collect_initial_request(
        webchat_event, MagicMock(), config, req=explicit_req
    )
    assert collected_explicit is not None
    assert collected_explicit.extra_body == {"reasoning_effort": "low"}

    default_event = _make_event()
    default_req, _ = await collect_initial_request(default_event, MagicMock(), config)
    assert default_req is not None
    assert default_req.extra_body == {}


def test_llm_metadata_resolves_provider_and_consensus_reasoning_efforts():
    snapshot_meta = dict(llm_metadata.LLM_METADATAS)
    snapshot_provider = dict(llm_metadata.LLM_PROVIDER_REASONING_EFFORTS)
    snapshot_consensus = dict(llm_metadata.LLM_CONSENSUS_REASONING_EFFORTS)
    try:
        llm_metadata.populate_llm_metadata(
            {
                "deepseek": {
                    "models": {
                        "deepseek-v4-flash": {
                            "id": "deepseek-v4-flash",
                            "reasoning": True,
                            "reasoning_options": [
                                {"type": "toggle"},
                                {"type": "effort", "values": ["low", "high", "max"]},
                            ],
                        }
                    }
                },
                "relay-a": {
                    "models": {
                        "deepseek-v4-flash": {
                            "id": "deepseek-v4-flash",
                            "reasoning": True,
                            "reasoning_options": [
                                {"type": "effort", "values": ["low", "high", "max"]},
                            ],
                        },
                        "mimo-v2.5": {
                            "id": "mimo-v2.5",
                            "reasoning": True,
                            "reasoning_options": [{"type": "toggle"}],
                        },
                    }
                },
                "relay-b": {
                    "models": {
                        "deepseek-v4-flash": {
                            "id": "deepseek-v4-flash",
                            "reasoning": True,
                            "reasoning_options": [
                                {"type": "effort", "values": ["low", "high", "max"]},
                            ],
                        },
                        "mimo-v2.5": {
                            "id": "mimo-v2.5",
                            "reasoning": True,
                            "reasoning_options": [{"type": "toggle"}],
                        },
                    }
                },
                "xiaomi": {
                    "models": {
                        "mimo-v2.5": {
                            "id": "mimo-v2.5",
                            "family": "mimo",
                            "reasoning": True,
                            "reasoning_options": [{"type": "toggle"}],
                        }
                    }
                },
                "kimi-code-plan-cn": {
                    "models": {
                        "kimi-for-coding": {
                            "id": "kimi-for-coding",
                            "family": "kimi-coding",
                            "reasoning": True,
                            "reasoning_options": [
                                {
                                    "type": "effort",
                                    "values": ["none", "low", "high", "max"],
                                }
                            ],
                        },
                        "kimi-for-coding-highspeed": {
                            "id": "kimi-for-coding-highspeed",
                            "family": "kimi-coding",
                            "reasoning": True,
                            "reasoning_options": [],
                        },
                    }
                },
                "openai": {
                    "models": {
                        "gpt-6-sol": {
                            "id": "gpt-6-sol",
                            "family": "gpt-sol",
                            "release_date": "2026-06-01",
                            "reasoning": True,
                            "reasoning_options": [
                                {
                                    "type": "effort",
                                    "values": ["low", "medium", "high", "xhigh", "max"],
                                }
                            ],
                        },
                        "gpt-6.1-sol": {
                            "id": "gpt-6.1-sol",
                            "family": "gpt-sol",
                            "release_date": "2026-09-01",
                            "reasoning": True,
                        },
                    }
                },
            }
        )

        # DeepSeek native provider adds "none" for verified toggle+effort models.
        ds_native = llm_metadata.resolve_model_metadata(
            "deepseek-v4-flash",
            provider="deepseek",
            adapter_type="openai_chat_completion",
        )
        assert ds_native is not None
        assert ds_native["reasoning_efforts"] == ["none", "low", "high", "max"]

        # Unknown relay falls back to cross-provider majority vote.
        ds_relay = llm_metadata.resolve_model_metadata(
            "deepseek-v4-flash",
            provider="custom",
            adapter_type="openai_chat_completion",
        )
        assert ds_relay is not None
        assert ds_relay["reasoning_efforts"] == ["low", "high", "max"]

        # Toggle-only MiMo yields empty reasoning_efforts (no effort levels).
        mimo = llm_metadata.resolve_model_metadata(
            "mimo-v2.5",
            provider="xiaomi",
            adapter_type="xiaomi_chat_completion",
        )
        assert mimo is not None
        assert mimo["reasoning"] is True
        assert mimo["reasoning_efforts"] == []

        # Newly added family sibling inherits newest prior sibling efforts.
        gpt_61 = llm_metadata.resolve_model_metadata(
            "gpt-6.1-sol",
            provider="openai",
            adapter_type="custom_adapter",
        )
        assert gpt_61 is not None
        assert gpt_61["reasoning_efforts"] == [
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        ]

        kimi_coding = llm_metadata.resolve_model_metadata(
            "kimi-for-coding",
            provider="kimi-code",
            adapter_type="kimi_code_chat_completion",
        )
        assert kimi_coding is not None
        assert kimi_coding["reasoning_efforts"] == ["none", "low", "high", "max"]

        kimi_hs = llm_metadata.resolve_model_metadata(
            "kimi-for-coding-highspeed",
            provider="kimi-code",
            adapter_type="kimi_code_chat_completion",
        )
        assert kimi_hs is not None
        assert kimi_hs["reasoning_efforts"] == []
    finally:
        llm_metadata.LLM_METADATAS.clear()
        llm_metadata.LLM_METADATAS.update(snapshot_meta)
        llm_metadata.LLM_METADATAS_BY_LOWER.clear()
        for mid, meta in snapshot_meta.items():
            lower_id = mid.lower()
            llm_metadata.LLM_METADATAS_BY_LOWER[lower_id] = meta
            llm_metadata.LLM_METADATAS_BY_LOWER.setdefault(
                lower_id.rsplit("/", 1)[-1], meta
            )
        llm_metadata.LLM_PROVIDER_REASONING_EFFORTS.clear()
        llm_metadata.LLM_PROVIDER_REASONING_EFFORTS.update(snapshot_provider)
        llm_metadata.LLM_CONSENSUS_REASONING_EFFORTS.clear()
        llm_metadata.LLM_CONSENSUS_REASONING_EFFORTS.update(snapshot_consensus)


def test_resolve_model_metadata_maps_aliases_adapter_fallback_and_mixed_case():
    snapshot_meta = dict(llm_metadata.LLM_METADATAS)
    snapshot_lower = dict(llm_metadata.LLM_METADATAS_BY_LOWER)
    snapshot_provider = dict(llm_metadata.LLM_PROVIDER_REASONING_EFFORTS)
    snapshot_consensus = dict(llm_metadata.LLM_CONSENSUS_REASONING_EFFORTS)
    try:
        llm_metadata.populate_llm_metadata(
            {
                "moonshotai": {
                    "models": {
                        "kimi-k3": {
                            "id": "kimi-k3",
                            "reasoning": True,
                            "reasoning_options": [
                                {"type": "effort", "values": ["low", "high", "max"]}
                            ],
                        }
                    }
                },
                "minimax-cn-coding-plan": {
                    "models": {
                        "MiniMax-M3.1-Flash": {
                            "id": "MiniMax-M3.1-Flash",
                            "reasoning": True,
                            "reasoning_options": [
                                {
                                    "type": "effort",
                                    "values": ["low", "medium", "high", "xhigh", "max"],
                                }
                            ],
                        }
                    }
                },
                "xiaomi-token-plan-cn": {
                    "models": {
                        "mimo-v2.5": {
                            "id": "mimo-v2.5",
                            "reasoning": True,
                            "reasoning_options": [{"type": "toggle"}],
                        }
                    }
                },
            }
        )

        moonshot = llm_metadata.resolve_model_metadata(
            "kimi-k3",
            provider="moonshot",
            adapter_type="openai_chat_completion",
        )
        assert moonshot is not None
        assert moonshot["reasoning_efforts"] == ["low", "high", "max"]

        # Mixed-case prefixed ID still resolves base_meta and provider efforts.
        minimax = llm_metadata.resolve_model_metadata(
            "minimax/MiniMax-M3.1-Flash",
            provider="minimax-token-plan",
            adapter_type="minimax_token_plan",
        )
        assert minimax is not None
        assert minimax["id"] == "MiniMax-M3.1-Flash"
        assert minimax["reasoning_efforts"] == [
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        ]

        # Unmapped provider brand falls through to adapter_type mapping.
        xiaomi_custom = llm_metadata.resolve_model_metadata(
            "mimo-v2.5",
            provider="my-xiaomi-plan",
            adapter_type="xiaomi_token_plan",
        )
        assert xiaomi_custom is not None
        assert xiaomi_custom["reasoning_efforts"] == []
    finally:
        llm_metadata.LLM_METADATAS.clear()
        llm_metadata.LLM_METADATAS.update(snapshot_meta)
        llm_metadata.LLM_METADATAS_BY_LOWER.clear()
        llm_metadata.LLM_METADATAS_BY_LOWER.update(snapshot_lower)
        llm_metadata.LLM_PROVIDER_REASONING_EFFORTS.clear()
        llm_metadata.LLM_PROVIDER_REASONING_EFFORTS.update(snapshot_provider)
        llm_metadata.LLM_CONSENSUS_REASONING_EFFORTS.clear()
        llm_metadata.LLM_CONSENSUS_REASONING_EFFORTS.update(snapshot_consensus)


@pytest.mark.asyncio
async def test_tool_loop_agent_runner_strips_reasoning_effort_for_fallback_provider():
    from astrbot.core.agent.run_context import ContextWrapper
    from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
    from astrbot.core.provider.entities import LLMResponse

    runner = ToolLoopAgentRunner()
    runner.req = ProviderRequest(
        prompt="hi",
        session_id="s1",
        model="deepseek-flash",
        extra_body={"reasoning_effort": "max", "custom_flag": True},
    )
    runner.streaming = False
    runner.request_max_retries = 1
    runner._abort_signal = None
    runner.run_context = ContextWrapper(
        context=None, messages=[{"role": "user", "content": "hi"}]
    )
    runner._func_tool_for_provider = lambda: None

    captured_payloads: list[dict] = []

    async def fake_recorded(payload, *, contexts, streaming):
        captured_payloads.append(dict(payload))
        yield LLMResponse(role="assistant", completion_text="ok")

    runner._recorded_responses = fake_recorded

    async for _ in runner._iter_llm_responses(include_model=True):
        pass
    async for _ in runner._iter_llm_responses(include_model=False):
        pass

    assert captured_payloads[0]["model"] == "deepseek-flash"
    assert captured_payloads[0]["extra_body"] == {
        "reasoning_effort": "max",
        "custom_flag": True,
    }
    assert "model" not in captured_payloads[1]
    assert captured_payloads[1]["extra_body"] == {"custom_flag": True}


@pytest.mark.asyncio
async def test_tool_loop_agent_runner_multi_turn_fallback_never_reinjects_effort():
    from astrbot.core.agent.run_context import ContextWrapper
    from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
    from astrbot.core.provider.entities import LLMResponse

    primary = SimpleNamespace(provider_config={"id": "primary-deepseek"})
    fallback = SimpleNamespace(provider_config={"id": "fallback-xiaomi"})
    runner = ToolLoopAgentRunner()
    runner.provider = primary
    runner.fallback_providers = [fallback]
    runner.req = ProviderRequest(
        prompt="hi",
        session_id="s1",
        model="deepseek-flash",
        extra_body={"reasoning_effort": "max", "custom_flag": True},
    )
    runner.streaming = False
    runner.request_max_retries = 1
    runner._abort_signal = None
    runner._is_stop_requested = lambda: False
    runner._sanitize_malformed_tool_calls = lambda _resp: None
    runner.run_context = ContextWrapper(
        context=None, messages=[{"role": "user", "content": "hi"}]
    )
    runner._func_tool_for_provider = lambda: None

    captured_calls: list[tuple[str, dict]] = []

    async def fake_recorded(payload, *, contexts, streaming):
        pid = runner.provider.provider_config["id"]
        captured_calls.append((pid, dict(payload)))
        if runner.provider is primary:
            yield LLMResponse(role="err", completion_text="primary down")
        else:
            yield LLMResponse(role="assistant", completion_text="fallback ok")

    runner._recorded_responses = fake_recorded

    # Turn 1: primary fails, switches to fallback.
    async for _ in runner._iter_llm_responses_with_fallback():
        pass
    # Turn 2 (after tool call): fallback is now at candidates[0] and must NOT
    # receive primary's model or reasoning_effort.
    async for _ in runner._iter_llm_responses_with_fallback():
        pass

    assert captured_calls[0][0] == "primary-deepseek"
    assert captured_calls[0][1]["model"] == "deepseek-flash"
    assert captured_calls[0][1]["extra_body"] == {
        "reasoning_effort": "max",
        "custom_flag": True,
    }
    assert captured_calls[1][0] == "fallback-xiaomi"
    assert "model" not in captured_calls[1][1]
    assert captured_calls[1][1]["extra_body"] == {"custom_flag": True}
    assert captured_calls[2][0] == "fallback-xiaomi"
    assert captured_calls[2][1]["model"] is None
    assert captured_calls[2][1]["extra_body"] == {"custom_flag": True}


@pytest.mark.asyncio
async def test_tool_loop_agent_runner_skills_like_forwards_extra_body():
    from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
    from astrbot.core.agent.tool import FunctionTool, ToolSet
    from astrbot.core.provider.entities import LLMResponse

    class DummyTool(FunctionTool):
        def __init__(self) -> None:
            super().__init__(
                name="lookup",
                description="Look up info",
                parameters={"type": "object", "properties": {}},
            )

        async def call(self, context, **kwargs):
            return "ok"

    tool_set = ToolSet([DummyTool()])
    runner = ToolLoopAgentRunner()
    runner.req = ProviderRequest(
        prompt="hi",
        session_id="s1",
        model="gpt-5.4",
        func_tool=tool_set,
        extra_body={"reasoning_effort": "low"},
    )
    runner._tool_schema_param_set = tool_set
    runner._abort_signal = None
    runner.request_max_retries = 1
    runner._build_tool_requery_context = lambda *args, **kwargs: [
        {"role": "user", "content": "hi"}
    ]
    runner._sanitize_malformed_tool_calls = lambda _resp: None

    captured_payloads: list[dict] = []

    async def fake_recorded(payload, *, contexts, streaming):
        captured_payloads.append(dict(payload))
        # First re-query returns empty output to trigger the repair re-query too.
        if len(captured_payloads) == 1:
            yield LLMResponse(role="assistant", completion_text="")
        else:
            yield LLMResponse(role="assistant", completion_text="repaired")

    runner._recorded_responses = fake_recorded

    initial_resp = LLMResponse(
        role="tool",
        tools_call_name=["lookup"],
        tools_call_args=[{}],
        tools_call_ids=["call-1"],
    )
    await runner._resolve_tool_exec(initial_resp)

    assert len(captured_payloads) == 2
    assert captured_payloads[0]["extra_body"] == {"reasoning_effort": "low"}
    assert captured_payloads[1]["extra_body"] == {"reasoning_effort": "low"}


def test_resolve_model_metadata_adds_none_for_anthropic_effort_models():
    snapshot_meta = dict(llm_metadata.LLM_METADATAS)
    snapshot_lower = dict(llm_metadata.LLM_METADATAS_BY_LOWER)
    snapshot_provider = dict(llm_metadata.LLM_PROVIDER_REASONING_EFFORTS)
    snapshot_consensus = dict(llm_metadata.LLM_CONSENSUS_REASONING_EFFORTS)
    try:
        llm_metadata.populate_llm_metadata(
            {
                "anthropic": {
                    "models": {
                        "claude-sonnet-4-6": {
                            "id": "claude-sonnet-4-6",
                            "reasoning": True,
                            "reasoning_options": [
                                {
                                    "type": "effort",
                                    "values": ["low", "medium", "high", "max"],
                                },
                                {"type": "budget_tokens", "min": 1024},
                            ],
                        },
                        "claude-sonnet-4-5": {
                            "id": "claude-sonnet-4-5",
                            "reasoning": True,
                            "reasoning_options": [
                                {"type": "budget_tokens", "min": 1024}
                            ],
                        },
                    }
                }
            }
        )

        sonnet_46 = llm_metadata.resolve_model_metadata(
            "claude-sonnet-4-6",
            provider="anthropic",
            adapter_type="anthropic_chat_completion",
        )
        assert sonnet_46 is not None
        assert sonnet_46["reasoning_efforts"] == [
            "none",
            "low",
            "medium",
            "high",
            "max",
        ]

        sonnet_45 = llm_metadata.resolve_model_metadata(
            "claude-sonnet-4-5",
            provider="anthropic",
            adapter_type="anthropic_chat_completion",
        )
        assert sonnet_45 is not None
        assert sonnet_45["reasoning_efforts"] == []
    finally:
        llm_metadata.LLM_METADATAS.clear()
        llm_metadata.LLM_METADATAS.update(snapshot_meta)
        llm_metadata.LLM_METADATAS_BY_LOWER.clear()
        llm_metadata.LLM_METADATAS_BY_LOWER.update(snapshot_lower)
        llm_metadata.LLM_PROVIDER_REASONING_EFFORTS.clear()
        llm_metadata.LLM_PROVIDER_REASONING_EFFORTS.update(snapshot_provider)
        llm_metadata.LLM_CONSENSUS_REASONING_EFFORTS.clear()
        llm_metadata.LLM_CONSENSUS_REASONING_EFFORTS.update(snapshot_consensus)


@pytest.mark.asyncio
async def test_chat_service_session_and_thread_expose_backend_resolved_default_provider():
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock

    from astrbot.core.provider.entities import ProviderType
    from astrbot.dashboard.services.chat_service import ChatService

    class FakeDB:
        async def get_platform_session_by_id(self, session_id):
            return SimpleNamespace(
                session_id=session_id,
                platform_id="webchat",
                creator="alice",
                display_name="Chat",
                is_group=0,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )

        async def get_project_by_session(self, **kwargs):
            return None

        async def get_webchat_threads_by_parent_session(self, **kwargs):
            return []

        async def get_webchat_thread_by_id(self, thread_id):
            return SimpleNamespace(
                thread_id=thread_id,
                parent_session_id="sess-1",
                parent_message_id=1,
                base_event_id=None,
                creator="alice",
                selected_text="quote",
                title="Thread",
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )

    class FakeHistoryMgr:
        async def get(self, **kwargs):
            return []

        async def count(self, **kwargs):
            return 0

    resolved_by_umo = {
        "webchat:FriendMessage:webchat!alice!sess-1": "provider-override-b",
        "webchat:FriendMessage:webchat!alice!thread-1": "provider-thread-c",
    }

    async def fake_get_using_provider_async(provider_type, umo=None):
        assert provider_type == ProviderType.CHAT_COMPLETION
        pid = resolved_by_umo.get(umo)
        return SimpleNamespace(provider_config={"id": pid}) if pid else None

    service = object.__new__(ChatService)
    service.db = FakeDB()
    service.platform_history_mgr = FakeHistoryMgr()
    service.running_convs = {}
    service.get_active_chat_runs = lambda _u, _s: []
    service.add_history_capabilities = AsyncMock()
    service.core_lifecycle = SimpleNamespace(
        astrbot_config_mgr=SimpleNamespace(
            get_conf=lambda _umo: {"agent": {"runtime": "astrbot"}}
        ),
        provider_manager=SimpleNamespace(
            get_using_provider_async=fake_get_using_provider_async
        ),
    )

    session_data = await service.get_session("alice", "sess-1", page=1, page_size=1)
    assert session_data["agent_runner_type"] == "astrbot"
    assert session_data["default_provider_id"] == "provider-override-b"

    thread_data = await service.get_thread("alice", "thread-1")
    assert thread_data["agent_runner_type"] == "astrbot"
    assert thread_data["default_provider_id"] == "provider-thread-c"
