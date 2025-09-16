"""Misskey 平台适配器通用工具函数"""

from typing import Dict, Any, List, Tuple, Optional, Union
import astrbot.api.message_components as Comp


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
            if text and "@" in text:
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
    user_id: Optional[str], user_cache: Dict[str, Any], self_id: Optional[str]
) -> Tuple[str, Optional[List[str]]]:
    """解析 Misskey 消息的可见性设置"""
    visibility = "public"
    visible_user_ids = None

    if user_id and user_cache:
        user_info = user_cache.get(user_id)
        if user_info:
            original_visibility = user_info.get("visibility", "public")
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
    """检查是否为有效的用户会话ID"""
    if not isinstance(session_id, str):
        return False
    return 5 <= len(session_id) <= 64 and " " not in session_id


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
            text = f"{mention} {text}".strip()
    elif nickname:
        mention = f"@{nickname}"
        if not text.startswith(mention):
            text = f"{mention} {text}".strip()

    return text
