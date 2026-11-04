import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest_asyncio

from astrbot.core.agent.input import PlainInput, format_input_content
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runtime import (
    AgentPermissions,
    AgentRuntime,
    AgentSession,
    AgentSessionRef,
    TurnResult,
)
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_runtime import AstrAgentRuntime
from astrbot.core.astr_agent_runtime.context import AstrAgentContext
from astrbot.core.astr_agent_runtime.main_agent import subagent
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.provider.provider import Provider
from astrbot.core.star.context import Context
from astrbot.core.subagents.caller import DelegatedAgentInput
from astrbot.core.subagents.messages import format_agent_messages
from astrbot.core.subagents.service import SubAgentService
from astrbot.core.subagents.store import SubAgentStore


class MemorySession(AgentSession):
    """Independent conversation used to verify the runtime boundary."""

    def __init__(self, runtime, session_id, umo):
        super().__init__(session_id, umo)
        self.runtime = runtime

    async def execute_turn(self, turn):
        self.runtime.inputs.append(turn.input)
        content = turn.input.content
        messages = [item.model_dump(exclude_none=True) for item in content]
        self.runtime.sessions[self.id].append(copy.deepcopy(messages))
        await self.runtime.started.put((self.id, messages))
        if self.runtime.release is not None:
            await self.runtime.release.wait()
        if self.runtime.failure:
            raise self.runtime.failure
        turn.emit("step_completed", {"steps": 1})
        return TurnResult(text=format_input_content(content))

    async def cancel_turn(self, turn):
        self.runtime.cancelled.append(self.id)

    async def history(self):
        return [
            {"role": "user", "content": format_agent_messages(messages)}
            for messages in self.runtime.sessions[self.id]
        ]


class MemoryAgentRuntime(AgentRuntime):
    """A foreign runtime with no native model or tool execution."""

    def __init__(self):
        self.sessions = {}
        self.inputs = []
        self.handles = {}
        self.started = asyncio.Queue()
        self.release = None
        self.cancelled = []
        self.failure = None

    async def open_session(self, umo, *, session_id=None, options=None, input=None):
        if session_id is None:
            session_id = "remote-" + uuid4().hex
            self.sessions[session_id] = []
        if session_id not in self.handles or self.handles[session_id]._closed:
            self.handles[session_id] = MemorySession(self, session_id, umo)
        return self.handles[session_id]

    async def close(self):
        await asyncio.gather(*(handle.close() for handle in self.handles.values()))


@pytest_asyncio.fixture
async def environment(tmp_path, request):
    """Bind real SDK tools, SQLite storage, native execution, and a foreign runner."""
    db = SQLiteDatabase(str(tmp_path / "agents.db"))
    await db.initialize()
    manager = FunctionToolManager()
    conversation = SimpleNamespace(
        cid="original",
        user_id=getattr(request, "param", "test:FriendMessage:alice"),
        history="[]",
        token_usage=0,
    )
    context = Context(
        asyncio.Queue(),
        {},
        db,
        SimpleNamespace(llm_tools=manager),
        MagicMock(),
        SimpleNamespace(
            get_conversation=AsyncMock(return_value=conversation),
            get_curr_conversation_id=AsyncMock(return_value=conversation.cid),
            update_conversation=AsyncMock(),
        ),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    context.platform_manager.platform_insts = [
        SimpleNamespace(
            meta=lambda: PlatformMetadata(id="test", name="test", description="Test")
        )
    ]
    context.persona_manager.get_persona_v3_by_id.return_value = None
    provider = MagicMock(spec=Provider)
    provider.provider_config = {"id": "model", "modalities": ["image", "tool_use"]}
    provider.get_model.return_value = "test-model"
    provider.text_chat = AsyncMock(
        return_value=LLMResponse(role="assistant", completion_text="Done")
    )
    context.provider_manager.get_provider_by_id = AsyncMock(return_value=provider)
    context.provider_manager.provider_insts = [
        SimpleNamespace(provider_config={"id": name}, get_model=lambda: "test-model")
        for name in ("model", "alternate")
    ]
    context.get_current_chat_provider_id = AsyncMock(return_value="model")
    config = {
        "enabled": True,
        "config_ids": [],
        "agents": [],
        "max_concurrent_agents": 3,
        "task_timeout": 600,
        "max_steps": 30,
    }
    context.get_config = lambda **kwargs: {
        "agent": {"runtime": "astrbot", "config": {"subagents": config}}
    }
    event = AgentWakeupEvent(
        context=context,
        session=MessageSession.from_str(conversation.user_id),
        platform_meta=context.get_platform_inst("test").meta(),
        source="plugin",
        prompt="Main task",
    )
    event.message_obj.sender.user_id = "alice"
    native, memory = AstrAgentRuntime(context), MemoryAgentRuntime()
    context.agent_runtime = native
    service = SubAgentService(SubAgentStore(db), {"astrbot": native})
    service.register_runtime("memory", memory)
    context.subagents = service
    context.agent_runtimes = service.runtimes
    await subagent.initialize_subagents(context)
    wrapper = ContextWrapper(
        context=AstrAgentContext(
            context=context,
            event=event,
            agent_session=AgentSessionRef("astrbot", conversation.cid),
        )
    )
    wrapper.runner = SimpleNamespace(
        req=ProviderRequest(conversation=conversation, func_tool=ToolSet())
    )
    await subagent.begin_main_agent(wrapper)

    async def save_agent(name="worker", *, runtime="astrbot", config=None, **legacy):
        from astrbot.core.agent.config import StoredAgentConfig

        runtime_config = config or {}
        if legacy:
            runtime_config = {
                "model": {"provider_id": legacy.get("provider_id") or ""},
                "persona": {
                    "persona_id": legacy.get("persona_id") or "",
                    "system_prompt": legacy.get("system_prompt", ""),
                    "tools": legacy.get("tools"),
                },
            }
        record = StoredAgentConfig(
            config_id=str(uuid4()),
            name=name,
            runtime=runtime,
            config=context.agent_runtimes[runtime].normalize_config(
                runtime_config, delegated=True
            ),
        )
        await context.agent_configs.save(record)
        config_ids = context.get_config()["agent"]["config"]["subagents"]["config_ids"]
        config_ids.append(record.config_id)
        return record

    env = SimpleNamespace(
        save_agent=save_agent,
        db=db,
        manager=manager,
        conversation=conversation,
        context=context,
        event=event,
        config=config,
        provider=provider,
        service=service,
        store=service.store,
        native=native,
        memory=memory,
        wrapper=wrapper,
        root=wrapper.context,
        scope=wrapper.context.subagent_scope,
        caller=service.delivery.callers[wrapper.context.subagent_scope],
        input=DelegatedAgentInput(
            event=event,
            permissions=AgentPermissions.from_event(event),
            content=[PlainInput(text="Task")],
            caller=service.delivery.callers[wrapper.context.subagent_scope],
        ),
    )
    try:
        yield env
    finally:
        await context.subagents.close()
        await db.engine.dispose()
