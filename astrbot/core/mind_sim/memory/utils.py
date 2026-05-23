"""MindSim 记忆系统工具函数"""

import json
import re
from typing import Any


def extract_json_from_response(response: str) -> Any:
    """从 LLM 响应中提取 JSON

    支持：
    - ```json ... ``` 代码块
    - 直接 JSON 数组 [...]
    - 直接 JSON 对象 {...}
    """
    if not response:
        return None

    # 尝试提取 ```json``` 代码块
    json_pattern = r"```json\s*(.*?)\s*```"
    matches = re.findall(json_pattern, response, re.DOTALL)
    if matches:
        json_str = matches[0].strip()
    else:
        # 尝试查找 JSON 数组
        start_idx = response.find("[")
        end_idx = response.rfind("]")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = response[start_idx : end_idx + 1].strip()
        else:
            # 尝试查找 JSON 对象
            start_idx = response.find("{")
            end_idx = response.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx : end_idx + 1].strip()
            else:
                # 清理 markdown 标记后尝试
                json_str = response.strip()
                json_str = re.sub(r"^```json\s*", "", json_str, flags=re.MULTILINE)
                json_str = re.sub(r"^```\s*", "", json_str, flags=re.MULTILINE)
                json_str = json_str.strip()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # 尝试修复常见 JSON 错误（尾部逗号等）
        json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None


def format_timestamp(ts: float) -> str:
    """将时间戳格式化为可读字符串"""
    from datetime import datetime, timezone

    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")
