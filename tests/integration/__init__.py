"""
AstrBot 集成测试

集成测试测试多个组件之间的协作，例如:
- Platform + Provider
- Pipeline + Agent
- Plugin + Context
- Database + Manager

运行集成测试:
    uv run pytest tests/integration/ -v

运行特定标记的测试:
    uv run pytest tests/integration/ -m integration -v
"""
