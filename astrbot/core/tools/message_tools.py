import json
import os
import shlex
import uuid

from pydantic import Field
from pydantic.dataclasses import dataclass

import astrbot.core.message.components as Comp
from astrbot.api import logger
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.computer.computer_client import get_booter
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.tools.computer_tools.util import check_admin_permission
from astrbot.core.tools.registry import builtin_tool
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path


@builtin_tool
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
                                "description": "File path for `image`, `record`, `video`, or `file` types. Both local path and sandbox path are supported.",
                            },
                            "url": {
                                "type": "string",
                                "description": "URL for `image`, `record`, `video`, or `file` types.",
                            },
                            "mention_user_id": {
                                "type": "string",
                                "description": "User ID to mention for `mention_user` type.",
                            },
                        },
                        "required": ["type"],
                    },
                },
                "session": {
                    "type": "string",
                    "description": (
                        "Optional. Leave empty for the current session. "
                        "Use 'platform_id:message_type:session_id' to target another session."
                    ),
                },
            },
            "required": ["messages"],
        }
    )

    async def _resolve_path_from_sandbox(
        self, context: ContextWrapper[AstrAgentContext], path: str
    ) -> tuple[str, bool]:
        # if the path is relative, check if the file exists in user's local workspace
        if not os.path.isabs(path):
            unified_msg_origin = context.context.event.unified_msg_origin
            if unified_msg_origin:
                from astrbot.core.tools.computer_tools.util import workspace_root

                try:
                    ws_path = workspace_root(unified_msg_origin)
                    ws_candidate = (ws_path / path).resolve()
                    if ws_candidate.is_file() and ws_candidate.is_relative_to(ws_path):
                        return str(ws_candidate), False
                except Exception:
                    pass
        # check if the file exists in local environment (only allow absolute paths to prevent traversal)
        elif os.path.isfile(path):
            return path, False

        try:
            sb = await get_booter(
                context.context.context,
                context.context.event.unified_msg_origin,
            )
            quoted_path = shlex.quote(path)
            result = await sb.shell.exec(f"test -f {quoted_path} && echo '_&exists_'")
            if "_&exists_" in json.dumps(result):
                name = os.path.basename(path)
                local_path = os.path.join(
                    get_astrbot_temp_path(), f"sandbox_{uuid.uuid4().hex[:4]}_{name}"
                )
                await sb.download_file(path, local_path)
                logger.info(f"Downloaded file from sandbox: {path} -> {local_path}")
                return local_path, True
        except Exception as exc:
            logger.warning(f"Failed to check/download file from sandbox: {exc}")

        return path, False

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        # Security: only AstrBot admins can send messages to other sessions.
        # Non-admin users are always restricted to their own session.
        # See https://github.com/AstrBotDevs/AstrBot/issues/7822
        current_session = context.context.event.unified_msg_origin
        session = kwargs.get("session") or current_session
        if session != current_session:
            if permission_error := check_admin_permission(
                context, "Send message to another session"
            ):
                return permission_error
        messages = kwargs.get("messages")
        if not isinstance(messages, list) or not messages:
            return "error: messages parameter is empty or invalid."

        components: list[Comp.BaseMessageComponent] = []
        for idx, msg in enumerate(messages):
            if not isinstance(msg, dict):
                return f"error: messages[{idx}] should be an object."

            msg_type = str(msg.get("type", "")).lower()
            if not msg_type:
                return f"error: messages[{idx}].type is required."

            try:
                if msg_type == "plain":
                    text = str(msg.get("text", "")).strip()
                    if not text:
                        return f"error: messages[{idx}].text is required for plain component."
                    components.append(Comp.Plain(text=text))
                elif msg_type == "image":
                    path = msg.get("path")
                    url = msg.get("url")
                    if path:
                        local_path, _ = await self._resolve_path_from_sandbox(
                            context, path
                        )
                        components.append(Comp.Image.fromFileSystem(path=local_path))
                    elif url:
                        components.append(Comp.Image.fromURL(url=url))
                    else:
                        return f"error: messages[{idx}] must include path or url for image component."
                elif msg_type == "record":
                    path = msg.get("path")
                    url = msg.get("url")
                    if path:
                        local_path, _ = await self._resolve_path_from_sandbox(
                            context, path
                        )
                        components.append(Comp.Record.fromFileSystem(path=local_path))
                    elif url:
                        components.append(Comp.Record.fromURL(url=url))
                    else:
                        return f"error: messages[{idx}] must include path or url for record component."
                elif msg_type == "video":
                    path = msg.get("path")
                    url = msg.get("url")
                    if path:
                        local_path, _ = await self._resolve_path_from_sandbox(
                            context, path
                        )
                        components.append(Comp.Video.fromFileSystem(path=local_path))
                    elif url:
                        components.append(Comp.Video.fromURL(url=url))
                    else:
                        return f"error: messages[{idx}] must include path or url for video component."
                elif msg_type == "file":
                    path = msg.get("path")
                    url = msg.get("url")
                    name = (
                        msg.get("text")
                        or (os.path.basename(path) if path else "")
                        or (os.path.basename(url) if url else "")
                        or "file"
                    )
                    if path:
                        local_path, _ = await self._resolve_path_from_sandbox(
                            context, path
                        )
                        components.append(Comp.File(name=name, file=local_path))
                    elif url:
                        components.append(Comp.File(name=name, url=url))
                    else:
                        return f"error: messages[{idx}] must include path or url for file component."
                elif msg_type == "mention_user":
                    mention_user_id = msg.get("mention_user_id")
                    if not mention_user_id:
                        return f"error: messages[{idx}].mention_user_id is required for mention_user component."
                    components.append(Comp.At(qq=mention_user_id))
                else:
                    return (
                        f"error: unsupported message type '{msg_type}' at index {idx}."
                    )
            except Exception as exc:
                return f"error: failed to build messages[{idx}] component: {exc}"

        try:
            target_session = (
                MessageSession.from_str(session)
                if isinstance(session, str)
                else session
            )
        except Exception:
            # LLM 在 cron 等主动场景下可能只传 session_id（如 oc_xxx），
            # 而不是完整的三段式 platform_id:message_type:session_id。
            # 此时用 current_session 的前两段补全。
            # 注意：这里的session是传入的session参数，实际上是用户输入的session_id
            # current_session才是完整的三段式session字符串。
            # 仅当传入字符串不含 ':'（明显是裸 session_id）时才用 current_session 补全，
            # 避免 LLM 传了带 ':' 但格式错误的目标 session 被错误修复。
            # issue: https://github.com/AstrBotDevs/AstrBot/issues/7907
            if isinstance(session, str) and current_session and ":" not in session:
                try:
                    cur = MessageSession.from_str(current_session)
                    target_session = MessageSession(
                        platform_name=cur.platform_id,
                        message_type=cur.message_type,
                        session_id=session,
                    )
                except Exception:
                    return f"error: invalid session: {session}"
            else:
                return f"error: invalid session: {session}"

        await context.context.context.send_message(
            target_session,
            MessageChain(chain=components),
        )
        return f"Message sent to session {target_session}"


__all__ = [
    "SendMessageToUserTool",
]
