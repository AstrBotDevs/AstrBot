import os
import uuid
import base64
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain, Image
from astrbot.core.utils.io import download_image_by_url
from astrbot.core import web_chat_back_queue

imgs_dir = "data/webchat/imgs"


class WebChatMessageEvent(AstrMessageEvent):
    def __init__(self, message_str, message_obj, platform_meta, session_id):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        os.makedirs(imgs_dir, exist_ok=True)

    @staticmethod
    async def _send(message: MessageChain, session_id: str):
        if not message:
            web_chat_back_queue.put_nowait(None)
            return

        cid = session_id.split("!")[-1]

        for comp in message.chain:
            if isinstance(comp, Plain):
                web_chat_back_queue.put_nowait((comp.text, cid))
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
                web_chat_back_queue.put_nowait((f"[IMAGE]{filename}", cid))
            else:
                logger.debug(f"webchat 忽略: {comp.type}")
        web_chat_back_queue.put_nowait(None)

    async def send(self, message: MessageChain):
        await WebChatMessageEvent._send(message, session_id=self.session_id)
        await super().send(message)
