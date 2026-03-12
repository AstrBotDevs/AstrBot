import os
import uuid

import httpx
from openai import NOT_GIVEN, AsyncOpenAI

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "openai_tts_api",
    "OpenAI TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderOpenAITTSAPI(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key = provider_config.get("api_key", "")
        self.voice = provider_config.get("openai-tts-voice", "alloy")

        timeout = provider_config.get("timeout", NOT_GIVEN)
        if isinstance(timeout, str):
            timeout = int(timeout)

        proxy = provider_config.get("proxy", "")
        http_client = None
        if proxy:
            logger.info(f"[OpenAI TTS] 使用代理: {proxy}")
            http_client = httpx.AsyncClient(proxy=proxy)
        self.client = AsyncOpenAI(
            api_key=self.chosen_api_key,
            base_url=provider_config.get("api_base"),
            timeout=timeout,
            http_client=http_client,
        )

        self.set_model(provider_config.get("model", ""))

    @staticmethod
    def _looks_like_text_payload(audio_bytes: bytes) -> bool:
        sample = audio_bytes[:128].lstrip()
        if not sample:
            return False
        if sample.startswith((b"{", b"[", b"<")):
            return True
        text_like = sum(1 for byte in sample if byte in b"\t\n\r" or 32 <= byte <= 126)
        return text_like / len(sample) > 0.95

    @classmethod
    def _resolve_audio_extension(cls, content_type: str | None, audio_bytes: bytes) -> str:
        normalized = (content_type or "").split(";", 1)[0].strip().lower()
        extension_map = {
            "audio/wav": ".wav",
            "audio/wave": ".wav",
            "audio/x-wav": ".wav",
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/x-mpeg": ".mp3",
            "audio/ogg": ".ogg",
            "audio/opus": ".ogg",
            "audio/flac": ".flac",
            "audio/x-flac": ".flac",
            "audio/aac": ".aac",
            "audio/x-aac": ".aac",
            "audio/webm": ".webm",
        }

        if normalized:
            if not normalized.startswith("audio/"):
                preview = audio_bytes[:200].decode("utf-8", errors="ignore").strip()
                preview = preview or "<empty response>"
                raise RuntimeError(
                    f"[OpenAI TTS] unexpected content-type {normalized!r} from TTS endpoint: {preview[:200]}"
                )
            if normalized in extension_map:
                return extension_map[normalized]

        header = audio_bytes[:16]
        if header.startswith(b"RIFF") and audio_bytes[8:12] == b"WAVE":
            return ".wav"
        if header.startswith(b"ID3") or (
            len(audio_bytes) >= 2
            and audio_bytes[0] == 0xFF
            and (audio_bytes[1] & 0xE0) == 0xE0
        ):
            return ".mp3"
        if header.startswith(b"OggS"):
            return ".ogg"
        if header.startswith(b"fLaC"):
            return ".flac"
        if header.startswith(b"\x1aE\xdf\xa3"):
            return ".webm"
        if header.startswith((b"\xff\xf1", b"\xff\xf9")):
            return ".aac"

        if cls._looks_like_text_payload(audio_bytes):
            preview = audio_bytes[:200].decode("utf-8", errors="ignore").strip()
            preview = preview or "<empty response>"
            raise RuntimeError(
                f"[OpenAI TTS] TTS endpoint returned a non-audio payload: {preview[:200]}"
            )

        return ".wav"

    async def get_audio(self, text: str) -> str:
        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)
        async with self.client.audio.speech.with_streaming_response.create(
            model=self.model_name,
            voice=self.voice,
            response_format="wav",
            input=text,
        ) as response:
            chunks = []
            async for chunk in response.iter_bytes(chunk_size=1024):
                if chunk:
                    chunks.append(chunk)

            if not chunks:
                raise RuntimeError("[OpenAI TTS] empty audio response")

            audio_bytes = b"".join(chunks)
            content_type = None
            if getattr(response, "headers", None):
                content_type = response.headers.get("content-type")

        ext = self._resolve_audio_extension(content_type, audio_bytes)
        path = os.path.join(temp_dir, f"openai_tts_api_{uuid.uuid4()}{ext}")
        with open(path, "wb") as f:
            f.write(audio_bytes)
        return path

    async def terminate(self):
        if self.client:
            await self.client.close()
