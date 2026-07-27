import asyncio
import audioop
import base64
import os
import subprocess
import tempfile
import wave
from io import BytesIO

import anyio
import pysilk  # requires silk-python (core dependency)

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

# The SILK SDK only supports these rates
_PYSILK_SUPPORTED_RATES = frozenset({8000, 12000, 16000, 24000, 32000, 48000})


async def tencent_silk_to_wav(silk_path: str, output_path: str) -> str:
    async with await anyio.open_file(silk_path, "rb") as f:
        input_data = await f.read()
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
    """Encode a WAV file as Tencent SILK and return its duration."""
    with wave.open(wav_path, "rb") as wav:
        rate = wav.getframerate()
        channels = wav.getnchannels()
        sampwidth = wav.getsampwidth()
        pcm_data = wav.readframes(wav.getnframes())

    # Downmix to mono, resample to 24 kHz if needed, and convert to 16-bit PCM
    # (pysilk only accepts 16-bit linear PCM)
    if channels == 2:
        pcm_data = audioop.tomono(pcm_data, sampwidth, 0.5, 0.5)
    if rate not in _PYSILK_SUPPORTED_RATES:
        pcm_data, _ = audioop.ratecv(pcm_data, sampwidth, 1, rate, 24000, None)
        rate = 24000
    if sampwidth != 2:
        pcm_data = audioop.lin2lin(pcm_data, sampwidth, 2)

    input_io = BytesIO(pcm_data)
    output_io = BytesIO()
    # tencent=True makes pysilk emit the QQ-compatible 0x02-prefixed SILK stream.
    pysilk.encode(input_io, output_io, rate, rate, tencent=True)
    with open(output_path, "wb") as f:
        f.write(output_io.getvalue())
    return len(pcm_data) / (2 * rate) if rate else 0


async def convert_to_pcm_wav(input_path: str, output_path: str) -> str:
    """将 MP3 或其他音频格式转换为 PCM 16bit WAV,采样率24000Hz,单声道｡
    若转换失败则抛出异常｡
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

    if (
        await anyio.Path(output_path).exists()
        and (await anyio.Path(output_path).stat()).st_size > 0
    ):
        return output_path
    raise RuntimeError("生成的WAV文件不存在或为空")


async def audio_to_tencent_silk_base64(audio_path: str) -> tuple[str, float]:
    """将 MP3/WAV 文件转为 Tencent Silk 并返回 base64 编码与时长(秒)｡

    参数:
    - audio_path: 输入音频文件路径(.mp3 或 .wav)

    返回:
    - silk_b64: Base64 编码的 Silk 字符串
    - duration: 音频时长(秒)
    """
    try:
        import pilk
    except ImportError as e:
        raise Exception("未安装 pilk: pip install pilk") from e  # noqa

    temp_dir = get_astrbot_temp_path()
    await anyio.Path(temp_dir).mkdir(parents=True, exist_ok=True)

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
        await anyio.Path(audio_path).unlink()
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

        async with await anyio.open_file(silk_path, "rb") as f:
            silk_bytes = await f.read()
            silk_b64 = base64.b64encode(silk_bytes).decode("utf-8")

        return silk_b64, duration  # 已是秒
    finally:
        if await anyio.Path(wav_path).exists() and wav_path != audio_path:
            await anyio.Path(wav_path).unlink()
        if await anyio.Path(silk_path).exists():
            await anyio.Path(silk_path).unlink()
