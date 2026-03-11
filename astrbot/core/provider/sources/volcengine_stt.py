import asyncio
import base64
import uuid
from pathlib import Path

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

    async def _get_audio_format(self, file_path: Path) -> str | None:
        silk_header = b"SILK"
        amr_header = b"#!AMR"
        try:
            file_header = file_path.read_bytes()[:8]
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
        temp_files: list[Path] = []  # 记录所有产生的临时文件，确保最后全部清理
        final_audio_path: Path = None
        try:
            # --- 步骤 1: 处理远程 URL 下载 ---
            # 这里的url来自项目认可的消息平台的url,具有安全性
            if audio_url.startswith("http"):
                async with aiohttp.ClientSession() as session:
                    async with session.head(audio_url) as resp:
                        size = int(resp.headers.get("Content-Length", 0))
                        if size > 20 * 1024 * 1024:
                            logger.warning(f"音频文件过大: {size} bytes")
                            raise ValueError("音频文件过大")
                is_tencent = "multimedia.nt.qq.com.cn" in audio_url
                temp_dir = Path(get_astrbot_temp_path())
                downloaded_path = temp_dir / f"volc_stt_{uuid.uuid4().hex[:8]}.input"
                await download_file(audio_url, str(downloaded_path))
                temp_files.append(downloaded_path)
                final_audio_path = downloaded_path
            else:
                is_tencent = False
                final_audio_path = Path(audio_url)

            if not final_audio_path.exists():
                logger.error(f"音频文件不存在: {final_audio_path}")
                return None

            # --- 步骤 2: 格式检测与转换 (Silk/AMR) ---
            if final_audio_path.suffix in [".amr", ".silk"] or is_tencent:
                file_format = await self._get_audio_format(final_audio_path)
                if file_format in ["silk", "amr"]:
                    temp_dir = Path(get_astrbot_temp_path())
                    converted_path = temp_dir / f"volc_stt_{uuid.uuid4().hex[:8]}.wav"

                    if file_format == "silk":
                        await tencent_silk_to_wav(
                            str(final_audio_path), str(converted_path)
                        )
                    else:
                        await convert_to_pcm_wav(
                            str(final_audio_path), str(converted_path)
                        )

                    temp_files.append(converted_path)
                    final_audio_path = converted_path

            # --- 步骤 3: 调用火山引擎 API ---
            result = await self._recognize_audio(final_audio_path)
            return result

        finally:
            # --- 步骤 4: 彻底清理所有协议产生的临时文件 ---
            for f_path in temp_files:
                if f_path.exists():
                    try:
                        f_path.unlink()
                    except Exception as e:
                        logger.error(f"清理火山引擎 STT 临时文件失败: {f_path}, {e}")
                        return ""

    async def _recognize_audio(self, file_path: Path) -> str:
        """执行具体的 API 请求"""
        if not self.appid or not self.api_key:
            logger.error("火山引擎 STT 配置不完整：需要 appid 和 api_key")
            return ""

        headers = {
            "X-Api-App-Key": self.appid,
            "X-Api-Access-Key": self.api_key,
            "X-Api-Resource-Id": "volc.bigasr.auc_turbo",
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Sequence": "-1",
        }

        try:
            audio_data = file_path.read_bytes()
            audio_b64 = base64.b64encode(audio_data).decode()
        except Exception as e:
            logger.error(f"读取音频文件失败: {e}")
            return ""

        request_body = {
            "user": {"uid": str(uuid.uuid4())},
            "audio": {"data": audio_b64},
            "request": {"model_name": "bigmodel"},
        }

        timeout = aiohttp.ClientTimeout(total=30)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.base_url, json=request_body, headers=headers
                ) as resp:
                    if resp.status != 200:
                        content = await resp.text()
                        logger.debug(f"原始数据{content}")
                        error_msg = content.get("message", "未知错误")
                        logger.error(
                            f"火山引擎 STT 识别失败 (Status: {resp.status}): {error_msg}"
                        )
                        return ""

                    status_code = resp.headers.get("X-Api-Status-Code")
                    data = await resp.json()
                    if status_code == "20000000":
                        text = data.get("result", {}).get("text", "")
                        return text
                    elif status_code == "20000001":
                        logger.warning("火山引擎 STT 正在处理中")
                        return "音频文件正在处理中"
                    elif status_code == "20000002":
                        logger.warning("任务在队列中")
                        return "音频文件在队列中"
                    elif status_code == "20000003":
                        logger.warning("空文本语音")
                        return "用户输入内容为空"
                    elif status_code == "45000001":
                        logger.warning(
                            "火山引擎 STT 请求参数缺失必需字段 / 字段值无效 / 重复请求"
                        )
                        return (
                            "火山引擎 STT 请求参数缺失必需字段 / 字段值无效 / 重复请求"
                        )
                    elif status_code == "45000002":
                        logger.warning("火山引擎 STT 空音频")
                        return "用户输入内容为空"
                    elif status_code == "45000151":
                        logger.warning("火山引擎 STT 音频格式不支持")
                        return "音频格式不支持"
                    elif status_code == "55000031":
                        logger.warning("火山引擎stt服务过载，无法处理当前请求。")
                        return "火山引擎stt服务过载，无法处理当前请求。"
                    elif status_code.startswith("550"):
                        logger.warning("火山引擎stt服务内部处理错误")
                        return "火山引擎stt服务内部处理错误"
                    else:
                        error_msg = data.get("message", "未知业务错误")
                        full_error = f"火山引擎 STT API 业务错误 (Code: {status_code}): {error_msg}"
                        logger.error(full_error)
                        return "火山引擎stt服务内部处理错误"

        except asyncio.TimeoutError:
            error_msg = "火山引擎 STT 请求超时 (超过 300 秒)"
            logger.error(error_msg)
            return "火山引擎 STT 请求超时 (超过 300 秒)"

        except aiohttp.ClientError as e:
            error_msg = f"火山引擎 STT 网络请求错误: {e}"
            logger.error(error_msg)
            return "火山引擎 STT 网络请求错误"

        except Exception as e:
            # 避免重复抛出已经包装过的异常
            if isinstance(
                e, (ValueError, IOError, ConnectionError, TimeoutError, RuntimeError)
            ):
                raise
            error_msg = f"火山引擎 STT 发生未知异常: {e}"
            logger.error(error_msg)
            return "火山引擎stt服务内部处理错误"

    async def get_audio_size(self, audio_url: str) -> int:
        """获取音频文件大小（字节）"""
        if audio_url.startswith("http"):
            # 远程文件：使用 HEAD 请求获取 Content-Length
            async with aiohttp.ClientSession() as session:
                async with session.head(audio_url) as resp:
                    return int(resp.headers.get("Content-Length", 0))
        else:
            # 本地文件
            path = Path(audio_url)
            if path.exists():
                return path.stat().st_size
        return 0
