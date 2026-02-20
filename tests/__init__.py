"""
AstrBot 测试包

测试目录结构:
- tests/
  ├── conftest.py         # 共享 fixtures 和配置
  ├── pyproject.toml      # pytest 配置（tool.pytest.ini_options）
  ├── TEST_REQUIREMENTS.md # 测试需求清单
  ├── unit/               # 单元测试
  ├── integration/        # 集成测试
  ├── agent/              # Agent 相关测试
  ├── fixtures/           # 测试数据和 fixtures
  └── test_*.py           # 根级别测试文件

辅助函数可在 conftest.py 中直接导入使用:
    from tests.conftest import create_mock_llm_response, create_mock_message_component
"""
