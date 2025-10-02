"""Misskey 平台适配器通用工具函数"""

from typing import Dict, Any, List, Tuple, Optional, Union
import astrbot.api.message_components as Comp
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType


def serialize_message_chain(chain: List[Any]) -> Tuple[str, bool]:
    """将消息链序列化为文本字符串"""
    text_parts = []
    has_at = False

    def process_component(component):
        nonlocal has_at
        if isinstance(component, Comp.Plain):
            return component.text
        elif isinstance(component, Comp.File):
            file_name = getattr(component, "name", "文件")
            return f"[文件: {file_name}]"
        elif isinstance(component, Comp.At):
            has_at = True
            return f"@{component.qq}"
        elif hasattr(component, "text"):
            text = getattr(component, "text", "")
            if "@" in text:
                has_at = True
            return text
        else:
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
    user_id: Optional[str],
    user_cache: Dict[str, Any],
    self_id: Optional[str],
    default_visibility: str = "public",
) -> Tuple[str, Optional[List[str]]]:
    """解析 Misskey 消息的可见性设置"""
    visibility = default_visibility
    visible_user_ids = None

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


def resolve_visibility_from_raw_message(
    raw_message: Dict[str, Any], self_id: Optional[str] = None
) -> Tuple[str, Optional[List[str]]]:
    """从原始消息数据中解析可见性设置"""
    visibility = "public"
    visible_user_ids = None

    if not raw_message:
        return visibility, visible_user_ids

    original_visibility = raw_message.get("visibility", "public")
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


def is_valid_user_session_id(session_id: Union[str, Any]) -> bool:
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


def is_valid_room_session_id(session_id: Union[str, Any]) -> bool:
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
    text: str, user_info: Optional[Dict[str, Any]], has_at: bool = False
) -> str:
    """如果需要且没有@用户，则添加@用户"""
    if has_at or not user_info:
        return text

    username = user_info.get("username")
    nickname = user_info.get("nickname")

    if username:
        mention = f"@{username}"
        if not text.startswith(mention):
            text = f"{mention}\n{text}".strip()
    elif nickname:
        mention = f"@{nickname}"
        if not text.startswith(mention):
            text = f"{mention}\n{text}".strip()

    return text


def create_file_component(file_info: Dict[str, Any]) -> Tuple[Any, str]:
    """创建文件组件和描述文本"""
    file_url = file_info.get("url", "")
    file_name = file_info.get("name", "未知文件")
    file_type = file_info.get("type", "")

    if file_type.startswith("image/"):
        return Comp.Image(url=file_url, file=file_name), f"图片[{file_name}]"
    elif file_type.startswith("audio/"):
        return Comp.Record(url=file_url, file=file_name), f"音频[{file_name}]"
    elif file_type.startswith("video/"):
        return Comp.Video(url=file_url, file=file_name), f"视频[{file_name}]"
    else:
        return Comp.File(name=file_name, url=file_url), f"文件[{file_name}]"


def process_files(
    message: AstrBotMessage, files: list, include_text_parts: bool = True
) -> list:
    """处理文件列表，添加到消息组件中并返回文本描述"""
    file_parts = []
    for file_info in files:
        component, part_text = create_file_component(file_info)
        message.message.append(component)
        if include_text_parts:
            file_parts.append(part_text)
    return file_parts


def extract_sender_info(
    raw_data: Dict[str, Any], is_chat: bool = False
) -> Dict[str, Any]:
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
    raw_data: Dict[str, Any],
    sender_info: Dict[str, Any],
    client_self_id: str,
    is_chat: bool = False,
    room_id: Optional[str] = None,
    unique_session: bool = False,
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
        if unique_session:
            session_id += f"_{sender_info['sender_id']}"
        message.type = MessageType.GROUP_MESSAGE
        message.group_id = room_id
    elif is_chat:
        session_prefix = "chat"
        session_id = f"{session_prefix}%{sender_info['sender_id']}"
        message.type = MessageType.FRIEND_MESSAGE
    else:
        session_prefix = "note"
        session_id = f"{session_prefix}%{sender_info['sender_id']}"
        message.type = MessageType.FRIEND_MESSAGE

    message.session_id = (
        session_id if sender_info["sender_id"] else f"{session_prefix}%unknown"
    )
    message.message_id = str(raw_data.get("id", ""))
    message.self_id = client_self_id

    return message


def process_at_mention(
    message: AstrBotMessage, raw_text: str, bot_username: str, client_self_id: str
) -> Tuple[List[str], str]:
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
    else:
        message.message.append(Comp.Plain(raw_text))
        message_parts.append(raw_text)
        return message_parts, raw_text


def cache_user_info(
    user_cache: Dict[str, Any],
    sender_info: Dict[str, Any],
    raw_data: Dict[str, Any],
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
        }

    user_cache[sender_info["sender_id"]] = user_cache_data


def cache_room_info(
    user_cache: Dict[str, Any], raw_data: Dict[str, Any], client_self_id: str
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
