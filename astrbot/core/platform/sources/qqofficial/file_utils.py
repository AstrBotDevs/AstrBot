"""
文件工具模块
参照 openclaw-qqbot 的 file-utils.ts 实现
"""

import os
from typing import Optional


# ============ 文件类型与大小限制 ============

class MediaFileType:
    IMAGE = 1
    VIDEO = 2
    VOICE = 3
    FILE = 4


# QQ Bot API 上传大小限制（字节）- 与 openclaw-qqbot 一致
MAX_UPLOAD_SIZES = {
    MediaFileType.IMAGE: 30 * 1024 * 1024,   # 30MB
    MediaFileType.VIDEO: 100 * 1024 * 1024,  # 100MB
    MediaFileType.VOICE: 20 * 1024 * 1024,   # 20MB
    MediaFileType.FILE: 100 * 1024 * 1024,   # 100MB
}

FILE_TYPE_NAMES = {
    MediaFileType.IMAGE: "图片",
    MediaFileType.VIDEO: "视频",
    MediaFileType.VOICE: "语音",
    MediaFileType.FILE: "文件",
}


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f}MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f}GB"


def get_max_upload_size(file_type: int) -> int:
    """获取文件类型对应的最大上传大小"""
    return MAX_UPLOAD_SIZES.get(file_type, 100 * 1024 * 1024)


def get_file_type_name(file_type: int) -> str:
    """获取文件类型名称"""
    return FILE_TYPE_NAMES.get(file_type, "文件")


async def file_exists_async(file_path: str) -> bool:
    """异步检查文件是否存在"""
    return os.path.exists(file_path)


async def get_file_size_async(file_path: str) -> int:
    """异步获取文件大小"""
    try:
        return os.path.getsize(file_path)
    except OSError:
        return 0


def is_image_file(file_path: str, mime_type: Optional[str] = None) -> bool:
    """判断是否为图片文件"""
    if mime_type and mime_type.startswith("image/"):
        return True
    
    
    ext = os.path.splitext(file_path)[1].lower()
    return ext in {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}


def is_video_file(file_path: str, mime_type: Optional[str] = None) -> bool:
    """判断是否为视频文件"""
    if mime_type and mime_type.startswith("video/"):
        return True
    
    
    ext = os.path.splitext(file_path)[1].lower()
    return ext in {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv'}


def is_audio_file(file_path: str, mime_type: Optional[str] = None) -> bool:
    """判断是否为音频文件"""
    if mime_type and mime_type.startswith("audio/"):
        return True
    
    
    ext = os.path.splitext(file_path)[1].lower()
    return ext in {'.mp3', '.wav', '.ogg', '.m4a', '.amr', '.silk', '.aac', '.flac'}


def get_file_extension(file_path: str) -> str:
    """
    获取文件扩展名（去除查询参数和 hash）
    
    Args:
        file_path: 文件路径或 URL
        
    Returns:
        文件扩展名（小写，包含点号）
    """
    # 去除查询参数和 hash
    clean_path = file_path.split("?")[0].split("#")[0]
    ext = os.path.splitext(clean_path)[1].lower()
    return ext
