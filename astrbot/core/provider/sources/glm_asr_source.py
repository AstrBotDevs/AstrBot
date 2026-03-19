import base64
import os
import uuid

import aiohttp

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_file
from astrbot.core.utils.tencent_record_helper import (
    convert_to_pcm_wav,
    tencent_silk_to_wav,
)

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "glm_asr",
    "GLM-ASR API",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderGLMASR(STTProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key: str = provider_config.get("api_key", "")
        self.model_name: str = provider_config.get("model", "glm-asr-2512")
        self.timeout: int = provider_config.get("timeout", 120)
        self.api_base: str = "https://open.bigmodel.cn/api/paas/v4/audio/transcriptions"

    def _get_audio_format(self, file_path: str) -> str | None:
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
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        output_path = None

        if audio_url.startswith("http"):
            temp_dir = get_astrbot_temp_path()
            local_path = os.path.join(temp_dir, f"glm_asr_{uuid.uuid4().hex[:8]}.input")
            await download_file(audio_url, local_path)
            audio_url = local_path

        if not os.path.exists(audio_url):
            raise FileNotFoundError(f"Audio file not found: {audio_url}")

        file_format = self._get_audio_format(audio_url)

        if file_format in ["silk", "amr"]:
            temp_dir = get_astrbot_temp_path()
            output_path = os.path.join(temp_dir, f"glm_asr_{uuid.uuid4().hex[:8]}.wav")

            logger.info(f"Converting {file_format} file to wav for GLM-ASR...")
            if file_format == "silk":
                await tencent_silk_to_wav(audio_url, output_path)
            elif file_format == "amr":
                await convert_to_pcm_wav(audio_url, output_path)

            audio_url = output_path

        with open(audio_url, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode("utf-8")

        payload = {
            "model": self.model_name,
            "file_base64": audio_base64,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_base,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"GLM-ASR API error: {response.status}, body: {error_text}")
                        response.raise_for_status()

                    result = await response.json()

                    if result.get("error"):
                        error_msg = result["error"].get("message", "Unknown error")
                        raise Exception(f"GLM-ASR API error: {error_msg}")

                    text = result.get("text", "")
                    return text

        except aiohttp.ClientError as e:
            raise Exception(f"GLM-ASR API request failed: {e!s}")
        finally:
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception as e:
                    logger.warning(f"Failed to remove temp file {output_path}: {e}")
            if audio_url.endswith(".input") and os.path.exists(audio_url):
                try:
                    os.remove(audio_url)
                except Exception as e:
                    logger.warning(f"Failed to remove temp file {audio_url}: {e}")

    async def terminate(self):
        pass