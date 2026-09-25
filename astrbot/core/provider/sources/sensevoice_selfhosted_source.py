"""Author: diudiu62
Date: 2025-02-24 18:04:18
LastEditTime: 2026-08-31 
LastEdit / Blame: xiewoc
"""

import asyncio
import re
import os
import shutil
from typing import Optional, TYPE_CHECKING

from astrbot.core.utils.pip_installer import PipInstaller
from astrbot.core.utils.media_utils import MediaResolver
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core import logger

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter

# 仅在类型检查时导入，避免运行时循环依赖或导入失败
if TYPE_CHECKING:
    from funasr_onnx import SenseVoiceSmall

_REQUIRED_MODULES = [
    "funasr", "funasr_onnx", "torch",  # "torchaudio", <- we don't need this, use FFmpeg instead
    "onnxruntime", "modelscope", "onnxscript"
]

# 模块级缓存，避免重复安装/导入
_sense_voice_cls = None
_postprocess_fn = None
_snapshot_download_fn = None


def _check_ffmpeg() -> None:
    """检测系统是否安装了 FFmpeg，未安装则记录错误并抛出异常阻断流程。"""
    if shutil.which("ffmpeg") is None:
        msg = (
            "未检测到 FFmpeg！SenseVoice STT 依赖 FFmpeg 进行音频转码。"
            "请安装 FFmpeg 并将其添加到系统 PATH 环境变量中。"
            "参考: https://ffmpeg.org/download.html"
        )
        logger.error(msg)
        raise RuntimeError(msg)


async def _install_dependencies():
    """异步安装依赖库"""
    pip = PipInstaller(pip_install_arg="")
    for item in _REQUIRED_MODULES:
        try:
            await pip.install(item)
        except Exception as e:
            logger.error(f"安装依赖 {item} 失败: {e}")
            raise


def _load_sense_voice_modules():
    """延迟加载 SenseVoice 相关模块，支持自动安装重试"""
    global _sense_voice_cls, _postprocess_fn, _snapshot_download_fn

    if _sense_voice_cls is not None:
        return _sense_voice_cls, _postprocess_fn, _snapshot_download_fn

    try:
        from modelscope import snapshot_download
        from funasr_onnx import SenseVoiceSmall
        from funasr_onnx.utils.postprocess_utils import rich_transcription_postprocess

        _sense_voice_cls = SenseVoiceSmall
        _postprocess_fn = rich_transcription_postprocess
        _snapshot_download_fn = snapshot_download
        return _sense_voice_cls, _postprocess_fn, _snapshot_download_fn

    except ImportError:
        logger.info("SenseVoice 依赖未安装，正在尝试自动安装...")
        try:
            # 注意：在已有事件循环中应使用 run_coroutine_threadsafe 或 nest_asyncio
            # 此处保留原逻辑但增加提示，实际部署建议改为插件初始化钩子
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.warning("检测到运行中的事件循环，自动安装可能失败。建议手动安装依赖。")
            asyncio.run(_install_dependencies())
        except Exception as e:
            logger.error(f"自动安装依赖失败: {e}")
            raise ImportError(
                "SenseVoice 依赖安装失败，请手动执行: pip install " + " ".join(_REQUIRED_MODULES)
            ) from e

        # 重试导入
        from modelscope import snapshot_download
        from funasr_onnx import SenseVoiceSmall
        from funasr_onnx.utils.postprocess_utils import rich_transcription_postprocess

        _sense_voice_cls = SenseVoiceSmall
        _postprocess_fn = rich_transcription_postprocess
        _snapshot_download_fn = snapshot_download
        return _sense_voice_cls, _postprocess_fn, _snapshot_download_fn


@register_provider_adapter(
    "sensevoice_stt_selfhost",
    "SenseVoice 自托管语音识别模型部署",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderSenseVoiceSTTSelfHost(STTProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.set_model(provider_config["stt_model"])

        self.model: Optional["SenseVoiceSmall"] = None
        self.is_emotion: bool = provider_config.get("is_emotion", False)
        self.model_path: str = os.path.join(get_astrbot_data_path(), "SenseVoiceSmall")

    async def initialize(self) -> None:
        # ✅ 优先检测 FFmpeg，缺失时快速失败，避免浪费模型下载/加载时间
        _check_ffmpeg()

        logger.info("正在下载或加载 SenseVoice 模型，首次可能需要较长时间...")

        SenseVoiceSmall, _, snapshot_download = _load_sense_voice_modules()

        # 模型下载（同步操作放入线程池）
        if not os.path.exists(os.path.join(self.model_path, "configuration.json")):
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: snapshot_download("iic/SenseVoiceSmall", local_dir=self.model_path),
            )

        # 模型加载（CPU/GPU 密集型操作放入线程池）
        self.model = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: SenseVoiceSmall(model_dir=self.model_path, quantize=True, batch_size=16),
        )
        logger.info("SenseVoice 模型加载完成。")

    async def get_text(self, audio_url: str) -> str:
        if self.model is None:
            raise RuntimeError("SenseVoice 模型未初始化，请先调用 initialize()")

        # 局部变量绑定，确保类型收窄且避免 lambda 中的属性访问问题
        model = self.model
        _, postprocess, _ = _load_sense_voice_modules()

        try:
            loop = asyncio.get_running_loop()

            async with MediaResolver(
                audio_url, media_type="audio", default_suffix=".wav"
            ).as_path(target_format="wav") as audio:
                res = await loop.run_in_executor(
                    None,
                    lambda: model(str(audio.path), language="auto", use_itn=True),
                )

            logger.debug(f"SenseVoice 原始识别结果: {res}")
            text = postprocess(res[0])

            if self.is_emotion:
                matches = re.findall(r"<\|([^|]+)\|>", res[0])
                if len(matches) >= 2:
                    text = f"(当前的情绪：{matches[1]}) {text}"
                else:
                    logger.warning("未能从识别结果中提取情绪标签")

            return text

        except Exception as e:
            logger.error(f"SenseVoice 语音识别失败: {e}", exc_info=True)
            raise