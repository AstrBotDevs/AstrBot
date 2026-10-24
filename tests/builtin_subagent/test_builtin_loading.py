from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


async def _probe_builtin_loading(root: Path) -> None:
    """Exercise the real built-in loader in an isolated process.

    Args:
        root: Temporary runtime root for configuration and database files.
    """
    from astrbot.builtin_stars.astrbot_plugin_subagent.tools import SUBAGENT_TOOL_NAMES
    from astrbot.core import sp
    from astrbot.core.agent.run_context import ContextWrapper
    from astrbot.core.astr_agent_context import AstrAgentContext
    from astrbot.core.cron.events import CronMessageEvent
    from astrbot.core.db.sqlite import SQLiteDatabase
    from astrbot.core.pipeline.context_utils import call_event_hook
    from astrbot.core.platform.message_session import MessageSession
    from astrbot.core.provider.entities import LLMResponse, ProviderRequest
    from astrbot.core.provider.register import llm_tools
    from astrbot.core.star.context import Context
    from astrbot.core.star.star_handler import EventType
    from astrbot.core.star.star_manager import PluginManager
    from astrbot.dashboard.services.plugin_page_service import PluginPageService

    (root / "data/config").mkdir(parents=True)
    db = SQLiteDatabase(str(root / "runtime.db"))
    await db.initialize()
    conversation = SimpleNamespace(
        cid="builtin", user_id="test:FriendMessage:alice", history="[]", token_usage=0
    )
    context = Context(
        asyncio.Queue(),
        {},
        db,
        SimpleNamespace(
            llm_tools=llm_tools,
            provider_insts=[
                SimpleNamespace(
                    provider_config={"id": "model"}, get_model=lambda: "test-model"
                )
            ],
        ),
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
    context.tool_loop_agent = AsyncMock(
        return_value=LLMResponse(
            role="assistant", completion_text="Builtin worker completed"
        )
    )
    manager = PluginManager(context, {})
    metadata = None
    try:
        modules = manager._get_plugin_modules()
        builtin = next(
            item for item in modules if item["pname"] == "astrbot_plugin_subagent"
        )
        assert builtin["reserved"] is True
        with (
            patch.object(
                sp,
                "global_get",
                AsyncMock(side_effect=lambda key, default=None: default),
            ),
            patch("astrbot.core.star.star_manager.sync_command_configs", AsyncMock()),
        ):
            success, error = await manager.load(
                specified_dir_name="astrbot_plugin_subagent"
            )
            assert success, error
            metadata = context.get_registered_star("astrbot_plugin_subagent")
            assert metadata is not None and metadata.reserved and metadata.activated
            assert (
                metadata.module_path
                == "astrbot.builtin_stars.astrbot_plugin_subagent.main"
            )
            assert metadata.config["max_concurrent_agents"] == 3
            assert Path(metadata.config.config_path).parent == root / "data/config"
            assert metadata.i18n["zh-CN"]["views"]["runtime"]["title"] == "子代理管理"
            assert SUBAGENT_TOOL_NAMES <= set(llm_tools.get_full_tool_set().names())
            pages = await PluginPageService(manager).discover_plugin_pages(metadata)
            assert [page.name for page in pages] == ["runtime"]
            assert {route[0] for route in context.registered_web_apis} >= {
                "/astrbot_plugin_subagent/runtime",
                "/astrbot_plugin_subagent/experts",
            }
            event = CronMessageEvent(
                context=context,
                session=MessageSession.from_str(conversation.user_id),
                message_type=MessageSession.from_str(conversation.user_id).message_type,
                message="Delegate a task",
            )
            request = ProviderRequest(conversation=conversation)
            await call_event_hook(event, EventType.OnLLMRequestEvent, request)
            wrapper = ContextWrapper(
                context=AstrAgentContext(context=context, event=event)
            )
            wrapper.runner = SimpleNamespace(req=request)
            await call_event_hook(event, EventType.OnAgentBeginEvent, wrapper)
            spawn = request.func_tool.get_tool("spawn_agent")
            receipt = json.loads(
                await spawn.call(
                    wrapper,
                    task="Check built-in execution",
                    name="builtin-worker",
                    provider_id="model",
                )
            )
            worker = wrapper.context.subagent_runtime.get_instance(receipt["agent_id"])
            await asyncio.wait_for(worker.execution_task, 3)
            assert (
                receipt["name"] == "builtin-worker"
                and receipt["provider_id"] == "model"
            )
            assert worker.result == "Builtin worker completed"
            assert worker.to_dict()["provider_id"] == "model"
            await call_event_hook(event, EventType.OnAgentDoneEvent, wrapper, None)
    finally:
        if metadata is not None and metadata.star_cls is not None:
            await metadata.star_cls.terminate()
        await db.engine.dispose()


def test_builtin_loads_configuration_views_hooks_and_worker(tmp_path: Path) -> None:
    """Load the shipped extension without sharing global plugin registries."""
    project = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "ASTRBOT_ROOT": str(tmp_path),
        "PYTHONPATH": os.pathsep.join(
            filter(None, (str(project), os.environ.get("PYTHONPATH")))
        ),
    }
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), str(tmp_path)],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    asyncio.run(_probe_builtin_loading(Path(sys.argv[1])))
