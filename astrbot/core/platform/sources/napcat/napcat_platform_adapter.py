from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable, Mapping
from pathlib import PurePosixPath
from time import monotonic
from typing import Any, cast

from astrbot import logger
from astrbot.core.message.components import (
    RPS,
    Anonymous,
    At,
    AtAll,
    BaseMessageComponent,
    Contact,
    Dice,
    Face,
    File,
    FlashTransfer,
    Forward,
    Image,
    Json,
    Location,
    Markdown,
    MFace,
    MiniApp,
    Music,
    Node,
    Nodes,
    OnlineFile,
    Plain,
    Poke,
    Record,
    Reply,
    Shake,
    Share,
    Unknown,
    Video,
    Xml,
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import MessageSession
from astrbot.core.platform.astrbot_message import AstrBotMessage, Group, MessageMember
from astrbot.core.platform.contracts.onebot import (
    ONEBOT_CAPABILITIES,
    OneBotActionRejected,
    OneBotActionResult,
    OneBotActionTimeout,
    OneBotActionValidationError,
    OneBotFileResult,
    OneBotGroupInfo,
    OneBotHistoryPage,
    OneBotMemberInfo,
    OneBotMessageReceipt,
    OneBotTransportError,
    get_capability_descriptor,
)
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform import Platform
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.register import register_platform_adapter
from astrbot.core.utils.error_redaction import safe_error

from ..aiocqhttp.forward_node_splitter import split_long_text_node
from .codec import (
    build_notice_message,
    build_request_message,
    coerce_bool_value,
    coerce_numeric_value,
    decode_cq_text,
    sanitize_segment_type,
)
from .exceptions import NapCatApiError, NapCatTransportError
from .forward_ws_client import NapCatForwardWebSocketClient
from .generated.ob11_events import (
    AnonymousSegment,
    AtSegment,
    ContactSegment,
    CustomMusicSegment,
    CustomNodeSegments,
    DiceSegment,
    DirectNodeSegment,
    FaceSegment,
    FileSegment,
    ForwardSegment,
    ImageSegment,
    JsonSegment,
    LocationSegment,
    MusicSegment,
    OB11AllEvent,
    OB11GroupMessage,
    OB11PrivateMessage,
    OB11Segment,
    OneBot11BotOffline,
    OneBot11FriendAdd,
    OneBot11FriendRecall,
    OneBot11FriendRequest,
    OneBot11GroupAdmin,
    OneBot11GroupBan,
    OneBot11GroupCard,
    OneBot11GroupDecrease,
    OneBot11GroupEssence,
    OneBot11GroupGrayTip,
    OneBot11GroupIncrease,
    OneBot11GroupMessageReaction,
    OneBot11GroupMessageReactionLagrange,
    OneBot11GroupName,
    OneBot11GroupRecall,
    OneBot11GroupRequest,
    OneBot11GroupTitle,
    OneBot11GroupUpload,
    OneBot11Honor,
    OneBot11InputStatus,
    OneBot11LuckyKing,
    OneBot11OnlineFileReceive,
    OneBot11OnlineFileSend,
    OneBot11Poke,
    OneBot11ProfileLike,
    PokeSegment,
    RecordSegment,
    ReplySegment,
    RpsSegment,
    ShakeSegment,
    ShareSegment,
    TextSegment,
    VideoSegment,
    XmlSegment,
)
from .generated.ob11_events import (
    FlashTransferSegment as OB11FlashTransferSegment,
)
from .generated.ob11_events import (
    MarkdownSegment as OB11MarkdownSegment,
)
from .generated.ob11_events import (
    MFaceSegment as OB11MFaceSegment,
)
from .generated.ob11_events import (
    MiniAppSegment as OB11MiniAppSegment,
)
from .generated.ob11_events import (
    OnlineFileSegment as OB11OnlineFileSegment,
)
from .inbound_events import NapCatGenericEvent, NapCatInboundEvent
from .message_event import NapCatMessageEvent
from .types import (
    NapCatFetchedMessage,
    NapCatLoginInfo,
    NapCatSendMessageResult,
    NapCatStatus,
    NapCatVersionInfo,
)


class NapCatOutboundProtocol:
    """Own the OneBot outbound transport protocol for an adapter instance."""

    def __init__(
        self,
        client: NapCatForwardWebSocketClient,
        build_message: Callable[[MessageChain], Awaitable[str | list[object]]],
        forward_message_max_retries: int = 3,
        forward_message_fallback_enabled: bool = True,
    ) -> None:
        self.client = client
        self._build_message = build_message
        self.forward_message_max_retries = forward_message_max_retries
        self.forward_message_fallback_enabled = forward_message_fallback_enabled

    async def send_standard(
        self,
        session: MessageSession,
        message_chain: MessageChain,
    ) -> None:
        payload = await self._build_message(message_chain)
        if session.message_type == MessageType.GROUP_MESSAGE:
            await self.client.send_group_message(
                group_id=session.session_id,
                message=payload,
            )
            return
        await self.client.send_private_message(
            user_id=session.session_id,
            message=payload,
        )

    async def send_forward(
        self,
        session: MessageSession,
        component: Node | Nodes,
    ) -> None:
        node_payload = (
            await component.to_dict()
            if isinstance(component, Nodes)
            else await Nodes([component]).to_dict()
        )
        messages = node_payload.get("messages", [])
        if not isinstance(messages, list) or not messages:
            raise ValueError("NapCat forward message payload did not contain nodes")
        if self.forward_message_fallback_enabled:
            await self._send_forward_with_fallback(
                session, messages, self.forward_message_max_retries
            )
        else:
            await self._send_forward_chunk(session, messages)

    @staticmethod
    def _is_forward_size_error(exc: NapCatApiError) -> bool:
        detail = " ".join(
            value for value in (exc.message, exc.wording, str(exc)) if value
        ).lower()
        return any(
            marker in detail
            for marker in ("resid", "message too long", "content too long", "too large")
        )

    async def _send_forward_chunk(
        self, session: MessageSession, messages: list[object]
    ) -> None:
        if session.message_type == MessageType.GROUP_MESSAGE:
            await self.client.send_group_forward_message(
                group_id=session.session_id,
                messages=messages,
            )
            return
        await self.client.send_private_forward_message(
            user_id=session.session_id,
            messages=messages,
        )

    @staticmethod
    def _plain_text(messages: list[object]) -> str | None:
        parts: list[str] = []
        for message in messages:
            if not isinstance(message, dict):
                return None
            data = message.get("data")
            content = data.get("content") if isinstance(data, dict) else None
            if not isinstance(content, list):
                return None
            for segment in content:
                if not isinstance(segment, dict) or segment.get("type") != "text":
                    return None
                segment_data = segment.get("data")
                if not isinstance(segment_data, dict):
                    return None
                text = segment_data.get("text")
                if not isinstance(text, str):
                    return None
                parts.append(text)
        return "".join(parts)

    async def _send_forward_with_fallback(
        self, session: MessageSession, messages: list[object], max_retries: int = 3
    ) -> None:
        try:
            await self._send_forward_chunk(session, messages)
            return
        except NapCatApiError as exc:
            if not self._is_forward_size_error(exc):
                raise

        pending = [messages]
        retries = 0
        while pending:
            chunk = pending.pop(0)
            try:
                await self._send_forward_chunk(session, chunk)
                continue
            except NapCatApiError as exc:
                if not self._is_forward_size_error(exc):
                    raise
                retries += 1
                if len(chunk) > 1 and retries <= max_retries:
                    midpoint = len(chunk) // 2
                    pending[:0] = [chunk[:midpoint], chunk[midpoint:]]
                    continue
                text = self._plain_text(chunk)
                if text is None:
                    raise
                for segment in split_long_text_node(
                    text, 1500, r"[^。？！~…]+[。？！~…]+"
                ):
                    await self.send_standard(session, MessageChain().message(segment))


NAPCAT_NOTICE_EVENT_TYPES = (
    OneBot11BotOffline,
    OneBot11FriendAdd,
    OneBot11FriendRecall,
    OneBot11GroupAdmin,
    OneBot11GroupBan,
    OneBot11GroupCard,
    OneBot11GroupDecrease,
    OneBot11GroupEssence,
    OneBot11GroupIncrease,
    OneBot11GroupMessageReaction,
    OneBot11GroupMessageReactionLagrange,
    OneBot11GroupRecall,
    OneBot11GroupUpload,
    OneBot11GroupGrayTip,
    OneBot11GroupName,
    OneBot11GroupTitle,
    OneBot11Honor,
    OneBot11InputStatus,
    OneBot11LuckyKing,
    OneBot11OnlineFileReceive,
    OneBot11OnlineFileSend,
    OneBot11Poke,
    OneBot11ProfileLike,
)

NAPCAT_REQUEST_EVENT_TYPES = (
    OneBot11FriendRequest,
    OneBot11GroupRequest,
)

_CQ_SEGMENT_PATTERN = re.compile(r"\[CQ:(\w+)((?:,\w+=[^,\]]*)*)]")

NAPCAT_CONFIG_TEMPLATE = {
    "type": "napcat",
    "enable": False,
    "id": "napcat",
    "ws_url": "ws://127.0.0.1:3001",
    "token": "",
    "verify_ssl": True,
    "timeout_seconds": 30,
    "reconnect_interval_seconds": 5,
    "max_frame_size_mb": 50,
}

NAPCAT_CONFIG_METADATA = {
    "ws_url": {
        "description": "NapCat WebSocket URL",
        "type": "string",
        "hint": "NapCat OneBot v11 forward WebSocket URL, for example ws://127.0.0.1:3001.",
    },
    "token": {
        "description": "NapCat Token",
        "type": "string",
        "hint": "Optional WebSocket authorization token configured in NapCat.",
        "collapsed": True,
    },
    "verify_ssl": {
        "description": "Verify SSL",
        "type": "boolean",
        "hint": "Disable only when NapCat uses a self-signed WSS certificate.",
        "collapsed": True,
    },
    "timeout_seconds": {
        "description": "Action Timeout Seconds",
        "type": "float",
        "hint": "Maximum time to wait for a NapCat action response over WebSocket.",
        "collapsed": True,
    },
    "reconnect_interval_seconds": {
        "description": "Reconnect Interval Seconds",
        "type": "float",
        "hint": "Delay before reconnecting after the NapCat WebSocket disconnects.",
        "collapsed": True,
    },
    "max_frame_size_mb": {
        "description": "Max Frame Size MB",
        "type": "int",
        "hint": "Maximum inbound WebSocket frame size in megabytes.",
        "collapsed": True,
    },
}

NAPCAT_I18N_RESOURCES = {
    "zh-CN": {
        "ws_url": {
            "description": "NapCat WebSocket 地址",
            "hint": "NapCat OneBot v11 正向 WebSocket 地址，例如 ws://127.0.0.1:3001。",
        },
        "token": {
            "description": "NapCat Token",
            "hint": "可选。填写 NapCat WebSocket 侧配置的鉴权令牌。",
        },
        "verify_ssl": {
            "description": "校验 SSL",
            "hint": "仅当 NapCat 使用自签名 WSS 证书时再关闭。",
        },
        "timeout_seconds": {
            "description": "动作超时秒数",
            "hint": "通过 WebSocket 调用 NapCat 动作时的单次响应超时时间。",
        },
        "reconnect_interval_seconds": {
            "description": "重连间隔秒数",
            "hint": "NapCat WebSocket 断开后，AstrBot 再次发起连接前的等待时间。",
        },
        "max_frame_size_mb": {
            "description": "最大帧大小(MB)",
            "hint": "允许接收的单个 WebSocket 帧的最大大小，单位 MB。",
        },
    },
    "en-US": {
        "ws_url": {
            "description": "NapCat WebSocket URL",
            "hint": "NapCat OneBot v11 forward WebSocket URL, for example ws://127.0.0.1:3001.",
        },
        "token": {
            "description": "NapCat Token",
            "hint": "Optional WebSocket authorization token configured in NapCat.",
        },
        "verify_ssl": {
            "description": "Verify SSL",
            "hint": "Disable only when NapCat uses a self-signed WSS certificate.",
        },
        "timeout_seconds": {
            "description": "Action Timeout Seconds",
            "hint": "Maximum time to wait for a NapCat action response over WebSocket.",
        },
        "reconnect_interval_seconds": {
            "description": "Reconnect Interval Seconds",
            "hint": "Delay before reconnecting after the NapCat WebSocket disconnects.",
        },
        "max_frame_size_mb": {
            "description": "Max Frame Size MB",
            "hint": "Maximum inbound WebSocket frame size in megabytes.",
        },
    },
}


@register_platform_adapter(
    "napcat",
    "NapCat platform adapter backed by a forward OneBot v11 WebSocket connection.",
    default_config_tmpl=NAPCAT_CONFIG_TEMPLATE,
    adapter_display_name="NapCat",
    support_streaming_message=False,
    config_metadata=NAPCAT_CONFIG_METADATA,
    i18n_resources=NAPCAT_I18N_RESOURCES,
)
class NapCatPlatformAdapter(Platform):
    PLATFORM_CAPABILITIES = ONEBOT_CAPABILITIES

    _MESSAGE_EVENT_HANDLE_SLOW_LOG_THRESHOLD_S = 0.2
    _MAX_INBOUND_COMPONENT_DEPTH = 8

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        self.metadata = PlatformMetadata(
            name="napcat",
            description="NapCat platform adapter",
            id=cast(str, self.config.get("id", "napcat")),
            adapter_display_name="NapCat",
            support_streaming_message=False,
            supported_actions=type(self).declared_supported_actions(),
        )
        self.shutdown_event = asyncio.Event()
        max_size_mb = int(platform_config.get("max_frame_size_mb", 50))
        self.client = NapCatForwardWebSocketClient(
            ws_url=str(platform_config.get("ws_url", "")).strip(),
            token=str(platform_config.get("token", "")).strip() or None,
            verify_ssl=bool(platform_config.get("verify_ssl", True)),
            action_timeout_seconds=float(platform_config.get("timeout_seconds", 30)),
            reconnect_interval_seconds=float(
                platform_config.get("reconnect_interval_seconds", 5)
            ),
            max_size_bytes=max_size_mb * 1024 * 1024,
            on_event=self.handle_forward_ws_event,
        )
        self.outbound = NapCatOutboundProtocol(
            self.client,
            self._build_outbound_message,
            int(platform_config.get("forward_message_max_retries", 3)),
            bool(platform_config.get("forward_message_fallback_enabled", True)),
        )

    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def set_group_admin(
        self,
        *,
        group_id: str | int,
        user_id: str | int,
        enable: bool = True,
    ) -> dict[str, object]:
        return await self.client.set_group_admin(
            group_id=group_id,
            user_id=user_id,
            enable=enable,
        )

    async def set_group_ban(
        self,
        *,
        group_id: str | int,
        user_id: str | int,
        duration: int | float = 0,
    ) -> dict[str, object]:
        return await self.client.set_group_ban(
            group_id=group_id,
            user_id=user_id,
            duration=duration,
        )

    async def set_group_card(
        self,
        *,
        group_id: str | int,
        user_id: str | int,
        card: str | None = None,
    ) -> dict[str, object]:
        return await self.client.set_group_card(
            group_id=group_id,
            user_id=user_id,
            card=card,
        )

    async def kick_group_member(
        self,
        *,
        group_id: str | int,
        user_id: str | int,
        reject_add_request: bool | None = None,
    ) -> dict[str, object]:
        return await self.client.set_group_kick(
            group_id=group_id,
            user_id=user_id,
            reject_add_request=reject_add_request,
        )

    async def kick_group_members(
        self,
        *,
        group_id: str | int,
        user_ids: list[str | int],
        reject_add_request: bool | None = None,
    ) -> dict[str, object]:
        return await self.client.set_group_kick_members(
            group_id=group_id,
            user_ids=user_ids,
            reject_add_request=reject_add_request,
        )

    async def leave_group(
        self,
        *,
        group_id: str | int,
        is_dismiss: bool | None = None,
    ) -> dict[str, object]:
        return await self.client.set_group_leave(
            group_id=group_id,
            is_dismiss=is_dismiss,
        )

    async def set_group_whole_ban(
        self,
        *,
        group_id: str | int,
        enable: bool = True,
    ) -> dict[str, object]:
        return await self.client.set_group_whole_ban(
            group_id=group_id,
            enable=enable,
        )

    async def set_essence_message(
        self,
        *,
        message_id: str | int | float,
    ) -> dict[str, object]:
        return await self.client.set_essence_message(message_id=message_id)

    async def delete_essence_message(
        self,
        *,
        message_id: str | int | float | None = None,
        msg_seq: str | None = None,
        msg_random: str | None = None,
        group_id: str | int | None = None,
    ) -> dict[str, object]:
        return await self.client.delete_essence_message(
            message_id=message_id,
            msg_seq=msg_seq,
            msg_random=msg_random,
            group_id=group_id,
        )

    async def send_group_notice(
        self,
        *,
        group_id: str | int,
        content: str,
        pinned: int | float | None = None,
        type_: int | float | None = None,
        confirm_required: int | float | None = None,
        is_show_edit_card: int | float | None = None,
        tip_window_type: int | float | None = None,
        image: str | None = None,
    ) -> dict[str, object]:
        return await self.client.send_group_notice(
            group_id=group_id,
            content=content,
            pinned=pinned,
            type_=type_,
            confirm_required=confirm_required,
            is_show_edit_card=is_show_edit_card,
            tip_window_type=tip_window_type,
            image=image,
        )

    async def send_like(
        self,
        *,
        user_id: str | int,
        times: int | float = 1,
    ) -> dict[str, object]:
        return await self.client.send_like(user_id=user_id, times=times)

    async def send_poke(
        self,
        *,
        user_id: str | int,
        group_id: str | int | None = None,
        target_id: str | int | None = None,
    ) -> dict[str, object]:
        if group_id is not None:
            return await self.client.group_poke(
                user_id=user_id,
                group_id=group_id,
                target_id=target_id,
            )
        return await self.client.friend_poke(
            user_id=user_id,
            target_id=target_id,
        )

    async def invoke_capability(
        self,
        capability_name: str,
        action_name: str,
        **kwargs: Any,
    ) -> object:
        """Provide only explicitly registered OneBot/NapCat actions."""
        if capability_name not in {"onebot.v11", "napcat.qq"}:
            raise OneBotActionValidationError(
                "Unsupported capability", action=action_name
            )
        descriptor = get_capability_descriptor(capability_name)
        action = descriptor.action(action_name) if descriptor is not None else None
        if action is None:
            raise OneBotActionValidationError(
                "Action is not registered", action=action_name
            )
        try:
            validated_kwargs = action.input_model.validate(kwargs)
        except OneBotActionValidationError as exc:
            raise OneBotActionValidationError(exc.message, action=action_name) from exc
        actions = {
            "send": lambda: self.client.send_message(**validated_kwargs),
            "send_private": lambda: self.client.send_private_message(
                **validated_kwargs
            ),
            "send_group": lambda: self.client.send_group_message(**validated_kwargs),
            "send_forward": lambda: (
                self.client.send_private_forward_message(**validated_kwargs)
                if validated_kwargs.get("user_id") is not None
                else self.client.send_group_forward_message(**validated_kwargs)
            ),
            "delete": lambda: self.client.delete_message(
                validated_kwargs["message_id"]
            ),
            "get_message": lambda: self.client.get_message(
                validated_kwargs["message_id"]
            ),
            "get_forward_message": lambda: self.client.get_forward_message(
                validated_kwargs["forward_id"]
            ),
            "get_login_info": self.client.get_login_info,
            "get_status": self.client.get_status,
            "get_version_info": self.client.get_version_info,
            "get_group_info": lambda: self.client.get_group_info(
                validated_kwargs["group_id"]
            ),
            "get_group_member_info": lambda: self.client.get_group_member_info(
                validated_kwargs["group_id"],
                validated_kwargs["user_id"],
                no_cache=validated_kwargs.get("no_cache"),
            ),
            "get_group_member_list": lambda: self.client.get_group_member_list(
                validated_kwargs["group_id"], no_cache=validated_kwargs.get("no_cache")
            ),
            "get_stranger_info": lambda: self.client.get_stranger_info(
                validated_kwargs["user_id"],
                no_cache=bool(validated_kwargs.get("no_cache", False)),
            ),
            "get_image": lambda: self.client.get_image(
                file=validated_kwargs.get("file"),
                file_id=validated_kwargs.get("file_id"),
            ),
            "get_file": lambda: self.client.get_file(
                file=validated_kwargs.get("file"),
                file_id=validated_kwargs.get("file_id"),
            ),
            "get_group_file_url": lambda: self.client.get_group_file_url(
                group_id=validated_kwargs["group_id"],
                file_id=validated_kwargs["file_id"],
            ),
            "get_private_file_url": lambda: self.client.get_private_file_url(
                file_id=validated_kwargs["file_id"]
            ),
            "set_group_admin": lambda: self.client.set_group_admin(**validated_kwargs),
            "set_group_ban": lambda: self.client.set_group_ban(**validated_kwargs),
            "set_group_card": lambda: self.client.set_group_card(**validated_kwargs),
            "kick_group_member": lambda: self.client.set_group_kick(**validated_kwargs),
            "kick_group_members": lambda: self.client.set_group_kick_members(
                **validated_kwargs
            ),
            "leave_group": lambda: self.client.set_group_leave(**validated_kwargs),
            "set_group_whole_ban": lambda: self.client.set_group_whole_ban(
                **validated_kwargs
            ),
            "set_essence_message": lambda: self.client.set_essence_message(
                message_id=validated_kwargs["message_id"]
            ),
            "delete_essence_message": lambda: self.client.delete_essence_message(
                **validated_kwargs
            ),
            "set_friend_add_request": lambda: self.client.set_friend_add_request(
                **validated_kwargs
            ),
            "set_group_add_request": lambda: self.client.set_group_add_request(
                **validated_kwargs
            ),
            "get_group_msg_history": lambda: self.client.get_group_msg_history(
                **validated_kwargs
            ),
            "get_friend_msg_history": lambda: self.client.get_friend_msg_history(
                **validated_kwargs
            ),
            "send_like": lambda: self.client.send_like(**validated_kwargs),
            "friend_poke": lambda: self.client.friend_poke(**validated_kwargs),
            "group_poke": lambda: self.client.group_poke(**validated_kwargs),
            "send_group_notice": lambda: self.client.send_group_notice(
                **validated_kwargs
            ),
            "set_input_status": lambda: self.client.set_input_status(
                **validated_kwargs
            ),
            "get_online_file_messages": lambda: self.client.get_online_file_messages(
                **validated_kwargs
            ),
            "create_flash_task": lambda: self.client.create_flash_task(
                **validated_kwargs
            ),
            "get_flash_file_list": lambda: self.client.get_flash_file_list(
                **validated_kwargs
            ),
            "get_flash_file_url": lambda: self.client.get_flash_file_url(
                **validated_kwargs
            ),
            "receive_online_file": lambda: self.client.receive_online_file(
                **validated_kwargs
            ),
            "refuse_online_file": lambda: self.client.refuse_online_file(
                **validated_kwargs
            ),
            "cancel_online_file": lambda: self.client.cancel_online_file(
                **validated_kwargs
            ),
            "send_online_file": lambda: self.client.send_online_file(
                **validated_kwargs
            ),
            "send_online_folder": lambda: self.client.send_online_folder(
                **validated_kwargs
            ),
            "send_flash_message": lambda: self.client.send_flash_message(
                **validated_kwargs
            ),
            "fetch_custom_face": lambda: self.client.fetch_custom_face(
                **validated_kwargs
            ),
            "get_ai_characters": lambda: self.client.get_ai_characters(
                **validated_kwargs
            ),
            "send_group_ai_record": lambda: self.client.send_group_ai_record(
                **validated_kwargs
            ),
        }
        handler = actions.get(action_name)
        if handler is None:
            raise OneBotActionValidationError(
                "Action is not registered", action=action_name
            )
        try:
            result = await handler()
        except asyncio.CancelledError:
            raise
        except (ValueError, TypeError, KeyError) as exc:
            raise OneBotActionValidationError(
                "Invalid OneBot action parameters", action=action_name
            ) from exc
        except NapCatApiError as exc:
            raise OneBotActionRejected(
                "OneBot action was rejected", action=action_name, code=exc.retcode
            ) from exc
        except NapCatTransportError as exc:
            retryable = action.retryable and not action.destructive
            if "timed out" in str(exc).lower():
                raise OneBotActionTimeout(
                    "OneBot action timed out", action=action_name, retryable=retryable
                ) from exc
            raise OneBotTransportError(
                "OneBot transport is unavailable",
                action=action_name,
                retryable=retryable,
            ) from exc
        except Exception as exc:
            logger.warning(
                "[NapCat] OneBot capability action %s failed: %s",
                action_name,
                safe_error("", exc),
            )
            raise OneBotTransportError(
                "OneBot action could not be completed",
                action=action_name,
                retryable=action.retryable and not action.destructive,
            ) from exc
        return self._to_onebot_result(action_name, result)

    @staticmethod
    def _to_onebot_result(action: str, result: Any) -> object:
        if isinstance(result, NapCatSendMessageResult):
            return OneBotMessageReceipt(
                str(result.message_id), result.res_id, result.forward_id, result.extra
            )
        if isinstance(result, NapCatLoginInfo):
            return OneBotActionResult(
                action,
                data=cast(
                    Any,
                    {
                        "user_id": str(result.user_id),
                        "nickname": result.nickname,
                        **result.extra,
                    },
                ),
                payload=result.extra,
            )
        if isinstance(result, NapCatStatus):
            return OneBotActionResult(
                action,
                data=cast(
                    Any,
                    {
                        "online": result.online,
                        "good": result.good,
                        "stat": result.stats,
                        **result.extra,
                    },
                ),
                payload=result.extra,
            )
        if isinstance(result, NapCatVersionInfo):
            return OneBotActionResult(
                action,
                data={
                    "app_name": result.app_name,
                    "app_version": result.app_version,
                    "protocol_version": result.protocol_version,
                    **result.extra,
                },
                payload=result.extra,
            )
        if isinstance(result, NapCatFetchedMessage):
            return OneBotActionResult(
                action,
                data=cast(
                    Any,
                    {
                        "message_id": str(result.message_id),
                        "user_id": str(result.sender_id)
                        if result.sender_id is not None
                        else None,
                        "time": result.time,
                        "raw_message": result.raw_message,
                        "message": result.message_payload,
                        **result.extra,
                    },
                ),
                payload=result.extra,
            )
        if isinstance(result, dict):
            if action == "get_group_info":
                return OneBotGroupInfo.from_payload(result)
            if action in {"get_group_member_info", "get_stranger_info"}:
                return OneBotMemberInfo.from_payload(result)
            if action in {
                "get_image",
                "get_file",
                "get_group_file_url",
                "get_private_file_url",
            }:
                return OneBotFileResult(
                    file_id=result.get("file_id"),
                    url=result.get("url"),
                    file=result.get("file"),
                    payload=result,
                )
            return OneBotActionResult(
                action,
                data=result.get("data"),
                retcode=result.get("retcode"),
                status=result.get("status"),
                payload=result,
            )
        if isinstance(result, list):
            if action == "get_group_member_list":
                return tuple(
                    OneBotMemberInfo.from_payload(item)
                    for item in result
                    if isinstance(item, Mapping)
                )
            if action in {"get_group_msg_history", "get_friend_msg_history"}:
                items = tuple(item for item in result if isinstance(item, Mapping))
                next_message_seq = str(items[-1].get("message_seq")) if items else None
                return OneBotHistoryPage(
                    items=items,
                    next_message_seq=next_message_seq,
                    payload=cast(Any, {"messages": result}),
                )
            return OneBotActionResult(
                action, data=cast(Any, result), payload=cast(Any, {"data": result})
            )
        return OneBotActionResult(action, data=result)

    async def set_input_status(
        self,
        *,
        user_id: str | int,
        event_type: int | float = 1,
    ) -> dict[str, object]:
        return await self.client.set_input_status(
            user_id=user_id,
            event_type=event_type,
        )

    async def get_group_msg_history(
        self,
        *,
        group_id: str | int,
        count: int = 20,
        message_seq: int | str | None = None,
    ) -> list[dict[str, object]]:
        return await self.client.get_group_msg_history(
            group_id=group_id,
            count=count,
            message_seq=message_seq,
        )

    async def get_friend_msg_history(
        self,
        *,
        user_id: str | int,
        count: int = 20,
        message_seq: int | str | None = None,
    ) -> list[dict[str, object]]:
        return await self.client.get_friend_msg_history(
            user_id=user_id,
            count=count,
            message_seq=message_seq,
        )

    async def fetch_custom_face(self, *, count: int = 48) -> list[object]:
        return await self.client.fetch_custom_face(count=count)

    async def get_ai_characters(
        self,
        *,
        group_id: str | int,
        chat_type: int | float = 1,
    ) -> list[object]:
        return await self.client.get_ai_characters(
            group_id=group_id,
            chat_type=chat_type,
        )

    async def send_group_ai_record(
        self,
        *,
        group_id: str | int,
        character: str,
        text: str,
        chat_type: int | float = 1,
        timeout_seconds: float = 10.0,
    ) -> dict[str, object]:
        return await self.client.send_group_ai_record(
            group_id=group_id,
            character=character,
            text=text,
            chat_type=chat_type,
            timeout_seconds=timeout_seconds,
        )

    async def run(self) -> None:
        while not self.shutdown_event.is_set():
            try:
                await self.client.start()
                version = await self.client.get_version_info()
                status = await self.client.get_status()
                login_info = await self.client.get_login_info()
            except NapCatApiError as exc:
                self.record_error(str(exc))
                logger.error("[NapCat] startup check failed: %s", exc)
                await self.client.close()
                raise
            except NapCatTransportError as exc:
                logger.warning(
                    "[NapCat] startup transport unavailable: %s. Retrying in %.1fs.",
                    exc,
                    self.client.reconnect_interval_seconds,
                )
                try:
                    await asyncio.wait_for(
                        self.shutdown_event.wait(),
                        timeout=self.client.reconnect_interval_seconds,
                    )
                except TimeoutError:
                    continue
                return

            logger.info(
                "[NapCat] Forward WebSocket adapter ready: user_id=%s nickname=%s app=%s version=%s online=%s good=%s",
                login_info.user_id,
                login_info.nickname,
                version.app_name,
                version.app_version,
                status.online,
                status.good,
            )
            break

        await self.shutdown_event.wait()

    async def terminate(self) -> None:
        self.shutdown_event.set()
        await self.client.close()

    async def send_by_session(
        self,
        session: MessageSession,
        message_chain: MessageChain,
    ):
        if any(
            isinstance(component, Node | Nodes) for component in message_chain.chain
        ):
            await self._send_mixed_outbound_message(session, message_chain)
        else:
            await self._send_standard_message(session, message_chain)
        return await super().send_by_session(session, message_chain)

    async def _send_standard_message(
        self,
        session: MessageSession,
        message_chain: MessageChain,
    ) -> None:
        await self.outbound.send_standard(session, message_chain)

    async def _send_mixed_outbound_message(
        self,
        session: MessageSession,
        message_chain: MessageChain,
    ) -> None:
        pending_standard: list[BaseMessageComponent] = []
        for component in message_chain.chain:
            if isinstance(component, Node | Nodes):
                if pending_standard:
                    await self._send_standard_message(
                        session,
                        message_chain.derive(chain=list(pending_standard)),
                    )
                    pending_standard.clear()
                await self._send_forward_component(session, component)
                continue
            pending_standard.append(component)

        if pending_standard:
            await self._send_standard_message(
                session,
                message_chain.derive(chain=pending_standard),
            )

    async def _send_forward_component(
        self,
        session: MessageSession,
        component: Node | Nodes,
    ) -> None:
        await self.outbound.send_forward(session, component)

    def _append_basic_outbound_segments(
        self,
        component: BaseMessageComponent,
        segments: list[object],
        fallback_parts: list[str],
    ) -> bool:
        """Convert text, mentions, replies, and expression components."""
        if isinstance(component, Plain):
            if component.text:
                segments.append(self.client.text(component.text))
                fallback_parts.append(component.text)
            return True
        if isinstance(component, AtAll):
            segments.append(self.client.at_all())
            fallback_parts.append("@all")
            return True
        if isinstance(component, At):
            segments.append(self.client.at(component.qq, name=component.name))
            fallback_parts.append(f"@{component.name or component.qq}")
            return True
        if isinstance(component, Reply):
            segments.append(self.client.reply(component.id))
            fallback_parts.append("[Reply]")
            return True
        if isinstance(component, Face):
            segments.append(self.client.face(component.id))
            fallback_parts.append("[Face]")
            return True
        if isinstance(component, MFace):
            segments.append(
                self.client.mface(
                    emoji_package_id=component.emoji_package_id,
                    emoji_id=component.emoji_id,
                    key=component.key,
                    summary=component.summary,
                )
            )
            fallback_parts.append(
                f"[MFace:{component.summary}]" if component.summary else "[MFace]"
            )
            return True
        return False

    async def _append_media_outbound_segment(
        self,
        component: BaseMessageComponent,
        segments: list[object],
        fallback_parts: list[str],
    ) -> bool:
        """Convert image, audio, video, and file components."""
        if isinstance(component, Image | Record | Video):
            file_value = component.file or component.url or component.path
            if not file_value:
                return False
            if isinstance(component, Image):
                segments.append(
                    self.client.image(
                        file=file_value,
                        url=component.url or None,
                        path=component.path or None,
                    )
                )
                fallback_parts.append("[Image]")
            elif isinstance(component, Record):
                segments.append(
                    self.client.record(
                        file=file_value,
                        url=component.url or None,
                        path=component.path or None,
                    )
                )
                fallback_parts.append("[Record]")
            else:
                segments.append(
                    self.client.video(
                        file=file_value,
                        url=component.url or None,
                        path=component.path or None,
                        thumb=component.cover or None,
                    )
                )
                fallback_parts.append("[Video]")
            return True

        if not isinstance(component, File):
            return False
        file_value = await component.get_file(allow_return_url=True)
        if not file_value:
            return False
        segments.append(
            self.client.file(
                file=file_value,
                url=component.url or None,
                name=component.name or None,
            )
        )
        fallback_parts.append(
            f"[File:{component.name}]" if component.name else "[File]"
        )
        return True

    async def _build_outbound_message(
        self, message_chain: MessageChain
    ) -> str | list[object]:
        segments: list[object] = []
        fallback_parts: list[str] = []

        for component in message_chain.chain:
            if self._append_basic_outbound_segments(
                component,
                segments,
                fallback_parts,
            ):
                continue

            if await self._append_media_outbound_segment(
                component,
                segments,
                fallback_parts,
            ):
                continue

            if isinstance(component, Contact):
                if component.id:
                    segments.append(
                        self.client.contact(
                            contact_type=component.sub_type,
                            contact_id=component.id,
                        )
                    )
                    fallback_parts.append("[Contact]")
                    continue

            if isinstance(component, Location):
                segments.append(
                    self.client.location(
                        lat=component.lat,
                        lon=component.lon,
                        title=component.title or None,
                        content=component.content or None,
                    )
                )
                fallback_parts.append("[Location]")
                continue

            if isinstance(component, Poke):
                poke_payload = (await component.to_dict()).get("data", {})
                segments.append(
                    self.client.poke(
                        poke_type=poke_payload.get("type"),
                        target_id=poke_payload.get("id"),
                    )
                )
                fallback_parts.append("[Poke]")
                continue

            if isinstance(component, Json):
                segments.append(self.client.json_message(component.data))
                fallback_parts.append("[Json]")
                continue

            if isinstance(component, Markdown):
                segments.append(self.client.markdown_message(component.content))
                fallback_parts.append("[Markdown]")
                continue

            if isinstance(component, MiniApp):
                segments.append(self.client.mini_app_message(component.data))
                fallback_parts.append("[MiniApp]")
                continue

            if isinstance(component, OnlineFile):
                segments.append(
                    self.client.online_file(
                        msg_id=component.msg_id,
                        element_id=component.element_id,
                        file_name=component.file_name,
                        file_size=component.file_size,
                        is_dir=component.is_dir,
                    )
                )
                fallback_parts.append(f"[OnlineFile:{component.file_name}]")
                continue

            if isinstance(component, Xml):
                segments.append(self.client.xml_message(component.data))
                fallback_parts.append("[Xml]")
                continue

            if isinstance(component, FlashTransfer):
                segments.append(
                    self.client.flash_transfer(file_set_id=component.file_set_id)
                )
                fallback_parts.append("[FlashTransfer]")
                continue

            if isinstance(component, Share):
                segments.append(
                    self.client.share(
                        url=component.url,
                        title=component.title,
                        content=component.content or None,
                        image=component.image or None,
                    )
                )
                fallback_parts.append("[Share]")
                continue

            if isinstance(component, Dice):
                segments.append(self.client.dice())
                fallback_parts.append("[Dice]")
                continue

            if isinstance(component, RPS):
                segments.append(self.client.rps())
                fallback_parts.append("[RPS]")
                continue

            if isinstance(component, Shake):
                segments.append(self.client.shake())
                fallback_parts.append("[Shake]")
                continue

            if isinstance(component, Music):
                if component.sub_type == "custom":
                    if component.url and component.image:
                        segments.append(
                            self.client.music(
                                music_type=component.sub_type,
                                url=component.url,
                                audio=component.audio or None,
                                title=component.title or None,
                                image=component.image,
                                content=component.content or None,
                            )
                        )
                        fallback_parts.append("[Music]")
                        continue
                elif component.id:
                    segments.append(
                        self.client.music(
                            music_type=component.sub_type,
                            music_id=component.id,
                        )
                    )
                    fallback_parts.append("[Music]")
                    continue

            if isinstance(component, Forward):
                if component.id:
                    segments.append(self.client.forward(component.id))
                    fallback_parts.append("[Forward]")
                    continue

            fallback_parts.append(f"[{component.__class__.__name__}]")

        if segments:
            return segments

        fallback = " ".join(part for part in fallback_parts if part).strip()
        if fallback:
            return fallback
        return "[Unsupported message]"

    def create_event(self, message: AstrBotMessage) -> NapCatMessageEvent:
        event = NapCatMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            adapter=self,
        )
        raw_event = message.raw_message
        sender = getattr(raw_event, "sender", None)
        role = getattr(sender, "role", None)
        # NapCat's sender role is a group-membership fact.  Private-message
        # payloads must never be able to promote their sender to a
        # session_owner/session_admin during authorization attachment.
        if not event.is_private_chat() and role is not None:
            event.set_platform_member_role(
                str(getattr(role, "value", role)), source="adapter"
            )
        self._populate_event_extras(event, raw_event)
        return event

    async def handle_forward_ws_event(self, event: NapCatInboundEvent) -> None:
        payload = event.root if isinstance(event, OB11AllEvent) else event
        if isinstance(payload, OB11GroupMessage | OB11PrivateMessage):
            ignore_reason = self._get_ignored_forward_ws_message_reason(payload)
            if ignore_reason is not None:
                logger.debug(
                    "[NapCat] Ignored forward WebSocket %s message: platform_id=%s reason=%s outline=%s",
                    payload.message_type,
                    self.meta().id,
                    ignore_reason,
                    payload.raw_message or "[empty]",
                )
                return
            started_at = monotonic()
            message = await self._convert_message_event(payload)
            queued_event = self.create_event(message)
            scope = "group" if message.type == MessageType.GROUP_MESSAGE else "private"
            logger.info(
                "[NapCat] Received %s message: platform_id=%s session=%s sender=%s outline=%s",
                scope,
                self.meta().id,
                message.session_id,
                message.sender.user_id if message.sender else "",
                queued_event.get_message_outline() or message.message_str or "[empty]",
            )
            self.commit_event(queued_event)
            elapsed = monotonic() - started_at
            if elapsed >= self._MESSAGE_EVENT_HANDLE_SLOW_LOG_THRESHOLD_S:
                logger.info(
                    "[NapCat] Slow inbound message handling: platform_id=%s session=%s elapsed=%.2fs outline=%s",
                    self.meta().id,
                    message.session_id,
                    elapsed,
                    queued_event.get_message_outline()
                    or message.message_str
                    or "[empty]",
                )
            return

        if isinstance(payload, NAPCAT_NOTICE_EVENT_TYPES) or (
            isinstance(payload, NapCatGenericEvent) and payload.post_type == "notice"
        ):
            ignore_reason = self._get_ignored_notice_event_reason(payload)
            if ignore_reason is not None:
                logger.debug(
                    "[NapCat] Ignored notice event: platform_id=%s reason=%s summary=%s",
                    self.meta().id,
                    ignore_reason,
                    self._build_notice_message_str(payload),
                )
                return
            message = self._convert_notice_event(payload)
            logger.info(
                "[NapCat] Received notice event: platform_id=%s session=%s summary=%s",
                self.meta().id,
                message.session_id,
                message.message_str or "[empty]",
            )
            self.commit_event(self.create_event(message))
            return

        if isinstance(payload, NAPCAT_REQUEST_EVENT_TYPES) or (
            isinstance(payload, NapCatGenericEvent) and payload.post_type == "request"
        ):
            message = self._convert_request_event(payload)
            logger.info(
                "[NapCat] Received request event: platform_id=%s session=%s summary=%s",
                self.meta().id,
                message.session_id,
                message.message_str or "[empty]",
            )
            self.commit_event(self.create_event(message))
            return

        post_type = getattr(payload, "post_type", "unknown")
        if post_type == "meta_event":
            logger.debug("[NapCat] Forward WebSocket meta event: %s", payload)
            return

        logger.debug(
            "[NapCat] Forward WebSocket ignored non-message event: %s", payload
        )

    def _get_ignored_forward_ws_message_reason(
        self,
        event: OB11GroupMessage | OB11PrivateMessage,
    ) -> str | None:
        if str(event.post_type) == "message_sent":
            return "post_type=message_sent"

        self_id = str(event.self_id).strip()
        sender_id = str(getattr(event.sender, "user_id", "")).strip()
        if not sender_id:
            sender_id = str(getattr(event, "user_id", "")).strip()

        if self_id and sender_id and sender_id == self_id:
            return f"sender matches self_id ({self_id})"

        return None

    def _get_ignored_notice_event_reason(self, event: object) -> str | None:
        if isinstance(event, OneBot11InputStatus):
            return "ephemeral notify:input_status"
        return None

    async def _convert_message_event(
        self,
        event: OB11GroupMessage | OB11PrivateMessage,
    ) -> AstrBotMessage:
        message = AstrBotMessage()
        message.self_id = str(event.self_id)
        message.message_id = str(event.message_id)
        message.timestamp = int(event.time)
        message.raw_message = event

        sender_name = getattr(event.sender, "card", None) or event.sender.nickname
        message.sender = MessageMember(str(event.sender.user_id), sender_name)

        if isinstance(event, OB11GroupMessage):
            message.type = MessageType.GROUP_MESSAGE
            message.group = Group(
                group_id=str(event.group_id),
                group_name=getattr(event, "group_name", None),
            )
            message.group_id = str(event.group_id)
            message.session_id = str(event.group_id)
        else:
            message.type = MessageType.FRIEND_MESSAGE
            message.session_id = message.sender.user_id
            temp_group_id = getattr(event, "group_id", None)
            if temp_group_id is not None:
                message.group = Group(
                    group_id=str(temp_group_id),
                    group_name=getattr(event, "group_name", None),
                )
                message.group_id = str(temp_group_id)

        message.message = []
        raw_message_text = str(getattr(event, "raw_message", "") or "")
        if isinstance(event.message, str):
            decoded_segments = self._decode_cq_message_string(
                event.message or raw_message_text
            )
            if not decoded_segments:
                message_text = event.message or raw_message_text
                if message_text:
                    message.message.append(Plain(text=message_text))
                    message.message_str = message_text.strip()
                else:
                    message.message_str = ""
                return message

            message_parts: list[str] = []
            first_at_self_processed = False
            for item in decoded_segments:
                converted_nonstandard = self._convert_nonstandard_segment_dict(item)
                if converted_nonstandard is not None:
                    components, segment_texts = converted_nonstandard
                    message.message.extend(components)
                    message_parts.extend(segment_texts)
                    continue

                try:
                    segment = OB11Segment.model_validate(item)
                except Exception as exc:
                    segment_type = sanitize_segment_type(item.get("type"))
                    placeholder = f"[Unsupported NapCat segment: {segment_type}]"
                    logger.warning(
                        "[NapCat] Failed to validate inbound string message segment type=%s error=%s",
                        segment_type,
                        type(exc).__name__,
                    )
                    message.message.append(
                        Unknown(text=placeholder, segment_type=segment_type)
                    )
                    message_parts.append(placeholder)
                    continue

                (
                    components,
                    segment_texts,
                    first_at_self_processed,
                ) = await self._convert_segment_payload_async(
                    segment.root,
                    self_id=message.self_id,
                    first_at_self_processed=first_at_self_processed,
                )
                message.message.extend(components)
                message_parts.extend(segment_texts)

            message.message_str = "".join(message_parts).strip()
            return message

        message_parts: list[str] = []
        first_at_self_processed = False

        for segment in event.message:
            payload = segment.root
            try:
                (
                    components,
                    segment_texts,
                    first_at_self_processed,
                ) = await self._convert_segment_payload_async(
                    payload,
                    self_id=message.self_id,
                    first_at_self_processed=first_at_self_processed,
                )
                message.message.extend(components)
                message_parts.extend(segment_texts)
            except Exception as exc:
                logger.warning(
                    "[NapCat] Failed to convert inbound message segment %s: %s",
                    payload,
                    exc,
                )

        message.message_str = "".join(message_parts).strip()
        return message

    def _convert_nonstandard_segment_dict(
        self,
        payload: dict[str, object],
    ) -> tuple[list[BaseMessageComponent], list[str]] | None:
        segment_type = payload.get("type")
        if not isinstance(segment_type, str):
            return None

        data = payload.get("data")
        if not isinstance(data, dict):
            data = {}

        if segment_type == "mface":
            emoji_id = data.get("emoji_id")
            key = data.get("key")
            summary = data.get("summary")
            emoji_package_id = self._coerce_numeric_segment_value(
                data.get("emoji_package_id")
            )
            if (
                isinstance(emoji_id, str)
                and isinstance(key, str)
                and isinstance(summary, str)
                and isinstance(emoji_package_id, int | float)
            ):
                return (
                    [
                        MFace(
                            emoji_package_id=emoji_package_id,
                            emoji_id=emoji_id,
                            key=key,
                            summary=summary,
                        )
                    ],
                    [],
                )
            return [], []

        if segment_type == "markdown":
            content = data.get("content")
            if isinstance(content, str):
                return [Markdown(content=content)], []
            return [], []

        if segment_type == "miniapp":
            miniapp_data = data.get("data")
            if isinstance(miniapp_data, str):
                return [MiniApp(data=miniapp_data)], []
            return [], []

        if segment_type == "onlinefile":
            msg_id = data.get("msgId")
            element_id = data.get("elementId")
            file_name = data.get("fileName")
            file_size = data.get("fileSize")
            is_dir = self._coerce_bool_segment_value(data.get("isDir"))
            if (
                isinstance(msg_id, str)
                and isinstance(element_id, str)
                and isinstance(file_name, str)
                and isinstance(file_size, str)
                and isinstance(is_dir, bool)
            ):
                return (
                    [
                        OnlineFile(
                            msg_id=msg_id,
                            element_id=element_id,
                            file_name=file_name,
                            file_size=file_size,
                            is_dir=is_dir,
                        )
                    ],
                    [],
                )
            return [], []

        if segment_type == "flashtransfer":
            file_set_id = data.get("fileSetId")
            if isinstance(file_set_id, str):
                return [FlashTransfer(file_set_id=file_set_id)], []
            return [], []

        return None

    def _decode_cq_message_string(self, payload: str) -> list[dict[str, object]]:
        if not payload:
            return []

        segments: list[dict[str, object]] = []
        cursor = 0
        for match in _CQ_SEGMENT_PATTERN.finditer(payload):
            if match.start() > cursor:
                text = self._decode_cq_text(payload[cursor : match.start()])
                if text:
                    segments.append({"type": "text", "data": {"text": text}})

            segment_type = match.group(1)
            attrs = match.group(2)
            data: dict[str, object] = {}
            if attrs:
                for raw_attr in attrs[1:].split(","):
                    key, separator, value = raw_attr.partition("=")
                    if not separator:
                        continue
                    data[key] = self._decode_cq_text(value)

            segment_payload: dict[str, object] = {"type": segment_type}
            if data:
                segment_payload["data"] = data
            segments.append(segment_payload)
            cursor = match.end()

        if cursor < len(payload):
            tail_text = self._decode_cq_text(payload[cursor:])
            if tail_text:
                segments.append({"type": "text", "data": {"text": tail_text}})

        if not segments and payload:
            return [{"type": "text", "data": {"text": self._decode_cq_text(payload)}}]
        return segments

    def _decode_cq_text(self, value: str) -> str:
        return decode_cq_text(value)

    def _coerce_numeric_segment_value(self, value: object) -> object:
        return coerce_numeric_value(value)

    def _coerce_bool_segment_value(self, value: object) -> object:
        return coerce_bool_value(value)

    async def _convert_nested_segment_dict(
        self,
        payload: Mapping[str, object],
        *,
        first_at_self_processed: bool,
        depth: int,
    ) -> tuple[list[BaseMessageComponent], list[str], bool]:
        try:
            segment = OB11Segment.model_validate(payload, extra="ignore")
        except Exception as exc:
            segment_type = sanitize_segment_type(payload.get("type"))
            placeholder = f"[Unsupported NapCat segment: {segment_type}]"
            logger.warning(
                "[NapCat] Failed to validate nested message segment type=%s error=%s",
                segment_type,
                type(exc).__name__,
            )
            return (
                [Unknown(text=placeholder, segment_type=segment_type)],
                [placeholder],
                first_at_self_processed,
            )

        return await self._convert_segment_payload_async(
            segment.root,
            self_id="",
            first_at_self_processed=first_at_self_processed,
            depth=depth,
        )

    async def _convert_forward_content(
        self,
        content: list[object],
        *,
        depth: int,
    ) -> list[Node]:
        if depth > self._MAX_INBOUND_COMPONENT_DEPTH:
            return []
        nodes: list[Node] = []
        for raw_node in content:
            if not isinstance(raw_node, Mapping):
                continue

            if raw_node.get("type") == "node":
                components, _, _ = await self._convert_nested_segment_dict(
                    raw_node,
                    first_at_self_processed=False,
                    depth=depth,
                )
                nodes.extend(
                    component for component in components if isinstance(component, Node)
                )
                continue

            sender = raw_node.get("sender")
            sender_data = sender if isinstance(sender, Mapping) else {}
            sender_name = str(
                sender_data.get("card")
                or sender_data.get("nickname")
                or sender_data.get("user_id")
                or raw_node.get("user_id")
                or "Unknown User"
            )
            sender_id = str(
                sender_data.get("user_id") or raw_node.get("user_id") or "0"
            )

            raw_chain = raw_node.get("message") or raw_node.get("content") or []
            if isinstance(raw_chain, str):
                try:
                    decoded_chain = self._decode_cq_message_string(raw_chain)
                except Exception:
                    decoded_chain = []
                raw_chain = decoded_chain or [
                    {"type": "text", "data": {"text": raw_chain}}
                ]

            nested_components: list[BaseMessageComponent] = []
            nested_first_at_self_processed = False
            if isinstance(raw_chain, list):
                for raw_segment in raw_chain:
                    if isinstance(raw_segment, str):
                        if raw_segment:
                            nested_components.append(Plain(text=raw_segment))
                        continue
                    if not isinstance(raw_segment, Mapping):
                        continue
                    (
                        converted_components,
                        _,
                        nested_first_at_self_processed,
                    ) = await self._convert_nested_segment_dict(
                        raw_segment,
                        first_at_self_processed=nested_first_at_self_processed,
                        depth=depth,
                    )
                    nested_components.extend(converted_components)

            node_time = raw_node.get("time")
            node_time_text = str(node_time or "")
            nodes.append(
                Node(
                    id=raw_node.get("message_id", raw_node.get("id", 0)),
                    uin=sender_id,
                    name=sender_name,
                    content=nested_components,
                    time=int(node_time_text) if node_time_text.isdigit() else 0,
                )
            )
        return nodes

    async def _convert_segment_payload_async(
        self,
        payload: object,
        *,
        self_id: str,
        first_at_self_processed: bool,
        depth: int = 0,
    ) -> tuple[list[BaseMessageComponent], list[str], bool]:
        if depth > self._MAX_INBOUND_COMPONENT_DEPTH:
            placeholder = "[NapCat message component depth limit reached]"
            return (
                [Unknown(text=placeholder, segment_type="depth_limit")],
                [placeholder],
                first_at_self_processed,
            )
        if isinstance(payload, ReplySegment):
            reply_id = payload.data.id or payload.data.seq
            if reply_id is None:
                return [], [], first_at_self_processed
            return [Reply(id=str(reply_id))], [], first_at_self_processed

        if isinstance(payload, ForwardSegment):
            nodes = await self._convert_forward_content(
                payload.data.content or [],
                depth=depth + 1,
            )
            return (
                [Forward(id=payload.data.id, content=[*nodes] or None)],
                [],
                first_at_self_processed,
            )

        if isinstance(payload, CustomNodeSegments):
            nested_components: list[BaseMessageComponent] = []
            nested_message_parts: list[str] = []
            nested_first_at_self_processed = False
            for nested_segment in payload.data.content:
                (
                    converted_components,
                    converted_parts,
                    nested_first_at_self_processed,
                ) = await self._convert_segment_payload_async(
                    nested_segment.root,
                    self_id="",
                    first_at_self_processed=nested_first_at_self_processed,
                    depth=depth + 1,
                )
                nested_components.extend(converted_components)
                nested_message_parts.extend(converted_parts)
            raw_news = getattr(payload.data, "news", None)
            news = None
            if isinstance(raw_news, list):
                news = []
                for item in raw_news:
                    model_dump = getattr(item, "model_dump", None)
                    if callable(model_dump):
                        news.append(model_dump(mode="json"))
                    elif isinstance(item, Mapping):
                        news.append(dict(item))
            raw_time = getattr(payload.data, "time", None)
            raw_time_text = str(raw_time or "")
            return (
                [
                    Node(
                        id=0,
                        uin=payload.data.user_id,
                        name=payload.data.nickname,
                        content=nested_components,
                        source=payload.data.source,
                        news=news,
                        summary=payload.data.summary,
                        prompt=payload.data.prompt,
                        time=int(raw_time_text) if raw_time_text.isdigit() else 0,
                    )
                ],
                ["".join(nested_message_parts)] if nested_message_parts else [],
                first_at_self_processed,
            )

        return self._convert_segment_payload(
            payload,
            self_id=self_id,
            first_at_self_processed=first_at_self_processed,
        )

    @staticmethod
    def _convert_media_segment(
        payload: object,
    ) -> list[BaseMessageComponent] | None:
        """Convert inbound image, record, video, and file segments."""
        if isinstance(payload, ImageSegment):
            image_sub_type = getattr(payload.data, "sub_type", None) or getattr(
                payload.data, "type", None
            )
            return [
                Image(
                    file=payload.data.file,
                    url=payload.data.url or "",
                    _type=str(image_sub_type) if image_sub_type is not None else "",
                )
            ]
        if isinstance(payload, RecordSegment):
            return [
                Record(
                    file=payload.data.file,
                    url=payload.data.url or "",
                    path=payload.data.path or None,
                )
            ]
        if isinstance(payload, VideoSegment):
            return [Video(file=payload.data.file, url=payload.data.url or "")]
        if isinstance(payload, FileSegment):
            file_name = (
                PurePosixPath(payload.data.file.replace("\\", "/")).name or "file"
            )
            return [
                File(
                    name=file_name,
                    file=payload.data.file,
                    url=payload.data.url or "",
                )
            ]
        return None

    @staticmethod
    def _convert_interactive_segment(
        payload: object,
    ) -> list[BaseMessageComponent] | None:
        """Convert emoji, interactive, and card-like inbound segments."""
        if isinstance(payload, FaceSegment):
            return [Face(id=int(payload.data.id))] if payload.data.id.isdigit() else []
        if isinstance(payload, OB11MFaceSegment):
            return [
                MFace(
                    emoji_package_id=payload.data.emoji_package_id,
                    emoji_id=payload.data.emoji_id,
                    key=payload.data.key,
                    summary=payload.data.summary,
                )
            ]
        if isinstance(payload, PokeSegment):
            return [Poke(id=payload.data.id or 0, poke_type=payload.data.type)]
        if isinstance(payload, DiceSegment):
            return [Dice()]
        if isinstance(payload, RpsSegment):
            return [RPS()]
        if isinstance(payload, ShakeSegment):
            return [Shake()]
        if isinstance(payload, JsonSegment):
            return [Json(data=payload.data.data)]
        if isinstance(payload, XmlSegment):
            return [Xml(data=payload.data.data)]
        if isinstance(payload, OB11MarkdownSegment):
            return [Markdown(content=payload.data.content)]
        if isinstance(payload, OB11MiniAppSegment):
            return [MiniApp(data=payload.data.data)]
        if isinstance(payload, ShareSegment):
            return [
                Share(
                    url=payload.data.url,
                    title=payload.data.title,
                    content=payload.data.content or "",
                    image=payload.data.image or "",
                )
            ]
        if isinstance(payload, OB11OnlineFileSegment):
            return [
                OnlineFile(
                    msg_id=payload.data.msgId,
                    element_id=payload.data.elementId,
                    file_name=payload.data.fileName,
                    file_size=payload.data.fileSize,
                    is_dir=payload.data.isDir,
                )
            ]
        if isinstance(payload, OB11FlashTransferSegment):
            return [FlashTransfer(file_set_id=payload.data.fileSetId)]
        return None

    @staticmethod
    def _convert_scalar_segment(
        payload: object,
    ) -> list[BaseMessageComponent] | None:
        """Convert remaining non-recursive scalar inbound segments."""
        if isinstance(payload, ContactSegment):
            contact_id = int(payload.data.id) if payload.data.id.isdigit() else 0
            return [Contact(_type=payload.data.type.value, id=contact_id)]
        if isinstance(payload, LocationSegment):
            return [
                Location(
                    lat=float(payload.data.lat),
                    lon=float(payload.data.lon),
                    title=payload.data.title or "",
                    content=payload.data.content or "",
                )
            ]
        if isinstance(payload, MusicSegment):
            music_id = int(payload.data.id) if payload.data.id.isdigit() else 0
            return [Music(_type=payload.data.type.value, id=music_id)]
        if isinstance(payload, CustomMusicSegment):
            return [
                Music(
                    _type="custom",
                    url=payload.data.url,
                    audio=payload.data.audio,
                    title=payload.data.title,
                    content=payload.data.content or "",
                    image=payload.data.image or "",
                )
            ]
        if isinstance(payload, DirectNodeSegment):
            node_id: int | str = payload.data.id
            if payload.data.id.isdigit():
                node_id = int(payload.data.id)
            return [Node(id=node_id, content=[])]
        return None

    def _convert_segment_payload(
        self,
        payload: object,
        *,
        self_id: str,
        first_at_self_processed: bool,
    ) -> tuple[list[BaseMessageComponent], list[str], bool]:
        if isinstance(payload, AnonymousSegment):
            ignore = payload.data.ignore
            return (
                [Anonymous(ignore=int(ignore) if ignore is not None else None)],
                [],
                first_at_self_processed,
            )

        if isinstance(payload, TextSegment):
            text = payload.data.text
            if text:
                return [Plain(text=text)], [text], first_at_self_processed
            return [], [], first_at_self_processed

        if isinstance(payload, AtSegment):
            target = payload.data.qq
            if target == "all":
                return [AtAll(name="全体成员")], [" @all "], first_at_self_processed

            resolved_name = payload.data.name
            component = At(qq=target, name=resolved_name or "")
            if self_id and str(target) == self_id and not first_at_self_processed:
                return [component], [], True
            return (
                [component],
                [f" @{resolved_name or target} "],
                (first_at_self_processed),
            )

        media_components = self._convert_media_segment(payload)
        if media_components is not None:
            return media_components, [], first_at_self_processed

        interactive_components = self._convert_interactive_segment(payload)
        if interactive_components is not None:
            return interactive_components, [], first_at_self_processed

        scalar_components = self._convert_scalar_segment(payload)
        if scalar_components is not None:
            return scalar_components, [], first_at_self_processed

        logger.debug("[NapCat] Ignored inbound message segment: %s", payload)
        return [], [], first_at_self_processed

    def _convert_notice_event(self, event: object) -> AstrBotMessage:
        message = AstrBotMessage()
        message.self_id = str(getattr(event, "self_id", ""))
        message.timestamp = int(getattr(event, "time", 0))
        message.message_id = str(getattr(event, "message_id", uuid.uuid4().hex))
        message.raw_message = event

        session_subject_id = self._pick_first_event_identifier(
            getattr(event, "user_id", None),
            getattr(event, "peer_id", None),
            getattr(event, "operator_id", None),
            getattr(event, "sender_id", None),
        )
        sender_id = self._pick_first_event_identifier(
            getattr(event, "sender_id", None),
            getattr(event, "user_id", None),
            getattr(event, "operator_id", None),
            getattr(event, "peer_id", None),
        )
        message.sender = MessageMember(sender_id, sender_id)
        group_id = self._pick_first_event_identifier(getattr(event, "group_id", None))
        if group_id:
            message.type = MessageType.GROUP_MESSAGE
            message.group = Group(group_id=group_id)
            message.group_id = group_id
            message.session_id = group_id
        else:
            message.type = MessageType.FRIEND_MESSAGE
            message.session_id = session_subject_id

        message.message = []
        message.message_str = self._build_notice_message_str(event)

        if isinstance(event, OneBot11Poke):
            message.message.append(Poke(id=str(event.target_id)))

        return message

    def _convert_request_event(self, event: object) -> AstrBotMessage:
        message = AstrBotMessage()
        message.self_id = str(getattr(event, "self_id", ""))
        message.timestamp = int(getattr(event, "time", 0))
        message.message_id = uuid.uuid4().hex
        message.raw_message = event

        sender_id = str(getattr(event, "user_id", ""))
        message.sender = MessageMember(sender_id, sender_id)
        group_id = getattr(event, "group_id", None)
        if group_id is not None:
            message.type = MessageType.GROUP_MESSAGE
            message.group = Group(group_id=str(group_id))
            message.group_id = str(group_id)
            message.session_id = str(group_id)
        else:
            message.type = MessageType.FRIEND_MESSAGE
            message.session_id = sender_id

        message.message = []
        message.message_str = self._build_request_message_str(event)
        return message

    def _populate_event_extras(
        self,
        event: NapCatMessageEvent,
        raw_event: object,
    ) -> None:
        event.set_extra("platform_event", "napcat")

        model_dump = getattr(raw_event, "model_dump", None)
        raw_payload = getattr(raw_event, "__astrbot_raw_payload__", None)
        if isinstance(raw_payload, Mapping):
            event.set_extra("onebot_raw_payload", dict(raw_payload))
            event.set_extra("napcat_raw_payload", dict(raw_payload))
        if callable(model_dump):
            try:
                event.set_lazy_extra(
                    "napcat_event",
                    lambda: model_dump(mode="json"),
                )
            except Exception as exc:
                logger.warning("[NapCat] Failed to dump raw event payload: %s", exc)

        for attr_name, extra_name in (
            ("post_type", "onebot_post_type"),
            ("message_type", "onebot_message_type"),
            ("notice_type", "onebot_notice_type"),
            ("request_type", "onebot_request_type"),
            ("sub_type", "onebot_sub_type"),
        ):
            value = self._stringify_event_value(getattr(raw_event, attr_name, None))
            if value:
                event.set_extra(extra_name, value)

        post_type = self._stringify_event_value(getattr(raw_event, "post_type", None))
        if post_type in {"notice", "request"}:
            event.set_extra("skip_private_wake", True)

        for attr_name, extra_name in (
            ("self_id", "napcat_self_id"),
            ("user_id", "napcat_user_id"),
            ("sender_id", "napcat_sender_id"),
            ("group_id", "napcat_group_id"),
            ("peer_id", "napcat_peer_id"),
            ("target_id", "napcat_target_id"),
            ("operator_id", "napcat_operator_id"),
            ("operator_nick", "napcat_operator_nick"),
            ("message_id", "napcat_message_id"),
            ("flag", "napcat_flag"),
            ("comment", "napcat_comment"),
            ("code", "napcat_code"),
            ("count", "napcat_count"),
            ("honor_type", "napcat_honor_type"),
            ("duration", "napcat_duration"),
            ("times", "napcat_times"),
            ("event_type", "napcat_event_type"),
            ("status_text", "napcat_status_text"),
            ("busi_id", "napcat_busi_id"),
            ("content", "napcat_content"),
            ("name_new", "napcat_name_new"),
            ("title", "napcat_title"),
            ("tag", "napcat_tag"),
            ("time", "napcat_time"),
        ):
            value = getattr(raw_event, attr_name, None)
            if value is None:
                continue
            if hasattr(value, "value"):
                value = value.value
            event.set_extra(extra_name, value)

        if post_type == "notice":
            notice_message = getattr(raw_event, "message", None)
            if notice_message is not None:
                if hasattr(notice_message, "value"):
                    notice_message = notice_message.value
                event.set_extra("napcat_notice_message", notice_message)

    def _stringify_event_value(self, value: object) -> str:
        if value is None:
            return ""
        return str(getattr(value, "value", value))

    def _pick_display_name(self, *values: object) -> str | None:
        for value in values:
            if isinstance(value, str):
                display_name = value.strip()
                if display_name:
                    return display_name
        return None

    def _pick_first_event_identifier(self, *values: object) -> str:
        for value in values:
            if value is None:
                continue
            text = str(getattr(value, "value", value)).strip()
            if text and text != "0":
                return text
        return ""

    def _value_from_mapping_or_attrs(self, value: object, field: str) -> object | None:
        if isinstance(value, Mapping):
            return value.get(field)
        return getattr(value, field, None)

    def _build_notice_message_str(self, event: object) -> str:
        return build_notice_message(event)

    def _build_request_message_str(self, event: object) -> str:
        return build_request_message(event)
