from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.provider import STTProvider
from astrbot.core.provider.register import register_provider_adapter

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
        self.proxy = provider_config.get("proxy", "")
        self.timeout = normalize_timeout(provider_config.get("timeout", 20))
        self.system_prompt = provider_config.get(
            "mimo-stt-system-prompt",
            DEFAULT_MIMO_STT_SYSTEM_PROMPT,
        )
        self.user_prompt = provider_config.get(
            "mimo-stt-user-prompt",
            DEFAULT_MIMO_STT_USER_PROMPT,
        )
        self.set_model(provider_config.get("model", DEFAULT_MIMO_STT_MODEL))
        self.client = create_http_client(self.timeout, self.proxy)

    async def get_text(self, audio_url: str) -> str:
        audio_data_url, cleanup_paths = await prepare_audio_input(audio_url)
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": self.system_prompt,
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": audio_data_url,
                            },
                        },
                        {
                            "type": "text",
                            "text": self.user_prompt,
                        },
                    ],
                },
            ],
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
            except Exception as exc:
                error_text = response.text[:1024]
                raise MiMoAPIError(
                    f"MiMo STT API request failed: HTTP {response.status_code}, response: {error_text}"
                ) from exc

            data = response.json()
            choices = data.get("choices") or []
            first_choice = choices[0] if choices else {}
            content = first_choice.get("message", {}).get("content", "")
            if not isinstance(content, str) or not content.strip():
                raise MiMoAPIError(f"MiMo STT API returned empty transcription: {data}")
            return content.strip()
        finally:
            cleanup_files(cleanup_paths)

    async def terminate(self):
        if self.client:
            await self.client.aclose()
