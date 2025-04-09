import uuid
import aiohttp
import urllib.parse
from ..provider import TTSProvider
from ..entities import ProviderType
from ..register import register_provider_adapter


@register_provider_adapter(
    "gsvi_tts_api", "GSVI TTS API", provider_type=ProviderType.TEXT_TO_SPEECH
)
class ProviderGSVITTS(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_base = provider_config.get("api_base", "http://127.0.0.1:5000")
        if self.api_base.endswith("/"):
            self.api_base = self.api_base[:-1]
        self.character = provider_config.get("character")
        self.emotion = provider_config.get("emotion")

    async def get_audio(self, text: str) -> str:
        path = f"data/temp/gsvi_tts_{uuid.uuid4()}.wav"
        params = {"text": text}

        if self.character:
            params["character"] = self.character
        if self.emotion:
            params["emotion"] = self.emotion

        query_parts = []
        for key, value in params.items():
            encoded_value = urllib.parse.quote(str(value))
            query_parts.append(f"{key}={encoded_value}")

        url = f"{self.api_base}/tts?{'&'.join(query_parts)}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    with open(path, "wb") as f:
                        f.write(await response.read())
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"GSVI TTS API 请求失败，状态码: {response.status}，错误: {error_text}"
                    )

        return path
