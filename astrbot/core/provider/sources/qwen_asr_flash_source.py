"""Qwen3-ASR-Flash STT Provider.
Author: muchstarlight
This provider uses DashScope's MultiModalConversation API with base64 encoded audio
for speech recognition. Model: qwen3-asr-flash

API documentation: https://help.aliyun.com/zh/model-studio/
"""

import asyncio
import base64
import os
import pathlib

import dashscope
from dashscope import MultiModalConversation

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_file
from astrbot.core.utils.media_utils import convert_audio_to_wav
from astrbot.core.utils.tencent_record_helper import (
    convert_to_pcm_wav,
    tencent_silk_to_wav,
)

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter


# Default API base URL for DashScope
DEFAULT_DASHSCOPE_API_BASE = "https://dashscope.aliyuncs.com/api/v1"


@register_provider_adapter(
    "qwen_asr_flash",
    "Qwen3-ASR-Flash",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderQwenASRFlash(STTProvider):
    """Qwen3-ASR-Flash STT Provider.

    Uses DashScope MultiModalConversation API with base64 encoded audio.
    Supports Chinese and English speech recognition with instant transcription.
    """

    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        self.api_base = provider_config.get(
            "api_base", DEFAULT_DASHSCOPE_API_BASE
        ).rstrip("/")
        self.model = provider_config.get("model", "qwen3-asr-flash")
        self.language = provider_config.get("language", "auto")
        self.enable_itn = provider_config.get("enable_itn", True)
        self.timeout = provider_config.get("timeout", 30)

        self.set_model(self.model)

    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type based on file extension."""
        ext_to_mime = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".mp4": "audio/mp4",
            ".m4a": "audio/m4a",
            ".ogg": "audio/ogg",
            ".opus": "audio/opus",
            ".amr": "audio/amr",
            ".silk": "audio/silk",
            ".aac": "audio/aac",
            ".flac": "audio/flac",
        }
        ext = os.path.splitext(file_path.lower())[1]
        return ext_to_mime.get(ext, "audio/mpeg")

    async def _get_audio_format(self, file_path) -> str | None:
        """Detect audio file format by header bytes."""
        silk_header = b"SILK"
        amr_header = b"#!AMR"

        def _read_header():
            try:
                with open(file_path, "rb") as f:
                    return f.read(8)
            except FileNotFoundError:
                return None

        try:
            file_header = await asyncio.to_thread(_read_header)
        except Exception:
            return None

        if file_header is None:
            return None
        if silk_header in file_header:
            return "silk"
        if amr_header in file_header:
            return "amr"
        return None

    async def _prepare_audio(self, audio_url: str) -> tuple[str, str | None]:
        """Prepare audio file for API upload.

        Downloads URL if needed, converts to WAV format.
        Returns tuple of (audio_path, output_path) where output_path is temp file if converted.
        """
        is_tencent = False
        output_path = None

        # Download from URL if needed
        if audio_url.startswith("http"):
            if "multimedia.nt.qq.com.cn" in audio_url:
                is_tencent = True

            temp_dir = get_astrbot_temp_path()
            path = os.path.join(
                temp_dir,
                f"qwen_asr_{os.urandom(4).hex()}.input",
            )
            await download_file(audio_url, path)
            audio_url = path

        if not os.path.exists(audio_url):
            raise FileNotFoundError(f"File not found: {audio_url}")

        lower_audio_url = audio_url.lower()

        # Convert various formats to wav (required for base64 API)
        if lower_audio_url.endswith(".opus"):
            temp_dir = get_astrbot_temp_path()
            output_path = os.path.join(temp_dir, f"qwen_asr_{os.urandom(4).hex()}.wav")
            logger.info("Converting opus file to wav...")
            await convert_audio_to_wav(audio_url, output_path)
            audio_url = output_path
        elif (
            lower_audio_url.endswith(".amr")
            or lower_audio_url.endswith(".silk")
            or is_tencent
        ):
            file_format = await self._get_audio_format(audio_url)

            if file_format in ["silk", "amr"]:
                temp_dir = get_astrbot_temp_path()
                output_path = os.path.join(temp_dir, f"qwen_asr_{os.urandom(4).hex()}.wav")

                if file_format == "silk":
                    logger.info("Converting silk file to wav...")
                    await tencent_silk_to_wav(audio_url, output_path)
                elif file_format == "amr":
                    logger.info("Converting amr file to wav...")
                    await convert_to_pcm_wav(audio_url, output_path)

                audio_url = output_path

        return audio_url, output_path

    async def _encode_audio_base64(self, file_path: str) -> str:
        """Encode audio file to base64 data URI."""
        mime_type = self._get_mime_type(file_path)

        def _read_and_encode():
            file_path_obj = pathlib.Path(file_path)
            if not file_path_obj.exists():
                raise FileNotFoundError(f"Audio file not found: {file_path}")
            file_bytes = file_path_obj.read_bytes()
            return base64.b64encode(file_bytes).decode()

        base64_str = await asyncio.to_thread(_read_and_encode)
        return f"data:{mime_type};base64,{base64_str}"

    async def get_text(self, audio_url: str) -> str:
        """Transcribe audio file to text using Qwen3-ASR-Flash API.

        Args:
            audio_url: URL or local path to the audio file

        Returns:
            str: Transcribed text
        """
        output_path = None

        try:
            # Prepare audio file (download if URL, convert if needed)
            audio_path, output_path = await self._prepare_audio(audio_url)

            # Encode audio to base64
            data_uri = await self._encode_audio_base64(audio_path)

            # Build messages for MultiModalConversation API
            messages = [
                {"role": "user", "content": [{"audio": data_uri}]}
            ]

            # Build ASR options
            asr_options = {"enable_itn": self.enable_itn}
            if self.language != "auto":
                asr_options["language"] = self.language

            # Call API in a thread to avoid blocking the event loop
            def _blocking_call():
                # Set API base for this call
                dashscope.base_http_api_url = self.api_base
                return MultiModalConversation.call(
                    api_key=self.api_key,
                    model=self.model,
                    messages=messages,
                    result_format="message",
                    asr_options=asr_options,
                )

            response = await asyncio.to_thread(_blocking_call)

            # Parse response
            if response.status_code != 200:
                error_msg = response.message or f"API error: {response.status_code}"
                logger.error(f"Qwen3-ASR-Flash API error: {error_msg}")
                raise Exception(f"Qwen3-ASR-Flash API error: {error_msg}")

            # Extract text from response
            # Response format: output.choices[0].message.content
            text = ""
            if (
                hasattr(response, "output")
                and response.output
                and hasattr(response.output, "choices")
            ):
                choices = response.output.choices
                if choices and len(choices) > 0:
                    choice = choices[0]
                    if hasattr(choice, "message") and choice.message:
                        content = choice.message.content
                        if content and isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and "text" in item:
                                    text += item["text"]
                                elif isinstance(item, dict) and "audio" in item:
                                    text += item.get("audio", "")
                        elif isinstance(content, str):
                            text = content

            text = text.strip()
            logger.debug(f"Qwen3-ASR-Flash transcription: {text}")
            return text

        except Exception as e:
            logger.error(f"Qwen3-ASR-Flash transcription error: {e}")
            raise

        finally:
            # Cleanup temp file
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception as e:
                    logger.error(f"Failed to remove temp file {output_path}: {e}")

    async def terminate(self):
        """Clean up resources."""
        pass  # No persistent connections to close
