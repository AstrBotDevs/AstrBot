import os
import uuid

from openai import NOT_GIVEN, AsyncOpenAI

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.io import download_file
from astrbot.core.utils.tencent_record_helper import (
    convert_to_pcm_wav,
    tencent_silk_to_wav,
)

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter


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
            base_url=provider_config.get("api_base"),
            timeout=provider_config.get("timeout", NOT_GIVEN),
        )

        self.set_model(provider_config["model"])

    async def _get_audio_format(self, file_path):
        # 定义要检测的头部字节
        silk_header = b"SILK"
        amr_header = b"#!AMR"

        try:
            with open(file_path, "rb") as f:
                file_header = f.read(8)
        except FileNotFoundError:
            return None

        if silk_header in file_header:
            return "silk"

        if amr_header in file_header:
            return "amr"
        return None

    async def get_text(self, audio_url: str) -> str:
        """Only supports mp3, mp4, mpeg, m4a, wav, webm"""
        is_tencent = False
        output_path = None

        if audio_url.startswith("http"):
            if "multimedia.nt.qq.com.cn" in audio_url:
                is_tencent = True

            name = str(uuid.uuid4())
            temp_dir = os.path.join(get_astrbot_data_path(), "temp")
            path = os.path.join(temp_dir, name)
            await download_file(audio_url, path)
            audio_url = path

        if not os.path.exists(audio_url):
            raise FileNotFoundError(f"文件不存在: {audio_url}")

        if audio_url.endswith(".amr") or audio_url.endswith(".silk") or is_tencent:
            file_format = await self._get_audio_format(audio_url)

            # 判断是否需要转换
            if file_format in ["silk", "amr"]:
                temp_dir = os.path.join(get_astrbot_data_path(), "temp")
                output_path = os.path.join(temp_dir, str(uuid.uuid4()) + ".wav")

                if file_format == "silk":
                    logger.info(
                        "Converting silk file to wav using tencent_silk_to_wav..."
                    )
                    await tencent_silk_to_wav(audio_url, output_path)
                elif file_format == "amr":
                    logger.info(
                        "Converting amr file to wav using convert_to_pcm_wav..."
                    )
                    await convert_to_pcm_wav(audio_url, output_path)

                audio_url = output_path

        result = await self.client.audio.transcriptions.create(
            model=self.model_name,
            file=("audio.wav", open(audio_url, "rb")),
        )

        # remove temp file
        if output_path and os.path.exists(output_path):
            try:
                os.remove(audio_url)
            except Exception as e:
                logger.error(f"Failed to remove temp file {audio_url}: {e}")
        return result.text
