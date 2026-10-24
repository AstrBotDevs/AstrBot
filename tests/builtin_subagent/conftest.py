import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio

from astrbot.builtin_stars.astrbot_plugin_subagent.context import SubAgentContext
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.cron.events import CronMessageEvent
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.star.context import Context
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import star_handlers_registry


@pytest_asyncio.fixture
async def environment(tmp_path, request):
    """Use the real SDK context, SQLite storage, and event queue without a model API."""
    db = SQLiteDatabase(str(tmp_path / "runtime.db"))
    await db.initialize()
    queue = asyncio.Queue()
    manager = FunctionToolManager()
    conversation = SimpleNamespace(
        cid="original",
        user_id=getattr(request, "param", "test:FriendMessage:alice"),
        history="[]",
        token_usage=0,
    )
    context = Context(
        queue,
        {},
        db,
        SimpleNamespace(llm_tools=manager),
        MagicMock(),
        SimpleNamespace(
            get_conversation=AsyncMock(return_value=conversation),
            get_curr_conversation_id=AsyncMock(return_value=conversation.cid),
        ),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    context.get_config = lambda **kwargs: {}
    context.get_current_chat_provider_id = AsyncMock(return_value="model")
    context.provider_manager.provider_insts = [
        SimpleNamespace(
            provider_config={"id": provider_id},
            get_model=lambda: "example-model",
        )
        for provider_id in ("model", "alternate")
    ]
    event = CronMessageEvent(
        context=context,
        session=MessageSession.from_str(conversation.user_id),
        message_type=MessageSession.from_str(conversation.user_id).message_type,
        message="Original task",
    )
    config = {"enabled": True, "agents": []}
    module = importlib.import_module(
        "astrbot.builtin_stars.astrbot_plugin_subagent.main"
    )
    if module.__name__ not in star_map:
        module = importlib.reload(module)
    Main = module.Main
    plugin = Main(context, config)
    handlers = [
        item
        for item in star_handlers_registry
        if item.handler_module_path == Main.__module__
    ]
    originals = {item.handler_full_name: item.handler for item in handlers}
    for handler in handlers:
        handler.handler = getattr(plugin, handler.handler_name)
    metadata = star_map[Main.__module__]
    previous_name = metadata.name
    previous_reserved = metadata.reserved
    metadata.name = "astrbot_plugin_subagent"
    metadata.reserved = True
    await plugin.initialize()
    parent = SubAgentContext(
        context=context, event=event, conversation_id=conversation.cid
    )
    await plugin.orchestrator.store.bind(parent)
    wrapper = ContextWrapper(context=parent)
    runtime = parent.subagent_runtime
    runtime.parent_context = wrapper
    env = SimpleNamespace(
        db=db,
        queue=queue,
        manager=manager,
        conversation=conversation,
        context=context,
        event=event,
        config=config,
        plugin=plugin,
        wrapper=wrapper,
        runtime=runtime,
    )
    try:
        yield env
    finally:
        await plugin.terminate()
        for handler in handlers:
            handler.handler = originals[handler.handler_full_name]
        metadata.name = previous_name
        metadata.reserved = previous_reserved
        await db.engine.dispose()
