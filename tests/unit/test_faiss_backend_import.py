"""faiss 后端导入失败时必须给出可操作的报错。

#9392 的回归测试：安装损坏或与当前 Python/平台不匹配的 faiss-cpu wheel 会在
faiss 自己的 ``__init__.py`` 里抛 ``NameError: name 'SuperKMeans' is not
defined``，那不是 ``ImportError``，过去会原样穿透到“创建知识库失败”，用户无法
看出问题出在 faiss 后端。

这里按路径加载模块：该模块只依赖 numpy，而导入 ``astrbot.core`` 会初始化数据库
和配置，与本测试无关。
"""

from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "astrbot"
    / "core"
    / "db"
    / "vec_db"
    / "faiss_impl"
    / "embedding_storage.py"
)


def _load_embedding_storage():
    spec = importlib.util.spec_from_file_location(
        "_embedding_storage_under_test",
        MODULE_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.EmbeddingStorage


@pytest.fixture
def embedding_storage():
    return _load_embedding_storage()


def _fail_faiss_import(monkeypatch, error: Exception) -> None:
    real_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name == "faiss":
            raise error
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)


def test_broken_faiss_import_raises_actionable_error(embedding_storage, monkeypatch):
    """损坏的 wheel 抛 NameError 时，应转成说明 faiss 后端的 RuntimeError。"""
    _fail_faiss_import(monkeypatch, NameError("name 'SuperKMeans' is not defined"))

    with pytest.raises(RuntimeError) as exc_info:
        embedding_storage(dimension=8)

    message = str(exc_info.value)
    assert "faiss 后端初始化失败" in message
    assert "pip install --force-reinstall faiss-cpu" in message
    # 原始错误要保留，便于贴日志排查。
    assert "SuperKMeans" in message
    assert isinstance(exc_info.value.__cause__, NameError)


def test_missing_faiss_keeps_the_install_hint(embedding_storage, monkeypatch):
    """faiss 确实没装时，仍然抛出带安装提示的 ImportError。"""
    _fail_faiss_import(monkeypatch, ImportError("No module named 'faiss'"))

    with pytest.raises(ImportError) as exc_info:
        embedding_storage(dimension=8)

    assert "faiss 未安装" in str(exc_info.value)
