import base64
import json
import os
import shutil
import uuid

import aiofiles

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import File, Image, Json, Plain, Record
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .tui_queue_mgr import tui_queue_mgr

attachments_dir = os.path.join(get_astrbot_data_path(), "attachments")


def _extract_conversation_id(session_id: str) -> str:
    """Extract raw TUI conversation id from event/session id."""
    if session_id.startswith("tui!"):
        parts = session_id.split("!", 2)
        if len(parts) == 3:
            return parts[2]
    return session_id


class TUIMessageEvent(AstrMessageEvent):
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
        conversation_id = _extract_conversation_id(session_id)
        tui_back_queue = tui_queue_mgr.get_or_create_back_queue(
            request_id,
            conversation_id,
        )
        if not message:
            await tui_back_queue.put(
                {
                    "type": "end",
                    "data": "",
                    "streaming": False,
                    "message_id": message_id,
                },
            )
            return

        data = ""
        for comp in message.chain:
            if isinstance(comp, Plain):
                data = comp.text
                await tui_back_queue.put(
                    {
                        "type": "plain",
                        "data": data,
                        "streaming": streaming,
                        "chain_type": message.type,
                        "message_id": message_id,
                    },
                )
            elif isinstance(comp, Json):
                await tui_back_queue.put(
                    {
                        "type": "plain",
                        "data": json.dumps(comp.data, ensure_ascii=False),
                        "streaming": streaming,
                        "chain_type": message.type,
                        "message_id": message_id,
                    },
                )
            elif isinstance(comp, Image):
                filename = f"{uuid.uuid4()!s}.jpg"
                path = os.path.join(attachments_dir, filename)
                image_base64 = await comp.convert_to_base64()
                async with aiofiles.open(path, "wb") as f:
                    await f.write(base64.b64decode(image_base64))
                data = f"[IMAGE]{filename}"
                await tui_back_queue.put(
                    {
                        "type": "image",
                        "data": data,
                        "streaming": streaming,
                        "message_id": message_id,
                    },
                )
            elif isinstance(comp, Record):
                filename = f"{uuid.uuid4()!s}.wav"
                path = os.path.join(attachments_dir, filename)
                record_base64 = await comp.convert_to_base64()
                async with aiofiles.open(path, "wb") as f:
                    await f.write(base64.b64decode(record_base64))
                data = f"[RECORD]{filename}"
                await tui_back_queue.put(
                    {
                        "type": "record",
                        "data": data,
                        "streaming": streaming,
                        "message_id": message_id,
                    },
                )
            elif isinstance(comp, File):
                file_path = await comp.get_file()
                original_name = comp.name or os.path.basename(file_path)
                ext = os.path.splitext(original_name)[1] or ""
                filename = f"{uuid.uuid4()!s}{ext}"
                dest_path = os.path.join(attachments_dir, filename)
                shutil.copy2(file_path, dest_path)
                data = f"[FILE]{filename}"
                await tui_back_queue.put(
                    {
                        "type": "file",
                        "data": data,
                        "streaming": streaming,
                        "message_id": message_id,
                    },
                )
            else:
                logger.debug(f"TUI ignores: {comp.type}")

        if emit_complete:
            await tui_back_queue.put(
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
        await TUIMessageEvent._send(message_id, message, session_id=self.session_id)
        await super().send(MessageChain([]))

    async def send_streaming(self, generator, use_fallback: bool = False) -> None:
        final_data = ""
        reasoning_content = ""
        message_id = self.message_obj.message_id
        request_id = str(message_id)
        conversation_id = _extract_conversation_id(self.session_id)
        tui_back_queue = tui_queue_mgr.get_or_create_back_queue(
            request_id,
            conversation_id,
        )
        async for chain in generator:
            if chain.type == "audio_chunk":
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

                await tui_back_queue.put(payload)
                continue

            r = await TUIMessageEvent._send(
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

        await tui_back_queue.put(
            {
                "type": "complete",
                "data": final_data,
                "reasoning": reasoning_content,
                "streaming": True,
                "message_id": message_id,
            },
        )
        await super().send_streaming(generator, use_fallback)
