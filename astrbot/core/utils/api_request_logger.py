"""API请求日志记录器

用于记录LLM API的完整请求和响应信息，便于调试和排查问题。
"""

import json
import logging
import os
from datetime import datetime
from typing import Any

from astrbot.core.utils.astrbot_path import get_astrbot_data_path


class APIRequestLogger:
    """API请求日志记录器"""

    _instance = None
    _logger = None

    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 创建专门的logger
        self._logger = logging.getLogger("api_requests")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False  # 不传播到root logger

        # 创建日志文件handler
        log_dir = os.path.join(get_astrbot_data_path(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "api_requests.log")

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)

        # 简单的格式，只包含时间和消息
        formatter = logging.Formatter("%(asctime)s - %(message)s")
        file_handler.setFormatter(formatter)

        self._logger.addHandler(file_handler)
        self._initialized = True

    def _serialize_messages(self, messages: list) -> list[dict]:
        """序列化messages，处理Message对象"""
        result = []
        for msg in messages:
            if hasattr(msg, "model_dump"):
                # Message对象，使用model_dump()
                result.append(msg.model_dump())
            elif isinstance(msg, dict):
                result.append(msg)
            else:
                result.append({"raw": str(msg)})
        return result

    def _serialize_tools(self, func_tool: Any) -> list[dict] | None:
        """序列化工具列表"""
        if func_tool is None:
            return None
        if hasattr(func_tool, "to_openai_tools"):
            return func_tool.to_openai_tools()
        return None

    def log_request(
        self,
        model: str,
        messages: list,
        tools: Any = None,
        streaming: bool = False,
        session_id: str = "",
        extra_info: dict | None = None,
    ):
        """记录API请求

        Args:
            model: 模型名称
            messages: 消息列表
            tools: 工具列表
            streaming: 是否流式响应
            session_id: 会话ID
            extra_info: 额外信息
        """
        try:
            request_type = "stream" if streaming else "non-stream"
            self._logger.info(f"=== API REQUEST ({request_type}) ===")
            self._logger.info(f"Model: {model}")
            self._logger.info(f"Session: {session_id}")

            # 序列化messages
            serialized_messages = self._serialize_messages(messages)
            self._logger.info(
                f"Messages: {json.dumps(serialized_messages, indent=2, ensure_ascii=False)}"
            )

            # 序列化tools
            if tools:
                serialized_tools = self._serialize_tools(tools)
                if serialized_tools:
                    self._logger.info(
                        f"Tools: {json.dumps(serialized_tools, indent=2, ensure_ascii=False)}"
                    )

            # 额外信息
            if extra_info:
                self._logger.info(
                    f"Extra: {json.dumps(extra_info, indent=2, ensure_ascii=False)}"
                )

        except Exception as e:
            self._logger.error(f"Error logging request: {e}")

    def log_response(
        self,
        response: Any,
        duration_ms: float | None = None,
        extra_info: dict | None = None,
    ):
        """记录API响应

        Args:
            response: LLM响应对象
            duration_ms: 响应时间（毫秒）
            extra_info: 额外信息
        """
        try:
            self._logger.info("=== API RESPONSE ===")

            if duration_ms is not None:
                self._logger.info(f"Duration: {duration_ms:.2f}ms")

            # 记录响应内容
            if hasattr(response, "completion_text"):
                self._logger.info(f"Completion: {response.completion_text}")

            if hasattr(response, "tools_call_name") and response.tools_call_name:
                self._logger.info(f"Tool Calls: {response.tools_call_name}")

            if hasattr(response, "tool_calls_result") and response.tool_calls_result:
                tool_calls_data = []
                for tc in response.tool_calls_result:
                    tool_calls_data.append(
                        {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        }
                    )
                self._logger.info(
                    f"Tool Call Details: {json.dumps(tool_calls_data, indent=2, ensure_ascii=False)}"
                )

            if hasattr(response, "token_usage") and response.token_usage:
                self._logger.info(f"Token Usage: {response.token_usage}")

            # 额外信息
            if extra_info:
                self._logger.info(
                    f"Extra: {json.dumps(extra_info, indent=2, ensure_ascii=False)}"
                )

            self._logger.info("=" * 50)

        except Exception as e:
            self._logger.error(f"Error logging response: {e}")

    def log_exception(
        self,
        exception: Exception,
        context: dict | None = None,
    ):
        """记录异常

        Args:
            exception: 异常对象
            context: 上下文信息
        """
        try:
            self._logger.info("=== API EXCEPTION ===")
            self._logger.info(f"Exception Type: {type(exception).__name__}")
            self._logger.info(f"Exception Message: {str(exception)}")

            if context:
                self._logger.info(
                    f"Context: {json.dumps(context, indent=2, ensure_ascii=False)}"
                )

            self._logger.info("=" * 50)

        except Exception as e:
            self._logger.error(f"Error logging exception: {e}")


# 全局实例
api_request_logger = APIRequestLogger()
