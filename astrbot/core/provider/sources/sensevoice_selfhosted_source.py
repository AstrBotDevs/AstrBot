"""Author: diudiu62
Date: 2025-02-24 18:04:18
LastEditTime: 2025-02-25 14:06:30
"""

import asyncio
import re
from typing import cast

from funasr_onnx import SenseVoiceSmall
from funasr_onnx.utils.postprocess_utils import rich_transcription_postprocess

from astrbot.core import logger
from astrbot.core.utils.media_utils import MediaResolver

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "sensevoice_stt_selfhost",
    "SenseVoice 自托管语音识别 模型部署",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderSenseVoiceSTTSelfHost(STTProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.set_model(provider_config["stt_model"])
        self.model = None
        self.is_emotion = provider_config.get("is_emotion", False)

    async def initialize(self) -> None:
        logger.info("下载或者加载 SenseVoice 模型中，这可能需要一些时间 ...")

        # 将模型加载放到线程池中执行
        self.model = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: SenseVoiceSmall(self.model_name, quantize=True, batch_size=16),
        )

        logger.info("SenseVoice 模型加载完成。")

    async def get_text(self, audio_url: str) -> str:
        try:
            # 使用 run_in_executor 来调用模型进行识别
            loop = asyncio.get_running_loop()
            async with MediaResolver(
                audio_url,
                media_type="audio",
                default_suffix=".wav",
            ).as_path(target_format="wav") as audio:
                res = await loop.run_in_executor(
                    None,  # 使用默认的线程池
                    lambda: cast(SenseVoiceSmall, self.model)(
                        str(audio.path), language="auto", use_itn=True
                    ),
                )

            # res = self.model(audio_url, language="auto", use_itn=True)
            logger.debug(f"SenseVoice识别到的文案：{res}")
            text = rich_transcription_postprocess(res[0])
            if self.is_emotion:
                # 提取第二个匹配的值
                matches = re.findall(r"<\|([^|]+)\|>", res[0])
                if len(matches) >= 2:
                    emotion = matches[1]
                    text = f"(当前的情绪：{emotion}) {text}"
                else:
                    logger.warning("未能提取到情绪信息")
            return text
        except Exception as e:
            logger.error(f"处理音频文件时出错: {e}")
            raise
