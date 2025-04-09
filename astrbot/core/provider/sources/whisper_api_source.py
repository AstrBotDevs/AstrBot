import uuid
import os
from openai import AsyncOpenAI, NOT_GIVEN
from ..provider import STTProvider
from ..entities import ProviderType
from astrbot.core.utils.io import download_file
from ..register import register_provider_adapter
from astrbot.core import logger
from astrbot.core.utils.tencent_record_helper import tencent_silk_to_wav


@register_provider_adapter(
    "openai_whisper_api",
    "OpenAI Whisper API",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderOpenAIWhisperAPI(STTProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key = provider_config.get("api_key", "")

        self.client = AsyncOpenAI(
            api_key=self.chosen_api_key,
            base_url=provider_config.get("api_base", None),
            timeout=provider_config.get("timeout", NOT_GIVEN),
        )

        self.set_model(provider_config.get("model", None))

    async def _is_silk_file(self, file_path):
        silk_header = b"SILK"
        with open(file_path, "rb") as f:
            file_header = f.read(8)

        if silk_header in file_header:
            return True
        else:
            return False

    async def get_text(self, audio_url: str) -> str:
        """only supports mp3, mp4, mpeg, m4a, wav, webm"""
        is_tencent = False

        if audio_url.startswith("http"):
            if "multimedia.nt.qq.com.cn" in audio_url:
                is_tencent = True

            name = str(uuid.uuid4())
            path = os.path.join("data/temp", name)
            await download_file(audio_url, path)
            audio_url = path

        if not os.path.exists(audio_url):
            raise FileNotFoundError(f"文件不存在: {audio_url}")

        if audio_url.endswith(".amr") or audio_url.endswith(".silk") or is_tencent:
            is_silk = await self._is_silk_file(audio_url)
            if is_silk:
                logger.info("Converting silk file to wav ...")
                output_path = os.path.join("data/temp", str(uuid.uuid4()) + ".wav")
                await tencent_silk_to_wav(audio_url, output_path)
                audio_url = output_path

        result = await self.client.audio.transcriptions.create(
            model=self.model_name,
            file=open(audio_url, "rb"),
        )
        return result.text
