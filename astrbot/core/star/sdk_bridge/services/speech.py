from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot_sdk.assets import AssetRef
from astrbot_sdk.errors import InvalidRequest, NotFound
from astrbot_sdk.llm import ProviderKind, Transcript

from .assets import AssetStore
from .llm import _resolve_provider

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


class SpeechTranscribeService:
    """Serve the speech.transcribe capability through STT providers."""

    capability_id = "speech.transcribe"

    def __init__(self, context: Context, store: AssetStore) -> None:
        """Initialize the service.

        Args:
            context: AstrBot star context with the provider manager.
            store: Asset store used to resolve audio asset references.
        """
        self._context = context
        self._store = store

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve the transcribe operation."""
        if operation != "transcribe":
            raise NotFound(f"unknown transcribe operation: {operation}")
        audio = payload.get("audio")
        if isinstance(audio, AssetRef):
            audio_url = str(self._store.resolve(audio))
        elif isinstance(audio, str) and audio.startswith(("http://", "https://")):
            audio_url = audio
        else:
            raise InvalidRequest("audio must be an AssetRef or a public URL")

        provider = await _resolve_provider(
            self._context.provider_manager,
            payload,
            default_kind=ProviderKind.SPEECH_TO_TEXT,
        )
        if provider is None:
            raise NotFound("no speech-to-text provider available")
        text = await provider.get_text(audio_url)
        return {"transcript": Transcript(text=text)}


class SpeechSynthesizeService:
    """Serve the speech.synthesize capability through TTS providers."""

    capability_id = "speech.synthesize"

    def __init__(self, context: Context, store: AssetStore) -> None:
        """Initialize the service.

        Args:
            context: AstrBot star context with the provider manager.
            store: Asset store holding synthesized audio.
        """
        self._context = context
        self._store = store

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve the synthesize operation."""
        if operation != "synthesize":
            raise NotFound(f"unknown synthesize operation: {operation}")
        text = payload.get("text")
        if not isinstance(text, str) or not text:
            raise InvalidRequest("text must be a non-empty string")

        provider = await _resolve_provider(
            self._context.provider_manager,
            payload,
            default_kind=ProviderKind.TEXT_TO_SPEECH,
        )
        if provider is None:
            raise NotFound("no text-to-speech provider available")
        path = Path(await provider.get_audio(text))
        media_type = {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
        }.get(path.suffix.lower(), "application/octet-stream")
        asset = self._store.put(
            path.read_bytes(),
            filename=path.name,
            media_type=media_type,
        )
        return {"asset": asset}
