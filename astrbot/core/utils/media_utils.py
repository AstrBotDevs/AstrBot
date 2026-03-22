"""媒体文件处理工具

提供音视频格式转换｡时长获取等功能｡

"""

import asyncio
import base64
import io
import os
import subprocess
import uuid
from pathlib import Path

import anyio
from PIL import Image as PILImage

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

IMAGE_COMPRESS_DEFAULT_MAX_SIZE = 1280
IMAGE_COMPRESS_DEFAULT_QUALITY = 95
IMAGE_COMPRESS_DEFAULT_OPTIMIZE = True
IMAGE_COMPRESS_DEFAULT_MIN_FILE_SIZE_MB = 1.0


async def get_media_duration(file_path: str) -> int | None:
    """使用ffprobe获取媒体文件时长

    Args:
        file_path: 媒体文件路径

    Returns:
        时长(毫秒),如果获取失败返回None
    """
    try:
        # 使用ffprobe获取时长
        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            file_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, _stderr = await process.communicate()

        if process.returncode == 0 and stdout:
            duration_seconds = float(stdout.decode().strip())
            duration_ms = int(duration_seconds * 1000)
            logger.debug(f"[Media Utils] 获取媒体时长: {duration_ms}ms")
            return duration_ms
        else:
            logger.warning(f"[Media Utils] 无法获取媒体文件时长: {file_path}")
            return None

    except FileNotFoundError:
        logger.warning(
            "[Media Utils] ffprobe未安装或不在PATH中,无法获取媒体时长｡请安装ffmpeg: https://ffmpeg.org/"
        )
        return None
    except Exception as e:
        logger.warning(f"[Media Utils] 获取媒体时长时出错: {e}")
        return None


async def convert_audio_to_opus(audio_path: str, output_path: str | None = None) -> str:
    """使用ffmpeg将音频转换为opus格式

    Args:
        audio_path: 原始音频文件路径
        output_path: 输出文件路径,如果为None则自动生成

    Returns:
        转换后的opus文件路径

    Raises:
        Exception: 转换失败时抛出异常
    """
    # 如果已经是opus格式,直接返回
    if audio_path.lower().endswith(".opus"):
        return audio_path

    # 生成输出文件路径
    if output_path is None:
        temp_dir = get_astrbot_temp_path()
        await anyio.Path(temp_dir).mkdir(parents=True, exist_ok=True)
        output_path = os.path.join(temp_dir, f"media_audio_{uuid.uuid4().hex}.opus")

    try:
        # 使用ffmpeg转换为opus格式
        # -y: 覆盖输出文件
        # -i: 输入文件
        # -acodec libopus: 使用opus编码器
        # -ac 1: 单声道
        # -ar 16000: 采样率16kHz
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            audio_path,
            "-acodec",
            "libopus",
            "-ac",
            "1",
            "-ar",
            "16000",
            output_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        _stdout, stderr = await process.communicate()

        if process.returncode != 0:
            # 清理可能已生成但无效的临时文件
            if output_path and await anyio.Path(output_path).exists():
                try:
                    await anyio.Path(output_path).unlink()
                    logger.debug(
                        f"[Media Utils] 已清理失败的opus输出文件: {output_path}"
                    )
                except OSError as e:
                    logger.warning(f"[Media Utils] 清理失败的opus输出文件时出错: {e}")

            error_msg = stderr.decode() if stderr else "未知错误"
            logger.error(f"[Media Utils] ffmpeg转换音频失败: {error_msg}")
            raise Exception(f"ffmpeg conversion failed: {error_msg}")

        logger.debug(f"[Media Utils] 音频转换成功: {audio_path} -> {output_path}")
        return output_path

    except FileNotFoundError:
        logger.error(
            "[Media Utils] ffmpeg未安装或不在PATH中,无法转换音频格式｡请安装ffmpeg: https://ffmpeg.org/"
        )
        raise Exception("ffmpeg not found")
    except Exception as e:
        logger.error(f"[Media Utils] 转换音频格式时出错: {e}")
        raise


async def convert_video_format(
    video_path: str, output_format: str = "mp4", output_path: str | None = None
) -> str:
    """使用ffmpeg转换视频格式

    Args:
        video_path: 原始视频文件路径
        output_format: 目标格式,默认mp4
        output_path: 输出文件路径,如果为None则自动生成

    Returns:
        转换后的视频文件路径

    Raises:
        Exception: 转换失败时抛出异常
    """
    # 如果已经是目标格式,直接返回
    if video_path.lower().endswith(f".{output_format}"):
        return video_path

    # 生成输出文件路径
    if output_path is None:
        temp_dir = get_astrbot_temp_path()
        await anyio.Path(temp_dir).mkdir(parents=True, exist_ok=True)
        output_path = os.path.join(
            temp_dir,
            f"media_video_{uuid.uuid4().hex}.{output_format}",
        )

    try:
        # 使用ffmpeg转换视频格式
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            output_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        _stdout, stderr = await process.communicate()

        if process.returncode != 0:
            # 清理可能已生成但无效的临时文件
            if output_path and await anyio.Path(output_path).exists():
                try:
                    await anyio.Path(output_path).unlink()
                    logger.debug(
                        f"[Media Utils] 已清理失败的{output_format}输出文件: {output_path}"
                    )
                except OSError as e:
                    logger.warning(
                        f"[Media Utils] 清理失败的{output_format}输出文件时出错: {e}"
                    )

            error_msg = stderr.decode() if stderr else "未知错误"
            logger.error(f"[Media Utils] ffmpeg转换视频失败: {error_msg}")
            raise Exception(f"ffmpeg conversion failed: {error_msg}")

        logger.debug(f"[Media Utils] 视频转换成功: {video_path} -> {output_path}")
        return output_path

    except FileNotFoundError:
        logger.error(
            "[Media Utils] ffmpeg未安装或不在PATH中,无法转换视频格式｡请安装ffmpeg: https://ffmpeg.org/"
        )
        raise Exception("ffmpeg not found")
    except Exception as e:
        logger.error(f"[Media Utils] 转换视频格式时出错: {e}")
        raise


async def convert_audio_format(
    audio_path: str,
    output_format: str = "amr",
    output_path: str | None = None,
) -> str:
    """使用ffmpeg将音频转换为指定格式｡

    Args:
        audio_path: 原始音频文件路径
        output_format: 目标格式,例如 amr / ogg
        output_path: 输出文件路径,如果为None则自动生成

    Returns:
        转换后的音频文件路径
    """
    if audio_path.lower().endswith(f".{output_format}"):
        return audio_path

    if output_path is None:
        temp_dir = anyio.Path(get_astrbot_temp_path())
        await temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(temp_dir / f"media_audio_{uuid.uuid4().hex}.{output_format}")

    args = ["ffmpeg", "-y", "-i", audio_path]
    if output_format == "amr":
        args.extend(["-ac", "1", "-ar", "8000", "-ab", "12.2k"])
    elif output_format == "ogg":
        args.extend(["-acodec", "libopus", "-ac", "1", "-ar", "16000"])
    args.append(output_path)

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            if output_path and await anyio.Path(output_path).exists():
                try:
                    await anyio.Path(output_path).unlink()
                except OSError as e:
                    logger.warning(f"[Media Utils] 清理失败的音频输出文件时出错: {e}")
            error_msg = stderr.decode() if stderr else "未知错误"
            raise Exception(f"ffmpeg conversion failed: {error_msg}")
        logger.debug(f"[Media Utils] 音频转换成功: {audio_path} -> {output_path}")
        return output_path
    except FileNotFoundError:
        raise Exception("ffmpeg not found")


async def convert_audio_to_amr(audio_path: str, output_path: str | None = None) -> str:
    """将音频转换为amr格式｡"""
    return await convert_audio_format(
        audio_path=audio_path,
        output_format="amr",
        output_path=output_path,
    )


async def convert_audio_to_wav(audio_path: str, output_path: str | None = None) -> str:
    """将音频转换为wav格式｡"""
    return await convert_audio_format(
        audio_path=audio_path,
        output_format="wav",
        output_path=output_path,
    )


async def extract_video_cover(
    video_path: str,
    output_path: str | None = None,
) -> str:
    """从视频中提取封面图(JPG)｡"""
    if output_path is None:
        temp_dir = anyio.Path(get_astrbot_temp_path())
        await temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(temp_dir / f"media_cover_{uuid.uuid4().hex}.jpg")

    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-ss",
            "00:00:00",
            "-frames:v",
            "1",
            output_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            if output_path and await anyio.Path(output_path).exists():
                try:
                    await anyio.Path(output_path).unlink()
                except OSError as e:
                    logger.warning(f"[Media Utils] 清理失败的视频封面文件时出错: {e}")
            error_msg = stderr.decode() if stderr else "未知错误"
            raise Exception(f"ffmpeg extract cover failed: {error_msg}")
        return output_path
    except FileNotFoundError:
        raise Exception("ffmpeg not found")


def _compress_image_sync(
    data: bytes,
    temp_dir: Path,
    max_size: int,
    quality: int,
    optimize: bool,
) -> str:
    """Run image compression synchronously via ``asyncio.to_thread``."""
    with PILImage.open(io.BytesIO(data)) as opened_img:
        img = opened_img
        converted_img: PILImage.Image | None = None

        try:
            if img.mode != "RGB":
                converted_img = img.convert("RGB")
                img = converted_img

            if max(img.size) > max_size:
                img.thumbnail((max_size, max_size), PILImage.Resampling.LANCZOS)

            new_uuid = uuid.uuid4().hex
            save_path = temp_dir / f"compressed_{new_uuid}.jpg"
            img.save(save_path, "JPEG", quality=quality, optimize=optimize)
            logger.debug(f"Image compressed successfully: {save_path}")
            return str(save_path)
        finally:
            if converted_img is not None:
                converted_img.close()


async def compress_image(
    url_or_path: str,
    max_size: int = IMAGE_COMPRESS_DEFAULT_MAX_SIZE,
    quality: int = IMAGE_COMPRESS_DEFAULT_QUALITY,
) -> str:
    """Compress large user-uploaded images.

    Args:
        url_or_path: Image path or URL.
        max_size: Longest edge of the compressed image in pixels.
        quality: JPEG output quality in the range 1-100.

    Returns:
        The compressed image path. Returns the original path if compression
        fails or the source does not need compression.
    """
    max_size = max(int(max_size), 1)
    quality = min(max(int(quality), 1), 100)
    optimize = IMAGE_COMPRESS_DEFAULT_OPTIMIZE
    min_file_size_bytes = int(IMAGE_COMPRESS_DEFAULT_MIN_FILE_SIZE_MB * 1024 * 1024)
    data = None
    # Skip compression for remote images and return the original value.
    if url_or_path.startswith("http"):
        return url_or_path
    elif url_or_path.startswith("data:image"):
        _header, encoded = url_or_path.split(",", 1)
        data = base64.b64decode(encoded)
        if len(data) < min_file_size_bytes:
            return url_or_path
    else:
        local_path = Path(url_or_path)
        if not local_path.exists():
            return url_or_path
        if local_path.stat().st_size < min_file_size_bytes:
            return url_or_path
        with local_path.open("rb") as f:
            data = f.read()

    if not data:
        return url_or_path

    temp_dir = Path(get_astrbot_temp_path())
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Offload the blocking image processing task to a thread.
    return await asyncio.to_thread(
        _compress_image_sync,
        data,
        temp_dir,
        max_size,
        quality,
        optimize,
    )
