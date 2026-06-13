import asyncio
from functools import partial
from typing import cast

import whisper

from astrbot.core import logger
from astrbot.core.utils.media_utils import MediaResolver

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
        self.device = str(provider_config.get("whisper_device", "cpu")).strip().lower()
        self.model = None

    def _resolve_device(self) -> str:
        if self.device == "mps":
            import torch  # torch is a dependency of openai-whisper

            mps_backend = getattr(torch.backends, "mps", None)
            if mps_backend and mps_backend.is_available():
                return "mps"
            logger.warning("Whisper 已配置为使用 MPS，但当前环境不可用，将回退到 CPU。")
            return "cpu"
        if self.device != "cpu":
            logger.warning(
                "Whisper 配置了未知 device=%s，将回退到 CPU。",
                self.device,
            )
        return "cpu"

    async def initialize(self) -> None:
        loop = asyncio.get_running_loop()
        device = self._resolve_device()
        logger.info("下载或者加载 Whisper 模型中，这可能需要一些时间 ...")
        self.model = await loop.run_in_executor(
            None,
            partial(whisper.load_model, self.model_name, device=device),
        )
        logger.info("Whisper 模型加载完成。device=%s", device)

    async def get_text(self, audio_url: str) -> str:
        loop = asyncio.get_running_loop()

        if not self.model:
            raise RuntimeError("Whisper 模型未初始化")

        async with MediaResolver(
            audio_url,
            media_type="audio",
            default_suffix=".wav",
        ).as_path(target_format="wav") as audio:
            result = await loop.run_in_executor(
                None,
                self.model.transcribe,
                str(audio.path),
            )
        return cast(str, result["text"])
