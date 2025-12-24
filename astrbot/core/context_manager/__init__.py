"""
AstrBot V2 上下文管理系统

统一的上下文压缩管理模块，实现多阶段处理流程：
1. Token初始统计 → 判断是否超过82%
2. 如果超过82%，执行压缩/截断（Agent模式/普通模式）
3. 最终处理：合并消息、清理Tool Calls、按数量截断
"""

from .context_compressor import ContextCompressor
from .context_manager import ContextManager
from .context_truncator import ContextTruncator
from .models import Message
from .token_counter import TokenCounter

__all__ = [
    "ContextManager",
    "TokenCounter",
    "ContextTruncator",
    "ContextCompressor",
    "Message",
]
