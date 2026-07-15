import asyncio
import base64
import json
import os
import shutil
import uuid
from pathlib import Path, PurePosixPath

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import File, Image, Json, Plain, Record
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.media_utils import (
    MEDIA_MIME_EXTENSIONS,
    detect_image_mime_type_async,
)

from .webchat_queue_mgr import webchat_queue_mgr

attachments_dir = os.path.join(get_astrbot_data_path(), "attachments")


class WebChatMessageEvent(AstrMessageEvent):
    def __init__(self, message_str, message_obj, platform_meta, session_id) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        os.makedirs(attachments_dir, exist_ok=True)

    @staticmethod
    async def _send(
        message_id: str,
        message: MessageChain | None,
        session_id: str,
        streaming: bool = False,
        emit_complete: bool = False,
    ) -> str | None:
        request_id = str(message_id)
        if not message:
            await webchat_queue_mgr.put_back_queue(
                request_id,
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
                accepted = await webchat_queue_mgr.put_back_queue(
                    request_id,
                    {
                        "type": "plain",
                        "data": data,
                        "streaming": streaming,
                        "chain_type": message.type,
                        "message_id": message_id,
                    },
                )
                if not accepted:
                    return None
            elif isinstance(comp, Json):
                accepted = await webchat_queue_mgr.put_back_queue(
                    request_id,
                    {
                        "type": "plain",
                        "data": json.dumps(comp.data, ensure_ascii=False),
                        "streaming": streaming,
                        "chain_type": message.type,
                        "message_id": message_id,
                    },
                )
                if not accepted:
                    return None
            elif isinstance(comp, Image):
                # save image to local
                image_base64 = await comp.convert_to_base64()
                image_bytes = base64.b64decode(image_base64)
                mime_type = await detect_image_mime_type_async(
                    image_bytes,
                    default_mime_type=None,
                )
                suffix = MEDIA_MIME_EXTENSIONS.get(mime_type or "", ".jpg")
                filename = f"{str(uuid.uuid4())}{suffix}"
                path = os.path.join(attachments_dir, filename)
                await asyncio.to_thread(Path(path).write_bytes, image_bytes)
                data = f"[IMAGE]{filename}"
                accepted = await webchat_queue_mgr.put_back_queue(
                    request_id,
                    {
                        "type": "image",
                        "data": data,
                        "streaming": streaming,
                        "message_id": message_id,
                    },
                )
                if not accepted:
                    return None
            elif isinstance(comp, Record):
                # save record to local
                filename = f"{str(uuid.uuid4())}.wav"
                path = os.path.join(attachments_dir, filename)
                record_base64 = await comp.convert_to_base64()
                record_bytes = base64.b64decode(record_base64)
                await asyncio.to_thread(Path(path).write_bytes, record_bytes)
                data = f"[RECORD]{filename}"
                accepted = await webchat_queue_mgr.put_back_queue(
                    request_id,
                    {
                        "type": "record",
                        "data": data,
                        "streaming": streaming,
                        "message_id": message_id,
                    },
                )
                if not accepted:
                    return None
            elif isinstance(comp, File):
                # save file to local
                file_path = await comp.get_file()
                raw_original_name = comp.name or os.path.basename(file_path)
                original_name = (
                    PurePosixPath(str(raw_original_name).replace("\\", "/"))
                    .name.replace("\x00", "")
                    .strip()
                )
                if original_name in {"", ".", ".."}:
                    original_name = os.path.basename(file_path) or "file"
                ext = os.path.splitext(original_name)[1] or ""
                filename = f"{uuid.uuid4()!s}{ext}"
                dest_path = os.path.join(attachments_dir, filename)
                shutil.copy2(file_path, dest_path)
                data = f"[FILE]{filename}|{original_name}"
                accepted = await webchat_queue_mgr.put_back_queue(
                    request_id,
                    {
                        "type": "file",
                        "data": data,
                        "streaming": streaming,
                        "message_id": message_id,
                    },
                )
                if not accepted:
                    return None
            else:
                logger.debug(f"webchat 忽略: {comp.type}")

        if emit_complete:
            await webchat_queue_mgr.put_back_queue(
                request_id,
                {
                    "type": "complete",
                    "data": data,
                    "streaming": streaming,
                    "chain_type": message.type,
                    "message_id": message_id,
                },
            )

        return data

    async def send(self, message: MessageChain | None) -> None:
        message_id = self.message_obj.message_id
        await WebChatMessageEvent._send(message_id, message, session_id=self.session_id)
        await super().send(MessageChain([]))

    async def send_streaming(self, generator, use_fallback: bool = False) -> None:
        final_data = ""
        reasoning_content = ""
        message_id = self.message_obj.message_id
        request_id = str(message_id)
        async for chain in generator:
            # 处理音频流（Live Mode）
            if chain.type == "audio_chunk":
                # 音频流数据，直接发送
                audio_b64 = ""
                text = None

                if chain.chain and isinstance(chain.chain[0], Plain):
                    audio_b64 = chain.chain[0].text

                if len(chain.chain) > 1 and isinstance(chain.chain[1], Json):
                    text = chain.chain[1].data.get("text")

                payload = {
                    "type": "audio_chunk",
                    "data": audio_b64,
                    "streaming": True,
                    "message_id": message_id,
                }
                if text:
                    payload["text"] = text

                accepted = await webchat_queue_mgr.put_back_queue(request_id, payload)
                if not accepted:
                    return
                continue

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

        await webchat_queue_mgr.put_back_queue(
            request_id,
            {
                "type": "complete",  # complete means we return the final result
                "data": final_data,
                "reasoning": reasoning_content,
                "streaming": True,
                "message_id": message_id,
            },
        )
        await super().send_streaming(generator, use_fallback)
