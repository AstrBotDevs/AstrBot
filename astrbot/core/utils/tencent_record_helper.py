from astrbot.core.lang import t
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


async def wav_to_tencent_silk(wav_path: str, output_path: str) -> int:
    """返回 duration"""
    try:
        import pilk
    except (ImportError, ModuleNotFoundError) as _:
        raise Exception(
            t("msg-377ae139"),
        )
    # with wave.open(wav_path, 'rb') as wav:
    #     wav_data = wav.readframes(wav.getnframes())
    #     wav_data = BytesIO(wav_data)
    #     output_io = BytesIO()
    #     pysilk.encode(wav_data, output_io, 24000, 24000)
    #     output_io.seek(0)

    #     # 在首字节添加 \x02,去除结尾的\xff\xff
    #     silk_data = output_io.read()
    #     silk_data_with_prefix = b'\x02' + silk_data[:-2]

    #     # return BytesIO(silk_data_with_prefix)
    #     with open(output_path, "wb") as f:
    #         f.write(silk_data_with_prefix)

    #     return 0
    with wave.open(wav_path, "rb") as wav:
        rate = wav.getframerate()
        duration = pilk.encode(wav_path, output_path, pcm_rate=rate, tencent=True)
        return duration


async def convert_to_pcm_wav(input_path: str, output_path: str) -> str:
    """将 MP3 或其他音频格式转换为 PCM 16bit WAV，采样率24000Hz，单声道。
    若转换失败则抛出异常。
    """
    try:
        from pyffmpeg import FFmpeg

        ff = FFmpeg()
        ff.convert(input_file=input_path, output_file=output_path)
    except Exception as e:
        logger.debug(t("msg-f4ab0713", e=e))

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
        logger.info(t("msg-33c88889", res=stdout.decode().strip()))
        logger.debug(t("msg-2470430c", res=stderr.decode().strip()))
        logger.info(t("msg-1321d5f7", res=p.returncode))

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return output_path
    raise RuntimeError(t("msg-c39d210c"))


async def audio_to_tencent_silk_base64(audio_path: str) -> tuple[str, float]:
    """将 MP3/WAV 文件转为 Tencent Silk 并返回 base64 编码与时长（秒）。

    参数:
    - audio_path: 输入音频文件路径（.mp3 或 .wav）

    返回:
    - silk_b64: Base64 编码的 Silk 字符串
    - duration: 音频时长（秒）
    """
    try:
        import pilk
    except ImportError as e:
        raise Exception(t("msg-6e04bdb8", e=e)) from e

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

    silk_path = tempfile.NamedTemporaryFile(
        prefix="tencent_record_",
        suffix=".silk",
        delete=False,
        dir=temp_dir,
    ).name

    try:
        duration = await asyncio.to_thread(
            pilk.encode,
            wav_path,
            silk_path,
            pcm_rate=rate,
            tencent=True,
        )

        with open(silk_path, "rb") as f:
            silk_bytes = await asyncio.to_thread(f.read)
            silk_b64 = base64.b64encode(silk_bytes).decode("utf-8")

        return silk_b64, duration  # 已是秒
    finally:
        if os.path.exists(wav_path) and wav_path != audio_path:
            os.remove(wav_path)
        if os.path.exists(silk_path):
            os.remove(silk_path)
