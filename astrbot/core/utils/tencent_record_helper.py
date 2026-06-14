import asyncio
import base64
import os
import subprocess
import tempfile
import wave
from io import BytesIO

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path


async def tencent_silk_to_wav(silk_path: str, output_path: str) -> str:
    import pysilk

    with open(silk_path, "rb") as f:
        input_data = f.read()
        if input_data.startswith(b"\x02"):
            input_data = input_data[1:]
        input_io = BytesIO(input_data)
        output_io = BytesIO()
        pysilk.decode(input_io, output_io, 24000)
        output_io.seek(0)
        with wave.open(output_path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(output_io.read())

    return output_path


async def wav_to_tencent_silk(wav_path: str, output_path: str) -> float:
    """Encode a WAV file to Tencent Silk.

    Args:
        wav_path: Input WAV file path.
        output_path: Output Tencent Silk file path.

    Returns:
        Audio duration in seconds.
    """
    try:
        import pysilk
    except (ImportError, ModuleNotFoundError) as _:
        raise Exception(
            "pysilk 模块未安装，请前往管理面板->平台日志->安装 silk-python 这个库",
        )

    with wave.open(wav_path, "rb") as wav:
        rate = wav.getframerate()
        frames = wav.getnframes()
        pcm_data = wav.readframes(frames)

    input_io = BytesIO(pcm_data)
    output_io = BytesIO()
    pysilk.encode(input_io, output_io, rate, rate, tencent=True)
    with open(output_path, "wb") as f:
        f.write(output_io.getvalue())
    return frames / rate if rate else 0


async def convert_to_pcm_wav(input_path: str, output_path: str) -> str:
    """将 MP3 或其他音频格式转换为 PCM 16bit WAV，采样率24000Hz，单声道。
    若转换失败则抛出异常。
    """
    try:
        from pyffmpeg import FFmpeg

        ff = FFmpeg()
        ff.convert(input_file=input_path, output_file=output_path)
    except Exception as e:
        logger.debug(f"pyffmpeg 转换失败: {e}, 尝试使用 ffmpeg 命令行进行转换")

        p = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-acodec",
            "pcm_s16le",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-af",
            "apad=pad_dur=2",
            "-fflags",
            "+genpts",
            "-hide_banner",
            output_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await p.communicate()
        logger.info(f"[FFmpeg] stdout: {stdout.decode().strip()}")
        logger.debug(f"[FFmpeg] stderr: {stderr.decode().strip()}")
        logger.info(f"[FFmpeg] return code: {p.returncode}")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return output_path
    raise RuntimeError("生成的WAV文件不存在或为空")


async def audio_to_tencent_silk_base64(audio_path: str) -> tuple[str, float]:
    """Encode an audio file to Tencent Silk base64.

    Args:
        audio_path: Input audio file path. Non-WAV input is converted to WAV first.

    Returns:
        A tuple containing the base64 encoded Tencent Silk payload and duration in
        seconds.
    """
    try:
        import pysilk
    except ImportError as e:
        raise Exception("未安装 pysilk: pip install silk-python") from e

    temp_dir = get_astrbot_temp_path()
    os.makedirs(temp_dir, exist_ok=True)

    # 是否需要转换为 WAV
    ext = os.path.splitext(audio_path)[1].lower()
    temp_wav = tempfile.NamedTemporaryFile(
        prefix="tencent_record_",
        suffix=".wav",
        delete=False,
        dir=temp_dir,
    ).name

    if ext != ".wav":
        await convert_to_pcm_wav(audio_path, temp_wav)
        # 删除原文件
        os.remove(audio_path)
        wav_path = temp_wav
    else:
        wav_path = audio_path

    with wave.open(wav_path, "rb") as wav_file:
        rate = wav_file.getframerate()
        frames = wav_file.getnframes()
        pcm_data = wav_file.readframes(frames)

    silk_path = tempfile.NamedTemporaryFile(
        prefix="tencent_record_",
        suffix=".silk",
        delete=False,
        dir=temp_dir,
    ).name

    try:
        input_io = BytesIO(pcm_data)
        output_io = BytesIO()
        await asyncio.to_thread(
            pysilk.encode,
            input_io,
            output_io,
            rate,
            rate,
            tencent=True,
        )

        with open(silk_path, "wb") as f:
            await asyncio.to_thread(f.write, output_io.getvalue())

        with open(silk_path, "rb") as f:
            silk_bytes = await asyncio.to_thread(f.read)
            silk_b64 = base64.b64encode(silk_bytes).decode("utf-8")

        return silk_b64, frames / rate if rate else 0
    finally:
        if os.path.exists(wav_path) and wav_path != audio_path:
            os.remove(wav_path)
        if os.path.exists(silk_path):
            os.remove(silk_path)
