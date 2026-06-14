"""Tencent Silk audio conversion helpers."""

import asyncio
import os
import subprocess
import wave
from io import BytesIO

from astrbot.core import logger


async def tencent_silk_to_wav(silk_path: str, output_path: str) -> str:
    """Decode a Tencent Silk file to 24 kHz mono PCM WAV.

    Args:
        silk_path: Input Tencent Silk file path.
        output_path: Output WAV file path.

    Returns:
        The output WAV file path.

    Raises:
        ImportError: Raised when ``silk-python`` is not installed.
        pysilk.SilkError: Raised when the Silk payload cannot be decoded.
        OSError: Raised when input or output files cannot be accessed.
    """
    import pysilk

    with open(silk_path, "rb") as f:
        input_data = f.read()
        # QQ/Tencent voice payloads may include a leading 0x02 marker before SILK.
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

    Raises:
        Exception: Raised when ``silk-python`` is not installed.
        OSError: Raised when input or output files cannot be accessed.
        wave.Error: Raised when the input file is not a readable WAV file.
    """
    try:
        import pysilk
    except (ImportError, ModuleNotFoundError) as e:
        raise Exception(
            "pysilk is not installed. Install the silk-python package from the "
            "dashboard platform logs page.",
        ) from e

    with wave.open(wav_path, "rb") as wav:
        rate = wav.getframerate()
        frames = wav.getnframes()
        pcm_data = wav.readframes(frames)

    input_io = BytesIO(pcm_data)
    output_io = BytesIO()
    # tencent=True makes pysilk emit the QQ-compatible 0x02-prefixed SILK stream.
    pysilk.encode(input_io, output_io, rate, rate, tencent=True)
    with open(output_path, "wb") as f:
        f.write(output_io.getvalue())
    return frames / rate if rate else 0


async def convert_to_pcm_wav(input_path: str, output_path: str) -> str:
    """Convert an audio file to 24 kHz mono 16-bit PCM WAV.

    Args:
        input_path: Source audio file path.
        output_path: Destination WAV file path.

    Returns:
        The output WAV file path.

    Raises:
        RuntimeError: Raised when conversion does not produce a non-empty WAV file.
    """
    try:
        from pyffmpeg import FFmpeg

        ff = FFmpeg()
        ff.convert(input_file=input_path, output_file=output_path)
    except Exception as e:
        logger.debug(
            "pyffmpeg conversion failed: %s. Falling back to ffmpeg CLI.",
            e,
        )

        # FFmpeg normalizes arbitrary audio input to the PCM WAV format required
        # by Tencent Silk encoding.
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
    raise RuntimeError("Converted WAV file is missing or empty")
