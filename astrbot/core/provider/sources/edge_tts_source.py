import asyncio
import importlib
import subprocess
import uuid
from pathlib import Path

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.error_redaction import safe_error

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

_AUDIO_GENERATION_ERROR = "Edge TTS audio generation failed."
_PROCESS_SHUTDOWN_TIMEOUT = 5.0


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
        self.timeout = self._get_timeout(provider_config.get("timeout", 30))

        from astrbot.core.utils.proxy_route import resolve_proxy_route

        self.proxy = resolve_proxy_route(local_config=provider_config).proxy_url

        self.set_model("edge_tts")

    @staticmethod
    def _get_timeout(value: object) -> float:
        if not isinstance(value, (str, int, float)):
            return 30.0
        try:
            timeout = float(value)
        except TypeError, ValueError:
            return 30.0
        return timeout if timeout > 0 else 30.0

    @staticmethod
    def _remove_file(path: Path, description: str) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(
                "Failed to remove incomplete Edge TTS %s: %s",
                description,
                safe_error("", exc),
            )

    @staticmethod
    async def _stop_ffmpeg_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return

        try:
            process.terminate()
        except ProcessLookupError:
            return

        try:
            await asyncio.wait_for(process.wait(), timeout=_PROCESS_SHUTDOWN_TIMEOUT)
            return
        except TimeoutError:
            pass
        except OSError as exc:
            logger.warning(
                "Failed while waiting for Edge TTS ffmpeg to stop: %s",
                safe_error("", exc),
            )
            return

        try:
            process.kill()
        except ProcessLookupError:
            return
        except OSError as exc:
            logger.warning(
                "Failed to kill Edge TTS ffmpeg: %s",
                safe_error("", exc),
            )
            return

        try:
            await asyncio.wait_for(process.wait(), timeout=_PROCESS_SHUTDOWN_TIMEOUT)
        except TimeoutError:
            logger.warning("Edge TTS ffmpeg did not exit after it was killed.")
        except OSError as exc:
            logger.warning(
                "Failed while waiting for killed Edge TTS ffmpeg: %s",
                safe_error("", exc),
            )

    async def _convert_with_ffmpeg(self, mp3_path: Path, wav_path: Path) -> None:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",  # 覆盖输出文件
            "-i",
            str(mp3_path),  # 输入文件
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
            str(wav_path),  # 输出文件
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(process.communicate(), timeout=self.timeout)
        except asyncio.CancelledError:
            await self._stop_ffmpeg_process(process)
            raise
        except TimeoutError:
            await self._stop_ffmpeg_process(process)
            raise RuntimeError("Edge TTS ffmpeg conversion timed out.") from None

        if process.returncode != 0:
            raise RuntimeError("Edge TTS ffmpeg conversion failed.")

    async def get_audio(self, text: str) -> str:
        try:
            edge_tts_module = importlib.import_module("edge_tts")
        except ImportError:
            raise RuntimeError("edge_tts is not installed") from None
        except Exception as exc:
            logger.error("Edge TTS module loading failed: %s", safe_error("", exc))
            raise RuntimeError(_AUDIO_GENERATION_ERROR) from None

        mp3_path: Path | None = None
        wav_path: Path | None = None
        completed = False

        try:
            temp_dir = Path(get_astrbot_temp_path())
            temp_dir.mkdir(parents=True, exist_ok=True)
            mp3_path = temp_dir / f"edge_tts_temp_{uuid.uuid4()}.mp3"
            wav_path = temp_dir / f"edge_tts_{uuid.uuid4()}.wav"

            # 构建 Edge TTS 参数
            kwargs = {"text": text, "voice": self.voice}
            if self.rate:
                kwargs["rate"] = self.rate
            if self.volume:
                kwargs["volume"] = self.volume
            if self.pitch:
                kwargs["pitch"] = self.pitch

            communicate = edge_tts_module.Communicate(proxy=self.proxy, **kwargs)
            await asyncio.wait_for(
                communicate.save(str(mp3_path)), timeout=self.timeout
            )

            try:
                pyffmpeg_module = importlib.import_module("pyffmpeg")
                ff = pyffmpeg_module.FFmpeg()
                ff.convert(input_file=str(mp3_path), output_file=str(wav_path))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug(
                    "Edge TTS pyffmpeg conversion failed; falling back to ffmpeg: %s",
                    safe_error("", exc),
                )
                await self._convert_with_ffmpeg(mp3_path, wav_path)

            if not wav_path.is_file() or wav_path.stat().st_size <= 0:
                raise RuntimeError("Edge TTS did not produce audio.")

            completed = True
            return str(wav_path)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Edge TTS generation failed: %s", safe_error("", exc))
            raise RuntimeError(_AUDIO_GENERATION_ERROR) from None
        finally:
            if mp3_path is not None:
                self._remove_file(mp3_path, "MP3 audio")
            if wav_path is not None and not completed:
                self._remove_file(wav_path, "WAV audio")
