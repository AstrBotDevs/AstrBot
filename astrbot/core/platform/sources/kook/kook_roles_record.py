import asyncio
from collections import defaultdict

import aiohttp
import pydantic

from astrbot import logger

from .kook_types import KookApiPaths, KookUserViewResponse

USER_VIEW_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=3)


class KookRolesRecord:
    """自动和缓存获取机器人所需响应的消息频道的role信息"""

    def __init__(self, bot_id: str, http_client: aiohttp.ClientSession):
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._lock = asyncio.Lock()
        self._bot_id = bot_id
        self._roles_dict: dict[int, set[int]] = {}
        self._http_client = http_client

    def set_bot_id(self, bot_id: str):
        self._bot_id = bot_id

    def clean_roles_cache(self):
        self._roles_dict.clear()

    async def _get_roles_by_channel_id(self, channel_id: int) -> None:
        url = KookApiPaths.USER_VIEW
        try:
            # 由于这里在has_role_in_channel方法调用时是加了异步锁的,
            # 后续来自同一个频道的消息,在第一次查这个role的时候,
            # 会一直阻塞消息接收直到请求完成或者报错,
            # 所以,这里特意调低了timeout时间,避免阻塞太久

            # TODO 这个超时时间后续加到适配器配置项里
            resp = await self._http_client.get(
                url,
                params={
                    "guild_id": channel_id,
                    "user_id": self._bot_id,
                },
                timeout=USER_VIEW_REQUEST_TIMEOUT,
            )
            if resp.status != 200:
                logger.error(
                    f'[KOOK] 获取机器人在频道"{channel_id}"的角色id信息失败，状态码: {resp.status} , {await resp.text()}'
                )
                return
            try:
                resp_content = KookUserViewResponse.from_dict(await resp.json())
            except pydantic.ValidationError as e:
                logger.error(
                    f'[KOOK] 获取机器人在频道"{channel_id}"的角色id信息失败, 响应数据格式错误: \n{e}'
                )
                logger.error(f"[KOOK] 响应内容: {await resp.text()}")
                return

            if not resp_content.success():
                logger.error(
                    f'[KOOK] 获取机器人在频道"{channel_id}"的角色id信息失败: {resp_content.model_dump_json()}'
                )
                return

            self._roles_dict[channel_id] = set(resp_content.data.roles)

            logger.info(f'[KOOK] 获取机器人在频道"{channel_id}"的角色id成功')

        except Exception as e:
            logger.error(
                f'[KOOK] 获取机器人在频道"{channel_id}"的角色id信息时请求异常: {e}'
            )

    async def has_role_in_channel(self, role_id: int, channel_id: int) -> bool:
        if channel_id in self._roles_dict:
            return role_id in self._roles_dict[channel_id]

        async with self._locks[channel_id]:
            if channel_id not in self._roles_dict:
                await self._get_roles_by_channel_id(channel_id)

            roles = self._roles_dict.get(channel_id, ())
            return role_id in roles
