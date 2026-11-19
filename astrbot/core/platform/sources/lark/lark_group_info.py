import asyncio
from collections import OrderedDict
from time import monotonic

import lark_oapi as lark
from lark_oapi.api.im.v1 import GetChatRequest

from astrbot import logger
from astrbot.api.platform import Group

GROUP_INFO_CACHE_TTL = 3600
GROUP_INFO_FAILURE_TTL = 300
GROUP_INFO_CACHE_MAX_SIZE = 1024
GROUP_INFO_REQUEST_TIMEOUT = 3


async def get_lark_group(bot: lark.Client, group: Group) -> Group | None:
    """Load cached Lark group details without requesting its member list.

    Cache entries belong to the API client. Successful names live for one hour;
    failed or nameless lookups live for five minutes. Concurrent cache misses
    share a client lock, while hits do not wait for unrelated requests.

    Args:
        bot: Authenticated Lark API client used to query the group.
        group: Incoming group to enrich, preserving unavailable fields.

    Returns:
        The enriched incoming group, or None if group details are unavailable.
    """
    if not group.group_id:
        return None

    cache = getattr(bot, "_astrbot_group_info_cache", None)
    if cache is None:
        cache = OrderedDict()
        setattr(bot, "_astrbot_group_info_cache", cache)
        setattr(bot, "_astrbot_group_info_lock", asyncio.Lock())

    cached = cache.get(group.group_id)
    if cached is None or cached[0] <= monotonic():
        async with getattr(bot, "_astrbot_group_info_lock"):
            cached = cache.get(group.group_id)
            if cached is None or cached[0] <= monotonic():
                chat_data = None
                try:
                    request = (
                        GetChatRequest.builder()
                        .chat_id(group.group_id)
                        .user_id_type("open_id")
                        .build()
                    )
                    response = await asyncio.wait_for(
                        bot.im.v1.chat.aget(request),
                        timeout=GROUP_INFO_REQUEST_TIMEOUT,
                    )
                    if response.success() and response.data is not None:
                        chat_data = response.data
                    else:
                        logger.warning(
                            "[Lark] Failed to get chat details for %s (%s): %s",
                            group.group_id,
                            response.code,
                            response.msg,
                        )
                except Exception as exc:
                    logger.warning(
                        "[Lark] Failed to get chat details for %s: %s",
                        group.group_id,
                        exc,
                    )
                ttl = (
                    GROUP_INFO_CACHE_TTL
                    if chat_data and chat_data.name
                    else GROUP_INFO_FAILURE_TTL
                )
                cached = (monotonic() + ttl, chat_data)
                cache[group.group_id] = cached
                if len(cache) > GROUP_INFO_CACHE_MAX_SIZE:
                    cache.popitem(last=False)

    cache.move_to_end(group.group_id)
    chat_data = cached[1]
    if chat_data is None:
        return None
    group.group_name = chat_data.name or group.group_name
    group.group_avatar = chat_data.avatar or group.group_avatar
    group.group_owner = chat_data.owner_id or group.group_owner
    group.group_admins = list(chat_data.user_manager_id_list or [])
    if chat_data.user_count is not None:
        try:
            group.member_count = int(chat_data.user_count)
        except (TypeError, ValueError):
            logger.warning(
                "[Lark] Chat %s returned an invalid user count: %r",
                group.group_id,
                chat_data.user_count,
            )
    return group
