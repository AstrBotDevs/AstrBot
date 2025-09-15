""""""import asyncio

Misskey 平台适配器专用工具函数

"""Misskey 平台适配器专用工具函数from typing import Callable

from typing import Any, Dict, Iterable, List, Optional, Tuple

"""

from astrbot.api.message_components import Plain, Image, At

from astrbot.core.message.components import Nodefrom typing import Any, Dict, Iterable, List, Optional, Tuple



def retry_async(max_retries=3, retryable_exceptions=()):

def serialize_message_chain(chain: Iterable[Any]) -> Tuple[str, bool]:

    """from astrbot.api.message_components import Plain, Image, At    def decorator(func: Callable):

    将消息链序列化为文本字符串。

    from astrbot.core.message.components import Node        async def wrapper(*args, **kwargs):

    Args:

        chain: 消息链组件列表            last_exc = None

        

    Returns:            for _ in range(max_retries):

        Tuple[str, bool]: (文本内容, 是否包含@用户)

    """def serialize_message_chain(chain: Iterable[Any]) -> Tuple[str, bool]:                try:

    text_parts = []

    has_at = False    """                    return await func(*args, **kwargs)

    

    for component in chain:    将消息链序列化为文本字符串。                except retryable_exceptions as e:

        if isinstance(component, Plain):

            text_parts.append(component.text)                        last_exc = e

        elif isinstance(component, Image):

            text_parts.append("[图片]")    Args:                    await asyncio.sleep(0.1)

        elif isinstance(component, Node):

            if component.content:        chain: 消息链组件列表                    continue

                for node_comp in component.content:

                    if isinstance(node_comp, Plain):                    if last_exc:

                        text_parts.append(node_comp.text)

                    elif isinstance(node_comp, Image):    Returns:                raise last_exc

                        text_parts.append("[图片]")

                    else:        Tuple[str, bool]: (文本内容, 是否包含@用户)

                        text_parts.append(str(node_comp))

        elif isinstance(component, At):    """        return wrapper

            has_at = True

            text_parts.append(f"@{component.qq}")    text_parts = []

        else:

            text_parts.append(str(component))    has_at = False    return decorator

    

    return "".join(text_parts), has_at    

    for component in chain:

        if isinstance(component, Plain):

def resolve_visibility(            text_parts.append(component.text)

    user_id: Optional[str],        elif isinstance(component, Image):

    user_cache: Dict[str, Any],            text_parts.append("[图片]")

    self_id: str        elif isinstance(component, Node):

) -> Tuple[str, Optional[List[str]]]:            if component.content:

    """                for node_comp in component.content:

    解析 Misskey 消息的可见性设置。                    if isinstance(node_comp, Plain):

                            text_parts.append(node_comp.text)

    Args:                    elif isinstance(node_comp, Image):

        user_id: 用户 ID                        text_parts.append("[图片]")

        user_cache: 用户缓存信息                    else:

        self_id: 机器人自己的用户 ID                        text_parts.append(str(node_comp))

                elif isinstance(component, At):

    Returns:            has_at = True

        Tuple[str, Optional[List[str]]]: (可见性级别, 可见用户ID列表)            text_parts.append(f"@{component.qq}")

    """        else:

    visibility = "public"            text_parts.append(str(component))

    visible_user_ids = None    

        return "".join(text_parts), has_at

    if user_id:

        user_info = user_cache.get(user_id)

        if user_info:def parse_session_id(username: str, host: str, user_id: str, platform_name: str) -> str:

            original_visibility = user_info.get("visibility", "public")    """

            if original_visibility == "specified":    构建标准化的会话 ID。

                visibility = "specified"    

                original_visible_users = user_info.get("visible_user_ids", [])    Args:

                users_to_include = [user_id]        username: 用户名

                if self_id:        host: 主机名

                    users_to_include.append(self_id)        user_id: 用户 ID

                visible_user_ids = list(        platform_name: 平台名称

                    set(original_visible_users + users_to_include)        

                )    Returns:

                visible_user_ids = [uid for uid in visible_user_ids if uid]        str: 格式化的会话 ID

            else:    """

                visibility = original_visibility    return f"{platform_name}:{username}@{host}:{user_id}"

    

    return visibility, visible_user_ids
def resolve_visibility(
    user_id: Optional[str],
    user_cache: Dict[str, Any],
    self_id: str
) -> Tuple[str, Optional[List[str]]]:
    """
    解析 Misskey 消息的可见性设置。
    
    Args:
        user_id: 用户 ID
        user_cache: 用户缓存信息
        self_id: 机器人自己的用户 ID
        
    Returns:
        Tuple[str, Optional[List[str]]]: (可见性级别, 可见用户ID列表)
    """
    visibility = "public"
    visible_user_ids = None
    
    if user_id:
        user_info = user_cache.get(user_id)
        if user_info:
            original_visibility = user_info.get("visibility", "public")
            if original_visibility == "specified":
                visibility = "specified"
                original_visible_users = user_info.get("visible_user_ids", [])
                users_to_include = [user_id]
                if self_id:
                    users_to_include.append(self_id)
                visible_user_ids = list(
                    set(original_visible_users + users_to_include)
                )
                visible_user_ids = [uid for uid in visible_user_ids if uid]
            else:
                visibility = original_visibility
    
    return visibility, visible_user_ids