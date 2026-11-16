"""Text-to-speech tools for the built-in agent runtime."""

from pydantic import Field
from pydantic.dataclasses import dataclass

import astrbot.core.message.components as Comp
from astrbot.core import file_token_service, logger
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_runtime.context import AstrAgentContext
from astrbot.core.astr_agent_runtime.tools.registry import builtin_tool
from astrbot.core.message.message_event_result import MessageChain


@builtin_tool
@dataclass
class SendVoiceTool(FunctionTool[AstrAgentContext]):
    """Synthesize text with the session TTS provider and deliver it as voice."""

    name: str = "send_voice"
    description: str = (
        "Convert text to speech with the session's TTS provider and send it as a "
        "voice message. Use this when the user asks for a voice reply, or when "
        "speaking suits the moment better than text. Pass only the text that should "
        "be spoken, without Markdown or code. The voice is sent immediately, so do "
        "not repeat the spoken text in your final reply unless the user needs it."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to speak. Keep it natural and free of Markdown or code.",
                },
                "keep_text": {
                    "type": "boolean",
                    "description": "Also send the text as a plain message. Defaults to true.",
                    "default": True,
                },
            },
            "required": ["text"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs,
    ) -> ToolExecResult:
        """Synthesize and send one voice message.

        Args:
            context: Current agent execution context.
            **kwargs: `text` to speak and optional `keep_text`.

        Returns:
            A status string for the model, or an `error:` string on failure.
        """
        text = str(kwargs.get("text") or "").strip()
        if not text:
            return "error: text is required."

        event = context.context.event
        umo = event.unified_msg_origin
        plugin_context = context.context.context
        config = plugin_context.get_config(umo=umo)
        settings = config.get("provider_tts_settings", {}) or {}

        try:
            provider = await plugin_context.get_using_tts_provider_async(umo)
        except Exception as exc:
            logger.error("Voice tool failed to resolve TTS provider: %s", exc)
            return f"error: failed to resolve TTS provider: {exc}"
        if provider is None:
            return "error: no TTS provider is configured for this session."

        try:
            audio_path = await provider.get_audio(text)
        except Exception as exc:
            logger.error("Voice tool failed to synthesize speech: %s", exc)
            return f"error: failed to synthesize speech: {exc}"

        if not audio_path:
            return "error: TTS provider returned no audio."

        keep_text = bool(kwargs.get("keep_text", True))
        try:
            url = None
            callback_api_base = str(config.get("callback_api_base") or "")
            if settings.get("use_file_service") and callback_api_base:
                token = await file_token_service.register_file(audio_path)
                url = f"{callback_api_base}/api/file/{token}"
            record = Comp.Record(
                file=url or audio_path,
                url=url or audio_path,
                text=text,
            )
            # Send components separately: mixed text/record chains are not
            # supported by every platform adapter.
            if keep_text:
                await event.send(MessageChain(chain=[Comp.Plain(text)]))
            await event.send(MessageChain(chain=[record]))
        except Exception as exc:
            logger.error("Voice tool failed to send speech: %s", exc)
            return f"error: failed to send voice message: {exc}"

        return f"Voice message sent to the user ({len(text)} characters)."
