"""SDK parameter helper types.

本模块提供 SDK 参数类型助手，用于增强命令参数解析能力。

GreedyStr:
用于标记"贪婪字符串"参数，在命令解析时将剩余所有文本作为一个整体参数。
例如：/echo hello world this is a test
如果最后一个参数类型为 GreedyStr，将获取 "hello world this is a test" 而非仅 "hello"

使用方式：
在 handler 签名中将最后一个参数标注为 GreedyStr 类型，
_loader_support 会识别此类型并调整参数解析逻辑。
"""

from __future__ import annotations


class GreedyStr(str):
    """Consume the remaining command text as one argument."""


__all__ = ["GreedyStr"]
