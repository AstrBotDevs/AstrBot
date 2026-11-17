import asyncio
from collections import OrderedDict
from time import monotonic

from botpy import Client
from botpy.http import Route

from astrbot import logger
from astrbot.api.platform import Group

GROUP_INFO_CACHE_TTL = 3600
GROUP_INFO_FAILURE_TTL = 300
GROUP_INFO_CACHE_MAX_SIZE = 1024
GROUP_INFO_REQUEST_TIMEOUT = 3


async def get_qq_group(bot: Client, group: Group) -> Group:
    """Enrich a QQ group using a bounded cache owned by its bot client.

    Successful names are cached for one hour; missing names and failed requests
    are cached for five minutes. The client lock coalesces concurrent cache
    misses, while cache hits do not wait for unrelated requests.

    Args:
        bot: Authenticated QQ bot client used to fetch group information.
        group: Incoming group to enrich, preserving fields absent from the API.

    Returns:
        The same group object with available name and member-count metadata.
    """
    if not group.group_id:
        return group

    cache = getattr(bot, "_astrbot_group_info_cache", None)
    if cache is None:
        cache = OrderedDict()
        bot._astrbot_group_info_cache = cache
        bot._astrbot_group_info_lock = asyncio.Lock()

    cached = cache.get(group.group_id)
    if cached is None or cached[0] <= monotonic():
        async with bot._astrbot_group_info_lock:
            cached = cache.get(group.group_id)
            if cached is None or cached[0] <= monotonic():
                payload = {}
                try:
                    route = Route(
                        "GET",
                        "/v2/groups/{group_openid}/info",
                        group_openid=group.group_id,
                    )
                    response = await asyncio.wait_for(
                        bot.api._http.request(route),
                        timeout=GROUP_INFO_REQUEST_TIMEOUT,
                    )
                    if isinstance(response, dict):
                        payload = response
                    else:
                        logger.warning(
                            "[QQOfficial] Group info API returned an invalid response for %s",
                            group.group_id,
                        )
                except Exception as exc:
                    logger.warning(
                        "[QQOfficial] Failed to get group info for %s: %s",
                        group.group_id,
                        exc,
                    )
                ttl = (
                    GROUP_INFO_CACHE_TTL
                    if payload.get("group_name")
                    else GROUP_INFO_FAILURE_TTL
                )
                cached = (monotonic() + ttl, payload)
                cache[group.group_id] = cached
                if len(cache) > GROUP_INFO_CACHE_MAX_SIZE:
                    cache.popitem(last=False)

    cache.move_to_end(group.group_id)
    payload = cached[1]
    group.group_name = payload.get("group_name") or group.group_name
    member_count = payload.get("group_member_num", payload.get("member_count"))
    if member_count is not None:
        try:
            group.member_count = int(member_count)
        except (TypeError, ValueError):
            logger.warning(
                "[QQOfficial] Group info API returned an invalid member_count for %s",
                group.group_id,
            )
    return group
