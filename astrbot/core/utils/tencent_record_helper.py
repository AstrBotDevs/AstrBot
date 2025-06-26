import base64
import wave
import os
import subprocess
from io import BytesIO
import asyncio
import tempfile
from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


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
            "pilk 模块未安装，请前往管理面板->控制台->安装pip库 安装 pilk 这个库"
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
    """
    将 MP3 或其他音频格式转换为 PCM 16bit WAV，采样率24000Hz，单声道。
    若转换失败则抛出异常。
    """
    try:
        from pyffmpeg import FFmpeg

        ff = FFmpeg()
        ff.convert(input=input_path, output=output_path)
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
    else:
        raise RuntimeError("生成的WAV文件不存在或为空")


async def audio_to_tencent_silk_base64(audio_path: str) -> tuple[str, float]:
    """
    将 MP3/WAV 文件转为 Tencent Silk 并返回 base64 编码与时长（秒）。

    参数:
    - audio_path: 输入音频文件路径（.mp3 或 .wav）

    返回:
    - silk_b64: Base64 编码的 Silk 字符串
    - duration: 音频时长（秒）
    """
    try:
        import pilk
    except ImportError as e:
        raise Exception("未安装 pysilk，请执行: pip install pysilk") from e

    temp_dir = os.path.join(get_astrbot_data_path(), "temp")
    os.makedirs(temp_dir, exist_ok=True)

    # 是否需要转换为 WAV
    ext = os.path.splitext(audio_path)[1].lower()
    temp_wav = tempfile.NamedTemporaryFile(
        suffix=".wav", delete=False, dir=temp_dir
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
        suffix=".silk", delete=False, dir=temp_dir
    ).name

    try:
        duration = await asyncio.to_thread(
            pilk.encode, wav_path, silk_path, pcm_rate=rate, tencent=True
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
