import base64
import json
import os
import shutil
import uuid

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import File, Image, Json, Plain, Record
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .webchat_queue_mgr import webchat_queue_mgr

imgs_dir = os.path.join(get_astrbot_data_path(), "webchat", "imgs")


class WebChatMessageEvent(AstrMessageEvent):
    def __init__(self, message_str, message_obj, platform_meta, session_id):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        os.makedirs(imgs_dir, exist_ok=True)

    @staticmethod
    async def _send(
        message_id: str,
        message: MessageChain | None,
        session_id: str,
        streaming: bool = False,
    ) -> str | None:
        cid = session_id.split("!")[-1]
        web_chat_back_queue = webchat_queue_mgr.get_or_create_back_queue(cid)
        if not message:
            await web_chat_back_queue.put(
                {
                    "type": "end",
                    "data": "",
                    "streaming": False,
                    "message_id": message_id,
                },  # end means this request is finished
            )
            return

        data = ""
        for comp in message.chain:
            if isinstance(comp, Plain):
                data = comp.text
                await web_chat_back_queue.put(
                    {
                        "type": "plain",
                        "data": data,
                        "streaming": streaming,
                        "chain_type": message.type,
                        "message_id": message_id,
                    },
                )
            elif isinstance(comp, Json):
                await web_chat_back_queue.put(
                    {
                        "type": "plain",
                        "data": json.dumps(comp.data, ensure_ascii=False),
                        "streaming": streaming,
                        "chain_type": message.type,
                        "message_id": message_id,
                    },
                )
            elif isinstance(comp, Image):
                # save image to local
                filename = f"{str(uuid.uuid4())}.jpg"
                path = os.path.join(imgs_dir, filename)
                image_base64 = await comp.convert_to_base64()
                with open(path, "wb") as f:
                    f.write(base64.b64decode(image_base64))
                data = f"[IMAGE]{filename}"
                await web_chat_back_queue.put(
                    {
                        "type": "image",
                        "data": data,
                        "streaming": streaming,
                        "message_id": message_id,
                    },
                )
            elif isinstance(comp, Record):
                # save record to local
                filename = f"{str(uuid.uuid4())}.wav"
                path = os.path.join(imgs_dir, filename)
                record_base64 = await comp.convert_to_base64()
                with open(path, "wb") as f:
                    f.write(base64.b64decode(record_base64))
                data = f"[RECORD]{filename}"
                await web_chat_back_queue.put(
                    {
                        "type": "record",
                        "data": data,
                        "streaming": streaming,
                        "message_id": message_id,
                    },
                )
            elif isinstance(comp, File):
                # save file to local
                file_path = await comp.get_file()
                original_name = comp.name or os.path.basename(file_path)
                ext = os.path.splitext(original_name)[1] or ""
                filename = f"{uuid.uuid4()!s}{ext}"
                dest_path = os.path.join(imgs_dir, filename)
                shutil.copy2(file_path, dest_path)
                data = f"[FILE]{filename}"
                await web_chat_back_queue.put(
                    {
                        "type": "file",
                        "data": data,
                        "streaming": streaming,
                        "message_id": message_id,
                    },
                )
            else:
                logger.debug(f"webchat 忽略: {comp.type}")

        return data

    async def send(self, message: MessageChain | None):
        message_id = self.message_obj.message_id
        await WebChatMessageEvent._send(message_id, message, session_id=self.session_id)
        await super().send(MessageChain([]))

    async def send_streaming(self, generator, use_fallback: bool = False):
        final_data = ""
        reasoning_content = ""
        cid = self.session_id.split("!")[-1]
        web_chat_back_queue = webchat_queue_mgr.get_or_create_back_queue(cid)
        message_id = self.message_obj.message_id
        async for chain in generator:
            # if chain.type == "break" and final_data:
            #     # 分割符
            #     await web_chat_back_queue.put(
            #         {
            #             "type": "break",  # break means a segment end
            #             "data": final_data,
            #             "streaming": True,
            #         },
            #     )
            #     final_data = ""
            #     continue

            r = await WebChatMessageEvent._send(
                message_id=message_id,
                message=chain,
                session_id=self.session_id,
                streaming=True,
            )
            if not r:
                continue
            if chain.type == "reasoning":
                reasoning_content += chain.get_plain_text()
            else:
                final_data += r

        await web_chat_back_queue.put(
            {
                "type": "complete",  # complete means we return the final result
                "data": final_data,
                "reasoning": reasoning_content,
                "streaming": True,
                "message_id": message_id,
            },
        )
        await super().send_streaming(generator, use_fallback)
