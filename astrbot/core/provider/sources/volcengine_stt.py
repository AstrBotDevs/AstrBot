import base64
import os
import uuid

import aiohttp

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_file
from astrbot.core.utils.tencent_record_helper import (
    convert_to_pcm_wav,
    tencent_silk_to_wav,
)

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "volcengine_stt",
    "火山引擎录音文件极速识别",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderVolcengineSTT(STTProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings
        self.base_url = provider_config.get(
            "api_base",
            "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash",
        )
        self.appid = provider_config.get("appid")
        self.api_key = provider_config.get("api_key")

    async def _get_audio_format(self, file_path) -> str | None:
        silk_header = b"SILK"
        amr_header = b"#!AMR"
        try:
            with open(file_path, "rb") as f:
                file_header = f.read(8)
            if silk_header in file_header:
                return "silk"
            if amr_header in file_header:
                return "amr"
        except Exception:
            return None
        return None

    async def get_text(self, audio_url: str) -> str:
        """
        获取音频文件的转录文本。
        """
        temp_files = []  # 记录所有产生的临时文件，确保最后全部清理
        final_audio_path = audio_url
        try:
            # --- 步骤 1: 处理远程 URL 下载 ---
            if audio_url.startswith("http"):
                is_tencent = "multimedia.nt.qq.com.cn" in audio_url
                temp_dir = get_astrbot_temp_path()
                downloaded_path = os.path.join(
                    temp_dir, f"volc_stt_{uuid.uuid4().hex[:8]}.input"
                )
                await download_file(audio_url, downloaded_path)
                temp_files.append(downloaded_path)
                final_audio_path = downloaded_path
            else:
                is_tencent = False

            if not os.path.exists(final_audio_path):
                logger.error(f"音频文件不存在: {final_audio_path}")

            # --- 步骤 2: 格式检测与转换 (Silk/AMR) ---
            if final_audio_path.endswith((".amr", ".silk")) or is_tencent:
                file_format = await self._get_audio_format(final_audio_path)
                if file_format in ["silk", "amr"]:
                    temp_dir = get_astrbot_temp_path()
                    converted_path = os.path.join(
                        temp_dir, f"volc_stt_{uuid.uuid4().hex[:8]}.wav"
                    )

                    if file_format == "silk":
                        await tencent_silk_to_wav(final_audio_path, converted_path)
                    else:
                        await convert_to_pcm_wav(final_audio_path, converted_path)

                    temp_files.append(converted_path)
                    final_audio_path = converted_path

            # --- 步骤 3: 调用火山引擎 API ---
            result = await self._recognize_audio(final_audio_path)
            return result

        finally:
            # --- 步骤 4: 彻底清理所有协议产生的临时文件 ---
            for f_path in temp_files:
                if os.path.exists(f_path):
                    try:
                        os.remove(f_path)
                    except Exception as e:
                        logger.error(f"清理火山引擎 STT 临时文件失败: {f_path}, {e}")

    async def _recognize_audio(self, file_path: str) -> str:
        """执行具体的 API 请求"""
        if not self.appid or not self.api_key:
            logger.error("火山引擎 STT 配置不完整：需要 appid 和 api_key")

        headers = {
            "X-Api-App-Key": self.appid,
            "X-Api-Access-Key": self.api_key,
            "X-Api-Resource-Id": "volc.bigasr.auc_turbo",
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Sequence": "-1",
        }

        with open(file_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()

        request_body = {
            "user": {"uid": str(uuid.uuid4())},
            "audio": {"data": audio_b64},
            "request": {"model_name": "bigmodel"},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.base_url, json=request_body, headers=headers
            ) as resp:
                status_code = resp.headers.get("X-Api-Status-Code")
                data = await resp.json()
                if status_code == "20000000":
                    text = data.get("result", {}).get("text", "")
                    return text
                else:
                    logger.debug(f"data原始数据{data}")
                    error_msg = data.get("message", "未知错误")
                    logger.error(
                        f"火山引擎 STT API 错误 (Status: {status_code}): {error_msg}"
                    )
                    logger.error(f"火山引擎 STT 识别失败: {error_msg}")
