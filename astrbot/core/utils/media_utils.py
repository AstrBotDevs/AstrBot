"""媒体文件处理工具

提供音视频格式转换、时长获取等功能。
"""
from astrbot.core.lang import t

import asyncio
import os
import subprocess
import uuid
from pathlib import Path

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path


async def get_media_duration(file_path: str) -> int | None:
    """使用ffprobe获取媒体文件时长

    Args:
        file_path: 媒体文件路径

    Returns:
        时长（毫秒），如果获取失败返回None
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

        stdout, stderr = await process.communicate()

        if process.returncode == 0 and stdout:
            duration_seconds = float(stdout.decode().strip())
            duration_ms = int(duration_seconds * 1000)
            logger.debug(t("msg-2f697658", duration_ms=duration_ms))
            return duration_ms
        else:
            logger.warning(t("msg-52dfbc26", file_path=file_path))
            return None

    except FileNotFoundError:
        logger.warning(
            t("msg-486d493a")
        )
        return None
    except Exception as e:
        logger.warning(t("msg-0f9c647b", e=e))
        return None


async def convert_audio_to_opus(audio_path: str, output_path: str | None = None) -> str:
    """使用ffmpeg将音频转换为opus格式

    Args:
        audio_path: 原始音频文件路径
        output_path: 输出文件路径，如果为None则自动生成

    Returns:
        转换后的opus文件路径

    Raises:
        Exception: 转换失败时抛出异常
    """
    # 如果已经是opus格式，直接返回
    if audio_path.lower().endswith(".opus"):
        return audio_path

    # 生成输出文件路径
    if output_path is None:
        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)
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

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            # 清理可能已生成但无效的临时文件
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                    logger.debug(
                        t("msg-aff4c5f8", output_path=output_path)
                    )
                except OSError as e:
                    logger.warning(t("msg-82427384", e=e))

            error_msg = stderr.decode() if stderr else "未知错误"
            logger.error(t("msg-215a0cfc", error_msg=error_msg))
            raise Exception(t("msg-8cce258e", error_msg=error_msg))

        logger.debug(t("msg-f0cfcb92", audio_path=audio_path, output_path=output_path))
        return output_path

    except FileNotFoundError:
        logger.error(
            t("msg-ead1395b")
        )
        raise Exception(t("msg-5df3a5ee"))
    except Exception as e:
        logger.error(t("msg-6322d4d2", e=e))
        raise


async def convert_video_format(
    video_path: str, output_format: str = "mp4", output_path: str | None = None
) -> str:
    """使用ffmpeg转换视频格式

    Args:
        video_path: 原始视频文件路径
        output_format: 目标格式，默认mp4
        output_path: 输出文件路径，如果为None则自动生成

    Returns:
        转换后的视频文件路径

    Raises:
        Exception: 转换失败时抛出异常
    """
    # 如果已经是目标格式，直接返回
    if video_path.lower().endswith(f".{output_format}"):
        return video_path

    # 生成输出文件路径
    if output_path is None:
        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)
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

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            # 清理可能已生成但无效的临时文件
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                    logger.debug(
                        t("msg-e125b1a5", output_format=output_format, output_path=output_path)
                    )
                except OSError as e:
                    logger.warning(
                        t("msg-5cf417e3", output_format=output_format, e=e)
                    )

            error_msg = stderr.decode() if stderr else "未知错误"
            logger.error(t("msg-3766cbb8", error_msg=error_msg))
            raise Exception(t("msg-8cce258e", error_msg=error_msg))

        logger.debug(t("msg-77f68449", video_path=video_path, output_path=output_path))
        return output_path

    except FileNotFoundError:
        logger.error(
            t("msg-3fb20b91")
        )
        raise Exception(t("msg-5df3a5ee"))
    except Exception as e:
        logger.error(t("msg-696c4a46", e=e))
        raise


async def convert_audio_format(
    audio_path: str,
    output_format: str = "amr",
    output_path: str | None = None,
) -> str:
    """使用ffmpeg将音频转换为指定格式。

    Args:
        audio_path: 原始音频文件路径
        output_format: 目标格式，例如 amr / ogg
        output_path: 输出文件路径，如果为None则自动生成

    Returns:
        转换后的音频文件路径
    """
    if audio_path.lower().endswith(f".{output_format}"):
        return audio_path

    if output_path is None:
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
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
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError as e:
                    logger.warning(t("msg-98cc8fb8", e=e))
            error_msg = stderr.decode() if stderr else "未知错误"
            raise Exception(t("msg-8cce258e", error_msg=error_msg))
        logger.debug(t("msg-f0cfcb92", audio_path=audio_path, output_path=output_path))
        return output_path
    except FileNotFoundError:
        raise Exception(t("msg-5df3a5ee"))


async def convert_audio_to_amr(audio_path: str, output_path: str | None = None) -> str:
    """将音频转换为amr格式。"""
    return await convert_audio_format(
        audio_path=audio_path,
        output_format="amr",
        output_path=output_path,
    )


async def convert_audio_to_wav(audio_path: str, output_path: str | None = None) -> str:
    """将音频转换为wav格式。"""
    return await convert_audio_format(
        audio_path=audio_path,
        output_format="wav",
        output_path=output_path,
    )


async def extract_video_cover(
    video_path: str,
    output_path: str | None = None,
) -> str:
    """从视频中提取封面图（JPG）。"""
    if output_path is None:
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
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
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError as e:
                    logger.warning(t("msg-3c27d5e8", e=e))
            error_msg = stderr.decode() if stderr else "未知错误"
            raise Exception(t("msg-072774ab", error_msg=error_msg))
        return output_path
    except FileNotFoundError:
        raise Exception(t("msg-5df3a5ee"))
