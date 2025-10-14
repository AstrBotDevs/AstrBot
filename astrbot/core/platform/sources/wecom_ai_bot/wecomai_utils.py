"""
企业微信智能机器人工具模块
提供常量定义、工具函数和辅助方法
"""

import string
import random
import hashlib
import base64
import aiohttp
import asyncio
from Crypto.Cipher import AES
from typing import Any, Tuple
from astrbot.api import logger


# 常量定义
class WecomAIBotConstants:
    """企业微信智能机器人常量"""

    # 消息类型
    MSG_TYPE_TEXT = "text"
    MSG_TYPE_IMAGE = "image"
    MSG_TYPE_MIXED = "mixed"
    MSG_TYPE_STREAM = "stream"
    MSG_TYPE_EVENT = "event"

    # 流消息状态
    STREAM_CONTINUE = False
    STREAM_FINISH = True

    # 错误码
    SUCCESS = 0
    DECRYPT_ERROR = -40001
    VALIDATE_SIGNATURE_ERROR = -40002
    PARSE_XML_ERROR = -40003
    COMPUTE_SIGNATURE_ERROR = -40004
    ILLEGAL_AES_KEY = -40005
    VALIDATE_APPID_ERROR = -40006
    ENCRYPT_AES_ERROR = -40007
    ILLEGAL_BUFFER = -40008


def generate_random_string(length: int = 10) -> str:
    """生成随机字符串

    Args:
        length: 字符串长度，默认为 10

    Returns:
        随机字符串
    """
    letters = string.ascii_letters + string.digits
    return "".join(random.choice(letters) for _ in range(length))


def calculate_image_md5(image_data: bytes) -> str:
    """计算图片数据的 MD5 值

    Args:
        image_data: 图片二进制数据

    Returns:
        MD5 哈希值（十六进制字符串）
    """
    return hashlib.md5(image_data).hexdigest()


def encode_image_base64(image_data: bytes) -> str:
    """将图片数据编码为 Base64

    Args:
        image_data: 图片二进制数据

    Returns:
        Base64 编码的字符串
    """
    return base64.b64encode(image_data).decode("utf-8")


def format_session_id(session_type: str, session_id: str) -> str:
    """格式化会话 ID

    Args:
        session_type: 会话类型 ("user", "group")
        session_id: 原始会话 ID

    Returns:
        格式化后的会话 ID
    """
    return f"wecom_ai_bot_{session_type}_{session_id}"


def parse_session_id(formatted_session_id: str) -> Tuple[str, str]:
    """解析格式化的会话 ID

    Args:
        formatted_session_id: 格式化的会话 ID

    Returns:
        (会话类型, 原始会话ID)
    """
    parts = formatted_session_id.split("_", 3)
    if (
        len(parts) >= 4
        and parts[0] == "wecom"
        and parts[1] == "ai"
        and parts[2] == "bot"
    ):
        return parts[3], "_".join(parts[4:]) if len(parts) > 4 else ""
    return "user", formatted_session_id


def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """安全地解析 JSON 字符串

    Args:
        json_str: JSON 字符串
        default: 解析失败时的默认值

    Returns:
        解析结果或默认值
    """
    import json

    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"JSON 解析失败: {e}, 原始字符串: {json_str}")
        return default


def format_error_response(error_code: int, error_msg: str) -> str:
    """格式化错误响应

    Args:
        error_code: 错误码
        error_msg: 错误信息

    Returns:
        格式化的错误响应字符串
    """
    return f"Error {error_code}: {error_msg}"


async def process_encrypted_image(
    image_url: str, aes_key_base64: str
) -> Tuple[bool, str]:
    """下载并解密加密图片

    Args:
        image_url: 加密图片的URL
        aes_key_base64: Base64编码的AES密钥(与回调加解密相同)

    Returns:
        Tuple[bool, str]: status 为 True 时 data 是解密后的图片数据的 base64 编码，
            status 为 False 时 data 是错误信息
    """
    # 1. 下载加密图片
    logger.info("开始下载加密图片: %s", image_url)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url, timeout=15) as response:
                response.raise_for_status()
                encrypted_data = await response.read()
        logger.info("图片下载成功，大小: %d 字节", len(encrypted_data))
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        error_msg = f"下载图片失败: {str(e)}"
        logger.error(error_msg)
        return False, error_msg

    # 2. 准备AES密钥和IV
    if not aes_key_base64:
        raise ValueError("AES密钥不能为空")

    # Base64解码密钥 (自动处理填充)
    aes_key = base64.b64decode(aes_key_base64 + "=" * (-len(aes_key_base64) % 4))
    if len(aes_key) != 32:
        raise ValueError("无效的AES密钥长度: 应为32字节")

    iv = aes_key[:16]  # 初始向量为密钥前16字节

    # 3. 解密图片数据
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    decrypted_data = cipher.decrypt(encrypted_data)

    # 4. 去除PKCS#7填充 (Python 3兼容写法)
    pad_len = decrypted_data[-1]  # 直接获取最后一个字节的整数值
    if pad_len > 32:  # AES-256块大小为32字节
        raise ValueError("无效的填充长度 (大于32字节)")

    decrypted_data = decrypted_data[:-pad_len]
    logger.info("图片解密成功，解密后大小: %d 字节", len(decrypted_data))

    # 5. 转换为base64编码
    base64_data = base64.b64encode(decrypted_data).decode("utf-8")
    logger.info("图片已转换为base64编码，编码后长度: %d", len(base64_data))

    return True, base64_data
