# AstrBot 开发任务

## 当前最高优先级

### 1. 实践验证 - 让架构真正工作 (P0)

**状态**: 进行中

架构必须经过实际验证，不能只是"代码通过测试"。以下是已验证和待验证项目：

#### ✅ 已验证 (84 tests passed)

| 组件 | 验证方式 | 结果 |
|------|---------|------|
| Orchestrator | `test_bootstrap.py` | ✓ 正常创建所有协议客户端 |
| ABP Client | `test_bootstrap.py` | ✓ Star 注册/注销/调用正常 |
| Gateway | `test_bootstrap.py` | ✓ 启动在 0.0.0.0:8765 |
| WebSocketManager | `test_bootstrap.py` | ✓ anyio.Lock 已修复 |
| MCP Client | `test_architecture_compliance.py` | ✓ 使用 anyio.Lock |
| 架构合规测试 | pytest | ✓ 11 passed |

#### ⚠ 需要修复 (anyio 违规)

| 组件 | 问题 | 状态 |
|------|------|------|
| `lsp/client.py` | 使用 `asyncio.create_subprocess_exec` | 待修复 |
| `lsp/client.py` | 使用 `asyncio.Future` | 待修复 |

#### 🔍 待验证

| 组件 | 验证方式 | 状态 |
|------|---------|------|
| MCP Client | 连接本地 MCP 服务器并调用工具 | 待验证 |
| ACP Client | 连接 ACP 服务并通信 | 待验证 |
| LSP Client + python-lsp-server | 接入标准 LSP 服务器 | 待验证 |
| ty LSP | ty server 不支持标准 LSP 协议 | 不适用 |

### 2. ABP 协议示例开发 (P0)

**目标**: 开发一个可运行的 ABP 协议演示

**计划**:
1. 创建 `examples/abp_demo.py`
2. 演示：
   - 创建 Orchestrator
   - 注册一个 mock star
   - 通过 ABP client 调用 star 工具
   - 验证结果

**状态**: 待开始

### 3. 将项目工具转为 MCP 服务器 (P1)

**目标**: 将 builtin_tools (cron_tools, kb_query, send_message) 暴露为 MCP 服务器

**待验证**:
- MCP client 能否连接到本地 MCP 服务器
- 工具调用是否正常工作

---

## 已完成任务

### ✅ anyio 违规修复 (完成)

- `orchestrator.py`: `asyncio.sleep` → `anyio.sleep`, `asyncio.CancelledError` → `anyio.get_cancelled_exc_class()`
- `mcp/client.py`: `asyncio.Lock` → `anyio.Lock`, `asyncio.Event` → `anyio.Event`
- `lsp/client.py`: import 排序修复
- `gateway/server.py`: 删除死代码 `asyncio.Task` 和 `import asyncio`
- `gateway/ws_manager.py`: `asyncio.Lock` → `anyio.Lock`

### ✅ 架构合规测试 (完成)
- `test_architecture_compliance.py`: 11 个测试全部通过
- 总计: 84 passed, 0 failed

### ✅ Bootstrap 集成测试 (完成)
- `test_bootstrap.py`: 验证所有组件可正常创建和交互

---

## 技术债务

1. **LSP Client 使用 asyncio**
   - `lsp/client.py` 使用 `asyncio.create_subprocess_exec` 和 `asyncio.Future`
   - 需要重构为 anyio
   - 影响: LSP 功能不可用

2. **ty LSP 服务器不兼容**
   - ty server 启动但不支持标准 `initialize` 请求
   - 需要使用 python-lsp-server 进行测试

3. **测试**: `tests/test_dashboard.py::test_auth_login` 失败
   - 错误: `AttributeError: 'FuncCall' object has no attribute 'register_internal_tools'`
   - 需要在 FuncCall 添加 register_internal_tools 方法或修复引用

---

## 端口说明

| 服务 | 端口 | 状态 |
|------|------|------|
| Gateway (FastAPI) | 8765 | ✓ 已验证可启动 |
| WebSocket | /ws | ✓ 已验证 |
| Dashboard | 6185 (推测) | 待验证 |
