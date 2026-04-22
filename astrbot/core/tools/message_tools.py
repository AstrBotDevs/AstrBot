import json
import os
import shlex
import uuid
from typing import TypedDict

import anyio
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
from astrbot.core.tools.registry import builtin_tool
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path


class MessageComponentPayload(TypedDict, total=False):
    type: str
    text: str
    path: str
    url: str
    mention_user_id: str


def _normalize_message_component(raw_msg: object) -> MessageComponentPayload | None:
    if not isinstance(raw_msg, dict):
        return None

    normalized: MessageComponentPayload = {}
    for key, value in raw_msg.items():
        if not isinstance(key, str):
            continue
        if key == "type" and isinstance(value, str):
            normalized["type"] = value
        elif key == "text" and isinstance(value, str):
            normalized["text"] = value
        elif key == "path" and isinstance(value, str):
            normalized["path"] = value
        elif key == "url" and isinstance(value, str):
            normalized["url"] = value
        elif key == "mention_user_id" and isinstance(value, str):
            normalized["mention_user_id"] = value
    return normalized


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
                    "description": "Optional. Target session string. Defaults to current session.",
                },
            },
            "required": ["messages"],
        },
    )

    async def _resolve_path_from_sandbox(
        self,
        context: ContextWrapper[AstrAgentContext],
        path: str,
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
        elif await anyio.Path(path).is_file():
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
                    get_astrbot_temp_path(),
                    f"sandbox_{uuid.uuid4().hex[:4]}_{name}",
                )
                await sb.download_file(path, local_path)
                logger.info(f"Downloaded file from sandbox: {path} -> {local_path}")
                return local_path, True
        except Exception as exc:
            logger.warning(f"Failed to check/download file from sandbox: {exc}")

        return path, False

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs,
    ) -> ToolExecResult:
        session = kwargs.get("session") or context.context.event.unified_msg_origin
        messages = kwargs.get("messages")
        if not isinstance(messages, list) or not messages:
            return "error: messages parameter is empty or invalid."

        components: list[Comp.BaseMessageComponent] = []
        for idx, msg in enumerate(messages):
            normalized_msg = _normalize_message_component(msg)
            if normalized_msg is None:
                return f"error: messages[{idx}] should be an object."

            msg_type = normalized_msg.get("type", "").lower()
            if not msg_type:
                return f"error: messages[{idx}].type is required."

            try:
                if msg_type == "plain":
                    text = normalized_msg.get("text", "").strip()
                    if not text:
                        return f"error: messages[{idx}].text is required for plain component."
                    components.append(Comp.Plain(text=text))
                elif msg_type == "image":
                    path = normalized_msg.get("path")
                    url = normalized_msg.get("url")
                    if path:
                        local_path, _ = await self._resolve_path_from_sandbox(
                            context,
                            path,
                        )
                        components.append(Comp.Image.fromFileSystem(path=local_path))
                    elif url:
                        components.append(Comp.Image.fromURL(url=url))
                    else:
                        return f"error: messages[{idx}] must include path or url for image component."
                elif msg_type == "record":
                    path = normalized_msg.get("path")
                    url = normalized_msg.get("url")
                    if path:
                        local_path, _ = await self._resolve_path_from_sandbox(
                            context,
                            path,
                        )
                        components.append(Comp.Record.fromFileSystem(path=local_path))
                    elif url:
                        components.append(Comp.Record.fromURL(url=url))
                    else:
                        return f"error: messages[{idx}] must include path or url for record component."
                elif msg_type == "video":
                    path = normalized_msg.get("path")
                    url = normalized_msg.get("url")
                    if path:
                        local_path, _ = await self._resolve_path_from_sandbox(
                            context,
                            path,
                        )
                        components.append(Comp.Video.fromFileSystem(path=local_path))
                    elif url:
                        components.append(Comp.Video.fromURL(url=url))
                    else:
                        return f"error: messages[{idx}] must include path or url for video component."
                elif msg_type == "file":
                    path = normalized_msg.get("path")
                    url = normalized_msg.get("url")
                    name = (
                        normalized_msg.get("text")
                        or (os.path.basename(path) if path else "")
                        or (os.path.basename(url) if url else "")
                        or "file"
                    )
                    if path:
                        local_path, _ = await self._resolve_path_from_sandbox(
                            context,
                            path,
                        )
                        components.append(Comp.File(name=name, file=local_path))
                    elif url:
                        components.append(Comp.File(name=name, url=url))
                    else:
                        return f"error: messages[{idx}] must include path or url for file component."
                elif msg_type == "mention_user":
                    mention_user_id = normalized_msg.get("mention_user_id")
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
        except Exception as exc:
            return f"error: invalid session: {exc}"

        await context.context.context.send_message(
            target_session,
            MessageChain(chain=components),
        )
        return f"Message sent to session {target_session}"


__all__ = [
    "SendMessageToUserTool",
]
