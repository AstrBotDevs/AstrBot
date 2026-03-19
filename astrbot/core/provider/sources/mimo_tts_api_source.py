import base64
import uuid
from pathlib import Path

import httpx

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter
from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path


def normalize_timeout(timeout: int | str | None) -> int | None:
    if timeout in (None, ""):
        return None
    if isinstance(timeout, str):
        return int(timeout)
    return timeout


def build_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["api-key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def get_temp_dir() -> Path:
    temp_dir = Path(get_astrbot_temp_path())
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def create_http_client(timeout: int | None, proxy: str) -> httpx.AsyncClient:
    client_kwargs: dict[str, object] = {
        "timeout": timeout,
        "follow_redirects": True,
    }
    if proxy:
        logger.info("[MiMo API] Using proxy: %s", proxy)
        client_kwargs["proxy"] = proxy
    return httpx.AsyncClient(**client_kwargs)


def build_api_url(api_base: str) -> str:
    normalized_api_base = api_base.rstrip("/")
    if normalized_api_base.endswith("/chat/completions"):
        return normalized_api_base
    return normalized_api_base + "/chat/completions"


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
        self.api_base = provider_config.get(
            "api_base",
            "https://api.xiaomimimo.com/v1",
        )
        self.proxy = provider_config.get("proxy", "")
        self.timeout = normalize_timeout(provider_config.get("timeout", 20))
        self.voice = provider_config.get("mimo-tts-voice", "mimo_default")
        self.audio_format = provider_config.get("mimo-tts-format", "wav")
        self.style_prompt = provider_config.get("mimo-tts-style-prompt", "")
        self.dialect = provider_config.get("mimo-tts-dialect", "")
        self.seed_text = provider_config.get(
            "mimo-tts-seed-text",
            "Hello, MiMo, have you had lunch?",
        )
        self.set_model(provider_config.get("model", "mimo-v2-tts"))
        self.client = create_http_client(self.timeout, self.proxy)

    def _build_user_prompt(self) -> str:
        prompt_parts: list[str] = []

        if self.style_prompt.strip():
            prompt_parts.append(self.style_prompt.strip())
        if self.dialect.strip():
            prompt_parts.append(f"Please use {self.dialect.strip()} when speaking.")

        if not prompt_parts:
            return self.seed_text

        if self.seed_text.strip():
            prompt_parts.append(self.seed_text.strip())

        return " ".join(prompt_parts)

    def _build_payload(self, text: str) -> dict:
        return {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": self._build_user_prompt(),
                },
                {
                    "role": "assistant",
                    "content": text,
                },
            ],
            "audio": {
                "format": self.audio_format,
                "voice": self.voice,
            },
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
            raise Exception(
                f"MiMo TTS API request failed: HTTP {response.status_code}, response: {error_text}"
            ) from exc

        data = response.json()
        choices = data.get("choices") or []
        first_choice = choices[0] if choices else {}
        message = first_choice.get("message", {})
        audio_data = message.get("audio", {}).get("data")
        if not audio_data:
            raise Exception(f"MiMo TTS API returned no audio payload: {data}")

        output_path = (
            get_temp_dir() / f"mimo_tts_api_{uuid.uuid4()}.{self.audio_format}"
        )
        output_path.write_bytes(base64.b64decode(audio_data))
        return str(output_path)

    async def terminate(self):
        if self.client:
            await self.client.aclose()
