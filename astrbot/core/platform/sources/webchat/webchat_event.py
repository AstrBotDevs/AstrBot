from pathlib import Path

from astrbot.core.message.components import Json, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.send_result import PlatformSendResult
from astrbot.core.webchat.emitter import emit_webchat_response
from astrbot.core.webchat.queue_manager import WebChatQueueManager


class WebChatMessageEvent(AstrMessageEvent):
    """A WebChat event bound to one runtime-owned response queue manager."""

    requires_empty_completion = True

    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        webchat_queue_manager: WebChatQueueManager,
        attachments_dir: str | Path,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self._webchat_queue_manager = webchat_queue_manager
        self._attachments_dir = Path(attachments_dir)

    async def send(self, message: MessageChain | None) -> PlatformSendResult | None:
        message_id = self.message_obj.message_id
        follow_up_capture = self.get_extra("_follow_up_captured")
        if message is None and isinstance(follow_up_capture, dict):
            await self._webchat_queue_manager.put_back_queue(
                str(message_id),
                {
                    "type": "follow_up_captured",
                    "data": follow_up_capture,
                    "streaming": False,
                    "message_id": message_id,
                },
            )
        await emit_webchat_response(
            self._webchat_queue_manager,
            message_id,
            message,
            attachments_dir=self._attachments_dir,
        )
        return await super().send(message or MessageChain([]))

    async def send_typing(self) -> None:
        """Emit a run-start signal before an independent LLM request."""
        message_id = self.message_obj.message_id
        await self._webchat_queue_manager.put_back_queue(
            str(message_id),
            {
                "type": "run_started",
                "data": {"run_id": str(message_id)},
                "streaming": False,
                "message_id": message_id,
            },
        )

    async def send_streaming(
        self,
        generator,
        use_fallback: bool = False,
    ) -> PlatformSendResult | None:
        final_data = ""
        reasoning_content = ""
        message_id = self.message_obj.message_id
        request_id = str(message_id)
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

                accepted = await self._webchat_queue_manager.put_back_queue(
                    request_id,
                    payload,
                )
                if not accepted:
                    return
                continue

            result = await emit_webchat_response(
                self._webchat_queue_manager,
                message_id,
                chain,
                attachments_dir=self._attachments_dir,
                streaming=True,
            )
            if not result:
                continue
            if chain.type == "reasoning":
                reasoning_content += chain.get_plain_text()
            else:
                final_data += result

        await self._webchat_queue_manager.put_back_queue(
            request_id,
            {
                "type": "complete",
                "data": final_data,
                "reasoning": reasoning_content,
                "streaming": True,
                "message_id": message_id,
            },
        )
        return await super().send_streaming(generator, use_fallback)
