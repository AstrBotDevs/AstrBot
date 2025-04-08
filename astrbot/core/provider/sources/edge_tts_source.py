import uuid
import os
import edge_tts
import subprocess
import asyncio
from ..provider import TTSProvider
from ..entities import ProviderType
from ..register import register_provider_adapter
from astrbot.core import logger

"""
edge_tts 方式，能够免费、快速生成语音，使用需要先安装edge-tts库
```
pip install edge_tts
```
Windows 如果提示找不到指定文件，以管理员身份运行命令行窗口，然后再次运行 AstrBot
"""


@register_provider_adapter(
    "edge_tts", "Microsoft Edge TTS", provider_type=ProviderType.TEXT_TO_SPEECH
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
        self.rate = provider_config.get("rate", None)
        self.volume = provider_config.get("volume", None)
        self.pitch = provider_config.get("pitch", None)
        self.timeout = provider_config.get("timeout", 30)

        self.proxy = os.getenv("https_proxy", None)

        self.set_model("edge_tts")

    async def get_audio(self, text: str) -> str:
        os.makedirs("data/temp", exist_ok=True)
        mp3_path = f"data/temp/edge_tts_temp_{uuid.uuid4()}.mp3"
        wav_path = f"data/temp/edge_tts_{uuid.uuid4()}.wav"

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
                ff.convert(input=mp3_path, output=wav_path)
            except Exception as e:
                logger.debug(f"pyffmpeg 转换失败: {e}, 尝试使用 ffmpeg 命令行进行转换")
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
                logger.info(f"[EdgeTTS] FFmpeg 标准输出: {stdout.decode().strip()}")
                logger.debug(f"FFmpeg错误输出: {stderr.decode().strip()}")
                logger.info(f"[EdgeTTS] 返回值(0代表成功): {p.returncode}")

            os.remove(mp3_path)
            if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
                return wav_path
            else:
                logger.error("生成的WAV文件不存在或为空")
                raise RuntimeError("生成的WAV文件不存在或为空")

        except subprocess.CalledProcessError as e:
            logger.error(
                f"FFmpeg 转换失败: {e.stderr.decode() if e.stderr else str(e)}"
            )
            try:
                if os.path.exists(mp3_path):
                    os.remove(mp3_path)
            except Exception:
                pass
            raise RuntimeError(f"FFmpeg 转换失败: {str(e)}")

        except Exception as e:
            logger.error(f"音频生成失败: {str(e)}")
            try:
                if os.path.exists(mp3_path):
                    os.remove(mp3_path)
            except Exception:
                pass
            raise RuntimeError(f"音频生成失败: {str(e)}")
