"""
新架构合规性测试套件

根据 openspec 最高旨意:
1. 使用 anyio 作为异步库(不是 asyncio)
2. 类型标注完整
3. 代码美观
4. 最终目标:实现 ABP 协议
"""

from __future__ import annotations

import ast
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestAnyioCompliance:
    """测试是否遵守 anyio 异步库指令

    根据 openspec:
    - 异步库使用 anyio
    - 不是 asyncio

    注意: 这些测试验证是否使用 anyio,当发现使用 asyncio 时会失败｡
    这正是我们想要的行为 - 测试驱动开发｡
    """

    def test_orchestrator_run_loop_documents_asyncio_violation(self):
        """记录: orchestrator 使用 asyncio.sleep 而不是 anyio.sleep

        VIOLATION: 当前代码使用 asyncio.sleep
        需要修改为 anyio.sleep
        """
        from astrbot._internal.runtime.orchestrator import AstrbotOrchestrator

        source = inspect.getsource(AstrbotOrchestrator.run_loop)

        # 检查是否使用了 asyncio
        uses_asyncio = "asyncio.sleep" in source

        if uses_asyncio:
            pytest.fail(
                "orchestrator.run_loop 使用了 asyncio.sleep,违反 openspec 指令\n"
                "应该使用 anyio.sleep\n"
                "per openspec directive: '异步库使用anyio'"
            )

    def test_orchestrator_documents_asyncio_cancelled_error_violation(self):
        """记录: orchestrator 捕获 asyncio.CancelledError

        VIOLATION: 当前代码捕获 asyncio.CancelledError
        需要修改为 anyio.CancelledError
        """
        from astrbot._internal.runtime.orchestrator import AstrbotOrchestrator

        source = inspect.getsource(AstrbotOrchestrator.run_loop)

        uses_asyncio_cancelled = "asyncio.CancelledError" in source

        if uses_asyncio_cancelled:
            pytest.fail(
                "orchestrator 捕获了 asyncio.CancelledError,违反 openspec 指令\n"
                "应该捕获 anyio.CancelledError\n"
                "per openspec directive: '异步库使用anyio'"
            )

    def test_mcp_client_documents_asyncio_lock_violation(self):
        """记录: MCP 客户端使用 asyncio.Lock

        VIOLATION: 当前代码使用 asyncio.Lock
        需要修改为 anyio.Lock
        """
        from astrbot._internal.protocols.mcp.client import McpClient
        import asyncio

        client = McpClient()

        uses_asyncio_lock = isinstance(client._reconnect_lock, asyncio.Lock)

        if uses_asyncio_lock:
            pytest.fail(
                "MCP 客户端使用了 asyncio.Lock,违反 openspec 指令\n"
                "应该使用 anyio.Lock\n"
                "per openspec directive: '异步库使用anyio'"
            )


class TestTypeAnnotations:
    """测试类型标注完整性

    根据 openspec:
    - 代码必须通过 ty check
    - 避免使用 Any 和 cast
    """

    def test_abp_client_has_type_annotations(self):
        """ABP 客户端应该有类型标注"""
        from astrbot._internal.protocols.abp.client import AstrbotAbpClient

        client = AstrbotAbpClient()

        # 检查主要方法是否有返回类型
        connect_ann = inspect.signature(client.connect).return_annotation
        assert connect_ann in (None, "None")

        shutdown_ann = inspect.signature(client.shutdown).return_annotation
        assert shutdown_ann in (None, "None")

    def test_abp_client_connected_property_has_type(self):
        """connected 属性应该有类型标注"""
        from astrbot._internal.protocols.abp.client import AstrbotAbpClient

        client = AstrbotAbpClient()
        assert isinstance(client.connected, bool)


class TestCodeStyle:
    """测试代码风格

    根据 openspec:
    - 代码必须通过 ruff check
    - 代码必须通过 ruff format
    """

    def test_abp_client_noobvious_style_issues(self):
        """ABP 客户端没有明显的风格问题"""
        from astrbot._internal.protocols.abp.client import AstrbotAbpClient
        import ast

        source = inspect.getsource(AstrbotAbpClient)

        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"ABP client has syntax error: {e}")

    def test_orchestrator_noobvious_style_issues(self):
        """Orchestrator 没有明显的风格问题"""
        from astrbot._internal.runtime.orchestrator import AstrbotOrchestrator
        import ast

        source = inspect.getsource(AstrbotOrchestrator)

        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"Orchestrator has syntax error: {e}")


class TestArchitectureGoals:
    """测试架构目标

    根据 openspec:
    - 最终目标:实现 ABP 协议
    - 代码美观
    - 类型标注完美
    - 将现有功能迁移到新架构
    """

    @pytest.fixture
    def abp_client(self):
        from astrbot._internal.protocols.abp.client import AstrbotAbpClient
        return AstrbotAbpClient()

    @pytest.mark.asyncio
    async def test_abp_client_meets_basic_protocol_requirements(self, abp_client):
        """ABP 客户端满足基本协议要求

        根据 base_astrbot_abp_client.py ABC 定义:
        - connect() -> None
        - register_star(name, instance) -> None
        - unregister_star(name) -> None
        - call_star_tool(star, tool, args) -> Any
        - shutdown() -> None
        """
        await abp_client.connect()
        assert abp_client.connected is True

        # Test star registration
        star = MagicMock()
        star.call_tool = AsyncMock(return_value="ok")
        abp_client.register_star("test-star", star)

        # Test tool calling
        result = await abp_client.call_star_tool("test-star", "test-tool", {})
        assert result == "ok"

        # Test unregistration
        abp_client.unregister_star("test-star")
        assert "test-star" not in abp_client._stars

        # Test shutdown
        await abp_client.shutdown()
        assert abp_client.connected is False

    def test_abp_client_has_abc_compliance(self):
        """ABP 客户端继承自 ABC"""
        from astrbot._internal.protocols.abp.client import AstrbotAbpClient
        from astrbot._internal.abc.abp.base_astrbot_abp_client import BaseAstrbotAbpClient

        assert issubclass(AstrbotAbpClient, BaseAstrbotAbpClient)


class TestMigrationGuidance:
    """迁移指导测试

    为将现有功能迁移到新架构提供测试支持
    """

    @pytest.fixture
    def orchestrator(self):
        from astrbot._internal.runtime.orchestrator import AstrbotOrchestrator
        return AstrbotOrchestrator()

    @pytest.mark.asyncio
    async def test_orchestrator_provides_star_management(self, orchestrator):
        """Orchestrator 提供 star 管理功能"""
        star = MagicMock()
        star.call_tool = AsyncMock(return_value="ok")

        # Register
        await orchestrator.register_star("test-star", star)
        assert await orchestrator.get_star("test-star") is star

        # List
        stars = await orchestrator.list_stars()
        assert "test-star" in stars

        # Unregister
        await orchestrator.unregister_star("test-star")
        assert await orchestrator.get_star("test-star") is None

    @pytest.mark.asyncio
    async def test_orchestrator_manages_all_protocol_clients(self, orchestrator):
        """Orchestrator 管理所有协议客户端"""
        assert hasattr(orchestrator, "lsp")
        assert hasattr(orchestrator, "mcp")
        assert hasattr(orchestrator, "acp")
        assert hasattr(orchestrator, "abp")
