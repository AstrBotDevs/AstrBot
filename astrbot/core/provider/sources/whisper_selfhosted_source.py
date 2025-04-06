import uuid
import os
import asyncio
import whisper
from ..provider import STTProvider
from ..entities import ProviderType
from astrbot.core.utils.io import download_file
from ..register import register_provider_adapter
from astrbot.core import logger
from astrbot.core.utils.tencent_record_helper import tencent_silk_to_wav


@register_provider_adapter(
    "openai_whisper_selfhost",
    "OpenAI Whisper 模型部署",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderOpenAIWhisperSelfHost(STTProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.set_model(provider_config.get("model", None))
        self.model = None

    async def initialize(self):
        loop = asyncio.get_event_loop()
        logger.info("下载或者加载 Whisper 模型中，这可能需要一些时间 ...")
        self.model = await loop.run_in_executor(
            None, whisper.load_model, self.model_name
        )
        logger.info("Whisper 模型加载完成。")

    async def _is_silk_file(self, file_path):
        silk_header = b"SILK"
        with open(file_path, "rb") as f:
            file_header = f.read(8)

        if silk_header in file_header:
            return True
        else:
            return False

    async def get_text(self, audio_url: str) -> str:
        loop = asyncio.get_event_loop()

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

        result = await loop.run_in_executor(None, self.model.transcribe, audio_url)
        return result["text"]
