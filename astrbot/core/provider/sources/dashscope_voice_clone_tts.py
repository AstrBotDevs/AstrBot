"""阿里云百炼 - 音色复刻（Qwen-TTS Voice Clone）TTS 提供商。

通过指定声音复刻产生的 voice_id（如 ``yourVoice``）与对应的 Qwen3 TTS-VC
合成模型（如 ``qwen3-tts-vc-2026-01-22``）调用阿里云 DashScope 的多模态生成
接口完成语音合成。该提供商仅负责"使用"已经在百炼控制台中创建好的复刻音色，
音色的创建/管理流程请直接通过百炼控制台或 API 完成。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import uuid

import aiohttp
import dashscope

try:
    from dashscope.aigc.multimodal_conversation import MultiModalConversation
except ImportError:  # pragma: no cover - 老版本 dashscope 没有 Qwen TTS 能力
    MultiModalConversation = None

from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "dashscope_voice_clone_tts",
    "阿里云百炼 音色复刻 TTS API (Qwen3-TTS-VC)",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderDashscopeVoiceCloneTTSAPI(TTSProvider):
    """使用阿里云百炼 Qwen3-TTS-VC 系列模型合成"复刻音色"的 TTS 提供商。"""

    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key: str = provider_config.get("api_key", "")
        # 复刻音色 ID，由百炼音色复刻接口返回（output.voice）
        self.voice_id: str = provider_config.get(
            "voice_id",
            "",
        )
        # 合成语种，可选；默认让模型自动判断
        self.language_type: str = provider_config.get(
            "language_type",
            "",
        )
        # workspace ID（可选），填写后会切换到百炼 workspace 专属域名以获得更佳性能
        self.workspace_id: str = provider_config.get(
            "workspace_id",
            "",
        )
        # 地域，默认 cn-beijing；可选 ap-southeast-1（新加坡）
        self.region: str = (
            provider_config.get(
                "region",
                "cn-beijing",
            )
            or "cn-beijing"
        )
        # 自定义 base url（优先级最高），不填时根据 workspace_id / region 推断
        self.base_http_api_url: str = provider_config.get(
            "base_url",
            "",
        )

        self.set_model(
            provider_config.get("model") or "qwen3-tts-vc-2026-01-22",
        )
        self.timeout_ms = float(provider_config.get("timeout", 20)) * 1000

        # API Key 和 Base URL 将在每次调用时通过 kwargs 动态传入，避免修改全局配置

    # public API#
    async def get_audio(self, text: str) -> str:
        model = self.get_model()
        if not model:
            raise RuntimeError("Dashscope Voice Clone TTS model is not configured.")
        if not self.voice_id:
            raise RuntimeError(
                "未配置复刻音色 ID（voice_id），"
                "请先在阿里云百炼控制台或 API 创建复刻音色后再填写。",
            )

        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)

        # 每次调用前确保 dashscope 全局配置使用本提供商指定的值。
        # 避免多 TTS 共存时被其它提供商覆盖。
        dashscope.api_key = self.chosen_api_key
        resolved_base_url = self._resolve_base_url()
        if resolved_base_url:
            dashscope.base_http_api_url = resolved_base_url

        audio_bytes = await self._synthesize(model, text)
        if not audio_bytes:
            raise RuntimeError(
                "音色复刻语音合成失败，返回内容为空。请检查模型名、voice_id "
                "以及对应的 API Key/地域是否匹配。",
            )

        path = os.path.join(
            temp_dir,
            f"dashscope_voice_clone_tts_{uuid.uuid4()}.wav",
        )
        with open(path, "wb") as f:
            f.write(audio_bytes)
        return path

    # internal helpers#
    def _resolve_base_url(self) -> str:
        """根据配置推断 DashScope HTTP base url。"""
        if self.base_http_api_url:
            return self.base_http_api_url.rstrip("/")
        if self.workspace_id:
            region = self.region or "cn-beijing"
            return f"https://{self.workspace_id}.{region}.maas.aliyuncs.com/api/v1"
        # 不指定专属域名时返回空字符串，使用 dashscope SDK 内置默认域名
        return ""

    def _call_qwen_tts(self, model: str, text: str):
        if MultiModalConversation is None:
            raise RuntimeError(
                "dashscope SDK 缺少 MultiModalConversation。请升级 dashscope "
                "至最新版本以使用 Qwen TTS 系列模型。",
            )

        kwargs = {
            "model": model,
            "messages": None,
            "api_key": self.chosen_api_key,
            "voice": self.voice_id,
            "text": text,
        }
        resolved_base_url = self._resolve_base_url()
        if resolved_base_url:
            kwargs["base_http_api_url"] = resolved_base_url
        if self.language_type:
            kwargs["language_type"] = self.language_type
        return MultiModalConversation.call(**kwargs)

    async def _synthesize(self, model: str, text: str) -> bytes | None:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            self._call_qwen_tts,
            model,
            text,
        )
        if hasattr(response, "status_code") and response.status_code != 200:
            raise RuntimeError(
                f"DashScope API 调用失败，状态码: {response.status_code}，" 
                f"错误码: {getattr(response, 'code', 'Unknown')}，" 
                f"错误信息: {getattr(response, 'message', 'Unknown')}"
            )
        audio_bytes = await self._extract_audio_from_response(response)
        if not audio_bytes:
            raise RuntimeError(
                f"模型 '{model}' 音色复刻语音合成失败。返回内容为空。",
            )
        return audio_bytes

    async def _extract_audio_from_response(self, response) -> bytes | None:
        output = getattr(response, "output", None)
        audio_obj = getattr(output, "audio", None) if output is not None else None
        if not audio_obj:
            return None

        data_b64 = getattr(audio_obj, "data", None)
        if data_b64:
            try:
                return base64.b64decode(data_b64)
            except (ValueError, TypeError):
                logging.exception("Failed to decode base64 audio data.")
                return None

        url = getattr(audio_obj, "url", None)
        if url:
            return await self._download_audio_from_url(url)
        return None

    async def _download_audio_from_url(self, url: str) -> bytes | None:
        if not url:
            return None
        timeout = max(self.timeout_ms / 1000, 1) if self.timeout_ms else 20
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response,
            ):
                if response.status != 200:
                    logging.error(f"Failed to download audio from URL {url}, HTTP status: {response.status}")
                    return None
                return await response.read()
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
            logging.exception(f"Failed to download audio from URL {url}: {e}")
            return None
