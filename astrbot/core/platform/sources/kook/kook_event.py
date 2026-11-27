import asyncio
import json
from collections.abc import AsyncGenerator, Coroutine
from pathlib import Path
from time import monotonic
from typing import Any

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, Group, MessageMember, PlatformMetadata
from astrbot.core.message.components import (
    ActionRow,
    At,
    AtAll,
    BaseMessageComponent,
    Button,
    File,
    Image,
    Json,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.core.platform import MessageType
from astrbot.core.platform.button_interaction import encode_button_callback

from .kook_client import KookClient
from .kook_types import (
    ActionGroupModule,
    ButtonElement,
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
        self.client = client
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
                    self.client.upload_asset(message_component.file),
                )

            case Video():
                self._file_message_counter += 1
                return wrap_upload(
                    index,
                    KookMessageType.VIDEO,
                    self.client.upload_asset(message_component.file),
                )
            case File():

                async def handle_file(index: int, f_item: File):
                    f_data = await f_item.get_file()
                    url = await self.client.upload_asset(f_data)
                    return OrderMessage(
                        index=index, text=url, type=KookMessageType.FILE
                    )

                self._file_message_counter += 1
                return handle_file(index, message_component)

            case Record():

                async def handle_audio(index: int, f_item: Record):
                    file_path = await f_item.convert_to_file_path()
                    url = await self.client.upload_asset(file_path)
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
            case ActionRow() | Button():
                return asyncio.to_thread(self._wrap_buttons, index, message_component)
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

    def _wrap_buttons(self, index: int, component: ActionRow | Button) -> OrderMessage:
        """Build a KOOK card with persisted callback tokens.

        Args:
            index: Component position within the original message.
            component: Button or action row to render.

        Returns:
            The card, or its fallback text when the row is empty.

        Raises:
            ValueError: If the action or number of buttons is unsupported.
        """
        buttons = component.buttons if isinstance(component, ActionRow) else [component]
        if not buttons:
            fallback_text = (
                component.fallback_text if isinstance(component, ActionRow) else ""
            )
            return OrderMessage(
                index=index, text=fallback_text or "", type=KookMessageType.KMARKDOWN
            )

        theme_map = {
            Button.Style.DEFAULT: "secondary",
            Button.Style.PRIMARY: "primary",
            Button.Style.SUCCESS: "success",
            Button.Style.DANGER: "danger",
        }
        elements = []
        for button in buttons:
            if isinstance(button.action, Button.CallbackAction):
                click = "return-val"
                value = encode_button_callback(
                    button.id,
                    button.action.data,
                    expires_at=component.action_expires_at
                    if isinstance(component, ActionRow)
                    else None,
                )
            elif isinstance(button.action, Button.UrlAction):
                click = "link"
                value = button.action.url
            else:
                raise ValueError(
                    f"Unsupported KOOK button action: {button.action.type}"
                )
            elements.append(
                ButtonElement(
                    text=button.label,
                    theme=theme_map[button.style],
                    value=value,
                    click=click,
                )
            )

        modules = [
            ActionGroupModule(elements=elements[offset : offset + 4])
            for offset in range(0, len(elements), 4)
        ]
        cards = [
            KookCardMessage(modules=modules[offset : offset + 50])
            for offset in range(0, len(modules), 50)
        ]
        if len(cards) > 5:
            raise ValueError("KOOK supports at most 1,000 buttons in one card message.")
        return OrderMessage(
            index=index,
            text=KookCardMessageContainer(cards).to_json(),
            type=KookMessageType.CARD,
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
                if isinstance(message.chain[index], (ActionRow, Button)):
                    raise result
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
                await self.client.send_text(
                    self.channel_id,
                    item.text,
                    self.astrbot_message_type,
                    item.type,
                    reply_id,
                )
            except RuntimeError as exp:
                await self.client.send_text(
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

        await super().send(message)

    async def send_streaming(
        self, generator: AsyncGenerator[MessageChain, None], use_fallback: bool = False
    ) -> None:
        """Stream cumulative KMarkdown text into editable KOOK messages.

        Args:
            generator: Incremental message chains from the response pipeline.
            use_fallback: Framework flag for platforms without native streaming.

        Raises:
            RuntimeError: If a message cannot be created or updated.
        """
        # KOOK recommends at most 8,000 characters per message.
        max_length = 8000
        msg_id = None
        content = sent = ""
        next_edit = 0.0

        async def publish() -> None:
            nonlocal msg_id, sent, next_edit
            if content == sent:
                return
            if msg_id is None:
                msg_id = await self.client.send_text(
                    self.channel_id,
                    content,
                    self.astrbot_message_type,
                    KookMessageType.KMARKDOWN,
                )
                if msg_id is None:
                    raise RuntimeError("KOOK streaming message creation failed")
            else:
                await self.client.update_text(
                    msg_id, content, self.astrbot_message_type
                )
            sent = content
            # Batch rapid deltas since each edit counts towards the message quota.
            next_edit = monotonic() + 1

        iterator = aiter(generator)
        while True:
            try:
                chain = await anext(iterator)
            except StopAsyncIteration:
                break
            except Exception:
                # Deliver text already received while preserving the generation error.
                try:
                    await publish()
                except Exception:
                    logger.exception("Failed to flush buffered KOOK text")
                raise

            if chain.type == "break" or any(
                not isinstance(component, Plain) for component in chain.chain
            ):
                await publish()
                msg_id = None
                content = sent = ""
                if chain.type != "break":
                    await self.send(chain)
                continue

            delta = "".join(component.text for component in chain.chain)
            while delta:
                available = max_length - len(content)
                content += delta[:available]
                delta = delta[available:]
                if len(content) == max_length:
                    await publish()
                    msg_id = None
                    content = sent = ""
                elif msg_id is None or monotonic() >= next_edit:
                    await publish()

        await publish()
        await super().send_streaming(generator, use_fallback)

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
            channel = await self.client.get_channel(channel_id)
            group.group_name = channel.get("name") or group.group_name
        except Exception as exc:
            logger.debug("KOOK channel lookup failed for %s: %s", channel_id, exc)
            return group

        guild_id = str(channel.get("guild_id") or "")
        if (
            not guild_id
            and channel_id == self.get_group_id()
            and isinstance(self.message_obj.raw_message, dict)
        ):
            extra = self.message_obj.raw_message.get("extra") or {}
            if isinstance(extra, dict):
                guild_id = str(extra.get("guild_id") or "")
        if not guild_id:
            return group

        guild_roles: list[dict] = []
        try:
            guild = await self.client.get_guild(guild_id)
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
                    role_page = await self.client.get_guild_roles(
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
                member_page = await self.client.get_guild_users(
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
                if isinstance(role_id, (int, str)) and str(role_id).isdigit()
            }
            if admin_role_ids.intersection(member_role_ids):
                admins.append(user_id)

        group.members = members
        group.group_admins = admins
        group.member_count = total if total is not None else len(members)
        return group
