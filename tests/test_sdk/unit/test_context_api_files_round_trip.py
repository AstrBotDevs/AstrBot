# ruff: noqa: E402
"""Files 客户端 Core Bridge 集成测试。

测试覆盖 01_context_api.md 中 ctx.files 的所有方法：
- register_file(): 注册文件并获取令牌
- handle_file(): 通过令牌解析文件路径
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_sdk.unit._context_api_roundtrip import build_roundtrip_runtime


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_files_register_file_returns_token(tmp_path, monkeypatch):
    """register_file 注册文件并返回 token。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    # 创建测试文件
    test_file = tmp_path / "test_image.jpg"
    test_file.write_text("fake image content")

    token = await ctx.files.register_file(str(test_file))

    assert token is not None
    assert token.startswith("file-token-")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_files_register_file_with_timeout(tmp_path, monkeypatch):
    """register_file 支持 timeout 参数。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    test_file = tmp_path / "timeout_test.png"
    test_file.write_text("content")

    token = await ctx.files.register_file(str(test_file), timeout=3600)

    assert token is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_files_handle_file_resolves_token(tmp_path, monkeypatch):
    """handle_file 通过 token 解析回原始文件路径。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    test_file = tmp_path / "resolve_test.txt"
    test_file.write_text("test content")

    # 先注册
    token = await ctx.files.register_file(str(test_file))

    # 再解析
    resolved_path = await ctx.files.handle_file(token)

    assert Path(resolved_path) == test_file


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_files_round_trip_workflow(tmp_path, monkeypatch):
    """完整的文件注册和解析工作流。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    # 创建多个测试文件
    files = []
    for i in range(3):
        file_path = tmp_path / f"file_{i}.dat"
        file_path.write_text(f"content {i}")
        files.append(file_path)

    # 注册所有文件
    tokens = []
    for file_path in files:
        token = await ctx.files.register_file(str(file_path))
        tokens.append(token)

    # 验证每个 token 都能解析回正确的路径
    for token, expected_path in zip(tokens, files):
        resolved = await ctx.files.handle_file(token)
        assert Path(resolved) == expected_path
