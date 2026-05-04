import uuid
from pathlib import Path

import aiohttp

from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "gsvi_tts_api",
    "GSVI TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderGSVITTS(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        self.api_base = provider_config.get("api_base", "http://127.0.0.1:8000")
        self.api_base = self.api_base.removesuffix("/")
        self.version = provider_config.get("version", "v4")
        self.character = provider_config.get("character")
        self.prompt_text_lang = provider_config.get("prompt_text_lang", "中文")
        self.emotion = provider_config.get("emotion", "默认")
        self.text_lang = provider_config.get("text_lang", "中文")

    async def get_audio(self, text: str) -> str:
        temp_dir = get_astrbot_temp_path()
        path = Path(temp_dir) / f"gsvi_tts_{uuid.uuid4()}.wav"
        url = f"{self.api_base}/infer_single"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = {
            "dl_url": self.api_base,
            "version": self.version,
            "model_name": self.character,
            "prompt_text_lang": self.prompt_text_lang,
            "emotion": self.emotion,
            "text": text,
            "text_lang": self.text_lang,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as response:
                if response.status == 200:
                    resp_json = await response.json()
                    msg = resp_json.get("msg")
                    audio_url = resp_json.get("audio_url")
                    if not msg or msg != "合成成功":
                        raise Exception(f"GSVI TTS API 合成失败: {msg}")
                    async with session.get(audio_url) as audio_response:
                        if audio_response.status == 200:
                            with open(path, "wb") as f:
                                f.write(await audio_response.read())
                        else:
                            error_text = await audio_response.text()
                            raise Exception(
                                f"GSVI TTS API 下载音频失败，状态码: {audio_response.status}，错误: {error_text}",
                            )
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"GSVI TTS API 请求失败，状态码: {response.status}，错误: {error_text}",
                    )

        return str(path)
