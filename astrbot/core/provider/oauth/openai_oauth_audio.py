import asyncio

from .openai_oauth_transcription import OpenAIOAuthTranscriptionClient


class OpenAIOAuthAudioMixin:
    """Translate audio attachments before constructing text-model requests."""

    async def _prepare_chat_payload(self, prompt, *args, **kwargs):
        tool_choice = kwargs.pop("_oauth_tool_choice", None)
        audio_urls = kwargs.get("audio_urls") or (args[1] if len(args) > 1 else None)
        if prompt is None and (audio_urls or kwargs.get("extra_user_content_parts")):
            prompt = ""
        prepared = await super()._prepare_chat_payload(prompt, *args, **kwargs)
        if tool_choice is not None and tool_choice != "auto":
            prepared[0]["tool_choice"] = tool_choice
        return prepared

    async def _resolve_audio_part(self, audio_url: str) -> dict:
        if self.provider_config.get("oauth_audio_transcription") is not True:
            raise ValueError(
                "Codex 文本模型不能直接接收音频。请配置 AstrBot STT，"
                "或在账户支持转录时启用 oauth_audio_transcription。"
            )
        transcript = await self.transcribe_audio(
            audio_url,
            model=self.provider_config.get("oauth_transcription_model")
            or "gpt-4o-transcribe",
        )
        return {"type": "text", "text": transcript}

    async def transcribe_audio(
        self,
        audio_url: str,
        model: str = "gpt-4o-transcribe",
        language: str | None = None,
        prompt: str | None = None,
    ) -> str:
        """Transcribe one audio reference using the existing OAuth account.

        This opt-in plugin API requires separate transcription entitlement.
        """
        if getattr(self, "_oauth_media_closed", False):
            raise RuntimeError("OAuth media provider is closed")
        if not hasattr(self, "_oauth_transcription_client"):
            self._oauth_transcription_client = OpenAIOAuthTranscriptionClient(self)
        return await self._oauth_transcription_client.transcribe_audio(
            audio_url, model=model, language=language, prompt=prompt
        )

    async def create_realtime_session(
        self,
        sdp_offer: str,
        *,
        model: str = "gpt-live-1-codex",
        voice: str = "cove",
        instructions: str = "",
    ):
        """Broker a plugin WebRTC offer and own its realtime control session."""
        from .openai_oauth_realtime import OpenAIOAuthRealtimeClient

        if getattr(self, "_oauth_media_closed", False):
            raise RuntimeError("OAuth media provider is closed")
        if not hasattr(self, "_oauth_realtime_client"):
            self._oauth_realtime_client = OpenAIOAuthRealtimeClient(self)
        return await self._oauth_realtime_client.create_session(
            sdp_offer, model=model, voice=voice, instructions=instructions
        )

    async def terminate(self) -> None:
        """Close media work before terminating the inherited chat client."""
        self._oauth_media_closed = True
        try:
            await asyncio.gather(
                *(
                    client.aclose()
                    for client in list(getattr(self, "_oauth_stream_clients", ()))
                )
            )
            await asyncio.gather(
                *(
                    client.close()
                    for name in (
                        "_oauth_transcription_client",
                        "_oauth_realtime_client",
                    )
                    if (client := getattr(self, name, None)) is not None
                )
            )
        finally:
            await super().terminate()
