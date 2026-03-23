# AstrBot 开发任务

## 当前最高优先级

### 1. 修复 anyio 违规 (P0)
**问题**: 代码使用 asyncio 但 openspec 要求使用 anyio

需要修改的文件:
- `astrbot/_internal/runtime/orchestrator.py`:
  - `asyncio.sleep` → `anyio.sleep`
  - `asyncio.CancelledError` → `anyio.CancelledError`
- `astrbot/_internal/protocols/mcp/client.py`:
  - `asyncio.Lock` → `anyio.Lock`
- `astrbot/_internal/protocols/abp/client.py`:
  - `asyncio.Future` → `anyio.Future`

### 2. 实现 ABP 协议完整功能 (P0)
ABP (AstrBot Protocol) 是最终目标

已完成:
- ABPClient 基础实现
- star 注册/注销
- call_star_tool 调用

待完成:
- ABP 服务端实现
- 完整的协议序列化
- 错误处理和重连机制

### 3. 测试覆盖提升 (P1)
当前测试: 81 passed, 3 failed (anyio 违规)

目标:
- 增加 _internal 模块测试覆盖率
- 修复 anyio 违规测试
- 添加协议集成测试

### 4. 类型标注完善 (P1)
执行: `uvx ty check astrbot/_internal/`

当前问题:
- 避免使用 Any
- 避免使用 cast
- 完善 return type annotations

---

## 进行中的任务

### 迁移现有功能到 _internal
状态: 部分完成

已迁移:
- MCP client → `astrbot/_internal/protocols/mcp/`
- ABP client → `astrbot/_internal/protocols/abp/`
- ACP client → `astrbot/_internal/protocols/acp/`
- LSP client → `astrbot/_internal/protocols/lsp/`
- Tools → `astrbot/_internal/tools/`

待迁移:
- 完整的 star 系统
- Gateway 服务端
- Orchestrator 核心

---

## 技术债务

1. **测试**: `tests/test_dashboard.py::test_auth_login` 失败
   - 错误: `AttributeError: 'FuncCall' object has no attribute 'register_internal_tools'`
   - 需要在 FuncCall 添加 register_internal_tools 方法或修复引用

2. **代码风格**: ruff ASYNC110 警告
   - orchestrator run_loop 使用 asyncio.sleep 而非 anyio
