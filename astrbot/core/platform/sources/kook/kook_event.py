import asyncio
import json
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from astrbot import logger
from astrbot.core.message.components import (
    At,
    AtAll,
    BaseMessageComponent,
    File,
    Image,
    Json,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import (
    AstrBotMessage,
    Group,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from .kook_client import KookClient
from .kook_types import (
    FileModule,
    KookCardMessage,
    KookCardMessageContainer,
    KookMessageType,
    KookModuleType,
    OrderMessage,
)


class KookEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        client: KookClient,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self._client = client
        self.channel_id = message_obj.group_id or message_obj.session_id
        self.astrbot_message_type: MessageType = message_obj.type
        self._file_message_counter = 0

    def _wrap_message(
        self, index: int, message_component: BaseMessageComponent
    ) -> Coroutine[Any, Any, OrderMessage]:
        async def wrap_upload(
            index: int, message_type: KookMessageType, upload_coro
        ) -> OrderMessage:
            url = await upload_coro
            return OrderMessage(index=index, text=url, type=message_type)

        async def handle_plain(
            index: int,
            text: str | None,
            reply_id: str | int = "",
            type: KookMessageType = KookMessageType.KMARKDOWN,
        ):
            if not text:
                text = ""
            return OrderMessage(
                index=index,
                text=text,
                type=type,
                reply_id=reply_id,
            )

        match message_component:
            case Image():
                self._file_message_counter += 1
                return wrap_upload(
                    index,
                    KookMessageType.IMAGE,
                    self._client.upload_asset(message_component.file),
                )

            case Video():
                self._file_message_counter += 1
                return wrap_upload(
                    index,
                    KookMessageType.VIDEO,
                    self._client.upload_asset(message_component.file),
                )
            case File():

                async def handle_file(index: int, f_item: File):
                    f_data = await f_item.get_file()
                    url = await self._client.upload_asset(f_data)
                    return OrderMessage(
                        index=index, text=url, type=KookMessageType.FILE
                    )

                self._file_message_counter += 1
                return handle_file(index, message_component)

            case Record():

                async def handle_audio(index: int, f_item: Record):
                    file_path = await f_item.convert_to_file_path()
                    url = await self._client.upload_asset(file_path)
                    title = f_item.text or Path(file_path).name
                    return OrderMessage(
                        index=index,
                        text=KookCardMessageContainer(
                            [
                                KookCardMessage(
                                    modules=[
                                        FileModule(
                                            type=KookModuleType.AUDIO,
                                            title=title,
                                            src=url,
                                        )
                                    ]
                                )
                            ]
                        ).to_json(),
                        type=KookMessageType.CARD,
                    )

                return handle_audio(index, message_component)
            case Plain():
                return handle_plain(index, message_component.text)
            case At():
                return handle_plain(index, f"(met){message_component.qq}(met)")
            case AtAll():
                return handle_plain(index, "(met)all(met)")
            case Reply():
                return handle_plain(index, "", reply_id=message_component.id)
            case Json():
                json_data = message_component.data
                # kook卡片json外层得是一个列表
                if isinstance(json_data, dict):
                    json_data = [json_data]
                return handle_plain(
                    index,
                    # 考虑到kook可能会更改消息结构,为了能让插件开发者
                    # 自行根据kook文档描述填卡片json内容,故不做模型校验
                    # KookCardMessage().model_validate(message_component.data).to_json(),
                    text=json.dumps(json_data),
                    type=KookMessageType.CARD,
                )
            case _:
                raise NotImplementedError(
                    f'kook适配器尚未实现对 "{message_component.type}" 消息类型的支持'
                )

    async def send(self, message: MessageChain):
        file_upload_tasks: list[Coroutine[Any, Any, OrderMessage]] = []
        for index, item in enumerate(message.chain):
            file_upload_tasks.append(self._wrap_message(index, item))

        if self._file_message_counter > 0:
            logger.debug("[Kook] 正在向kook服务器上传文件")

        tasks_result = await asyncio.gather(*file_upload_tasks, return_exceptions=True)
        order_messages: list[OrderMessage] = []

        for index, result in enumerate(tasks_result):
            if isinstance(result, BaseException):
                logger.error(f"[Kook] {result}")
                # 构造一个虚假的 OrderMessage，让用户知道这里本来有张图但坏了
                # 这样后面的 for 循环就能把它当成普通文本发出去
                err_node = OrderMessage(
                    index=index,
                    text=str(result),
                    type=KookMessageType.TEXT,
                )
                order_messages.append(err_node)
            else:
                order_messages.append(result)

        order_messages.sort(key=lambda x: x.index)

        reply_id: str | int = ""
        errors: list[Exception] = []
        for item in order_messages:
            if item.reply_id:
                reply_id = item.reply_id
            if not item.text:
                logger.debug(f'[Kook] 跳过空消息,类型为"{item.type.name}"')
                continue
            try:
                await self._client.send_text(
                    self.channel_id,
                    item.text,
                    self.astrbot_message_type,
                    item.type,
                    reply_id,
                )
            except RuntimeError as exp:
                await self._client.send_text(
                    self.channel_id,
                    str(exp),
                    self.astrbot_message_type,
                    KookMessageType.TEXT,
                    reply_id,
                )
                errors.append(exp)

        if errors:
            err_msg = "\n".join([str(err) for err in errors])
            logger.error(f"[kook] {err_msg}")

        return await super().send(message)

    async def get_group(self, group_id=None, **kwargs):
        """Gets KOOK channel and guild member information.

        Args:
            group_id: Optional KOOK channel identifier.
            **kwargs: Reserved compatibility arguments.

        Returns:
            Enriched channel information, or a basic group if lookup fails.
        """
        channel_id = group_id or self.get_group_id()
        if not channel_id:
            return None

        current_group = self.message_obj.group
        group = Group(
            group_id=channel_id,
            group_name=(
                current_group.group_name
                if current_group and current_group.group_id == channel_id
                else None
            ),
        )

        try:
            channel = await self._client.get_channel(channel_id)
            group.group_name = channel.get("name") or group.group_name
        except Exception as exc:
            logger.debug("KOOK channel lookup failed for %s: %s", channel_id, exc)
            return group

        guild_id = str(channel.get("guild_id") or "")
        if not guild_id and channel_id == self.get_group_id():
            raw = self.message_obj.raw_message
            extra_guild_id = None
            if isinstance(raw, dict):
                extra = raw.get("extra") or {}
                if isinstance(extra, dict):
                    extra_guild_id = extra.get("guild_id")
            else:
                extra = getattr(raw, "extra", None)
                extra_guild_id = getattr(extra, "guild_id", None)
            if extra_guild_id:
                guild_id = str(extra_guild_id)
        if not guild_id:
            return group

        guild_roles: list[dict] = []
        try:
            guild = await self._client.get_guild(guild_id)
            group.group_avatar = guild.get("icon") or None
            group.group_owner = str(guild.get("user_id") or "") or None
            guild_roles.extend(
                role for role in (guild.get("roles") or []) if isinstance(role, dict)
            )
        except Exception as exc:
            logger.debug("KOOK guild lookup failed for %s: %s", guild_id, exc)

        if not guild_roles:
            role_page_number = 1
            role_page_size = 50
            try:
                while True:
                    role_page = await self._client.get_guild_roles(
                        guild_id,
                        page=role_page_number,
                        page_size=role_page_size,
                    )
                    role_items = role_page.get("items") or []
                    guild_roles.extend(
                        role for role in role_items if isinstance(role, dict)
                    )
                    role_meta = role_page.get("meta") or {}
                    page_total = (
                        role_meta.get("page_total")
                        if isinstance(role_meta, dict)
                        else None
                    )
                    if isinstance(page_total, int):
                        if role_page_number >= page_total:
                            break
                    elif len(role_items) < role_page_size:
                        break
                    role_page_number += 1
            except Exception as exc:
                logger.debug("KOOK guild role lookup failed for %s: %s", guild_id, exc)

        admin_role_ids: set[int] = set()
        for role in guild_roles:
            role_id = role.get("role_id") or role.get("id")
            permissions = role.get("permissions")
            if (
                role_id is None
                or not str(role_id).isdigit()
                or not isinstance(permissions, int)
            ):
                continue
            if permissions & 1:
                admin_role_ids.add(int(role_id))

        member_items: list[dict] = []
        total: int | None = None
        page = 1
        page_size = 50
        try:
            while True:
                member_page = await self._client.get_guild_users(
                    guild_id,
                    channel_id=channel_id,
                    page=page,
                    page_size=page_size,
                )
                items = member_page.get("items") or []
                member_items.extend(item for item in items if isinstance(item, dict))
                meta = member_page.get("meta") or {}
                if isinstance(meta, dict) and isinstance(meta.get("total"), int):
                    total = meta["total"]
                page_total = meta.get("page_total") if isinstance(meta, dict) else None
                if isinstance(page_total, int):
                    if page >= page_total:
                        break
                elif len(items) < page_size:
                    break
                if total is not None and len(member_items) >= total:
                    break
                page += 1
        except Exception as exc:
            logger.debug("KOOK guild member lookup failed for %s: %s", guild_id, exc)
            return group

        unique_members: dict[str, dict] = {}
        for member in member_items:
            user_id = str(member.get("id") or "")
            if user_id:
                unique_members[user_id] = member

        members: list[MessageMember] = []
        admins: list[str] = []
        for user_id, member in unique_members.items():
            members.append(
                MessageMember(
                    user_id=user_id,
                    nickname=(
                        member.get("nickname") or member.get("username") or user_id
                    ),
                ),
            )
            member_role_ids = {
                int(role_id)
                for role_id in (member.get("roles") or [])
                if isinstance(role_id, int | str) and str(role_id).isdigit()
            }
            if admin_role_ids.intersection(member_role_ids):
                admins.append(user_id)

        group.members = members
        group.group_admins = admins
        group.member_count = total if total is not None else len(members)
        return group
