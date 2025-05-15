import os
import uuid
import base64
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain, Image, Record
from astrbot.core.utils.io import download_image_by_url
from astrbot.core import web_chat_back_queue
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

imgs_dir = os.path.join(get_astrbot_data_path(), "webchat", "imgs")


class WebChatMessageEvent(AstrMessageEvent):
    def __init__(self, message_str, message_obj, platform_meta, session_id):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        os.makedirs(imgs_dir, exist_ok=True)

    @staticmethod
    async def _send(message: MessageChain, session_id: str, streaming: bool = False):
        if not message:
            await web_chat_back_queue.put(
                {"type": "end", "data": "", "streaming": False}
            )
            return ""

        cid = session_id.split("!")[-1]
        data = ""
        for comp in message.chain:
            if isinstance(comp, Plain):
                data = comp.text
                await web_chat_back_queue.put(
                    {
                        "type": "plain",
                        "cid": cid,
                        "data": data,
                        "streaming": streaming,
                    }
                )
            elif isinstance(comp, Image):
                # save image to local
                filename = str(uuid.uuid4()) + ".jpg"
                path = os.path.join(imgs_dir, filename)
                if comp.file and comp.file.startswith("file:///"):
                    ph = comp.file[8:]
                    with open(path, "wb") as f:
                        with open(ph, "rb") as f2:
                            f.write(f2.read())
                elif comp.file.startswith("base64://"):
                    base64_str = comp.file[9:]
                    image_data = base64.b64decode(base64_str)
                    with open(path, "wb") as f:
                        f.write(image_data)
                elif comp.file and comp.file.startswith("http"):
                    await download_image_by_url(comp.file, path=path)
                else:
                    with open(path, "wb") as f:
                        with open(comp.file, "rb") as f2:
                            f.write(f2.read())
                data = f"[IMAGE]{filename}"
                await web_chat_back_queue.put(
                    {
                        "type": "image",
                        "cid": cid,
                        "data": data,
                        "streaming": streaming,
                    }
                )
            elif isinstance(comp, Record):
                # save record to local
                filename = str(uuid.uuid4()) + ".wav"
                path = os.path.join(imgs_dir, filename)
                if comp.file and comp.file.startswith("file:///"):
                    ph = comp.file[8:]
                    with open(path, "wb") as f:
                        with open(ph, "rb") as f2:
                            f.write(f2.read())
                elif comp.file and comp.file.startswith("http"):
                    await download_image_by_url(comp.file, path=path)
                else:
                    with open(path, "wb") as f:
                        with open(comp.file, "rb") as f2:
                            f.write(f2.read())
                data = f"[RECORD]{filename}"
                await web_chat_back_queue.put(
                    {
                        "type": "record",
                        "cid": cid,
                        "data": data,
                        "streaming": streaming,
                    }
                )
            else:
                logger.debug(f"webchat 忽略: {comp.type}")

        return data

    async def send(self, message: MessageChain):
        await WebChatMessageEvent._send(message, session_id=self.session_id)
        await web_chat_back_queue.put(
            {
                "type": "end",
                "data": "",
                "streaming": False,
                "cid": self.session_id.split("!")[-1],
            }
        )
        await super().send(message)

    async def send_streaming(self, generator, use_fallback: bool = False):
        final_data = ""
        async for chain in generator:
            final_data += await WebChatMessageEvent._send(
                chain, session_id=self.session_id, streaming=True
            )

        await web_chat_back_queue.put(
            {
                "type": "end",
                "data": final_data,
                "streaming": True,
                "cid": self.session_id.split("!")[-1],
            }
        )
        await super().send_streaming(generator, use_fallback)
