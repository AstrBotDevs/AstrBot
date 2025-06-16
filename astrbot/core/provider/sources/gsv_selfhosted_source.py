
import asyncio
import os
import uuid

import aiohttp
from ..provider import TTSProvider
from ..entities import ProviderType
from ..register import register_provider_adapter
from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


@register_provider_adapter(
    provider_type_name="gsv_tts_selfhost",
    desc=" GPT-SoVITS TTS(本地加载)",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderGSVTTS(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        # 基础URL
        self.api_base = provider_config.get("api_base", "http://127.0.0.1:9880")
        if self.api_base.endswith("/"):
            self.api_base = self.api_base[:-1]

        # 模型文件路径
        self.gpt_weights_path: str = provider_config.get("gpt_weights_path", "")
        self.sovits_weights_path: str = provider_config.get("sovits_weights_path", "")
        asyncio.create_task(self._set_model_weights())

        # 默认参数
        raw_params = provider_config.get("gsv_default_parms", {})
        self.default_params: dict = {
            key.removeprefix("gsv_"): str(value).lower()
            for key, value in raw_params.items()
        }

        # 情绪预设
        self.emotions = provider_config.get("emotions", {})

    async def _make_request(
        self,
        endpoint: str,
        params=None,
    ) -> str | bytes:
        """通用的异步请求方法"""
        async with aiohttp.ClientSession() as session:
            async with session.request("GET", endpoint, params=params) as response:
                if response.status != 200:
                    return await response.text()
                else:
                    return await response.read()

    async def _set_model_weights(self):
        """设置模型"""
        try:
            # 设置 GPT 模型
            if self.gpt_weights_path:
                gpt_endpoint = f"{self.api_base}/set_gpt_weights"
                gpt_params = {"weights_path": self.gpt_weights_path}
                if await self._make_request(endpoint=gpt_endpoint, params=gpt_params):
                    logger.info(f"成功设置 GPT 模型路径：{self.gpt_weights_path}")
            else:
                logger.info("GPT 模型路径未配置，将使用GPT_SoVITS内置的GPT模型")

            # 设置 SoVITS 模型
            if self.sovits_weights_path:
                sovits_endpoint = f"{self.api_base}/set_sovits_weights"
                sovits_params = {"weights_path": self.sovits_weights_path}
                if await self._make_request(
                    endpoint=sovits_endpoint, params=sovits_params
                ):
                    logger.info(f"成功设置 SoVITS 模型路径：{self.sovits_weights_path}")
            else:
                logger.info("SoVITS 模型路径未配置，将使用GPT_SoVITS内置的SoVITS模型")
        except aiohttp.ClientError as e:
            logger.error(f"设置模型路径时发生错误：{e}")
        except Exception as e:
            logger.error(f"发生未知错误：{e}")

    async def get_audio(self, text: str) -> str:
        """实现 TTS 核心方法，根据文本内容自动切换情绪"""
        endpoint = f"{self.api_base}/tts"

        params = self.default_params.copy()
        params["text"] = text

        temp_dir = os.path.join(get_astrbot_data_path(), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        path = os.path.join(temp_dir, f"gsvi_tts_{uuid.uuid4()}.wav")

        logger.debug(f"正在调用GSV语音合成接口，参数：{params}")

        result = await self._make_request(endpoint, params)
        if isinstance(result, bytes):
            with open(path, "wb") as f:
                f.write(result)
            return path
        else:
            raise Exception(f"GSVI TTS API 请求失败: {result}")

