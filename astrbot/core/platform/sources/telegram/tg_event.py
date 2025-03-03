from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata, MessageType
from astrbot.api.message_components import Plain, Image, Reply, At, File, Record
from telegram.ext import ExtBot


class TelegramPlatformEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        client: ExtBot,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client

    @staticmethod
    async def send_with_client(client: ExtBot, message: MessageChain, user_name: str):
        image_path = None

        has_reply = False
        reply_message_id = None
        at_user_id = None
        for i in message.chain:
            if isinstance(i, Reply):
                has_reply = True
                reply_message_id = i.id
            if isinstance(i, At):
                at_user_id = i.name

        at_flag = False
        for i in message.chain:
            payload = {
                "chat_id": user_name,
            }
            if has_reply:
                payload["reply_to_message_id"] = reply_message_id

            if isinstance(i, Plain):
                if at_user_id and not at_flag:
                    i.text = f"@{at_user_id} " + i.text
                    at_flag = True
                await client.send_message(text=i.text, **payload)
            elif isinstance(i, Image):
                if i.path:
                    image_path = i.path
                else:
                    image_path = i.file

                if image_path.startswith("base64://"):
                    import base64

                    base64_data = image_path[9:]
                    image_bytes = base64.b64decode(base64_data)
                    await client.send_photo(photo=image_bytes, **payload)
                else:
                    await client.send_photo(photo=image_path, **payload)
            elif isinstance(i, File):
                await client.send_document(document=i.file, filename=i.name, **payload)
            elif isinstance(i, Record):
                await client.send_voice(voice=i.file, **payload)

    async def send(self, message: MessageChain):
        if self.get_message_type() == MessageType.GROUP_MESSAGE:
            await self.send_with_client(self.client, message, self.message_obj.group_id)
        else:
            await self.send_with_client(self.client, message, self.get_sender_id())
        await super().send(message)
