from astrbot.core.lang import t
import asyncio
import os
import uuid
from typing import cast

import whisper

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_file
from astrbot.core.utils.tencent_record_helper import tencent_silk_to_wav

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter


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
        self.set_model(provider_config["model"])
        self.model = None

    async def initialize(self) -> None:
        loop = asyncio.get_event_loop()
        logger.info(t("msg-27fda50a"))
        self.model = await loop.run_in_executor(
            None,
            whisper.load_model,
            self.model_name,
        )
        logger.info(t("msg-4e70f563"))

    async def _is_silk_file(self, file_path) -> bool:
        silk_header = b"SILK"
        with open(file_path, "rb") as f:
            file_header = f.read(8)

        if silk_header in file_header:
            return True
        return False

    async def get_text(self, audio_url: str) -> str:
        loop = asyncio.get_event_loop()

        is_tencent = False

        if audio_url.startswith("http"):
            if "multimedia.nt.qq.com.cn" in audio_url:
                is_tencent = True

            temp_dir = get_astrbot_temp_path()
            path = os.path.join(
                temp_dir,
                f"whisper_selfhost_{uuid.uuid4().hex[:8]}.input",
            )
            await download_file(audio_url, path)
            audio_url = path

        if not os.path.exists(audio_url):
            raise FileNotFoundError(t("msg-28cbbf07", audio_url=audio_url))

        if audio_url.endswith(".amr") or audio_url.endswith(".silk") or is_tencent:
            is_silk = await self._is_silk_file(audio_url)
            if is_silk:
                logger.info(t("msg-d98780e5"))
                temp_dir = get_astrbot_temp_path()
                output_path = os.path.join(
                    temp_dir,
                    f"whisper_selfhost_{uuid.uuid4().hex[:8]}.wav",
                )
                await tencent_silk_to_wav(audio_url, output_path)
                audio_url = output_path

        if not self.model:
            raise RuntimeError(t("msg-e3e1215c"))

        result = await loop.run_in_executor(None, self.model.transcribe, audio_url)
        return cast(str, result["text"])
