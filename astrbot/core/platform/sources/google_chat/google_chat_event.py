import aiohttp
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain, Image
from astrbot import logger


class GoogleChatMessageEvent(AstrMessageEvent):
    @staticmethod
    async def _send_chain(webhook_url: str, message: MessageChain):
        text = ""
        images = []
        for comp in message.chain:
            if isinstance(comp, Plain):
                text += comp.text
            elif isinstance(comp, Image):
                if comp.file and comp.file.startswith("http"):
                    images.append(comp.file)
                elif comp.url and comp.url.startswith("http"):
                    images.append(comp.url)
                else:
                    try:
                        image_url = await comp.register_to_file_service()
                        images.append(image_url)
                    except Exception as e:
                        logger.error(f"Failed to register image: {e}")
        payload = {}
        if text:
            payload["text"] = text
        if images:
            widgets = [{"image": {"imageUrl": url}} for url in images]
            payload.setdefault("cards", []).append({"sections": [{"widgets": widgets}]})
        if not payload:
            payload["text"] = ""

        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload) as resp:
                if resp.status != 200:
                    try:
                        error_text = await resp.text()
                    except Exception:
                        error_text = resp.status
                    logger.error(
                        f"Failed to send Google Chat message: {error_text}"
                    )

    async def send(self, message: MessageChain):
        await self._send_chain(self.session_id, message)
        await super().send(message)
