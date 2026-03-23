# AstrBot 架构规范

## 核心原则

1. **anyio 优先**: 所有异步代码必须使用 anyio，不是 asyncio
2. **类型安全**: 必须通过 `uvx ty check`，避免 Any 和 cast
3. **代码美观**: 必须通过 `ruff check .` 和 `ruff format .`
4. **测试完整**: 新功能必须有对应测试

## 协议系统

```
┌─────────────────────────────────────────────────────────┐
│                   Orchestrator (Runtime)                  │
│  协调 LSP, MCP, ACP, ABP 协议客户端                     │
└─────────────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
   ┌─────────┐     ┌─────────┐     ┌─────────┐
   │   LSP   │     │   MCP   │     │   ACP   │
   │ Client  │     │ Client  │     │ Client  │
   └─────────┘     └─────────┘     └─────────┘
        │               │               │
        ▼               ▼               ▼
   LSP Servers    MCP Servers    ACP Services

   ┌─────────────────────────────────────────────────┐
   │                     ABP Client                   │
   │        (进程内 Star (插件) 通信)                  │
   └─────────────────────────────────────────────────┘
                        │
                        ▼
                   ┌─────────┐
                   │  Stars  │
                   │ (插件)   │
                   └─────────┘
```

## ABP 协议 (AstrBot Protocol)

**目标**: 最终实现 ABP 协议

### 已完成
```python
class BaseAstrbotAbpClient(ABC):
    connected: bool
    async def connect() -> None
    def register_star(name: str, instance: Any) -> None
    def unregister_star(name: str) -> None
    async def call_star_tool(star, tool, args) -> Any
    async def shutdown() -> None
```

### 待完成
- ABP 服务端实现
- 完整的 JSON-RPC 2.0 消息格式
- star 心跳和健康检查
- 批量调用支持

## 文件结构

```
astrbot/_internal/
├── abc/                      # 抽象基类
│   ├── base_astrbot_gateway.py
│   ├── base_astrbot_orchestrator.py
│   ├── abp/
│   ├── acp/
│   ├── lsp/
│   └── mcp/
├── protocols/                 # 协议实现
│   ├── abp/client.py
│   ├── acp/client.py
│   ├── lsp/client.py
│   └── mcp/client.py
├── runtime/
│   └── orchestrator.py        # 核心运行时
├── geteway/                   # FastAPI 网关
│   ├── server.py
│   └── ws_manager.py
└── tools/
    ├── base.py
    ├── builtin.py
    └── registry.py
```

## 异步库要求

### 正确 ✓
```python
import anyio

async def run():
    async with anyio.create_task_group() as tg:
        tg.start_soon(coro1)
        tg.start_soon(coro2)

# 等待事件
event = anyio.Event()
await event.wait()

# 锁
lock = anyio.Lock()
async with lock:
    ...
```

### 错误 ✗
```python
import asyncio  # 禁止使用!

# 错误
await asyncio.sleep(1)
asyncio.Lock()
asyncio.CancelledError
```

## 测试要求

测试文件位置: `tests/unit/test_internal/`

必须测试:
1. 每个协议客户端的 connect/disconnect
2. star 注册/注销
3. 工具调用
4. 错误处理
5. 生命周期管理

## 类型标注规范

```python
# Good ✓
async def call_star_tool(
    self,
    star_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> Any:
    ...

# Bad ✗
async def call_star_tool(self, star, tool, args):  # 没有类型
    ...

# Acceptable (必要时使用 Any)
async def call_star_tool(
    self,
    star_name: str,
    tool_name: str,
    arguments: dict[str, Any],  # Any 是允许的因为参数结构可变
) -> Any:  # Any 是允许的因为返回类型可变
    ...
```

## 实践验证记录

### 验证方法
- 集成测试: `test_bootstrap.py` - 验证组件可正常创建和交互
- 单元测试: `pytest tests/unit/test_internal/` - 验证架构合规性
- 协议测试: 针对各协议客户端的实际连接测试

### 已知问题
1. **LSP Client**: 当前使用 `asyncio` 而非 `anyio`，需要重构
2. **ty LSP**: ty server 不支持标准 LSP 协议，不适合作为 LSP 测试目标
3. **ACP Client**: 尚未进行实际连接测试

### 端口配置
| 服务 | 默认端口 | 说明 |
|------|---------|------|
| Gateway | 8765 | FastAPI + WebSocket |
| Dashboard | 6185 | Vue.js 前端 (推测) |
