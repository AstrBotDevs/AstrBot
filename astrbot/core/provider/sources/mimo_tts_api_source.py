import asyncio
import base64
import binascii
import uuid
from collections.abc import Mapping
from pathlib import Path

from astrbot import logger
from astrbot.core.utils.error_redaction import safe_error

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
        self.provider_config = provider_config
        self.timeout = normalize_timeout(provider_config.get("timeout", 20))
        self.voice = provider_config.get("mimo-tts-voice", DEFAULT_MIMO_TTS_VOICE)
        self.audio_format = provider_config.get("mimo-tts-format", "wav")
        self.style_prompt = provider_config.get("mimo-tts-style-prompt", "")
        self.dialect = provider_config.get("mimo-tts-dialect", "")
        self.seed_text = provider_config.get(
            "mimo-tts-seed-text", DEFAULT_MIMO_TTS_SEED_TEXT
        )
        self.set_model(provider_config.get("model", DEFAULT_MIMO_TTS_MODEL))
        self.client = create_http_client(self.timeout, provider_config)

    def _build_user_prompt(self) -> str | None:
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
            return "<style>唱歌</style>"

        return f"<style>{style_content}</style>"

    def _build_assistant_content(self, text: str) -> str:
        return f"{self._build_style_prefix()}{text}"

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

        audio_params = {"format": self.audio_format}
        # voice design 模型不支持 audio.voice 参数
        if "voicedesign" not in self.model_name:
            audio_params["voice"] = self.voice

        return {
            "model": self.model_name,
            "messages": messages,
            "audio": audio_params,
        }

    async def get_audio(self, text: str) -> str:
        output_path: Path | None = None
        completed = False
        try:
            response = await self.client.post(
                build_api_url(self.api_base),
                headers=build_headers(self.chosen_api_key),
                json=self._build_payload(text),
            )

            try:
                response.raise_for_status()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("MiMo TTS request failed: %s", safe_error("", exc))
                raise MiMoAPIError("MiMo TTS API request failed.") from exc

            try:
                data = response.json()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "MiMo TTS returned invalid JSON: %s",
                    safe_error("", exc),
                )
                raise MiMoAPIError(
                    "MiMo TTS API returned an invalid response."
                ) from exc

            if not isinstance(data, Mapping):
                logger.warning("MiMo TTS returned an invalid response shape.")
                raise MiMoAPIError("MiMo TTS API returned an invalid response.")

            choices = data.get("choices") or []
            if not isinstance(choices, list):
                logger.warning("MiMo TTS returned an invalid response shape.")
                raise MiMoAPIError("MiMo TTS API returned an invalid response.")

            first_choice = choices[0] if choices else {}
            if not isinstance(first_choice, Mapping):
                logger.warning("MiMo TTS returned an invalid response shape.")
                raise MiMoAPIError("MiMo TTS API returned an invalid response.")

            message = first_choice.get("message") or {}
            if not isinstance(message, Mapping):
                logger.warning("MiMo TTS returned an invalid response shape.")
                raise MiMoAPIError("MiMo TTS API returned an invalid response.")

            audio = message.get("audio") or {}
            if not isinstance(audio, Mapping):
                logger.warning("MiMo TTS returned an invalid response shape.")
                raise MiMoAPIError("MiMo TTS API returned an invalid response.")

            audio_data = audio.get("data")
            if not isinstance(audio_data, str) or not audio_data.strip():
                raise MiMoAPIError("MiMo TTS API returned no audio payload.")

            try:
                audio_bytes = base64.b64decode(audio_data, validate=True)
            except (binascii.Error, ValueError) as exc:
                logger.warning(
                    "MiMo TTS returned invalid audio data: %s",
                    safe_error("", exc),
                )
                raise MiMoAPIError(
                    "MiMo TTS API returned an invalid audio payload."
                ) from exc

            if not audio_bytes:
                raise MiMoAPIError("MiMo TTS API returned an invalid audio payload.")

            output_path = (
                get_temp_dir() / f"mimo_tts_api_{uuid.uuid4()}.{self.audio_format}"
            )
            output_path.write_bytes(audio_bytes)
            completed = True
            return str(output_path)
        except asyncio.CancelledError:
            raise
        except MiMoAPIError:
            raise
        except Exception as exc:
            logger.error("MiMo TTS failed: %s", safe_error("", exc))
            raise MiMoAPIError("MiMo TTS API request failed.") from exc
        finally:
            if output_path is not None and not completed:
                try:
                    output_path.unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning(
                        "Failed to remove incomplete MiMo TTS audio: %s",
                        safe_error("", exc),
                    )

    async def terminate(self):
        if self.client:
            await self.client.aclose()
