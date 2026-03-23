"""SendMessageToUserTool — proactive message delivery to users.

Extracted from ``astr_main_agent_resources.py`` to its own module.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, TypedDict

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
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path


class MessageComponent(TypedDict, total=False):
    """Type-safe message component structure."""

    type: str
    text: str
    path: str
    url: str
    mention_user_id: str


@dataclass
class SendMessageToUserTool(FunctionTool[AstrAgentContext]):
    name: str = "send_message_to_user"
    description: str = "Directly send message to the user. Only use this tool when you need to proactively message the user. Otherwise you can directly output the reply in the conversation."

    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "description": "An ordered list of message components to send. `mention_user` type can be used to mention the user.",
                    "items": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
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
            import shlex

            result = await sb.shell.exec(
                f"test -f {shlex.quote(path)} && echo '_&exists_'"
            )
            if "_&exists_" in json.dumps(result):
                # Download the file from sandbox
                name = anyio.Path(path).name
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
        session: str | MessageSession = kwargs.get("session") or context.context.event.unified_msg_origin
        messages: list[dict[str, Any]] | None = kwargs.get("messages")

        if not isinstance(messages, list) or not messages:
            return "error: messages parameter is empty or invalid."

        components: list[Comp.BaseMessageComponent] = []

        for idx, msg in enumerate(messages):
            if not isinstance(msg, dict):
                return f"error: messages[{idx}] should be an object."

            if "type" not in msg:
                return f"error: messages[{idx}].type is required."
            msg_type = str(msg["type"]).lower()

            _file_from_sandbox = False

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
                        (
                            local_path,
                            _file_from_sandbox,
                        ) = await self._resolve_path_from_sandbox(context, path)
                        components.append(Comp.Image.fromFileSystem(path=local_path))
                    elif url:
                        components.append(Comp.Image.fromURL(url=url))
                    else:
                        return f"error: messages[{idx}] must include path or url for image component."
                elif msg_type == "record":
                    path = msg.get("path")
                    url = msg.get("url")
                    if path:
                        (
                            local_path,
                            _file_from_sandbox,
                        ) = await self._resolve_path_from_sandbox(context, path)
                        components.append(Comp.Record.fromFileSystem(path=local_path))
                    elif url:
                        components.append(Comp.Record.fromURL(url=url))
                    else:
                        return f"error: messages[{idx}] must include path or url for record component."
                elif msg_type == "video":
                    path = msg.get("path")
                    url = msg.get("url")
                    if path:
                        (
                            local_path,
                            _file_from_sandbox,
                        ) = await self._resolve_path_from_sandbox(context, path)
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
                    mention_user_id = msg.get("mention_user_id")
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
            except Exception as exc:
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

        return f"Message sent to session {target_session}"


SEND_MESSAGE_TO_USER_TOOL = SendMessageToUserTool()


def get_all_tools() -> list[FunctionTool]:
    """Return all send-message tools for registration."""
    return [SEND_MESSAGE_TO_USER_TOOL]
