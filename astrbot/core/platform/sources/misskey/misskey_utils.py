"""
Misskey 平台适配器通用工具函数
"""

from typing import Dict, Any, List, Tuple, Optional, Union
import astrbot.api.message_components as Comp


def serialize_message_chain(chain: List[Any]) -> Tuple[str, bool]:
    """
    将消息链序列化为文本字符串

    Args:
        chain: 消息链

    Returns:
        Tuple[str, bool]: (序列化后的文本, 是否包含@用户)
    """
    text_parts = []
    has_at = False

    for component in chain:
        if isinstance(component, Comp.Plain):
            text_parts.append(component.text)
        elif isinstance(component, Comp.Image):
            text_parts.append("[图片]")
        elif isinstance(component, Comp.Node):
            if component.content:
                for node_comp in component.content:
                    if isinstance(node_comp, Comp.Plain):
                        text_parts.append(node_comp.text)
                    elif isinstance(node_comp, Comp.Image):
                        text_parts.append("[图片]")
                    else:
                        text_parts.append(str(node_comp))
        elif isinstance(component, Comp.At):
            has_at = True
            text_parts.append(f"@{component.qq}")
        else:
            # 通用处理：检查是否有 text 属性
            if hasattr(component, "text"):
                text = getattr(component, "text", "")
                if text:
                    text_parts.append(text)
                    if "@" in text:
                        has_at = True
            else:
                text_parts.append(str(component))

    return "".join(text_parts), has_at


def resolve_message_visibility(
    user_id: Optional[str], user_cache: Dict[str, Any], self_id: Optional[str]
) -> Tuple[str, Optional[List[str]]]:
    """
    解析 Misskey 消息的可见性设置

    Args:
        user_id: 目标用户ID
        user_cache: 用户缓存
        self_id: 机器人自身ID

    Returns:
        Tuple[str, Optional[List[str]]]: (可见性设置, 可见用户ID列表)
    """
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
                # 过滤掉空值
                visible_user_ids = [uid for uid in visible_user_ids if uid]
            else:
                visibility = original_visibility

    return visibility, visible_user_ids


def resolve_visibility_from_raw_message(
    raw_message: Dict[str, Any], self_id: Optional[str] = None
) -> Tuple[str, Optional[List[str]]]:
    """
    从原始消息数据中解析可见性设置

    Args:
        raw_message: 原始消息数据
        self_id: 机器人自身ID

    Returns:
        Tuple[str, Optional[List[str]]]: (可见性设置, 可见用户ID列表)
    """
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
        # 过滤掉空值
        visible_user_ids = [uid for uid in visible_user_ids if uid]
    else:
        visibility = original_visibility

    return visibility, visible_user_ids


def is_valid_user_session_id(session_id: Union[str, Any]) -> bool:
    """
    检查是否为有效的用户会话ID

    Args:
        session_id: 会话ID

    Returns:
        bool: 是否为有效的用户会话ID
    """
    if not isinstance(session_id, str):
        return False
    return 5 <= len(session_id) <= 64 and " " not in session_id


def add_at_mention_if_needed(
    text: str, user_info: Optional[Dict[str, Any]], has_at: bool = False
) -> str:
    """
    如果需要且没有@用户，则添加@用户

    Args:
        text: 原始文本
        user_info: 用户信息
        has_at: 是否已包含@用户

    Returns:
        str: 处理后的文本
    """
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
