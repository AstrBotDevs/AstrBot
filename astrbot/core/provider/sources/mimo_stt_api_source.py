import asyncio
from collections.abc import Mapping

from astrbot import logger
from astrbot.core.utils.error_redaction import safe_error

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter
from .mimo_api_common import (
    DEFAULT_MIMO_API_BASE,
    DEFAULT_MIMO_STT_MODEL,
    DEFAULT_MIMO_STT_SYSTEM_PROMPT,
    DEFAULT_MIMO_STT_USER_PROMPT,
    MiMoAPIError,
    build_api_url,
    build_headers,
    cleanup_files,
    create_http_client,
    normalize_timeout,
    prepare_audio_input,
)


@register_provider_adapter(
    "mimo_stt_api",
    "MiMo STT API",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderMiMoSTTAPI(STTProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key = provider_config.get("api_key", "")
        self.api_base = provider_config.get("api_base", DEFAULT_MIMO_API_BASE)
        self.timeout = normalize_timeout(provider_config.get("timeout", 20))
        self.set_model(provider_config.get("model", DEFAULT_MIMO_STT_MODEL))
        self.client = create_http_client(self.timeout, provider_config)

    def _is_asr_model(self) -> bool:
        return "asr" in (self.model_name or "").lower()

    def _build_messages(self, audio_data_url: str) -> list[dict]:
        audio_content = {
            "type": "input_audio",
            "input_audio": {
                "data": audio_data_url,
            },
        }
        if self._is_asr_model():
            # Dedicated ASR models (speech-recognition docs) take bare audio.
            return [
                {
                    "role": "user",
                    "content": [audio_content],
                },
            ]
        # Multimodal models such as mimo-v2.5 (audio-understanding docs)
        # require a text instruction alongside the audio, otherwise the API
        # rejects the request.
        return [
            {
                "role": "system",
                "content": DEFAULT_MIMO_STT_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    audio_content,
                    {
                        "type": "text",
                        "text": DEFAULT_MIMO_STT_USER_PROMPT,
                    },
                ],
            },
        ]

    async def get_text(self, audio_url: str) -> str:
        audio_data_url, cleanup_paths = await prepare_audio_input(audio_url)
        payload = {
            "model": self.model_name,
            "messages": self._build_messages(audio_data_url),
            "max_completion_tokens": 1024,
        }

        try:
            response = await self.client.post(
                build_api_url(self.api_base),
                headers=build_headers(self.chosen_api_key),
                json=payload,
            )
            try:
                response.raise_for_status()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("MiMo STT request failed: %s", safe_error("", exc))
                raise MiMoAPIError("MiMo STT API request failed.") from exc

            try:
                data = response.json()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "MiMo STT returned invalid JSON: %s",
                    safe_error("", exc),
                )
                raise MiMoAPIError(
                    "MiMo STT API returned an invalid response."
                ) from exc

            if not isinstance(data, Mapping):
                logger.warning("MiMo STT returned an invalid response shape.")
                raise MiMoAPIError("MiMo STT API returned an invalid response.")

            choices = data.get("choices") or []
            if not isinstance(choices, list):
                logger.warning("MiMo STT returned an invalid response shape.")
                raise MiMoAPIError("MiMo STT API returned an invalid response.")

            first_choice = choices[0] if choices else {}
            if not isinstance(first_choice, Mapping):
                logger.warning("MiMo STT returned an invalid response shape.")
                raise MiMoAPIError("MiMo STT API returned an invalid response.")

            message = first_choice.get("message") or {}
            if not isinstance(message, Mapping):
                logger.warning("MiMo STT returned an invalid response shape.")
                raise MiMoAPIError("MiMo STT API returned an invalid response.")

            content = message.get("content") or message.get("reasoning_content") or ""
            if not isinstance(content, str) or not content.strip():
                raise MiMoAPIError("MiMo STT API returned empty transcription")
            return content.strip()
        except asyncio.CancelledError:
            raise
        except MiMoAPIError:
            raise
        except Exception as exc:
            logger.error("MiMo STT failed: %s", safe_error("", exc))
            raise MiMoAPIError("MiMo STT API request failed.") from exc
        finally:
            cleanup_files(cleanup_paths)

    async def terminate(self):
        if self.client:
            await self.client.aclose()
