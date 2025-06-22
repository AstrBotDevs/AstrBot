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
    desc="GPT-SoVITS TTS(本地加载)",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderGSVTTS(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)

        self.api_base = provider_config.get("api_base", "http://127.0.0.1:9880").rstrip(
            "/"
        )
        self.gpt_weights_path: str = provider_config.get("gpt_weights_path", "")
        self.sovits_weights_path: str = provider_config.get("sovits_weights_path", "")

        # TTS 请求的默认参数，移除前缀gsv_
        self.default_params: dict = {
            key.removeprefix("gsv_"): str(value).lower()
            for key, value in provider_config.get("gsv_default_parms", {}).items()
        }
        self.timeout = provider_config.get("timeout", 60)
        self._session: aiohttp.ClientSession | None = None

    async def initialize(self):
        """异步初始化：在 ProviderManager 中被调用"""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
        try:
            await self._set_model_weights()
            logger.info("[GSV TTS] 初始化完成")
        except Exception as e:
            logger.error(f"[GSV TTS] 初始化失败：{e}")
            raise

    def get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            raise RuntimeError(
                "[GSV TTS] Provider HTTP session is not ready or closed."
            )
        return self._session

    async def _make_request(
        self, endpoint: str, params=None, retries: int = 3
    ) -> bytes | None:
        """发起请求"""
        for attempt in range(retries):
            logger.debug(f"[GSV TTS] 请求地址：{endpoint}，参数：{params}")
            try:
                async with self.get_session().get(endpoint, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(
                            f"[GSV TTS] Request to {endpoint} failed with status {response.status}: {error_text}"
                        )
                    return await response.read()
            except Exception as e:
                if attempt < retries - 1:
                    logger.warning(
                        f"[GSV TTS] 请求 {endpoint} 第 {attempt + 1} 次失败：{e}，重试中..."
                    )
                    await asyncio.sleep(1)
                else:
                    logger.error(f"[GSV TTS] 请求 {endpoint} 最终失败：{e}")
                    raise

    async def _set_model_weights(self):
        """设置模型路径"""
        try:
            if self.gpt_weights_path:
                await self._make_request(
                    f"{self.api_base}/set_gpt_weights",
                    {"weights_path": self.gpt_weights_path},
                )
                logger.info(f"[GSV TTS] 成功设置 GPT 模型路径：{self.gpt_weights_path}")
            else:
                logger.info("[GSV TTS] GPT 模型路径未配置，将使用内置 GPT 模型")

            if self.sovits_weights_path:
                await self._make_request(
                    f"{self.api_base}/set_sovits_weights",
                    {"weights_path": self.sovits_weights_path},
                )
                logger.info(
                    f"[GSV TTS] 成功设置 SoVITS 模型路径：{self.sovits_weights_path}"
                )
            else:
                logger.info("[GSV TTS] SoVITS 模型路径未配置，将使用内置 SoVITS 模型")
        except aiohttp.ClientError as e:
            logger.error(f"[GSV TTS] 设置模型路径时发生网络错误：{e}")
        except Exception as e:
            logger.error(f"[GSV TTS] 设置模型路径时发生未知错误：{e}")

    async def get_audio(self, text: str) -> str:
        """实现 TTS 核心方法，根据文本内容自动切换情绪"""
        if not text.strip():
            raise ValueError("[GSV TTS] TTS 文本不能为空")

        endpoint = f"{self.api_base}/tts"

        params = self.build_synthesis_params(text)

        temp_dir = os.path.join(get_astrbot_data_path(), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        path = os.path.join(temp_dir, f"gsv_tts_{uuid.uuid4().hex}.wav")

        logger.debug(f"[GSV TTS] 正在调用语音合成接口，参数：{params}")

        result = await self._make_request(endpoint, params)
        if isinstance(result, bytes):
            with open(path, "wb") as f:
                f.write(result)
            return path
        else:
            raise Exception(f"[GSV TTS] 合成失败，输入文本：{text}，错误信息：{result}")

    def build_synthesis_params(self, text: str) -> dict:
        """
        构建语音合成所需的参数字典。

        当前仅包含默认参数 + 文本，未来可在此基础上动态添加如情绪、角色等语义控制字段。
        """
        params = self.default_params.copy()
        params["text"] = text
        # TODO: 在此处添加情绪分析，例如 params["emotion"] = detect_emotion(text)
        return params

    async def terminate(self):
        """终止释放资源：在 ProviderManager 中被调用"""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("[GSV TTS] Session 已关闭")
