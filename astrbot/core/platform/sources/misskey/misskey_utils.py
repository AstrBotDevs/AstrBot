"""Misskey 平台适配器通用工具函数"""

import mimetypes
import os
from typing import Dict, Any, List, Tuple, Optional, Union
import astrbot.api.message_components as Comp
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType


class FileIDExtractor:
    """从 API 响应中提取文件 ID 的帮助类（无状态）。"""

    @staticmethod
    def extract_file_id(result: Any) -> Optional[str]:
        if not isinstance(result, dict):
            return None

        id_paths = [
            lambda r: r.get("createdFile", {}).get("id"),
            lambda r: r.get("file", {}).get("id"),
            lambda r: r.get("id"),
        ]

        for p in id_paths:
            try:
                fid = p(result)
                if fid:
                    return fid
            except Exception:
                continue

        return None


class MessagePayloadBuilder:
    """构建不同类型消息负载的帮助类（无状态）。"""

    @staticmethod
    def build_chat_payload(
        user_id: str, text: Optional[str], file_id: Optional[str] = None
    ) -> Dict[str, Any]:
        payload = {"toUserId": user_id}
        if text:
            payload["text"] = text
        if file_id:
            payload["fileId"] = file_id
        return payload

    @staticmethod
    def build_room_payload(
        room_id: str, text: Optional[str], file_id: Optional[str] = None
    ) -> Dict[str, Any]:
        payload = {"toRoomId": room_id}
        if text:
            payload["text"] = text
        if file_id:
            payload["fileId"] = file_id
        return payload

    @staticmethod
    def build_note_payload(
        text: Optional[str], file_ids: Optional[List[str]] = None, **kwargs
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if text:
            payload["text"] = text
        if file_ids:
            payload["fileIds"] = file_ids
        payload.update(kwargs)
        return payload


def serialize_message_chain(chain: List[Any]) -> Tuple[str, bool]:
    """将消息链序列化为文本字符串"""
    text_parts = []
    has_at = False

    def process_component(component):
        nonlocal has_at
        if isinstance(component, Comp.Plain):
            return component.text
        elif isinstance(component, Comp.File):
            # 为文件组件返回占位符，但适配器仍会处理原组件
            return "[文件]"
        elif isinstance(component, Comp.Image):
            # 为图片组件返回占位符，但适配器仍会处理原组件
            return "[图片]"
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


def is_valid_chat_session_id(session_id: Union[str, Any]) -> bool:
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


def format_poll(poll: Dict[str, Any]) -> str:
    """将 Misskey 的 poll 对象格式化为可读字符串。"""
    if not poll or not isinstance(poll, dict):
        return ""
    parts = []
    multiple = poll.get("multiple", False)
    choices = poll.get("choices", [])
    parts.append("[投票]")
    parts.append("允许多选" if multiple else "单选")
    text_choices = []
    for idx, c in enumerate(choices, start=1):
        text = c.get("text", "")
        votes = c.get("votes", 0)
        text_choices.append(f"({idx}) {text} [{votes}票]")
    if text_choices:
        parts.append("选项: " + ", ".join(text_choices))
    return " ".join(parts)


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
        message.type = MessageType.OTHER_MESSAGE

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


def detect_mime_ext(path: str) -> Optional[str]:
    """检测文件 MIME 并返回常用扩展，作为 adapter 的可复用工具。"""
    try:
        try:
            from magic import Magic  # type: ignore

            m = Magic(mime=True)
            mime = m.from_file(path)
        except Exception:
            import mimetypes as _m

            mime, _ = _m.guess_type(path)
    except Exception:
        mime = None

    if not mime:
        return None

    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/webm": ".webm",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/x-matroska": ".mkv",
        "video/quicktime": ".mov",
        "video/avi": ".avi",
        "video/mpeg": ".mpeg",
        "text/plain": ".txt",
        "application/pdf": ".pdf",
    }
    return mapping.get(mime, mimetypes.guess_extension(mime) or None)


async def resolve_component_url_or_path(
    comp: Any,
) -> Tuple[Optional[str], Optional[str]]:
    """尝试从组件解析可上传的远程 URL 或本地路径。

    返回 (url_candidate, local_path)。两者可能都为 None。
    这个函数尽量不抛异常，调用方可按需处理 None。
    """
    url_candidate = None
    local_path = None

    try:
        if hasattr(comp, "convert_to_file_path"):
            try:
                p = await comp.convert_to_file_path()
                if isinstance(p, str):
                    if p.startswith("http"):
                        url_candidate = p
                    else:
                        local_path = p
            except Exception:
                pass

        if not local_path and hasattr(comp, "get_file"):
            try:
                p = await comp.get_file()
                if isinstance(p, str):
                    if p.startswith("http"):
                        url_candidate = p
                    else:
                        local_path = p
            except Exception:
                pass

        # register_to_file_service or get_file(True) may provide a URL
        if not url_candidate and hasattr(comp, "register_to_file_service"):
            try:
                r = await comp.register_to_file_service()
                if isinstance(r, str) and r.startswith("http"):
                    url_candidate = r
            except Exception:
                pass

        if not url_candidate and hasattr(comp, "get_file"):
            try:
                maybe = await comp.get_file(True)
                if isinstance(maybe, str) and maybe.startswith("http"):
                    url_candidate = maybe
            except Exception:
                pass

        # fallback to common attributes
        if not url_candidate and not local_path:
            for attr in ("file", "url", "path", "src", "source"):
                try:
                    val = getattr(comp, attr, None)
                except Exception:
                    val = None
                if val and isinstance(val, str):
                    if val.startswith("http"):
                        url_candidate = val
                        break
                    else:
                        local_path = val
                        break
    except Exception:
        return None, None

    return url_candidate, local_path


def summarize_component_for_log(comp: Any) -> Dict[str, Any]:
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
    preferred_name: Optional[str],
    folder_id: Optional[str],
) -> Optional[str]:
    """尝试本地上传并在遇到 unallowed 错误时按扩展名重试，返回 file id 或 None。"""
    try:
        res = await api.upload_file(local_path, preferred_name, folder_id)
        if isinstance(res, dict):
            fid = res.get("id") or (res.get("raw") or {}).get("createdFile", {}).get(
                "id"
            )
            if fid:
                return str(fid)
    except Exception as e:
        msg = str(e).lower()
        if "unallowed" in msg or "unallowed_file_type" in msg:
            base = os.path.basename(local_path)
            name_root, ext = os.path.splitext(base)
            try_ext = detect_mime_ext(local_path)
            candidates = []
            if try_ext:
                candidates.append(try_ext)
            candidates.extend([".jpg", ".png", ".txt", ".bin"])
            if ext and len(ext) <= 5 and ext not in candidates:
                candidates.insert(0, ext)
            tried = set()
            for c in candidates:
                try_name = name_root + c
                if try_name in tried:
                    continue
                tried.add(try_name)
                try:
                    r = await api.upload_file(local_path, try_name, folder_id)
                    if isinstance(r, dict):
                        fid = r.get("id") or (r.get("raw") or {}).get(
                            "createdFile", {}
                        ).get("id")
                        if fid:
                            return str(fid)
                except Exception:
                    continue
    return None
