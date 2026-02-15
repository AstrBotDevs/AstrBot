"""JSON响应构建器

负责构建统一格式的JSON响应，与业务逻辑解耦。
"""

import json
from typing import Any

from astrbot.core.message.message_event_result import MessageChain

from .image_processor import ImageInfo, ImageProcessor


class ResponseBuilder:
    """JSON响应构建器

    I/O契约:
        Input: MessageChain 或 error_msg
        Output: JSON字符串
    """

    @staticmethod
    def build_success(
        message_chain: MessageChain,
        request_id: str,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """构建成功响应

        Args:
            message_chain: 消息链
            request_id: 请求ID
            extra: 额外字段

        Returns:
            JSON字符串
        """
        response_text = message_chain.get_plain_text()
        images = ImageProcessor.extract_images(message_chain)

        result = {
            "status": "success",
            "response": response_text,
            "images": [ResponseBuilder._image_to_dict(img) for img in images],
            "request_id": request_id,
        }

        if extra:
            result.update(extra)

        return json.dumps(result, ensure_ascii=False)

    @staticmethod
    def build_error(
        error_msg: str,
        request_id: str | None = None,
        error_code: str | None = None,
    ) -> str:
        """构建错误响应

        Args:
            error_msg: 错误消息
            request_id: 请求ID
            error_code: 错误代码

        Returns:
            JSON字符串
        """
        result = {
            "status": "error",
            "error": error_msg,
        }

        if request_id:
            result["request_id"] = request_id
        if error_code:
            result["error_code"] = error_code

        return json.dumps(result, ensure_ascii=False)

    @staticmethod
    def _image_to_dict(image_info: ImageInfo) -> dict:
        """将ImageInfo转换为字典"""
        return ImageProcessor.image_info_to_dict(image_info)
