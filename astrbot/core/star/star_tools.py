import inspect
import os
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, ClassVar

from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.core.message.components import BaseMessageComponent
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.star.context import Context
from astrbot.core.star.star import star_map
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.io import ensure_dir


class StarTools:
    """Convenience utility methods for plugins."""

    _context: ClassVar[Context | None] = None

    @classmethod
    def initialize(cls, context: Context) -> None:
        """Initializes StarTools with a context reference.

        Args:
            context: Context exposed to plugins.
        """
        cls._context = context

    @classmethod
    async def send_message(
        cls,
        session: str | MessageSesion,
        message_chain: MessageChain,
    ) -> bool:
        """Sends a message to a session by unified message origin.

        Args:
            session: Message session from event.session or event.unified_msg_origin.
            message_chain: Message chain to send.

        Returns:
            Whether a matching platform was found.

        Raises:
            ValueError: If StarTools is not initialized or session parsing fails.
        """
        if cls._context is None:
            raise ValueError("StarTools not initialized")
        return await cls._context.send_message(session, message_chain)

    @classmethod
    async def create_message(
        cls,
        type: str,
        self_id: str,
        session_id: str,
        sender: MessageMember,
        message: list[BaseMessageComponent],
        message_str: str,
        message_id: str = "",
        raw_message: object = None,
        group_id: str = "",
    ) -> AstrBotMessage:
        """Creates an AstrBot message object.

        Args:
            type: Message type, such as "GroupMessage", "FriendMessage", or
                "OtherMessage".
            self_id: Bot self ID.
            session_id: Session ID, usually a user ID or group ID.
            sender: Sender information, such as
                MessageMember(user_id="123456", nickname="Nickname").
            message: Message component list. This message chain is not sent to
                the LLM directly, but it may be processed by other handlers.
            message_str: Plain text message sent to the LLM, aligned with the
                message chain.
            message_id: Message ID. Leave empty to generate one automatically.
            raw_message: Raw message object.
            group_id: Group ID. Empty for private chats.

        Returns:
            Created AstrBot message object.
        """
        abm = AstrBotMessage()
        abm.type = MessageType(type)
        abm.self_id = self_id
        abm.session_id = session_id
        if message_id == "":
            message_id = uuid.uuid4().hex
        abm.message_id = message_id
        abm.sender = sender
        abm.message = message
        abm.message_str = message_str
        abm.raw_message = raw_message
        abm.group_id = group_id
        return abm

    @classmethod
    async def create_event(
        cls,
        abm: AstrBotMessage,
        platform: str = "aiocqhttp",
        is_wake: bool = True,
    ) -> None:
        """Creates and commits an event to the target platform.

        Args:
            abm: Message object to submit. Create it with create_message first.
            platform: Platform ID or adapter name. Defaults to aiocqhttp for
                backward compatibility.
            is_wake: Whether to mark the event as a wake event. Only wake events
                receive LLM responses.

        Raises:
            ValueError: If StarTools is not initialized or the platform is not
                found.
        """
        if cls._context is None:
            raise ValueError("StarTools not initialized")
        platforms = cls._context.platform_manager.get_insts()
        adapter = next((p for p in platforms if p.meta().id == platform), None)
        if adapter is None:
            adapter = next((p for p in platforms if p.meta().name == platform), None)
        if adapter is None:
            raise ValueError(f"Platform not found: {platform}")

        event = adapter.create_event(abm)
        event.is_wake = is_wake
        adapter.commit_event(event)

    @classmethod
    def activate_llm_tool(cls, name: str) -> bool:
        """Activates a registered function-calling tool.

        Args:
            name: Tool name.

        Returns:
            Whether the tool was activated successfully.

        Raises:
            ValueError: If StarTools is not initialized.
        """
        if cls._context is None:
            raise ValueError("StarTools not initialized")
        return cls._context.activate_llm_tool(name)

    @classmethod
    def deactivate_llm_tool(cls, name: str) -> bool:
        """Deactivates a registered function-calling tool.

        Args:
            name: Tool name.

        Returns:
            Whether the tool was deactivated successfully.

        Raises:
            ValueError: If StarTools is not initialized.
        """
        if cls._context is None:
            raise ValueError("StarTools not initialized")
        return cls._context.deactivate_llm_tool(name)

    @classmethod
    def register_llm_tool(
        cls,
        name: str,
        func_args: list,
        desc: str,
        func_obj: Callable[..., Awaitable[Any]],
    ) -> None:
        """Registers a function-calling tool.

        Args:
            name: Tool name.
            func_args: Function argument definitions.
            desc: Tool description.
            func_obj: Function object. It must be async.

        Raises:
            ValueError: If StarTools is not initialized.
        """
        if cls._context is None:
            raise ValueError("StarTools not initialized")
        cls._context.register_llm_tool(name, func_args, desc, func_obj)

    @classmethod
    def unregister_llm_tool(cls, name: str) -> None:
        """Unregisters a function-calling tool.

        Args:
            name: Tool name.

        Raises:
            ValueError: If StarTools is not initialized.
        """
        if cls._context is None:
            raise ValueError("StarTools not initialized")
        cls._context.unregister_llm_tool(name)

    @classmethod
    def get_data_dir(cls, plugin_name: str | None = None) -> Path:
        """Returns the absolute path to a plugin data directory.

        This method creates a dedicated directory under data/plugin_data. If
        plugin_name is not provided, it detects the caller plugin from the call
        stack.

        Args:
            plugin_name: Optional plugin name. If None, the caller plugin name is
                detected automatically.

        Returns:
            Absolute plugin data directory path at data/plugin_data/{plugin_name}.

        Raises:
            RuntimeError: If caller module information or module metadata cannot
                be resolved, or if directory creation fails.
            ValueError: If the plugin name cannot be resolved.
        """
        if not plugin_name:
            frame = inspect.currentframe()
            module = None
            if frame:
                frame = frame.f_back
                module = inspect.getmodule(frame)

            if not module:
                raise RuntimeError("Unable to resolve caller module information")

            metadata = star_map.get(module.__name__, None)

            if not metadata:
                raise RuntimeError(
                    f"Unable to resolve metadata for module {module.__name__}",
                )

            plugin_name = metadata.name

        if not plugin_name:
            raise ValueError("Unable to resolve plugin name")

        data_dir = Path(
            os.path.join(get_astrbot_data_path(), "plugin_data", plugin_name),
        )

        try:
            ensure_dir(data_dir)
        except OSError as e:
            if isinstance(e, PermissionError):
                raise RuntimeError(
                    f"Unable to create directory {data_dir}: permission denied",
                ) from e
            raise RuntimeError(f"Unable to create directory {data_dir}: {e!s}") from e

        return data_dir.resolve()
