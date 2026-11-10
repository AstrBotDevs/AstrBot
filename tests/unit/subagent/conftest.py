import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest_asyncio

from astrbot.core.agent.config_store import AgentConfigStore
from astrbot.core.agent.events import ExecutionMetrics
from astrbot.core.agent.input import format_input_content
from astrbot.core.agent.output import PlainOutput
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runtime import (
    AgentRuntime,
    AgentSession,
    AgentSessionRef,
    TurnResult,
)
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_runtime import AstrAgentRuntime
from astrbot.core.astr_agent_runtime.context import AstrAgentContext
from astrbot.core.astr_agent_runtime.main_agent import subagent
from astrbot.core.astr_agent_runtime.subagents.messages import format_agent_messages
from astrbot.core.astr_agent_runtime.subagents.service import SubAgentService
from astrbot.core.astr_agent_runtime.subagents.store import SubAgentStore
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.provider.provider import Provider
from astrbot.core.star.context import Context


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

        return TurnResult(
            content=(PlainOutput(text=format_input_content(content)),),
            metrics=ExecutionMetrics(steps=1),
        )

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
    runtimes = {}
    agent_configs = AgentConfigStore(db)
    service = SubAgentService(SubAgentStore(db), runtimes)
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
        agent_runtimes=runtimes,
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
    native = AstrAgentRuntime(context, agent_configs=agent_configs, subagents=service)
    memory = MemoryAgentRuntime()
    context.agent.register_runtime("astrbot", native)
    context.agent.register_runtime("memory", memory)
    await service.start(context)
    wrapper = ContextWrapper(
        context=AstrAgentContext(
            context=context,
            event=event,
            agent_session=AgentSessionRef("astrbot", conversation.cid),
            _runtime=native,
        )
    )
    await subagent.begin_main_agent(
        wrapper, conversation_id=conversation.cid, tools=ToolSet()
    )

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
            config=runtimes[runtime].normalize_config(runtime_config, delegated=True),
        )
        await agent_configs.save(record)
        config_ids = context.get_config()["agent"]["config"]["subagents"]["config_ids"]
        config_ids.append(record.config_id)
        return record

    env = SimpleNamespace(
        save_agent=save_agent,
        agent_configs=agent_configs,
        runtimes=runtimes,
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
    )
    try:
        yield env
    finally:
        await service.close()
        await db.engine.dispose()
