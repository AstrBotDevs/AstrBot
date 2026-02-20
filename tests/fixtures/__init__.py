"""
AstrBot 测试数据

此目录存放测试用的静态数据和配置文件。

目录结构:
- fixtures/
  ├── configs/        # 测试配置文件
  ├── messages/       # 测试消息数据
  ├── plugins/        # 测试插件
  └── knowledge_base/ # 测试知识库数据
"""

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent


def load_fixture(filename: str) -> dict:
    """加载 JSON 格式的测试数据。"""
    filepath = FIXTURES_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Fixture not found: {filepath}")
    return json.loads(filepath.read_text(encoding="utf-8"))


def get_fixture_path(filename: str) -> Path:
    """获取测试数据文件路径。"""
    filepath = FIXTURES_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Fixture not found: {filepath}")
    return filepath
