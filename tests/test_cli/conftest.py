"""CLI测试共享fixtures"""

import asyncio
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def event_loop():
    """创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_platform_meta():
    """创建模拟的PlatformMetadata"""
    meta = MagicMock()
    meta.name = "cli"
    return meta


@pytest.fixture
def mock_output_queue():
    """创建模拟的输出队列"""
    return asyncio.Queue()


@pytest.fixture
def mock_message_chain():
    """创建模拟的MessageChain"""
    chain = MagicMock()
    chain.chain = []
    chain.get_plain_text.return_value = "Test response"
    return chain
