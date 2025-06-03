import os
import dashscope
import uuid
import asyncio
from dashscope.audio.tts_v2 import *
from ..provider import TTSProvider
from ..entities import ProviderType
from ..register import register_provider_adapter
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


@register_provider_adapter(
    "dashscope_tts", "Dashscope TTS API", provider_type=ProviderType.TEXT_TO_SPEECH
)
class ProviderDashscopeTTSAPI(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key: str = provider_config.get("api_key", "")
        self.voice: str = provider_config.get("dashscope_tts_voice", "loongstella")
        self.set_model(provider_config.get("model", None))
        self.timeout_ms = float(provider_config.get("timeout", 20)) * 1000
        dashscope.api_key = self.chosen_api_key

    async def get_audio(self, text: str) -> str:
        temp_dir = os.path.join(get_astrbot_data_path(), "temp")
        path = os.path.join(temp_dir, f"dashscope_tts_{uuid.uuid4()}.wav")
        self.synthesizer = SpeechSynthesizer(
            model=self.get_model(),
            voice=self.voice,
            format=AudioFormat.WAV_24000HZ_MONO_16BIT,
        )
        audio = await asyncio.get_event_loop().run_in_executor(
            None, self.synthesizer.call, text, self.timeout_ms
        )
        with open(path, "wb") as f:
            f.write(audio)
        return path
