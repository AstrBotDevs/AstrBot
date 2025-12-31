"""Misskey 平台适配器通用工具函数"""

from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType


class FileIDExtractor:
    """从 API 响应中提取文件 ID 的帮助类（无状态）。"""

    @staticmethod
    def extract_file_id(result: Any) -> str | None:
        if not isinstance(result, dict):
            return None

        id_paths = [
            lambda r: r.get("createdFile", {}).get("id"),
            lambda r: r.get("file", {}).get("id"),
            lambda r: r.get("id"),
        ]

        for p in id_paths:
            try:
                if fid := p(result):
                    return fid
            except Exception:
                continue

        return None


class MessagePayloadBuilder:
    """构建不同类型消息负载的帮助类（无状态）。"""

    @staticmethod
    def build_chat_payload(
        user_id: str,
        text: str | None,
        file_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {"toUserId": user_id}
        if text:
            payload["text"] = text
        if file_id:
            payload["fileId"] = file_id
        return payload

    @staticmethod
    def build_room_payload(
        room_id: str,
        text: str | None,
        file_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {"toRoomId": room_id}
        if text:
            payload["text"] = text
        if file_id:
            payload["fileId"] = file_id
        return payload

    @staticmethod
    def build_note_payload(
        text: str | None,
        file_ids: list[str] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if text:
            payload["text"] = text
        if file_ids:
            payload["fileIds"] = file_ids
        payload |= kwargs
        return payload


def serialize_message_chain(chain: list[Any]) -> tuple[str, bool]:
    """将消息链序列化为文本字符串"""
    text_parts = []
    has_at = False

    def process_component(component):
        nonlocal has_at
        if isinstance(component, Comp.Plain):
            return component.text
        if isinstance(component, Comp.File):
            # 为文件组件返回占位符，但适配器仍会处理原组件
            return "[文件]"
        if isinstance(component, Comp.Image):
            # 为图片组件返回占位符，但适配器仍会处理原组件
            return "[图片]"
        if isinstance(component, Comp.At):
            has_at = True
            # 优先使用name字段（用户名），如果没有则使用qq字段
            # 这样可以避免在Misskey中生成 @<user_id> 这样的无效提及
            if hasattr(component, "name") and component.name:
                return f"@{component.name}"
            return f"@{component.qq}"
        if hasattr(component, "text"):
            text = getattr(component, "text", "")
            if "@" in text:
                has_at = True
            return text
        return str(component)

    for component in chain:
        if isinstance(component, Comp.Node) and component.content:
            for node_comp in component.content:
                result = process_component(node_comp)
                if result:
                    text_parts.append(result)
        else:
            result = process_component(component)
            if result:
                text_parts.append(result)

    return "".join(text_parts), has_at


def resolve_message_visibility(
    user_id: str | None = None,
    user_cache: dict[str, Any] | None = None,
    self_id: str | None = None,
    raw_message: dict[str, Any] | None = None,
    default_visibility: str = "public",
) -> tuple[str, list[str] | None]:
    """解析 Misskey 消息的可见性设置

    可以从 user_cache 或 raw_message 中解析，支持两种调用方式：
    1. 基于 user_cache: resolve_message_visibility(user_id, user_cache, self_id)
    2. 基于 raw_message: resolve_message_visibility(raw_message=raw_message, self_id=self_id)
    """
    visibility = default_visibility
    visible_user_ids = None

    # 优先从 user_cache 解析
    if user_id and user_cache:
        user_info = user_cache.get(user_id)
        if user_info:
            original_visibility = user_info.get("visibility", default_visibility)
            if original_visibility == "specified":
                visibility = "specified"
                original_visible_users = user_info.get("visible_user_ids", [])
                users_to_include = [user_id]
                if self_id:
                    users_to_include.append(self_id)
                visible_user_ids = list(set(original_visible_users + users_to_include))
                visible_user_ids = [uid for uid in visible_user_ids if uid]
            else:
                visibility = original_visibility
            return visibility, visible_user_ids

    # 回退到从 raw_message 解析
    if raw_message:
        original_visibility = raw_message.get("visibility", default_visibility)
        if original_visibility == "specified":
            visibility = "specified"
            original_visible_users = raw_message.get("visibleUserIds", [])
            sender_id = raw_message.get("userId", "")

            users_to_include = []
            if sender_id:
                users_to_include.append(sender_id)
            if self_id:
                users_to_include.append(self_id)

            visible_user_ids = list(set(original_visible_users + users_to_include))
            visible_user_ids = [uid for uid in visible_user_ids if uid]
        else:
            visibility = original_visibility

    return visibility, visible_user_ids


# 保留旧函数名作为向后兼容的别名
def resolve_visibility_from_raw_message(
    raw_message: dict[str, Any],
    self_id: str | None = None,
) -> tuple[str, list[str] | None]:
    """从原始消息数据中解析可见性设置（已弃用，使用 resolve_message_visibility 替代）"""
    return resolve_message_visibility(raw_message=raw_message, self_id=self_id)


def is_valid_user_session_id(session_id: str | Any) -> bool:
    """检查 session_id 是否是有效的聊天用户 session_id (仅限chat%前缀)"""
    if not isinstance(session_id, str) or "%" not in session_id:
        return False

    parts = session_id.split("%")
    return (
        len(parts) == 2
        and parts[0] == "chat"
        and bool(parts[1])
        and parts[1] != "unknown"
    )


def is_valid_room_session_id(session_id: str | Any) -> bool:
    """检查 session_id 是否是有效的房间 session_id (仅限room%前缀)"""
    if not isinstance(session_id, str) or "%" not in session_id:
        return False

    parts = session_id.split("%")
    return (
        len(parts) == 2
        and parts[0] == "room"
        and bool(parts[1])
        and parts[1] != "unknown"
    )


def is_valid_chat_session_id(session_id: str | Any) -> bool:
    """检查 session_id 是否是有效的聊天 session_id (仅限chat%前缀)"""
    if not isinstance(session_id, str) or "%" not in session_id:
        return False

    parts = session_id.split("%")
    return (
        len(parts) == 2
        and parts[0] == "chat"
        and bool(parts[1])
        and parts[1] != "unknown"
    )


def extract_user_id_from_session_id(session_id: str) -> str:
    """从 session_id 中提取用户 ID"""
    if "%" in session_id:
        parts = session_id.split("%")
        if len(parts) >= 2:
            return parts[1]
    return session_id


def extract_room_id_from_session_id(session_id: str) -> str:
    """从 session_id 中提取房间 ID"""
    if "%" in session_id:
        parts = session_id.split("%")
        if len(parts) >= 2 and parts[0] == "room":
            return parts[1]
    return session_id


def add_at_mention_if_needed(
    text: str,
    user_info: dict[str, Any] | None,
    has_at: bool = False,
) -> str:
    """如果需要且没有@用户，则添加@用户

    注意：仅在有有效的username时才添加@提及，避免使用用户ID
    """
    if has_at or not user_info:
        return text

    username = user_info.get("username")
    # 如果没有username，则不添加@提及，返回原文本
    # 这样可以避免生成 @<user_id> 这样的无效提及
    if not username:
        return text

    mention = f"@{username}"
    if not text.startswith(mention):
        text = f"{mention}\n{text}".strip()

    return text


def create_file_component(file_info: dict[str, Any]) -> tuple[Any, str]:
    """创建文件组件和描述文本"""
    file_url = file_info.get("url", "")
    file_name = file_info.get("name", "未知文件")
    file_type = file_info.get("type", "")

    if file_type.startswith("image/"):
        return Comp.Image(url=file_url, file=file_name), f"图片[{file_name}]"
    if file_type.startswith("audio/"):
        return Comp.Record(url=file_url, file=file_name), f"音频[{file_name}]"
    if file_type.startswith("video/"):
        return Comp.Video(url=file_url, file=file_name), f"视频[{file_name}]"
    return Comp.File(name=file_name, url=file_url), f"文件[{file_name}]"


def process_files(
    message: AstrBotMessage,
    files: list,
    include_text_parts: bool = True,
) -> list:
    """处理文件列表，添加到消息组件中并返回文本描述"""
    file_parts = []
    for file_info in files:
        component, part_text = create_file_component(file_info)
        message.message.append(component)
        if include_text_parts:
            file_parts.append(part_text)
    return file_parts


def format_poll(poll: dict[str, Any]) -> str:
    """将 Misskey 的 poll 对象格式化为可读字符串。"""
    if not poll or not isinstance(poll, dict):
        return ""
    multiple = poll.get("multiple", False)
    choices = poll.get("choices", [])
    text_choices = [
        f"({idx}) {c.get('text', '')} [{c.get('votes', 0)}票]"
        for idx, c in enumerate(choices, start=1)
    ]
    parts = ["[投票]", ("允许多选" if multiple else "单选")] + (
        ["选项: " + ", ".join(text_choices)] if text_choices else []
    )
    return " ".join(parts)


def extract_sender_info(
    raw_data: dict[str, Any],
    is_chat: bool = False,
) -> dict[str, Any]:
    """提取发送者信息"""
    if is_chat:
        sender = raw_data.get("fromUser", {})
        sender_id = str(sender.get("id", "") or raw_data.get("fromUserId", ""))
    else:
        sender = raw_data.get("user", {})
        sender_id = str(sender.get("id", ""))

    return {
        "sender": sender,
        "sender_id": sender_id,
        "nickname": sender.get("name", sender.get("username", "")),
        "username": sender.get("username", ""),
    }


def create_base_message(
    raw_data: dict[str, Any],
    sender_info: dict[str, Any],
    client_self_id: str,
    is_chat: bool = False,
    room_id: str | None = None,
) -> AstrBotMessage:
    """创建基础消息对象"""
    message = AstrBotMessage()
    message.raw_message = raw_data
    message.message = []

    message.sender = MessageMember(
        user_id=sender_info["sender_id"],
        nickname=sender_info["nickname"],
    )

    if room_id:
        session_prefix = "room"
        session_id = f"{session_prefix}%{room_id}"
        message.type = MessageType.GROUP_MESSAGE
        message.group_id = room_id
    elif is_chat:
        session_prefix = "chat"
        session_id = f"{session_prefix}%{sender_info['sender_id']}"
        message.type = MessageType.FRIEND_MESSAGE
    else:
        session_prefix = "note"
        session_id = f"{session_prefix}%{sender_info['sender_id']}"
        message.type = MessageType.OTHER_MESSAGE

    message.session_id = (
        session_id if sender_info["sender_id"] else f"{session_prefix}%unknown"
    )
    message.message_id = str(raw_data.get("id", ""))
    message.self_id = client_self_id

    return message


def process_at_mention(
    message: AstrBotMessage,
    raw_text: str,
    bot_username: str,
    client_self_id: str,
) -> tuple[list[str], str]:
    """处理@提及逻辑，返回消息部分列表和处理后的文本"""
    message_parts = []

    if not raw_text:
        return message_parts, ""

    if bot_username and raw_text.startswith(f"@{bot_username}"):
        at_mention = f"@{bot_username}"
        message.message.append(Comp.At(qq=client_self_id))
        remaining_text = raw_text[len(at_mention) :].strip()
        if remaining_text:
            message.message.append(Comp.Plain(remaining_text))
            message_parts.append(remaining_text)
        return message_parts, remaining_text
    message.message.append(Comp.Plain(raw_text))
    message_parts.append(raw_text)
    return message_parts, raw_text


def cache_user_info(
    user_cache: dict[str, Any],
    sender_info: dict[str, Any],
    raw_data: dict[str, Any],
    client_self_id: str,
    is_chat: bool = False,
):
    """缓存用户信息"""
    if is_chat:
        user_cache_data = {
            "username": sender_info["username"],
            "nickname": sender_info["nickname"],
            "visibility": "specified",
            "visible_user_ids": [client_self_id, sender_info["sender_id"]],
        }
    else:
        user_cache_data = {
            "username": sender_info["username"],
            "nickname": sender_info["nickname"],
            "visibility": raw_data.get("visibility", "public"),
            "visible_user_ids": raw_data.get("visibleUserIds", []),
            # 保存原消息ID，用于回复时作为reply_id
            "reply_to_note_id": raw_data.get("id"),
        }

    user_cache[sender_info["sender_id"]] = user_cache_data


def cache_room_info(
    user_cache: dict[str, Any],
    raw_data: dict[str, Any],
    client_self_id: str,
):
    """缓存房间信息"""
    room_data = raw_data.get("toRoom")
    room_id = raw_data.get("toRoomId")

    if room_data and room_id:
        room_cache_key = f"room:{room_id}"
        user_cache[room_cache_key] = {
            "room_id": room_id,
            "room_name": room_data.get("name", ""),
            "room_description": room_data.get("description", ""),
            "owner_id": room_data.get("ownerId", ""),
            "visibility": "specified",
            "visible_user_ids": [client_self_id],
        }


async def resolve_component_url_or_path(
    comp: Any,
) -> tuple[str | None, str | None]:
    """尝试从组件解析可上传的远程 URL 或本地路径。

    返回 (url_candidate, local_path)。两者可能都为 None。
    这个函数尽量不抛异常，调用方可按需处理 None。
    """
    url_candidate = None
    local_path = None

    async def _get_str_value(coro_or_val):
        """辅助函数：统一处理协程或普通值"""
        try:
            if hasattr(coro_or_val, "__await__"):
                result = await coro_or_val
            else:
                result = coro_or_val
            return result if isinstance(result, str) else None
        except Exception:
            return None

    try:
        # 1. 尝试异步方法
        for method in ["convert_to_file_path", "get_file", "register_to_file_service"]:
            if not hasattr(comp, method):
                continue
            try:
                value = await _get_str_value(getattr(comp, method)())
                if value:
                    if value.startswith("http"):
                        url_candidate = value
                        break
                    local_path = value
            except Exception:
                continue

        # 2. 尝试 get_file(True) 获取可直接访问的 URL
        if not url_candidate and hasattr(comp, "get_file"):
            try:
                value = await _get_str_value(comp.get_file(True))
                if value and value.startswith("http"):
                    url_candidate = value
            except Exception:
                pass

        # 3. 回退到同步属性
        if not url_candidate and not local_path:
            for attr in ("file", "url", "path", "src", "source"):
                try:
                    value = getattr(comp, attr, None)
                    if value and isinstance(value, str):
                        if value.startswith("http"):
                            url_candidate = value
                            break
                        local_path = value
                        break
                except Exception:
                    continue

    except Exception:
        pass

    return url_candidate, local_path


def summarize_component_for_log(comp: Any) -> dict[str, Any]:
    """生成适合日志的组件属性字典（尽量不抛异常）。"""
    attrs = {}
    for a in ("file", "url", "path", "src", "source", "name"):
        try:
            v = getattr(comp, a, None)
            if v is not None:
                attrs[a] = v
        except Exception:
            continue
    return attrs


async def upload_local_with_retries(
    api: Any,
    local_path: str,
    preferred_name: str | None,
    folder_id: str | None,
) -> str | None:
    """尝试本地上传，返回 file id 或 None。如果文件类型不允许则直接失败。"""
    try:
        res = await api.upload_file(local_path, preferred_name, folder_id)
        if isinstance(res, dict):
            fid = res.get("id") or (res.get("raw") or {}).get("createdFile", {}).get(
                "id",
            )
            if fid:
                return str(fid)
    except Exception:
        # 上传失败，直接返回 None，让上层处理错误
        return None

    return None
