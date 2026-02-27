from astrbot.core.lang import t
import asyncio
import os
import subprocess
import uuid

import edge_tts

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter

"""
edge_tts 方式，能够免费、快速生成语音，使用需要先安装edge-tts库
```
pip install edge_tts
```
Windows 如果提示找不到指定文件，以管理员身份运行命令行窗口，然后再次运行 AstrBot
"""


@register_provider_adapter(
    "edge_tts",
    "Microsoft Edge TTS",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderEdgeTTS(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)

        # 设置默认语音，如果没有指定则使用中文小萱
        self.voice = provider_config.get("edge-tts-voice", "zh-CN-XiaoxiaoNeural")
        self.rate = provider_config.get("rate")
        self.volume = provider_config.get("volume")
        self.pitch = provider_config.get("pitch")
        self.timeout = provider_config.get("timeout", 30)

        self.proxy = os.getenv("https_proxy", None)

        self.set_model("edge_tts")

    async def get_audio(self, text: str) -> str:
        temp_dir = get_astrbot_temp_path()
        mp3_path = os.path.join(temp_dir, f"edge_tts_temp_{uuid.uuid4()}.mp3")
        wav_path = os.path.join(temp_dir, f"edge_tts_{uuid.uuid4()}.wav")

        # 构建 Edge TTS 参数
        kwargs = {"text": text, "voice": self.voice}
        if self.rate:
            kwargs["rate"] = self.rate
        if self.volume:
            kwargs["volume"] = self.volume
        if self.pitch:
            kwargs["pitch"] = self.pitch

        try:
            communicate = edge_tts.Communicate(proxy=self.proxy, **kwargs)
            await communicate.save(mp3_path)

            try:
                from pyffmpeg import FFmpeg

                ff = FFmpeg()
                ff.convert(input_file=mp3_path, output_file=wav_path)
            except Exception as e:
                logger.debug(t("msg-f4ab0713", e=e))
                # use ffmpeg command line

                # 使用ffmpeg将MP3转换为标准WAV格式
                p = await asyncio.create_subprocess_exec(
                    "ffmpeg",
                    "-y",  # 覆盖输出文件
                    "-i",
                    mp3_path,  # 输入文件
                    "-acodec",
                    "pcm_s16le",  # 16位PCM编码
                    "-ar",
                    "24000",  # 采样率24kHz (适合微信语音)
                    "-ac",
                    "1",  # 单声道
                    "-af",
                    "apad=pad_dur=2",  # 确保输出时长准确
                    "-fflags",
                    "+genpts",  # 强制生成时间戳
                    "-hide_banner",  # 隐藏版本信息
                    wav_path,  # 输出文件
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                # 等待进程完成并获取输出
                stdout, stderr = await p.communicate()
                logger.info(t("msg-ddc3594a", res=stdout.decode().strip()))
                logger.debug(t("msg-1b8c0a83", res=stderr.decode().strip()))
                logger.info(t("msg-1e980a68", res=p.returncode))

            os.remove(mp3_path)
            if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
                return wav_path
            logger.error(t("msg-c39d210c"))
            raise RuntimeError(t("msg-c39d210c"))

        except subprocess.CalledProcessError as e:
            logger.error(
                t("msg-57f60837", res=e.stderr.decode() if e.stderr else str(e)),
            )
            try:
                if os.path.exists(mp3_path):
                    os.remove(mp3_path)
            except Exception:
                pass
            raise RuntimeError(t("msg-ca94a42a", e=e))

        except Exception as e:
            logger.error(t("msg-be660d63", e=e))
            try:
                if os.path.exists(mp3_path):
                    os.remove(mp3_path)
            except Exception:
                pass
            raise RuntimeError(t("msg-be660d63", e=e))
