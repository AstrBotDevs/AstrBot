import base64
import uuid
from pathlib import Path

from astrbot import logger

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter
from .mimo_api_common import (
    DEFAULT_MIMO_API_BASE,
    DEFAULT_MIMO_TTS_MODEL,
    DEFAULT_MIMO_TTS_SEED_TEXT,
    DEFAULT_MIMO_TTS_VOICE,
    MiMoAPIError,
    build_api_url,
    build_headers,
    create_http_client,
    get_temp_dir,
    normalize_timeout,
)


@register_provider_adapter(
    "mimo_tts_api",
    "MiMo TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderMiMoTTSAPI(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key = provider_config.get("api_key", "")
        self.api_base = provider_config.get("api_base", DEFAULT_MIMO_API_BASE)
        self.proxy = provider_config.get("proxy", "")
        self.timeout = normalize_timeout(provider_config.get("timeout", 20))
        self.voice = provider_config.get("mimo-tts-voice", DEFAULT_MIMO_TTS_VOICE)
        self.audio_format = provider_config.get("mimo-tts-format", "wav")
        self.style_prompt = provider_config.get("mimo-tts-style-prompt", "")
        self.dialect = provider_config.get("mimo-tts-dialect", "")
        self.seed_text = provider_config.get(
            "mimo-tts-seed-text", DEFAULT_MIMO_TTS_SEED_TEXT
        )
        self.user_prompt = provider_config.get("mimo-tts-user-prompt", "")
        self.voice_audio_path = provider_config.get("mimo-tts-voice-audio-path", "")
        self.set_model(provider_config.get("model", DEFAULT_MIMO_TTS_MODEL))
        self.client = create_http_client(self.timeout, self.proxy)

    def _is_v2_5(self) -> bool:
        """Check if the current model is a v2.5 series model."""
        return "v2.5" in self.model_name

    def _build_user_prompt(self) -> str | None:
        # For voicedesign models, custom user prompt takes precedence.
        if "voicedesign" in self.model_name and self.user_prompt.strip():
            return self.user_prompt.strip()
        # For other models, use seed_text as fallback.
        seed_text = self.seed_text.strip()
        return seed_text or None

    def _build_style_prefix(self) -> str:
        style_parts: list[str] = []

        if self.style_prompt.strip():
            style_parts.append(self.style_prompt.strip())
        if self.dialect.strip():
            style_parts.append(self.dialect.strip())

        style_content = " ".join(style_parts).strip()
        if not style_content:
            return ""

        # MiMo recommends using only the singing style tag at the very beginning.
        if "唱歌" in style_content:
            # v2.5 uses parentheses; v2 uses <style> tags.
            if self._is_v2_5():
                return "（唱歌）"
            return "<style>唱歌</style>"

        # v2.5 uses parentheses; v2 uses <style> tags.
        if self._is_v2_5():
            return f"（{style_content}）"
        return f"<style>{style_content}</style>"

    def _build_assistant_content(self, text: str) -> str:
        return f"{self._build_style_prefix()}{text}"

    def _read_voice_audio_base64(self) -> str:
        if not self.voice_audio_path.strip():
            return ""
        path = Path(self.voice_audio_path.strip())
        if not path.exists():
            logger.warning("Voice audio file not found: %s", path)
            return ""
        try:
            suffix = path.suffix.lower().lstrip(".")
            mime_map = {"wav": "audio/wav", "mp3": "audio/mpeg", "ogg": "audio/ogg"}
            mime = mime_map.get(suffix, "audio/wav")
            b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
            return f"data:{mime};base64,{b64}"
        except Exception as exc:
            logger.warning("Failed to read voice audio file %s: %s", path, exc)
            return ""

    def _build_payload(self, text: str) -> dict:
        messages: list[dict[str, str]] = []

        user_prompt = self._build_user_prompt()
        if user_prompt:
            messages.append(
                {
                    "role": "user",
                    "content": user_prompt,
                }
            )

        messages.append(
            {
                "role": "assistant",
                "content": self._build_assistant_content(text),
            }
        )

        audio_params: dict[str, str] = {"format": self.audio_format}
        if "voicedesign" not in self.model_name:
            if "voiceclone" in self.model_name:
                voice_audio_b64 = self._read_voice_audio_base64()
                if voice_audio_b64:
                    audio_params["voice"] = voice_audio_b64
                else:
                    audio_params["voice"] = self.voice
            else:
                audio_params["voice"] = self.voice

        return {
            "model": self.model_name,
            "messages": messages,
            "audio": audio_params,
        }

    async def get_audio(self, text: str) -> str:
        response = await self.client.post(
            build_api_url(self.api_base),
            headers=build_headers(self.chosen_api_key),
            json=self._build_payload(text),
        )

        try:
            response.raise_for_status()
        except Exception as exc:
            error_text = response.text[:1024]
            raise MiMoAPIError(
                f"MiMo TTS API request failed: HTTP {response.status_code}, response: {error_text}"
            ) from exc

        data = response.json()
        choices = data.get("choices") or []
        first_choice = choices[0] if choices else {}
        message = first_choice.get("message", {})
        audio_data = message.get("audio", {}).get("data")
        if not audio_data:
            raise MiMoAPIError(f"MiMo TTS API returned no audio payload: {data}")

        output_path = (
            get_temp_dir() / f"mimo_tts_api_{uuid.uuid4()}.{self.audio_format}"
        )
        output_path.write_bytes(base64.b64decode(audio_data))
        return str(output_path)

    async def terminate(self):
        if self.client:
            await self.client.aclose()
