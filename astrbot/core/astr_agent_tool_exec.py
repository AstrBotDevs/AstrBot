import asyncio
import inspect
import json
import time
import traceback
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from collections.abc import Set as AbstractSet
from typing import Any

import mcp

from astrbot import logger
from astrbot.core import astrbot_config as _astrbot_config
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.message import Message
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolSchema, ToolSet
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.astr_main_agent_resources import (
    BACKGROUND_TASK_RESULT_WOKE_SYSTEM_PROMPT,
    BACKGROUND_TASK_WOKE_USER_PROMPT,
    CONVERSATION_HISTORY_INJECT_PREFIX,
)
from astrbot.core.computer.sandbox_tool_binding import tool_available_in_runtime
from astrbot.core.cron.events import CronMessageEvent
from astrbot.core.message.components import Image
from astrbot.core.message.message_event_result import (
    CommandResult,
    MessageChain,
    MessageEventResult,
)
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.provider.entites import ProviderRequest
from astrbot.core.provider.register import llm_tools
from astrbot.core.subagent_manager import SubAgentManager
from astrbot.core.tools.computer_tools import (
    CopyFileBetweenSandboxesTool,
    CreateSandboxTool,
    DestroySandboxTool,
    ExecuteShellTool,
    FileDownloadTool,
    FileEditTool,
    FileReadTool,
    FileUploadTool,
    FileWriteTool,
    GetCurrentSandboxTool,
    GrepTool,
    KeepAliveSandboxTool,
    ListSandboxesTool,
    ListSandboxProvidersTool,
    LocalPythonTool,
    PythonTool,
    ReleaseSandboxTool,
    ScreenshotSandboxTool,
    SetSandboxRetentionPolicyTool,
    SwitchSandboxTool,
    TakeoverSandboxTool,
)
from astrbot.core.tools.message_tools import SendMessageToUserTool
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.history_saver import persist_agent_history
from astrbot.core.utils.image_ref_utils import is_supported_image_ref
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings
from astrbot.core.utils.trace import _current_span as _trace_current_span


class FunctionToolExecutor(BaseFunctionToolExecutor[AstrAgentContext]):
    _runtime_computer_tools_cache: dict[
        tuple[int, str, str], dict[str, FunctionTool]
    ] = {}

    @classmethod
    def clear_runtime_computer_tools_cache(cls, provider_id: str | None = None) -> None:
        if provider_id is None:
            cls._runtime_computer_tools_cache.clear()
            return

        normalized_provider_id = str(provider_id).strip().lower()
        if not normalized_provider_id:
            return

        keys_to_remove = [
            key
            for key in cls._runtime_computer_tools_cache
            if key[2] == normalized_provider_id
        ]
        for key in keys_to_remove:
            cls._runtime_computer_tools_cache.pop(key, None)

    @classmethod
    def _collect_image_urls_from_args(cls, image_urls_raw: T.Any) -> list[str]:
        if image_urls_raw is None:
            return []
        if isinstance(image_urls_raw, str):
            return [image_urls_raw]
        if isinstance(image_urls_raw, (Sequence, AbstractSet)) and (
            not isinstance(image_urls_raw, (str, bytes, bytearray))
        ):
            return [item for item in image_urls_raw if isinstance(item, str)]
        logger.debug(
            "Unsupported image_urls type in handoff tool args: %s",
            type(image_urls_raw).__name__,
        )
        return []

    @classmethod
    async def _collect_image_urls_from_message(
        cls,
        run_context: ContextWrapper[AstrAgentContext],
    ) -> list[str]:
        urls: list[str] = []
        event = getattr(run_context.context, "event", None)
        message_obj = getattr(event, "message_obj", None)
        message = getattr(message_obj, "message", None)
        if message:
            for idx, component in enumerate(message):
                if not isinstance(component, Image):
                    continue
                try:
                    path = await component.convert_to_file_path()
                    if path:
                        urls.append(path)
                except Exception as e:
                    logger.error(
                        "Failed to convert handoff image component at index %d: %s",
                        idx,
                        e,
                        exc_info=True,
                    )
        return urls

    @classmethod
    async def _collect_handoff_image_urls(
        cls,
        run_context: ContextWrapper[AstrAgentContext],
        image_urls_raw: Any,
    ) -> list[str]:
        candidates: list[str] = []
        candidates.extend(cls._collect_image_urls_from_args(image_urls_raw))
        candidates.extend(await cls._collect_image_urls_from_message(run_context))
        normalized = normalize_and_dedupe_strings(candidates)
        extensionless_local_roots = (get_astrbot_temp_path(),)
        sanitized = [
            item
            for item in normalized
            if is_supported_image_ref(
                item,
                allow_extensionless_existing_local_file=True,
                extensionless_local_roots=extensionless_local_roots,
            )
        ]
        dropped_count = len(normalized) - len(sanitized)
        if dropped_count > 0:
            logger.debug(
                "Dropped %d invalid image_urls entries in handoff image inputs.",
                dropped_count,
            )
        return sanitized

    @classmethod
    async def execute(cls, tool, run_context, **tool_args):
        """执行函数调用｡

        Args:
            tool: The tool to execute.
            run_context: The run context.
            **tool_args: Tool-specific arguments.
            **kwargs: 函数调用的参数｡

        Returns:
            AsyncGenerator[None | mcp.types.CallToolResult, None]

        """
        if isinstance(tool, HandoffTool):
            is_bg, bg_error = cls._parse_background_task_arg(
                tool.name,
                tool_args.pop("background_task", None),
            )
            if bg_error is not None:
                yield bg_error
                return
            if is_bg:
                async for r in cls._execute_handoff_background(
                    tool,
                    run_context,
                    **tool_args,
                ):
                    yield r
                return
            async for r in cls._execute_handoff(tool, run_context, **tool_args):
                yield r
            return
        elif isinstance(tool, MCPTool):
            async for r in cls._execute_mcp(tool, run_context, **tool_args):
                yield r
            return
        elif tool.is_background_task:
            task_id = uuid.uuid4().hex

            async def _run_in_background() -> None:
                try:
                    await cls._execute_background(
                        tool=tool,
                        run_context=run_context,
                        task_id=task_id,
                        **tool_args,
                    )
                except Exception as e:
                    logger.error(
                        f"Background task {task_id} failed: {e!s}",
                        exc_info=True,
                    )

            asyncio.create_task(_run_in_background())
            text_content = mcp.types.TextContent(
                type="text",
                text=f"Background task submitted. task_id={task_id}",
            )
            yield mcp.types.CallToolResult(content=[text_content])
            return
        else:
            rejection = cls._check_sandbox_capability(tool, run_context)
            if rejection is not None:
                yield rejection
                return
            async for r in cls._execute_local(tool, run_context, **tool_args):
                yield r
            return

    _BROWSER_TOOL_NAMES: frozenset[str] = frozenset(
        {
            "astrbot_execute_browser",
            "astrbot_execute_browser_batch",
            "astrbot_run_browser_skill",
        },
    )

    @classmethod
    def _check_sandbox_capability(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[AstrAgentContext],
    ) -> mcp.types.CallToolResult | None:
        """Return a rejection result if the tool requires a sandbox capability
        that is not available, or None if the tool may proceed.
        """
        if tool.name not in cls._BROWSER_TOOL_NAMES:
            return None
        from astrbot.core.computer.computer_client import get_sandbox_capabilities

        session_id = run_context.context.event.unified_msg_origin
        caps = get_sandbox_capabilities(session_id)
        if caps is None:
            return None
        if "browser" not in caps:
            msg = f"Tool '{tool.name}' requires browser capability, but the current sandbox profile does not include it (capabilities: {list(caps)}). Please ask the administrator to switch to a sandbox profile with browser support, or use shell/python tools instead."
            logger.warning(
                "[ToolExec] capability_rejected tool=%s caps=%s",
                tool.name,
                list(caps),
            )
            return mcp.types.CallToolResult(
                content=[mcp.types.TextContent(type="text", text=msg)],
                isError=True,
            )
        return None

    @classmethod
    def _get_runtime_computer_tools(
        cls,
        runtime: str,
        tool_mgr: Any = None,
        booter: str | None = None,
    ) -> dict[str, FunctionTool]:
        booter = "" if booter is None else str(booter).lower()
        cache_key = (id(tool_mgr), runtime, booter)
        if cache_key in cls._runtime_computer_tools_cache:
            return cls._runtime_computer_tools_cache[cache_key]
        if runtime == "sandbox":
            shell_tool = tool_mgr.get_builtin_tool(ExecuteShellTool)
            list_sandboxes_tool = tool_mgr.get_builtin_tool(ListSandboxesTool)
            list_sandbox_providers_tool = tool_mgr.get_builtin_tool(
                ListSandboxProvidersTool
            )
            get_current_sandbox_tool = tool_mgr.get_builtin_tool(GetCurrentSandboxTool)
            create_sandbox_tool = tool_mgr.get_builtin_tool(CreateSandboxTool)
            switch_sandbox_tool = tool_mgr.get_builtin_tool(SwitchSandboxTool)
            keep_alive_sandbox_tool = tool_mgr.get_builtin_tool(KeepAliveSandboxTool)
            release_sandbox_tool = tool_mgr.get_builtin_tool(ReleaseSandboxTool)
            set_sandbox_retention_policy_tool = tool_mgr.get_builtin_tool(
                SetSandboxRetentionPolicyTool
            )
            takeover_sandbox_tool = tool_mgr.get_builtin_tool(TakeoverSandboxTool)
            destroy_sandbox_tool = tool_mgr.get_builtin_tool(DestroySandboxTool)
            screenshot_sandbox_tool = tool_mgr.get_builtin_tool(ScreenshotSandboxTool)
            copy_between_sandboxes_tool = tool_mgr.get_builtin_tool(
                CopyFileBetweenSandboxesTool
            )
            python_tool = tool_mgr.get_builtin_tool(PythonTool)
            upload_tool = tool_mgr.get_builtin_tool(FileUploadTool)
            download_tool = tool_mgr.get_builtin_tool(FileDownloadTool)
            read_tool = tool_mgr.get_builtin_tool(FileReadTool)
            write_tool = tool_mgr.get_builtin_tool(FileWriteTool)
            edit_tool = tool_mgr.get_builtin_tool(FileEditTool)
            grep_tool = tool_mgr.get_builtin_tool(GrepTool)
            tools = {
                shell_tool.name: shell_tool,
                list_sandboxes_tool.name: list_sandboxes_tool,
                list_sandbox_providers_tool.name: list_sandbox_providers_tool,
                get_current_sandbox_tool.name: get_current_sandbox_tool,
                create_sandbox_tool.name: create_sandbox_tool,
                switch_sandbox_tool.name: switch_sandbox_tool,
                keep_alive_sandbox_tool.name: keep_alive_sandbox_tool,
                release_sandbox_tool.name: release_sandbox_tool,
                set_sandbox_retention_policy_tool.name: set_sandbox_retention_policy_tool,
                takeover_sandbox_tool.name: takeover_sandbox_tool,
                destroy_sandbox_tool.name: destroy_sandbox_tool,
                screenshot_sandbox_tool.name: screenshot_sandbox_tool,
                copy_between_sandboxes_tool.name: copy_between_sandboxes_tool,
                python_tool.name: python_tool,
                upload_tool.name: upload_tool,
                download_tool.name: download_tool,
                read_tool.name: read_tool,
                write_tool.name: write_tool,
                edit_tool.name: edit_tool,
                grep_tool.name: grep_tool,
            }
            cls._runtime_computer_tools_cache[cache_key] = tools
            return tools
        if runtime == "local":
            shell_tool = tool_mgr.get_builtin_tool(ExecuteShellTool)
            python_tool = tool_mgr.get_builtin_tool(LocalPythonTool)
            read_tool = tool_mgr.get_builtin_tool(FileReadTool)
            write_tool = tool_mgr.get_builtin_tool(FileWriteTool)
            edit_tool = tool_mgr.get_builtin_tool(FileEditTool)
            grep_tool = tool_mgr.get_builtin_tool(GrepTool)
            tools = {
                shell_tool.name: shell_tool,
                python_tool.name: python_tool,
                read_tool.name: read_tool,
                write_tool.name: write_tool,
                edit_tool.name: edit_tool,
                grep_tool.name: grep_tool,
            }
            cls._runtime_computer_tools_cache[cache_key] = tools
            return tools
        return {}

    @classmethod
    def _build_handoff_toolset(
        cls,
        run_context: ContextWrapper[AstrAgentContext],
        tools: list[str | FunctionTool] | None,
    ) -> ToolSet | None:
        ctx = run_context.context.context
        event = run_context.context.event
        cfg = ctx.get_config(umo=event.unified_msg_origin)
        session_config = await SessionPluginManager.get_session_plugin_config(
            event.unified_msg_origin
        )
        provider_settings = cfg.get("provider_settings", {})
        runtime = str(provider_settings.get("computer_use_runtime", "local"))
        tool_mgr = ctx.get_llm_tool_manager()
        runtime_computer_tools = cls._get_runtime_computer_tools(
            runtime,
            tool_mgr,
        )
        if tools is None:
            toolset = ToolSet()
            # 使用 tool_mgr 代替全局 llm_tools，确保多租户环境一致性
            for registered_tool in tool_mgr.func_list:
                if isinstance(registered_tool, HandoffTool):
                    continue
                if registered_tool.active and tool_available_in_runtime(
                    registered_tool, runtime
                ):
                    toolset.add_tool(registered_tool)
            # 添加计算机工具（根据 computer_use_runtime 配置）
            for runtime_tool in runtime_computer_tools.values():
                toolset.add_tool(runtime_tool)
            # 添加 Web 搜索工具（根据配置）
            cls._apply_web_search_tools(toolset, tool_mgr, cfg)
            return None if toolset.empty() else toolset
        if not tools:
            return None
        toolset = ToolSet()
        for tool_name_or_obj in tools:
            if isinstance(tool_name_or_obj, str):
                registered_tool = llm_tools.get_func(tool_name_or_obj)
                if (
                    registered_tool
                    and registered_tool.active
                    and cls._tool_enabled_for_session(registered_tool, session_config)
                ):
                    toolset.add_tool(registered_tool)
                    continue
                runtime_tool = runtime_computer_tools.get(tool_name_or_obj)
                if runtime_tool:
                    toolset.add_tool(runtime_tool)
            elif isinstance(tool_name_or_obj, FunctionTool):
                toolset.add_tool(tool_name_or_obj)

        # Always add send_shared_context tool for shared context feature
        try:
            from astrbot.core.subagent_manager import (
                SEND_SHARED_CONTEXT_TOOL,
                SubAgentManager,
            )

            session_id = event.unified_msg_origin
            session = SubAgentManager.get_session(session_id)
            if session and session.shared_context_enabled:
                toolset.add_tool(SEND_SHARED_CONTEXT_TOOL)
        except Exception as e:
            logger.debug(f"[SubAgent] Failed to add shared context tool: {e}")

        return None if toolset.empty() else toolset

    @classmethod
    def _build_handoff_system_prompt(
        cls,
        instructions: str | None,
        skill_names: list[str] | None,
        runtime: str,
    ) -> str:
        skills_prompt = cls._build_handoff_skills_prompt(skill_names, runtime)
        parts = [
            part.strip()
            for part in (instructions, skills_prompt)
            if isinstance(part, str) and part.strip()
        ]
        return "\n\n".join(parts)

    @classmethod
    def _build_handoff_skills_prompt(
        cls,
        skill_names: list[str] | None,
        runtime: str,
    ) -> str:
        if skill_names == []:
            return ""

        skills = SkillManager().list_skills(active_only=True, runtime=runtime)
        if skill_names is not None:
            allowed = set(skill_names)
            skills = [skill for skill in skills if skill.name in allowed]

        if not skills:
            return ""
        return build_skills_prompt(skills)

    @classmethod
    async def _execute_handoff(
        cls,
        tool: HandoffTool[Any],
        run_context: ContextWrapper[Any],
        *,
        image_urls_prepared: bool = False,
        **tool_args: Any,
    ):
        tool_args = dict(tool_args)
        input_, input_error = cls._normalize_handoff_input(
            tool.name,
            tool_args.get("input"),
        )
        if input_error is not None:
            yield input_error
            return
        tool_args["input"] = input_
        if image_urls_prepared:
            prepared_image_urls = tool_args.get("image_urls")
            if isinstance(prepared_image_urls, list):
                image_urls = prepared_image_urls
            else:
                logger.debug(
                    "Expected prepared handoff image_urls as list[str], got %s.",
                    type(prepared_image_urls).__name__,
                )
                image_urls = []
        else:
            image_urls = await cls._collect_handoff_image_urls(
                run_context,
                tool_args.get("image_urls"),
            )
        tool_args["image_urls"] = image_urls

        # Build handoff toolset from registered tools plus runtime computer tools.
        toolset = cls._build_handoff_toolset(run_context, tool.agent.tools)
        ctx = run_context.context.context
        event = run_context.context.event
        umo = event.unified_msg_origin

        # Use per-subagent provider override if configured; otherwise fall back
        # to the current/default provider resolution.
        prov_id = await cls._resolve_handoff_provider_id(
            tool,
            ctx=ctx,
            umo=umo,
        )

        # prepare begin dialogs
        contexts = None
        dialogs = tool.agent.begin_dialogs
        if dialogs:
            contexts = []
            for dialog in dialogs:
                try:
                    contexts.append(
                        dialog
                        if isinstance(dialog, Message)
                        else Message.model_validate(dialog),
                    )
                except Exception:
                    continue

        cfg = ctx.get_config(umo=umo)
        prov_settings: dict = cfg.get("provider_settings", {})
        runtime = str(prov_settings.get("computer_use_runtime", "local"))
        system_prompt = cls._build_handoff_system_prompt(
            tool.agent.instructions,
            getattr(tool.agent, "skills", []),
            runtime,
        )
        agent_max_step = int(prov_settings.get("max_agent_step", 30))
        stream = prov_settings.get("streaming_response", False)

        # 获取子代理的历史上下文
        subagent_history, agent_name = cls._load_subagent_history(umo, tool)
        # 如果有历史上下文，合并到 contexts 中
        if subagent_history:
            if contexts is None:
                contexts = subagent_history
            else:
                contexts = subagent_history + contexts

        # 构建子代理的 system_prompt
        subagent_system_prompt = cls._build_subagent_system_prompt(
            umo, tool, prov_settings
        )

        # 构建子代理的追加内容
        extra_content_parts = SubAgentManager.build_subagent_extra_content_parts(
            umo, agent_name
        )

        # 获取子代理的超时时间
        execution_timeout = cls._get_subagent_execution_timeout()

        # 用于存储本轮的完整历史上下文
        runner_messages = []

        # 构建 tool_loop_agent 协程
        async def _run_subagent():
            return await ctx.tool_loop_agent(
                event=event,
                chat_provider_id=prov_id,
                prompt=input_,
                image_urls=image_urls,
                system_prompt=subagent_system_prompt,
                tools=toolset,
                contexts=contexts,
                max_steps=agent_max_step,
                tool_call_timeout=run_context.tool_call_timeout,
                stream=stream,
                runner_messages=runner_messages,
                extra_user_content_parts=extra_content_parts,
            )

        # 添加执行超时控制
        if execution_timeout > 0:
            try:
                llm_resp = await asyncio.wait_for(
                    _run_subagent(), timeout=execution_timeout
                )
            except asyncio.TimeoutError:
                # 若超时，保存已产生的部分历史
                cls._save_subagent_history(umo, runner_messages, agent_name)
                error_msg = f"SubAgent '{agent_name}' execution timeout after {execution_timeout:.1f} seconds."
                logger.warning(f"[SubAgent:Timeout] {error_msg}")

                cls._handle_subagent_timeout(umo=umo, agent_name=agent_name)

                yield mcp.types.CallToolResult(
                    content=[
                        mcp.types.TextContent(type="text", text=f"error: {error_msg}")
                    ]
                )
                return
        else:
            # 不设置超时
            llm_resp = await _run_subagent()
        # 保存历史上下文
        cls._save_subagent_history(umo, runner_messages, agent_name)

        yield mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text=llm_resp.completion_text)],
        )

    @classmethod
    async def _execute_handoff_background(
        cls,
        tool: HandoffTool,
        run_context: ContextWrapper[AstrAgentContext],
        **tool_args,
    ):
        """Execute a handoff as a background task.

        Immediately yields a success response with a task_id, then runs
        the subagent asynchronously.  When the subagent finishes, a
        ``CronMessageEvent`` is created so the main LLM can inform the
        user of the result – the same pattern used by
        ``_execute_background`` for regular background tasks.

        当启用增强SubAgent时，会在 SubAgentManager 中创建 pending 任务，
        并返回 task_id 给主 Agent，以便后续通过 wait_for_subagent 获取结果。
        """
        event = run_context.context.event
        umo = event.unified_msg_origin
        agent_name = getattr(tool.agent, "name", None)

        # check if enhanced subagent
        subagent_task_id = cls._register_subagent_task(umo, agent_name)

        original_task_id = uuid.uuid4().hex

        async def _run_handoff_in_background() -> None:
            try:
                await cls._do_handoff_background(
                    tool=tool,
                    run_context=run_context,
                    task_id=original_task_id,
                    subagent_task_id=subagent_task_id,
                    **tool_args,
                )

            except Exception as e:  # noqa: BLE001
                logger.error(
                    f"Background handoff {original_task_id} ({tool.name}) failed: {e!s}",
                    exc_info=True,
                )

        asyncio.create_task(_run_handoff_in_background())

        text_content = cls._build_background_submission_message(
            agent_name, original_task_id, subagent_task_id
        )
        yield mcp.types.CallToolResult(content=[text_content])

    @classmethod
    async def _do_handoff_background(
        cls,
        tool: HandoffTool,
        run_context: ContextWrapper[AstrAgentContext],
        task_id: str,
        **tool_args,
    ) -> None:
        """Run the subagent handoff.
        当增强版 SubAgent 启用时，结果存储到 SubAgentManager，主 Agent 可通过 wait_for_subagent 获取。
        否则使用原有的 _wake_main_agent_for_background_result 流程。
        """

        start_time = time.time()
        result_text = ""
        error_text = None
        tool_args = dict(tool_args)
        tool_args["image_urls"] = await cls._collect_handoff_image_urls(
            run_context,
            tool_args.get("image_urls"),
        )

        event = run_context.context.event
        umo = event.unified_msg_origin
        agent_name = getattr(tool.agent, "name", None)
        # 获取SubAgent的超时时间
        execution_timeout = cls._get_subagent_execution_timeout()

        try:

            async def _run():
                nonlocal result_text
                async for r in cls._execute_handoff(
                    tool,
                    run_context,
                    image_urls_prepared=True,
                    **tool_args,
                ):
                    if isinstance(r, mcp.types.CallToolResult):
                        for content in r.content:
                            if isinstance(content, mcp.types.TextContent):
                                result_text += content.text + "\n"

            if execution_timeout > 0:
                await asyncio.wait_for(_run(), timeout=execution_timeout)
            else:
                await _run()

        except asyncio.TimeoutError:
            error_text = f"Execution timeout after {execution_timeout:.1f} seconds."
            result_text = f"error: Background SubAgent '{agent_name}' {error_text}"
            logger.warning(f"[SubAgent:BackgroundTask] {error_text}")

        except Exception as e:
            error_text = str(e)
            result_text = (
                f"error: Background task execution failed, internal error: {e!s}"
            )

        execution_time = time.time() - start_time
        # Check if it's enhanced subagent
        is_managed = cls._is_managed_subagent(umo, agent_name)
        if is_managed:
            await cls._handle_subagent_background_result(
                umo=umo,
                agent_name=agent_name,
                task_id=tool_args.get("subagent_task_id"),
                result_text=result_text,
                error_text=error_text,
                execution_time=execution_time,
                run_context=run_context,
                tool=tool,
                tool_args=tool_args,
            )
        else:
            await cls._wake_main_agent_for_background_result(
                run_context=run_context,
                task_id=task_id,
                tool_name=tool.name,
                result_text=result_text,
                tool_args=tool_args,
                note=(
                    event.get_extra("background_note")
                    or f"Background task for subagent '{agent_name}' finished."
                ),
                summary_name=f"Dedicated to subagent `{agent_name}`",
                extra_result_fields={"subagent_name": agent_name},
            )

    @classmethod
    async def _execute_background(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[AstrAgentContext],
        task_id: str,
        **tool_args,
    ) -> None:
        result_text = ""
        try:
            async for r in cls._execute_local(
                tool,
                run_context,
                tool_call_timeout=3600,
                **tool_args,
            ):
                if isinstance(r, mcp.types.CallToolResult):
                    result_text = ""
                    for content in r.content:
                        if isinstance(content, mcp.types.TextContent):
                            result_text += content.text + "\n"
        except Exception as e:
            result_text = (
                f"error: Background task execution failed, internal error: {e!s}"
            )
        event = run_context.context.event
        await cls._wake_main_agent_for_background_result(
            run_context=run_context,
            task_id=task_id,
            tool_name=tool.name,
            result_text=result_text,
            tool_args=tool_args,
            note=event.get_extra("background_note")
            or f"Background task {tool.name} finished.",
            summary_name=tool.name,
        )

    @classmethod
    async def _wake_main_agent_for_background_result(
        cls,
        run_context: ContextWrapper[AstrAgentContext],
        *,
        task_id: str,
        tool_name: str,
        result_text: str,
        tool_args: dict[str, Any],
        note: str,
        summary_name: str,
        extra_result_fields: dict[str, Any] | None = None,
    ) -> None:
        from astrbot.core.astr_main_agent import (
            MainAgentBuildConfig,
            _get_session_conv,
            build_main_agent,
        )

        event = run_context.context.event
        ctx = run_context.context.context
        task_result = {
            "task_id": task_id,
            "tool_name": tool_name,
            "result": result_text or "",
            "tool_args": tool_args,
        }
        if extra_result_fields:
            task_result.update(extra_result_fields)
        extras = {"background_task_result": task_result}
        session = MessageSession.from_str(event.unified_msg_origin)
        cron_event = CronMessageEvent(
            context=ctx,
            session=session,
            message=note,
            extras=extras,
            message_type=session.message_type,
        )
        cron_event.role = event.role
        session_config = ctx.get_config(umo=event.unified_msg_origin)
        provider_settings = session_config.get("provider_settings", {})
        config = MainAgentBuildConfig(
            tool_call_timeout=run_context.tool_call_timeout,
            streaming_response=provider_settings.get("stream", False),
            computer_use_runtime=str(
                provider_settings.get("computer_use_runtime", "local")
            ),
            sandbox_cfg=provider_settings.get("sandbox", {}),
            provider_settings=provider_settings,
        )
        req = ProviderRequest()
        req.system_prompt = ""
        conv = await _get_session_conv(event=cron_event, plugin_context=ctx)
        req.conversation = conv
        context = json.loads(conv.history)
        if context:
            req.contexts = context
            context_dump = req._print_friendly_context()
            req.contexts = []
            req.system_prompt += CONVERSATION_HISTORY_INJECT_PREFIX + context_dump
        bg = json.dumps(extras["background_task_result"], ensure_ascii=False)
        req.system_prompt += BACKGROUND_TASK_RESULT_WOKE_SYSTEM_PROMPT.format(
            background_task_result=bg,
        )
        req.prompt = BACKGROUND_TASK_WOKE_USER_PROMPT
        if not req.func_tool:
            req.func_tool = ToolSet()
        req.func_tool.add_tool(SEND_MESSAGE_TO_USER_TOOL)
        result = await build_main_agent(
            event=cron_event,
            plugin_context=ctx,
            config=config,
            req=req,
        )
        if not result:
            logger.error(f"Failed to build main agent for background task {tool_name}.")
            return
        runner = result.agent_runner
        async for _ in runner.step_until_done(3):
            pass
        llm_resp = runner.get_final_llm_resp()
        task_meta = extras.get("background_task_result", {})
        summary_note = f"[BackgroundTask] {summary_name} (task_id={task_meta.get('task_id', task_id)}) finished. Result: {task_meta.get('result') or result_text or 'no content'}"
        if llm_resp and llm_resp.completion_text:
            summary_note += (
                f"I finished the task, here is the result: {llm_resp.completion_text}"
            )
        await persist_agent_history(
            ctx.conversation_manager,
            event=cron_event,
            req=req,
            summary_note=summary_note,
        )
        if not llm_resp:
            logger.warning("background task agent got no response")
            return

    @classmethod
    async def _execute_local(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[AstrAgentContext],
        *,
        tool_call_timeout: int | None = None,
        **tool_args,
    ):
        event = run_context.context.event
        if not event:
            raise ValueError("Event must be provided for local function tools.")
        is_override_call = False
        for ty in type(tool).mro():
            if "call" in ty.__dict__ and ty.__dict__["call"] is not FunctionTool.call:
                is_override_call = True
                break
        if not tool.handler and (not hasattr(tool, "run")) and (not is_override_call):
            raise ValueError("Tool must have a valid handler or override 'run' method.")
        awaitable = None
        method_name = ""
        if tool.handler:
            awaitable = tool.handler
            method_name = "decorator_handler"
        elif is_override_call:
            awaitable = tool.call
            method_name = "call"
        else:
            awaitable = getattr(tool, "run", None)
            if awaitable is not None:
                method_name = "run"
        if awaitable is None:
            raise ValueError("Tool must have a valid handler or override 'run' method.")
        sdk_plugin_bridge = getattr(
            run_context.context.context,
            "sdk_plugin_bridge",
            None,
        )
        if sdk_plugin_bridge is not None:
            try:
                await sdk_plugin_bridge.dispatch_message_event(
                    "calling_func_tool",
                    event,
                    {
                        "tool_name": tool.name,
                        "tool_args": json.loads(
                            json.dumps(tool_args, ensure_ascii=False, default=str),
                        ),
                    },
                )
            except Exception as exc:
                logger.warning("SDK calling_func_tool dispatch failed: %s", exc)
        _HandlerType = Callable[
            ...,
            Awaitable[MessageEventResult | mcp.types.CallToolResult | str | None]
            | AsyncGenerator[MessageEventResult | CommandResult | str | None, None],
        ]
        wrapper = call_local_llm_tool(
            context=run_context,
            handler=awaitable,
            method_name=method_name,
            **tool_args,
        )
        while True:
            try:
                if (
                    tool.name == "wait_for_subagent"
                ):  # wait工具有自己的超时，避免受到tool_call_timeout影响
                    resp = await asyncio.wait_for(
                        anext(wrapper),
                        timeout=3600,
                    )
                else:
                    resp = await asyncio.wait_for(
                        anext(wrapper),
                        timeout=tool_call_timeout or run_context.tool_call_timeout,
                    )
                if resp is not None:
                    if isinstance(resp, mcp.types.CallToolResult):
                        yield resp
                    else:
                        text_content = mcp.types.TextContent(
                            type="text",
                            text=str(resp),
                        )
                        yield mcp.types.CallToolResult(content=[text_content])
                else:
                    res = run_context.context.event.get_result()
                    if res and res.chain:
                        try:
                            await event.send(
                                MessageChain(
                                    chain=res.chain,
                                    type="tool_direct_result",
                                ),
                            )
                        except Exception as e:
                            logger.error(f"Tool 直接发送消息失败: {e}", exc_info=True)
                        yield None
                    else:
                        yield mcp.types.CallToolResult(
                            content=[
                                mcp.types.TextContent(
                                    type="text",
                                    text="Tool executed successfully with no output.",
                                ),
                            ],
                        )
            except TimeoutError:
                raise Exception(
                    f"tool {tool.name} execution timeout after {tool_call_timeout or run_context.tool_call_timeout} seconds.",
                ) from None
            except StopAsyncIteration:
                break

    @classmethod
    async def _execute_mcp(
        cls,
        tool: FunctionTool,
        run_context: ContextWrapper[AstrAgentContext],
        **tool_args,
    ):
        res = await tool.call(run_context, **tool_args)
        if not res:
            return
        yield res

    @staticmethod
    def _load_subagent_history(
        umo: str, tool: HandoffTool
    ) -> tuple[list[Message], str]:
        agent_name = getattr(tool.agent, "name", None)
        subagent_history = []
        if agent_name:
            # 仅在历史功能启用时加载历史
            if SubAgentManager.is_history_enabled():
                try:
                    stored_history = SubAgentManager.get_subagent_history(
                        umo, agent_name
                    )
                    if stored_history:
                        # 将历史消息转换为 Message 对象
                        for hist_msg in stored_history:
                            try:
                                if isinstance(hist_msg, dict):
                                    subagent_history.append(
                                        Message.model_validate(hist_msg)
                                    )
                                elif isinstance(hist_msg, Message):
                                    subagent_history.append(hist_msg)
                            except Exception:
                                continue
                        if subagent_history:
                            logger.debug(
                                f"[SubAgentHistory] Loaded {len(subagent_history)} history messages for {agent_name}"
                            )

                except Exception as e:
                    logger.warning(
                        f"[SubAgentHistory] Failed to load history for {agent_name}: {e}"
                    )
            else:
                logger.debug(
                    f"[SubAgentHistory] History is disabled, skipping load for {agent_name}"
                )
        return subagent_history, agent_name

    @staticmethod
    def _build_subagent_system_prompt(
        umo: str, tool: HandoffTool, prov_settings: dict
    ) -> str:
        agent_name = getattr(tool.agent, "name", None)
        base = tool.agent.instructions or ""
        subagent_system_prompt = (
            f"# Role\nYour name is **{agent_name}** (used for tool calling)\n{base}\n"
        )
        if agent_name:
            runtime = prov_settings.get("computer_use_runtime", "local")
            subagent_system_prompt += SubAgentManager.build_subagent_system_prompt(
                umo, agent_name, runtime
            )
        return subagent_system_prompt

    @staticmethod
    def _save_subagent_history(
        umo: str, runner_messages: list[Message], agent_name: str
    ) -> None:
        if agent_name and runner_messages:
            # 仅在历史功能启用时保存历史
            if SubAgentManager.is_history_enabled():
                SubAgentManager.update_subagent_history(
                    umo, agent_name, runner_messages
                )
            else:
                logger.debug(
                    f"[SubAgentHistory] History is disabled, skipping save for {agent_name}"
                )
        else:
            return

    @staticmethod
    def _register_subagent_task(umo: str, agent_name: str | None) -> str | None:
        if not agent_name:
            return None
        try:
            session = SubAgentManager.get_session(umo)
            if session and (agent_name in session.subagents):
                subagent_task_id = SubAgentManager.create_pending_subagent_task(
                    session_id=umo, agent_name=agent_name
                )

                if subagent_task_id.startswith("__PENDING_TASK_CREATE_FAILED__"):
                    logger.info(
                        f"[SubAgent:BackgroundTask] Failed to created background task {subagent_task_id} for {agent_name}"
                    )
                else:
                    SubAgentManager.set_subagent_status(
                        session_id=umo,
                        agent_name=agent_name,
                        status="RUNNING",
                    )

                    logger.info(
                        f"[SubAgent:BackgroundTask] Created background task {subagent_task_id} for {agent_name}"
                    )
                return subagent_task_id
        except Exception as e:
            logger.info(
                f"[SubAgent:BackgroundTask] Failed to created background task for {agent_name}: {e}"
            )
            return None

    @staticmethod
    def _build_background_submission_message(
        agent_name: str | None,
        original_task_id: str,
        subagent_task_id: str | None,
    ) -> mcp.types.TextContent:
        if subagent_task_id and not subagent_task_id.startswith(
            "__PENDING_TASK_CREATE_FAILED__"
        ):
            return mcp.types.TextContent(
                type="text",
                text=(
                    f"Background task submitted. subagent_task_id={subagent_task_id}. "
                    f"SubAgent '{agent_name}' is working on the task. "
                    f"Use wait_for_subagent(subagent_name='{agent_name}', task_id='{subagent_task_id}') to get the result."
                ),
            )
        else:
            return mcp.types.TextContent(
                type="text",
                text=(
                    f"Background task submitted. task_id={original_task_id}. "
                    f"SubAgent '{agent_name}' is working on the task. "
                    f"You will be notified when it finishes."
                ),
            )

    @staticmethod
    def _get_subagent_execution_timeout() -> float:
        try:
            return SubAgentManager.get_execution_timeout()
        except Exception:
            return -1

    @staticmethod
    def _handle_subagent_timeout(
        umo: str,
        agent_name: str,
    ) -> None:
        SubAgentManager.set_subagent_status(
            session_id=umo,
            agent_name=agent_name,
            status="FAILED",
        )

    @staticmethod
    def _is_managed_subagent(umo: str, agent_name: str | None) -> bool:
        if not agent_name:
            return False
        session = SubAgentManager.get_session(umo)
        if session and agent_name in session.subagents:
            return True
        return False

    @classmethod
    async def _handle_subagent_background_result(
        cls,
        *,
        umo: str,
        agent_name: str,
        task_id: str | None,
        result_text: str,
        error_text: str | None,
        execution_time: float,
        run_context: ContextWrapper[AstrAgentContext],
        tool: HandoffTool,
        tool_args: dict,
    ) -> None:
        success = error_text is None
        status = "COMPLETED" if success else "FAILED"
        SubAgentManager.set_subagent_status(
            session_id=umo, agent_name=agent_name, status=status
        )

        SubAgentManager.store_subagent_result(
            session_id=umo,
            agent_name=agent_name,
            success=success,
            result=result_text,
            task_id=task_id,
            error=error_text,
            execution_time=execution_time,
        )

        if not await cls._maybe_wake_main_agent_after_background(
            run_context=run_context,
            tool=tool,
            task_id=task_id,
            agent_name=agent_name,
            result_text=result_text,
            tool_args=tool_args,
        ):
            return

    @classmethod
    async def _maybe_wake_main_agent_after_background(
        cls,
        *,
        run_context: ContextWrapper[AstrAgentContext],
        tool: HandoffTool,
        task_id: str,
        agent_name: str | None,
        result_text: str,
        tool_args: dict,
    ) -> bool:
        event = run_context.context.event
        try:
            context_extra = getattr(run_context.context, "extra", None)
            if context_extra and isinstance(context_extra, dict):
                main_agent_runner = context_extra.get("main_agent_runner")
                main_agent_is_running = (
                    main_agent_runner is not None and not main_agent_runner.done()
                )
            else:
                main_agent_is_running = False
        except Exception as e:
            logger.error("Failed to check main agent status: %s", e)
            main_agent_is_running = False  # 异常时尝试通知，避免结果丢失

        if main_agent_is_running:
            return False
        else:
            await cls._wake_main_agent_for_background_result(
                run_context=run_context,
                task_id=task_id,
                tool_name=tool.name,
                result_text=result_text,
                tool_args=tool_args,
                note=(
                    event.get_extra("background_note")
                    or f"Background task for subagent '{agent_name}' finished."
                ),
                summary_name=f"Dedicated to subagent `{agent_name}`",
                extra_result_fields={"subagent_name": agent_name},
            )
            return True


async def call_local_llm_tool(
    context: ContextWrapper[AstrAgentContext],
    handler: Callable[
        ...,
        Awaitable[MessageEventResult | mcp.types.CallToolResult | str | None]
        | AsyncGenerator[MessageEventResult | CommandResult | str | None, None],
    ],
    method_name: str,
    *args,
    **kwargs,
) -> AsyncGenerator[Any, None]:
    """执行本地 LLM 工具的处理函数并处理其返回结果"""
    ready_to_call = None
    trace_ = None
    event = context.context.event
    try:
        if method_name == "run" or method_name == "decorator_handler":
            ready_to_call = handler(event, *args, **kwargs)
        elif method_name == "call":
            ready_to_call = handler(context, *args, **kwargs)
        else:
            raise ValueError(f"未知的方法名: {method_name}")
    except ValueError as e:
        raise Exception(f"Tool execution ValueError: {e}") from e
    except TypeError as e:
        try:
            sig = inspect.signature(handler)
            params = list(sig.parameters.values())
            if params:
                params = params[1:]
            param_strs = []
            for param in params:
                param_str = param.name
                if param.annotation != inspect.Parameter.empty:
                    if isinstance(param.annotation, type):
                        type_str = param.annotation.__name__
                    else:
                        type_str = str(param.annotation)
                    param_str += f": {type_str}"
                if param.default != inspect.Parameter.empty:
                    param_str += f" = {param.default!r}"
                param_strs.append(param_str)
            handler_param_str = (
                ", ".join(param_strs) if param_strs else "(no additional parameters)"
            )
        except Exception:
            handler_param_str = "(unable to inspect signature)"
        raise Exception(
            f"Tool handler parameter mismatch, please check the handler definition. Handler parameters: {handler_param_str}",
        ) from e
    except Exception as e:
        trace_ = traceback.format_exc()
        raise Exception(f"Tool execution error: {e}. Traceback: {trace_}") from e
    if not ready_to_call:
        return
    if inspect.isasyncgen(ready_to_call):
        _has_yielded = False
        try:
            async for ret in ready_to_call:
                _has_yielded = True
                if isinstance(ret, MessageEventResult | CommandResult):
                    event.set_result(ret)
                    yield
                else:
                    yield ret
            if not _has_yielded:
                yield
        except Exception as e:
            logger.error(f"Previous Error: {trace_}")
            raise e
    elif inspect.iscoroutine(ready_to_call):
        ret = await ready_to_call
        if isinstance(ret, MessageEventResult | CommandResult):
            event.set_result(ret)
            yield
        else:
            yield ret
