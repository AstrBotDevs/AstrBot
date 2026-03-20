"""Pytest configuration for AstrBot tests."""

import pytest
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def sample_messages():
    """提供测试用的示例消息列表。"""
    from astrbot.core.agent.message import Message
    
    return [
        Message(role="system", content="You are a helpful assistant."),
        Message(role="user", content="Hello, how are you?"),
        Message(role="assistant", content="I'm doing well, thank you!"),
        Message(role="user", content="What's the weather like?"),
        Message(role="assistant", content="I don't have access to weather data."),
    ]


@pytest.fixture
def large_message_list():
    """提供大量消息用于测试压缩。"""
    from astrbot.core.agent.message import Message
    
    messages = []
    for i in range(100):
        messages.append(Message(
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message {i}: " + "这是一段比较长的测试消息内容。" * 10
        ))
    return messages
