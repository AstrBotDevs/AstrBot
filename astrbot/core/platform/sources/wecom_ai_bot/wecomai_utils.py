"""
企业微信智能机器人工具模块
提供常量定义、工具函数和辅助方法
"""

import logging
import string
import random
import hashlib
import base64
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)


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


def validate_config(config: Dict[str, Any]) -> Tuple[bool, str]:
    """验证配置参数

    Args:
        config: 配置字典

    Returns:
        (是否有效, 错误信息)
    """
    required_fields = ["token", "encoding_aes_key", "callback_url", "port"]

    for field in required_fields:
        if not config.get(field):
            return False, f"缺少必要配置项: {field}"

    # 验证端口号
    try:
        port = int(config.get("port", 0))
        if port <= 0 or port > 65535:
            return False, "端口号必须在 1-65535 范围内"
    except (ValueError, TypeError):
        return False, "端口号必须是有效的数字"

    # 验证 AES 密钥长度
    encoding_aes_key = config.get("encoding_aes_key", "")
    if len(encoding_aes_key) != 43:
        return False, "EncodingAESKey 长度必须为 43 位"

    return True, ""


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
