import asyncio
import os
import uuid

import httpx2
from openai import NOT_GIVEN, AsyncOpenAI

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.error_redaction import safe_error

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "openai_tts_api",
    "OpenAI TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderOpenAITTSAPI(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key = provider_config.get("api_key", "")
        self.voice = provider_config.get("openai-tts-voice", "alloy")

        timeout = provider_config.get("timeout", NOT_GIVEN)
        if isinstance(timeout, str):
            timeout = int(timeout)

        proxy = provider_config.get("proxy", "")
        http_client = None
        if proxy:
            logger.info(f"[OpenAI TTS] 使用代理: {proxy}")
            http_client = httpx2.AsyncClient(proxy=proxy)
        self.client = AsyncOpenAI(
            api_key=self.chosen_api_key,
            base_url=provider_config.get("api_base"),
            timeout=timeout,
            http_client=http_client,
        )

        self.set_model(provider_config.get("model", ""))

    async def get_audio(self, text: str) -> str:
        temp_dir = get_astrbot_temp_path()
        path = os.path.join(temp_dir, f"openai_tts_api_{uuid.uuid4()}.wav")
        completed = False

        try:
            os.makedirs(temp_dir, exist_ok=True)
            bytes_written = 0
            async with self.client.audio.speech.with_streaming_response.create(
                model=self.model_name,
                voice=self.voice,
                response_format="wav",
                input=text,
            ) as response:
                with open(path, "wb") as f:
                    async for chunk in response.iter_bytes(chunk_size=1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        bytes_written += len(chunk)

            if not bytes_written:
                raise RuntimeError("OpenAI TTS returned empty audio.")

            completed = True
            return path
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("OpenAI TTS generation failed: %s", safe_error("", exc))
            raise RuntimeError("OpenAI TTS audio generation failed.") from None
        finally:
            if not completed:
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    logger.warning(
                        "Failed to remove incomplete OpenAI TTS audio: %s",
                        safe_error("", exc),
                    )

    async def terminate(self):
        if self.client:
            await self.client.close()
