from astrbot.core.lang import t
import os
import uuid

import aiohttp
from xinference_client.client.restful.async_restful_client import (
    AsyncClient as Client,
)

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.tencent_record_helper import (
    convert_to_pcm_wav,
    tencent_silk_to_wav,
)

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter


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
            "launch_model_if_not_running",
            False,
        )
        self.client = None
        self.model_uid = None

    async def initialize(self) -> None:
        if self.api_key:
            logger.info(t("msg-4e31e089"))
            self.client = Client(self.base_url, api_key=self.api_key)
        else:
            logger.info(t("msg-e291704e"))
            self.client = Client(self.base_url)

        try:
            running_models = await self.client.list_models()
            for uid, model_spec in running_models.items():
                if model_spec.get("model_name") == self.model_name:
                    logger.info(
                        t("msg-b0d1e564", res=self.model_name, uid=uid),
                    )
                    self.model_uid = uid
                    break

            if self.model_uid is None:
                if self.launch_model_if_not_running:
                    logger.info(t("msg-16965859", res=self.model_name))
                    self.model_uid = await self.client.launch_model(
                        model_name=self.model_name,
                        model_type="audio",
                    )
                    logger.info(t("msg-7b1dfdd3"))
                else:
                    logger.warning(
                        t("msg-3fc7310e", res=self.model_name),
                    )
                    return

        except Exception as e:
            logger.error(t("msg-15f19a42", e=e))
            logger.debug(
                t("msg-01af1651", e=e),
                exc_info=True,
            )

    async def get_text(self, audio_url: str) -> str:
        if not self.model_uid or self.client is None or self.client.session is None:
            logger.error(t("msg-42ed8558"))
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
                                t("msg-bbc43272", audio_url=audio_url, res=resp.status),
                            )
                            return ""
            elif os.path.exists(audio_url):
                with open(audio_url, "rb") as f:
                    audio_bytes = f.read()
            else:
                logger.error(t("msg-f4e53d3d", audio_url=audio_url))
                return ""

            if not audio_bytes:
                logger.error(t("msg-ebab7cac"))
                return ""

            # 2. Check for conversion
            conversion_type = None

            if b"SILK" in audio_bytes[:8]:
                conversion_type = "silk"
            elif b"#!AMR" in audio_bytes[:6]:
                conversion_type = "amr"
            elif audio_url.endswith(".silk") or is_tencent:
                conversion_type = "silk"
            elif audio_url.endswith(".amr"):
                conversion_type = "amr"

            # 3. Perform conversion if needed
            if conversion_type:
                logger.info(
                    t("msg-7fd63838", conversion_type=conversion_type)
                )
                temp_dir = get_astrbot_temp_path()
                os.makedirs(temp_dir, exist_ok=True)

                input_path = os.path.join(
                    temp_dir,
                    f"xinference_stt_{uuid.uuid4().hex[:8]}.input",
                )
                output_path = os.path.join(
                    temp_dir,
                    f"xinference_stt_{uuid.uuid4().hex[:8]}.wav",
                )
                temp_files.extend([input_path, output_path])

                with open(input_path, "wb") as f:
                    f.write(audio_bytes)

                if conversion_type == "silk":
                    logger.info(t("msg-d03c4ede"))
                    await tencent_silk_to_wav(input_path, output_path)
                elif conversion_type == "amr":
                    logger.info(t("msg-79486689"))
                    await convert_to_pcm_wav(input_path, output_path)

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
                "file",
                audio_bytes,
                filename="audio.wav",
                content_type="audio/wav",
            )

            async with self.client.session.post(
                url,
                data=data,
                headers=headers,
                timeout=self.timeout,
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    text = result.get("text", "")
                    logger.debug(t("msg-c4305a5b", text=text))
                    return text
                error_text = await resp.text()
                logger.error(
                    t("msg-d4241bd5", res=resp.status, error_text=error_text),
                )
                return ""

        except Exception as e:
            logger.error(t("msg-8efe4ef1", e=e))
            logger.debug(t("msg-b1554c7c", e=e), exc_info=True)
            return ""
        finally:
            # 5. Cleanup
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                        logger.debug(t("msg-9d33941a", temp_file=temp_file))
                except Exception as e:
                    logger.error(t("msg-7dc5bc44", temp_file=temp_file, e=e))

    async def terminate(self) -> None:
        """关闭客户端会话"""
        if self.client:
            logger.info(t("msg-31904a1c"))
            try:
                await self.client.close()
            except Exception as e:
                logger.error(t("msg-633a269f", e=e), exc_info=True)
