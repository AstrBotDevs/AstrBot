from typing import TYPE_CHECKING
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.api.message_components import Plain, Image, At, File, Record

if TYPE_CHECKING:
    from .satori_adapter import SatoriPlatformAdapter


class SatoriPlatformEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        adapter: "SatoriPlatformAdapter",
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.adapter = adapter
        self.platform = None
        self.user_id = None
        if (
            hasattr(message_obj, "raw_message")
            and message_obj.raw_message
            and isinstance(message_obj.raw_message, dict)
        ):
            login = message_obj.raw_message.get("login", {})
            self.platform = login.get("platform")
            user = login.get("user", {})
            self.user_id = user.get("id") if user else None

    @classmethod
    async def send_with_adapter(
        cls, adapter: "SatoriPlatformAdapter", message: MessageChain, session_id: str
    ):
        try:
            content_parts = []

            for component in message.chain:
                if isinstance(component, Plain):
                    text = (
                        component.text.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                    )
                    content_parts.append(text)

                elif isinstance(component, At):
                    if component.qq:
                        content_parts.append(f'<at id="{component.qq}"/>')
                    elif component.name:
                        content_parts.append(f'<at name="{component.name}"/>')

                elif isinstance(component, Image):
                    try:
                        image_base64 = await component.convert_to_base64()
                        if image_base64:
                            content_parts.append(
                                f'<img src="data:image/jpeg;base64,{image_base64}"/>'
                            )
                    except Exception as e:
                        logger.error(f"图片转换为base64失败: {e}")

                elif isinstance(component, File):
                    content_parts.append(
                        f'<file src="{component.file}" name="{component.name or "文件"}"/>'
                    )

                elif isinstance(component, Record):
                    try:
                        record_base64 = await component.convert_to_base64()
                        if record_base64:
                            content_parts.append(
                                f'<audio src="data:audio/wav;base64,{record_base64}"/>'
                            )
                    except Exception as e:
                        logger.error(f"语音转换为base64失败: {e}")

            content = "".join(content_parts)
            channel_id = session_id
            data = {"channel_id": channel_id, "content": content}

            platform = None
            user_id = None

            if hasattr(adapter, "logins") and adapter.logins:
                current_login = adapter.logins[0]
                platform = current_login.get("platform", "")
                user = current_login.get("user", {})
                user_id = user.get("id", "") if user else ""

            result = await adapter.send_http_request(
                "POST", "/message.create", data, platform, user_id
            )
            if result:
                return result
            else:
                return None

        except Exception as e:
            logger.error(f"Satori 消息发送异常: {e}")
            return None

    async def send(self, message: MessageChain):
        platform = getattr(self, "platform", None)
        user_id = getattr(self, "user_id", None)

        if not platform or not user_id:
            if hasattr(self.adapter, "logins") and self.adapter.logins:
                current_login = self.adapter.logins[0]
                platform = current_login.get("platform", "")
                user = current_login.get("user", {})
                user_id = user.get("id", "") if user else ""

        try:
            content_parts = []

            for component in message.chain:
                if isinstance(component, Plain):
                    text = (
                        component.text.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                    )
                    content_parts.append(text)

                elif isinstance(component, At):
                    if component.qq:
                        content_parts.append(f'<at id="{component.qq}"/>')
                    elif component.name:
                        content_parts.append(f'<at name="{component.name}"/>')

                elif isinstance(component, Image):
                    try:
                        image_base64 = await component.convert_to_base64()
                        if image_base64:
                            content_parts.append(
                                f'<img src="data:image/jpeg;base64,{image_base64}"/>'
                            )
                    except Exception as e:
                        logger.error(f"图片转换为base64失败: {e}")

                elif isinstance(component, File):
                    content_parts.append(
                        f'<file src="{component.file}" name="{component.name or "文件"}"/>'
                    )

                elif isinstance(component, Record):
                    try:
                        record_base64 = await component.convert_to_base64()
                        if record_base64:
                            content_parts.append(
                                f'<audio src="data:audio/wav;base64,{record_base64}"/>'
                            )
                    except Exception as e:
                        logger.error(f"语音转换为base64失败: {e}")

            content = "".join(content_parts)
            channel_id = self.session_id
            data = {"channel_id": channel_id, "content": content}

            result = await self.adapter.send_http_request(
                "POST", "/message.create", data, platform, user_id
            )
            if not result:
                logger.error("Satori 消息发送失败")
        except Exception as e:
            logger.error(f"Satori 消息发送异常: {e}")

        await super().send(message)

    async def send_streaming(self, generator, use_fallback: bool = False):
        try:
            content_parts = []

            async for chain in generator:
                if isinstance(chain, MessageChain):
                    if chain.type == "break":
                        if content_parts:
                            content = "".join(content_parts)
                            temp_chain = MessageChain([Plain(text=content)])
                            await self.send(temp_chain)
                            content_parts = []
                        continue

                    for component in chain.chain:
                        if isinstance(component, Plain):
                            content_parts.append(component.text)
                        elif isinstance(component, Image):
                            if content_parts:
                                content = "".join(content_parts)
                                temp_chain = MessageChain([Plain(text=content)])
                                await self.send(temp_chain)
                                content_parts = []
                            try:
                                image_base64 = await component.convert_to_base64()
                                if image_base64:
                                    img_chain = MessageChain(
                                        [
                                            Plain(
                                                text=f'<img src="data:image/jpeg;base64,{image_base64}"/>'
                                            )
                                        ]
                                    )
                                    await self.send(img_chain)
                            except Exception as e:
                                logger.error(f"图片转换为base64失败: {e}")
                        else:
                            content_parts.append(str(component))

            if content_parts:
                content = "".join(content_parts)
                temp_chain = MessageChain([Plain(text=content)])
                await self.send(temp_chain)

        except Exception as e:
            logger.error(f"Satori 流式消息发送异常: {e}")

        return await super().send_streaming(generator, use_fallback)
