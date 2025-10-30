import uuid
import os
import aiohttp
from xinference_client.client.restful.async_restful_client import (
    AsyncClient as Client,
)
from ..provider import STTProvider
from ..entities import ProviderType
from ..register import register_provider_adapter
from astrbot.core import logger
from astrbot.core.utils.tencent_record_helper import tencent_silk_to_wav
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


@register_provider_adapter(
    "xinference_stt",
    "Xinference STT",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderXinferenceSTT(STTProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings
        self.base_url = provider_config.get("api_base", "http://127.0.0.1:9997")
        self.base_url = self.base_url.rstrip("/")
        self.timeout = provider_config.get("timeout", 180)
        self.model_name = provider_config.get("model", "whisper-large-v3")
        self.api_key = provider_config.get("api_key")
        self.launch_model_if_not_running = provider_config.get(
            "launch_model_if_not_running", False
        )
        self.client = None
        self.model_uid = None

    async def initialize(self):
        if self.api_key:
            logger.info("Xinference STT: Using API key for authentication.")
            self.client = Client(self.base_url, api_key=self.api_key)
        else:
            logger.info("Xinference STT: No API key provided.")
            self.client = Client(self.base_url)

        try:
            running_models = await self.client.list_models()
            for uid, model_spec in running_models.items():
                if model_spec.get("model_name") == self.model_name:
                    logger.info(
                        f"Model '{self.model_name}' is already running with UID: {uid}"
                    )
                    self.model_uid = uid
                    break

            if self.model_uid is None:
                if self.launch_model_if_not_running:
                    logger.info(f"Launching {self.model_name} model...")
                    self.model_uid = await self.client.launch_model(
                        model_name=self.model_name, model_type="audio"
                    )
                    logger.info("Model launched.")
                else:
                    logger.warning(
                        f"Model '{self.model_name}' is not running and auto-launch is disabled. Provider will not be available."
                    )
                    return

        except Exception as e:
            logger.error(f"Failed to initialize Xinference model: {e}")
            logger.debug(
                f"Xinference initialization failed with exception: {e}", exc_info=True
            )

    async def get_text(self, audio_url: str) -> str:
        if not self.model_uid or self.client is None or self.client.session is None:
            logger.error("Xinference STT model is not initialized.")
            return ""

        audio_bytes = None
        temp_files = []
        is_tencent = False

        try:
            # 1. Get audio bytes
            if audio_url.startswith("http"):
                if "multimedia.nt.qq.com.cn" in audio_url:
                    is_tencent = True
                async with aiohttp.ClientSession() as session:
                    async with session.get(audio_url, timeout=self.timeout) as resp:
                        if resp.status == 200:
                            audio_bytes = await resp.read()
                        else:
                            logger.error(
                                f"Failed to download audio from {audio_url}, status: {resp.status}"
                            )
                            return ""
            else:
                if os.path.exists(audio_url):
                    with open(audio_url, "rb") as f:
                        audio_bytes = f.read()
                else:
                    logger.error(f"File not found: {audio_url}")
                    return ""

            if not audio_bytes:
                logger.error("Audio bytes are empty.")
                return ""

            # 2. Check for conversion
            needs_conversion = False
            if (
                audio_url.endswith((".amr", ".silk"))
                or is_tencent
                or b"SILK" in audio_bytes[:8]
            ):
                needs_conversion = True

            # 3. Perform conversion if needed
            if needs_conversion:
                logger.info("Audio requires conversion, using temporary files...")
                temp_dir = os.path.join(get_astrbot_data_path(), "temp")
                os.makedirs(temp_dir, exist_ok=True)

                input_path = os.path.join(temp_dir, str(uuid.uuid4()))
                output_path = os.path.join(temp_dir, str(uuid.uuid4()) + ".wav")
                temp_files.extend([input_path, output_path])

                with open(input_path, "wb") as f:
                    f.write(audio_bytes)

                logger.info("Converting silk/amr file to wav ...")
                await tencent_silk_to_wav(input_path, output_path)

                with open(output_path, "rb") as f:
                    audio_bytes = f.read()

            # 4. Transcribe
            # 官方asyncCLient的客户端似乎实现有点问题，这里直接用aiohttp实现openai标准兼容请求，提交issue等待官方修复后再改回来
            url = f"{self.base_url}/v1/audio/transcriptions"
            headers = {
                "accept": "application/json",
            }
            if self.client and self.client._headers:
                headers.update(self.client._headers)

            data = aiohttp.FormData()
            data.add_field("model", self.model_uid)
            data.add_field(
                "file", audio_bytes, filename="audio.wav", content_type="audio/wav"
            )

            async with self.client.session.post(
                url, data=data, headers=headers, timeout=self.timeout
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    text = result.get("text", "")
                    logger.debug(f"Xinference STT result: {text}")
                    return text
                else:
                    error_text = await resp.text()
                    logger.error(
                        f"Xinference STT transcription failed with status {resp.status}: {error_text}"
                    )
                    return ""

        except Exception as e:
            logger.error(f"Xinference STT failed: {e}")
            logger.debug(f"Xinference STT failed with exception: {e}", exc_info=True)
            return ""
        finally:
            # 5. Cleanup
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                        logger.debug(f"Removed temporary file: {temp_file}")
                except Exception as e:
                    logger.error(f"Failed to remove temporary file {temp_file}: {e}")

    async def terminate(self) -> None:
        """关闭客户端会话"""
        if self.client:
            logger.info("Closing Xinference STT client...")
            try:
                await self.client.close()
            except Exception as e:
                logger.error(f"Failed to close Xinference client: {e}", exc_info=True)
