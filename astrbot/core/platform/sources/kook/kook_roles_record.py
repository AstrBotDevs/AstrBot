import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass

import aiohttp
import pydantic

from astrbot import logger

from .kook_types import KookApiPaths, KookUserViewResponse

USER_VIEW_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=3)
ROLES_CACHE_MAX_SIZE = 2000
MAX_RETRY_TIMES = 3
RETRY_INTERVAL_SECOND = 1 * 60


@dataclass
class RolesCache:
    value: set[int] | None = None
    failed_count: int = 0
    latest_update_time: float = 0

    def update(self, roles: set[int] | None) -> None:
        if roles is not None:
            self.failed_count = 0
        self.value = roles
        self.latest_update_time = time.time()

    def add_failed(self):
        self.failed_count += 1

    def reset(self, without_value=False):
        if not without_value:
            self.value = None
        self.failed_count = 0
        self.latest_update_time = 0


class KookRolesRecord:
    """自动和缓存获取机器人所需响应的消息频道的role信息"""

    def __init__(self, bot_id: str, http_client: aiohttp.ClientSession):
        # self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._lock = asyncio.Lock()
        self._bot_id = bot_id
        self._http_client = http_client
        # TODO 这个些配置后续加到适配器配置项里
        self._cache_max_size = ROLES_CACHE_MAX_SIZE
        self._max_retry_times = MAX_RETRY_TIMES
        self._retry_interval = RETRY_INTERVAL_SECOND
        self._roles_cache: OrderedDict[int, RolesCache] = OrderedDict()
        self._pending_tasks: dict[int, asyncio.Future] = {}

    def set_bot_id(self, bot_id: str):
        self._bot_id = bot_id

    def clear_guild_roles_cache(self, guild_id: int):
        self._roles_cache.pop(guild_id, None)
        self._pending_tasks.pop(guild_id, None)

    async def _fetch_roles_by_guild_id(self, guild_id: int) -> set[int] | None:
        # 由于需要判断bot账号是属于某个角色(role)才会回复消息,
        # 而后续来自同一个频道的消息,在第一次查这个role的时候,
        # 会一直阻塞消息接收直到请求完成或者报错,
        # 所以,这里特意调低了timeout时间,避免阻塞太久
        url = KookApiPaths.USER_VIEW
        try:
            async with self._http_client.get(
                url,
                params={
                    "guild_id": guild_id,
                    "user_id": self._bot_id,
                },
                # TODO 这个超时时间后续加到适配器配置项里
                timeout=USER_VIEW_REQUEST_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    logger.error(
                        f'[KOOK] 获取机器人在频道"{guild_id}"的角色id信息失败，状态码: {resp.status} , {await resp.text()}'
                    )
                    return
                try:
                    resp_content = KookUserViewResponse.from_dict(await resp.json())
                except pydantic.ValidationError as e:
                    logger.error(
                        f'[KOOK] 获取机器人在频道"{guild_id}"的角色id信息失败, 响应数据格式错误: \n{e}'
                    )
                    logger.error(f"[KOOK] 响应内容: {await resp.text()}")
                    return

                if not resp_content.success():
                    logger.error(
                        f'[KOOK] 获取机器人在频道"{guild_id}"的角色id信息失败: {resp_content.model_dump_json()}'
                    )
                    return

                logger.info(f'[KOOK] 获取机器人在频道"{guild_id}"的角色id成功')
                return set(resp_content.data.roles)

        except Exception as e:
            logger.error(
                f'[KOOK] 获取机器人在频道"{guild_id}"的角色id信息时请求异常: {e}'
            )
            return

    async def has_role_in_channel(self, role_id: int, guild_id: int) -> bool:
        if (cache := self._roles_cache.get(guild_id)) is not None:
            self._roles_cache.move_to_end(guild_id)
            roles = cache.value
            if roles is not None:
                return role_id in roles

        new_future: asyncio.Future[set[int] | None] = asyncio.Future()
        actual_future: asyncio.Future[set[int] | None] = self._pending_tasks.setdefault(
            guild_id, new_future
        )

        if actual_future is not new_future:
            roles = await actual_future
            if roles is None:
                return False
            return role_id in roles

        try:
            if (cache := self._roles_cache.get(guild_id)) is not None:
                if (
                    cache.failed_count > self._max_retry_times
                    and time.time() - cache.latest_update_time < self._retry_interval
                ):
                    new_future.set_result(None)
                    return False

            # 简单的容量控制 (LRU)
            if len(self._roles_cache) + 1 > self._cache_max_size:
                self._roles_cache.popitem(last=False)

            roles_set = await self._fetch_roles_by_guild_id(guild_id)

            cache = self._roles_cache.get(guild_id)
            if cache is not None:
                cache.update(roles_set)
                self._roles_cache.move_to_end(guild_id)
            else:
                cache = RolesCache(roles_set, latest_update_time=time.time())
                self._roles_cache[guild_id] = cache

            result = False
            if roles_set is None:
                cache.add_failed()
            else:
                result = role_id in roles_set

            new_future.set_result(roles_set)
            return result
        except Exception as e:
            new_future.set_result(None)
            logger.error(
                f'[KOOK] 获取机器人在频道"{guild_id}"的角色id信息时发生异常: {e}'
            )
            return False
        finally:
            self._pending_tasks.pop(guild_id, None)
