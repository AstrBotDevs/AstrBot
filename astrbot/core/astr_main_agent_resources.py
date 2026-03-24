import base64
import json
import os
import uuid
from typing import Any

import anyio
from pydantic import Field
from pydantic.dataclasses import dataclass

import astrbot.core.message.components as Comp
from astrbot.api import logger, sp
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.computer.computer_client import get_booter
from astrbot.core.computer.tools import (
    AnnotateExecutionTool,
    BrowserBatchExecTool,
    BrowserExecTool,
    CreateSkillCandidateTool,
    CreateSkillPayloadTool,
    EvaluateSkillCandidateTool,
    ExecuteShellTool,
    FileDownloadTool,
    FileUploadTool,
    GetExecutionHistoryTool,
    GetSkillPayloadTool,
    ListSkillCandidatesTool,
    ListSkillReleasesTool,
    LocalPythonTool,
    PromoteSkillCandidateTool,
    PythonTool,
    RollbackSkillReleaseTool,
    RunBrowserSkillTool,
    SyncSkillReleaseTool,
)
from astrbot.core.knowledge_base.kb_helper import KBHelper
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.star.context import Context
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path


@dataclass
class KnowledgeBaseQueryTool(FunctionTool[AstrAgentContext]):
    name: str = "astr_kb_search"
    description: str = (
        "Query the knowledge base for facts or relevant context. "
        "Use this tool when the user's question requires factual information, "
        "definitions, background knowledge, or previously indexed content. "
        "Only send short keywords or a concise question as the query."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A concise keyword query for the knowledge base.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        query = kwargs.get("query", "")
        if not query:
            return "error: Query parameter is empty."
        result = await retrieve_knowledge_base(
            query=kwargs.get("query", ""),
            umo=context.context.event.unified_msg_origin,
            context=context.context.context,
        )
        if not result:
            return "No relevant knowledge found."
        return result


@dataclass
class SendMessageToUserTool(FunctionTool[AstrAgentContext]):
    name: str = "send_message_to_user"
    description: str = (
        "Send message to the user. "
        "Supports various message types including `plain`, `image`, `record`, `video`, `file`, and `mention_user`. "
        "Use this tool to send media files (`image`, `record`, `video`, `file`), "
        "or when you need to proactively message the user(such as cron job). For normal text replies, you can output directly."
    )

    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "description": "An ordered list of message components to send. `mention_user` type can be used to mention the user.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "description": (
                                    "Component type. One of: "
                                    "plain, image, record, video, file, mention_user. Record is voice message."
                                ),
                            },
                            "text": {
                                "type": "string",
                                "description": "Text content for `plain` type.",
                            },
                            "path": {
                                "type": "string",
                                "description": "File path for `image`, `record`, or `file` types. Both local path and sandbox path are supported.",
                            },
                            "url": {
                                "type": "string",
                                "description": "URL for `image`, `record`, or `file` types.",
                            },
                            "mention_user_id": {
                                "type": "string",
                                "description": "User ID to mention for `mention_user` type.",
                            },
                        },
                        "required": ["type"],
                    },
                },
            },
            "required": ["messages"],
        }
    )

    async def _resolve_path_from_sandbox(
        self, context: ContextWrapper[AstrAgentContext], path: str
    ) -> tuple[str, bool]:
        """
        If the path exists locally, return it directly.
        Otherwise, check if it exists in the sandbox and download it.

        bool: indicates whether the file was downloaded from sandbox.
        """
        if await anyio.Path(path).exists():
            return path, False

        # Try to check if the file exists in the sandbox
        try:
            sb = await get_booter(
                context.context.context,
                context.context.event.unified_msg_origin,
            )
            # Use shell to check if the file exists in sandbox
            result = await sb.shell.exec(f"test -f {path} && echo '_&exists_'")
            if "_&exists_" in json.dumps(result):
                # Download the file from sandbox
                name = os.path.basename(path)
                local_path = os.path.join(
                    get_astrbot_temp_path(), f"sandbox_{uuid.uuid4().hex[:4]}_{name}"
                )
                await sb.download_file(path, local_path)
                logger.info(f"Downloaded file from sandbox: {path} -> {local_path}")
                return local_path, True
        except Exception as e:
            logger.warning(f"Failed to check/download file from sandbox: {e}")

        # Return the original path (will likely fail later, but that's expected)
        return path, False

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs: Any
    ) -> ToolExecResult:
        session = kwargs.get("session") or context.context.event.unified_msg_origin
        messages_raw: list[dict[str, Any]] | None = kwargs.get("messages")

        if not isinstance(messages_raw, list) or not messages_raw:
            return "error: messages parameter is empty or invalid."

        components: list[Comp.BaseMessageComponent] = []

        for idx, msg in enumerate(messages_raw):
            if not isinstance(msg, dict):
                return f"error: messages[{idx}] should be an object."

            msg_dict: dict[str, Any] = msg
            msg_type = str(msg_dict.get("type", "")).lower()
            if not msg_type:
                return f"error: messages[{idx}].type is required."

            file_from_sandbox = False

            try:
                if msg_type == "plain":
                    text = str(msg_dict.get("text", "")).strip()
                    if not text:
                        return f"error: messages[{idx}].text is required for plain component."
                    components.append(Comp.Plain(text=text))
                elif msg_type == "image":
                    path = msg_dict.get("path")
                    url = msg_dict.get("url")
                    if path:
                        (
                            local_path,
                            file_from_sandbox,
                        ) = await self._resolve_path_from_sandbox(context, path)
                        components.append(Comp.Image.fromFileSystem(path=local_path))
                    elif url:
                        components.append(Comp.Image.fromURL(url=url))
                    else:
                        return f"error: messages[{idx}] must include path or url for image component."
                elif msg_type == "record":
                    path = msg_dict.get("path")
                    url = msg_dict.get("url")
                    if path:
                        (
                            local_path,
                            file_from_sandbox,
                        ) = await self._resolve_path_from_sandbox(context, path)
                        components.append(Comp.Record.fromFileSystem(path=local_path))
                    elif url:
                        components.append(Comp.Record.fromURL(url=url))
                    else:
                        return f"error: messages[{idx}] must include path or url for record component."
                elif msg_type == "video":
                    path = msg_dict.get("path")
                    url = msg_dict.get("url")
                    if path:
                        (
                            local_path,
                            file_from_sandbox,
                        ) = await self._resolve_path_from_sandbox(context, path)
                        components.append(Comp.Video.fromFileSystem(path=local_path))
                    elif url:
                        components.append(Comp.Video.fromURL(url=url))
                    else:
                        return f"error: messages[{idx}] must include path or url for video component."
                elif msg_type == "file":
                    path = msg_dict.get("path")
                    url = msg_dict.get("url")
                    name = (
                        msg_dict.get("text")
                        or (os.path.basename(path) if path else "")
                        or (os.path.basename(url) if url else "")
                        or "file"
                    )
                    if path:
                        (
                            local_path,
                            _file_from_sandbox,
                        ) = await self._resolve_path_from_sandbox(context, path)
                        components.append(Comp.File(name=name, file=local_path))
                    elif url:
                        components.append(Comp.File(name=name, url=url))
                    else:
                        return f"error: messages[{idx}] must include path or url for file component."
                elif msg_type == "mention_user":
                    mention_user_id = msg_dict.get("mention_user_id")
                    if not mention_user_id:
                        return f"error: messages[{idx}].mention_user_id is required for mention_user component."
                    components.append(
                        Comp.At(
                            qq=mention_user_id,
                        ),
                    )
                else:
                    return (
                        f"error: unsupported message type '{msg_type}' at index {idx}."
                    )
            except Exception as exc:  # 捕获组件构造异常,避免直接抛出
                return f"error: failed to build messages[{idx}] component: {exc}"

        try:
            target_session = (
                MessageSession.from_str(session)
                if isinstance(session, str)
                else session
            )
        except Exception as e:
            return f"error: invalid session: {e}"

        await context.context.context.send_message(
            target_session,
            MessageChain(chain=components),
        )

        # if file_from_sandbox:
        #     try:
        #         os.remove(local_path)
        #     except Exception as e:
        #         logger.error(f"Error removing temp file {local_path}: {e}")

        return f"Message sent to session {target_session}"


def check_all_kb(kb_list: list[KBHelper | None]) -> bool:
    """检查是否所有的知识库都为空
    Args:
        kb_list: 所选的知识库
    Returns:
        bool: 是否全为空
    """
    return not any(
        kb and (kb.kb.doc_count != 0 or kb.kb.chunk_count != 0) for kb in kb_list
    )


async def retrieve_knowledge_base(
    query: str,
    umo: str,
    context: Context,
) -> str | None:
    """Inject knowledge base context into the provider request

    Args:
        umo: Unique message object (session ID)
        p_ctx: Pipeline context
    """
    kb_mgr = context.kb_manager
    config = context.get_config(umo=umo)

    # 1. 优先读取会话级配置
    session_config = await sp.session_get(umo, "kb_config", default={})

    if session_config and "kb_ids" in session_config:
        # 会话级配置
        kb_ids = session_config.get("kb_ids", [])

        # 如果配置为空列表,明确表示不使用知识库
        if not kb_ids:
            logger.info(f"[知识库] 会话 {umo} 已被配置为不使用知识库")
            return

        top_k = session_config.get("top_k", 5)

        # 将 kb_ids 转换为 kb_names
        kb_names = []
        invalid_kb_ids = []
        for kb_id in kb_ids:
            kb_helper = await kb_mgr.get_kb(kb_id)
            if kb_helper:
                kb_names.append(kb_helper.kb.kb_name)
            else:
                logger.warning(f"[知识库] 知识库不存在或未加载: {kb_id}")
                invalid_kb_ids.append(kb_id)

        if invalid_kb_ids:
            logger.warning(
                f"[知识库] 会话 {umo} 配置的以下知识库无效: {invalid_kb_ids}",
            )

        if not kb_names:
            return

        logger.debug(f"[知识库] 使用会话级配置,知识库数量: {len(kb_names)}")
    else:
        kb_names = config.get("kb_names", [])
        top_k = config.get("kb_final_top_k", 5)
        logger.debug(f"[知识库] 使用全局配置,知识库数量: {len(kb_names)}")

    top_k_fusion = config.get("kb_fusion_top_k", 20)

    if not kb_names:
        return

    all_kbs = [await kb_mgr.get_kb_by_name(kb) for kb in kb_names]

    if check_all_kb(all_kbs):
        logger.debug("所配置的所有知识库全为空, 跳过检索过程")
        return

    logger.debug(f"[知识库] 开始检索知识库,数量: {len(kb_names)}, top_k={top_k}")

    kb_context = await kb_mgr.retrieve(
        query=query,
        kb_names=kb_names,
        top_k_fusion=top_k_fusion,
        top_m_final=top_k,
    )

    if not kb_context:
        return

    formatted = kb_context.get("context_text", "")
    if formatted:
        results = kb_context.get("results", [])
        logger.debug(f"[知识库] 为会话 {umo} 注入了 {len(results)} 条相关知识块")
        return formatted


KNOWLEDGE_BASE_QUERY_TOOL = KnowledgeBaseQueryTool()
SEND_MESSAGE_TO_USER_TOOL = SendMessageToUserTool()

EXECUTE_SHELL_TOOL = ExecuteShellTool()
LOCAL_EXECUTE_SHELL_TOOL = ExecuteShellTool(is_local=True)
PYTHON_TOOL = PythonTool()
LOCAL_PYTHON_TOOL = LocalPythonTool()
FILE_UPLOAD_TOOL = FileUploadTool()
FILE_DOWNLOAD_TOOL = FileDownloadTool()
BROWSER_EXEC_TOOL = BrowserExecTool()
BROWSER_BATCH_EXEC_TOOL = BrowserBatchExecTool()
RUN_BROWSER_SKILL_TOOL = RunBrowserSkillTool()
GET_EXECUTION_HISTORY_TOOL = GetExecutionHistoryTool()
ANNOTATE_EXECUTION_TOOL = AnnotateExecutionTool()
CREATE_SKILL_PAYLOAD_TOOL = CreateSkillPayloadTool()
GET_SKILL_PAYLOAD_TOOL = GetSkillPayloadTool()
CREATE_SKILL_CANDIDATE_TOOL = CreateSkillCandidateTool()
LIST_SKILL_CANDIDATES_TOOL = ListSkillCandidatesTool()
EVALUATE_SKILL_CANDIDATE_TOOL = EvaluateSkillCandidateTool()
PROMOTE_SKILL_CANDIDATE_TOOL = PromoteSkillCandidateTool()
LIST_SKILL_RELEASES_TOOL = ListSkillReleasesTool()
ROLLBACK_SKILL_RELEASE_TOOL = RollbackSkillReleaseTool()
SYNC_SKILL_RELEASE_TOOL = SyncSkillReleaseTool()

# we prevent astrbot from connecting to known malicious hosts
# these hosts are base64 encoded
BLOCKED = {"dGZid2h2d3IuY2xvdWQuc2VhbG9zLmlv", "a291cmljaGF0"}
decoded_blocked = [base64.b64decode(b).decode("utf-8") for b in BLOCKED]
