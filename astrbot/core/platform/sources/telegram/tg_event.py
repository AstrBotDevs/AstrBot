from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata, MessageType
from astrbot.api.message_components import Plain, Image, Reply, At, File, Record
from telegram.ext import ExtBot
from astrbot.core.utils.io import download_file


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
        message_thread_id = None
        if "#" in user_name:
            # it's a supergroup chat with message_thread_id
            user_name, message_thread_id = user_name.split("#")
        for i in message.chain:
            payload = {
                "chat_id": user_name,
            }
            if has_reply:
                payload["reply_to_message_id"] = reply_message_id
            if message_thread_id:
                payload["reply_to_message_id"] = message_thread_id

            if isinstance(i, Plain):
                if at_user_id and not at_flag:
                    i.text = f"@{at_user_id} " + i.text
                    at_flag = True
                await client.send_message(text=i.text, **payload)
            elif isinstance(i, Image):
                image_path = await i.convert_to_file_path()
                await client.send_photo(photo=image_path, **payload)
            elif isinstance(i, File):
                if i.file.startswith("https://"):
                    path = "data/temp/" + i.name
                    await download_file(i.file, path)
                    i.file = path

                await client.send_document(document=i.file, filename=i.name, **payload)
            elif isinstance(i, Record):
                path = await i.convert_to_file_path()
                await client.send_voice(voice=path, **payload)

    async def send(self, message: MessageChain):
        if self.get_message_type() == MessageType.GROUP_MESSAGE:
            await self.send_with_client(self.client, message, self.message_obj.group_id)
        else:
            await self.send_with_client(self.client, message, self.get_sender_id())
        await super().send(message)
