# 插件注册与能力调用流程

> 本文档解释插件如何被发现、加载、注册能力，以及 Core 如何调用这些能力。

---

## 一句话概括

**插件在独立进程中运行，通过"能力路由器"向 Core 注册自己能做什么，Core 需要时就去找对应的插件干活。**

---

## 核心概念

### 什么是"能力"(Capability)？

能力就是插件**能做的事情**。比如：
- `llm.chat` - 跟 AI 聊天
- `platform.send` - 发送消息
- `my_plugin.translate` - 翻译文本（你自定义的）

你可以把它理解成**插件的技能清单**。

### 为什么要进程隔离？

想象一下：插件 A 写了个死循环把进程卡死了。如果没有隔离，整个 AstrBot 都会崩掉。

有了进程隔离：
- 插件 A 崩了 → 只是插件 A 不可用
- 插件 B、C、D → 照常运行

---

## 架构全景图

```
┌─────────────────────────────────────────────────────────────┐
│                      AstrBot Core                           │
│                   (大脑：决定做什么)                         │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          │ "我要调用 llm.chat"
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  SupervisorRuntime (主进程)                  │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐  │
│   │            CapabilityRouter (总调度)                 │  │
│   │                                                     │  │
│   │   谁会什么？                                        │  │
│   │   ├─ llm.chat      → 找 Worker A                   │  │
│   │   ├─ platform.send → 找 Worker A                   │  │
│   │   └─ my_plugin.foo → 找 Worker B                   │  │
│   └─────────────────────────────────────────────────────┘  │
│                                                             │
│         Worker A                    Worker B               │
│         (插件A的进程)               (插件B的进程)            │
└─────────────────────────────────────────────────────────────┘
```

---

## 插件注册流程（三步走）

### 第一步：被发现

Supervisor 启动时扫描 `plugins/` 目录：

```
plugins/
├── my_plugin/
│   ├── plugin.yaml      ← 必须有这个文件
│   └── main.py
└── another_plugin/
    ├── plugin.yaml
    └── main.py
```

Supervisor 读取每个 `plugin.yaml`，确认插件的基本信息（名称、版本、入口类等）。

### 第二步：被加载

Worker 进程启动后：
1. 导入你的插件类（如 `main:MyPlugin`）
2. 实例化（无参构造）
3. 扫描所有方法上的装饰器

```python
class MyPlugin(Star):
    @on_command("hello")           # → 发现一个 handler
    async def hello(self, ...): ...

    @provide_capability("calc")    # → 发现一个 capability
    async def calculate(self, ...): ...
```

### 第三步：握手注册

Worker 把发现的 handler 和 capability 列表发送给 Supervisor：

```
Worker                              Supervisor
  │                                     │
  │  "我有这些能力：                    │
  │   - handler: hello                  │
  │   - capability: calc"               │
  │                                     │
  ├────────────────────────────────────►│
  │                                     │
  │                        CapabilityRouter 记录：
  │                        "calc 这个能力归这个 Worker 管"
  │                                     │
  │◄────────────────────────────────────┤
  │  "注册成功，你可以开始工作了"        │
```

---

## 能力调用流程

### 从调用到执行的完整链路

```
用户使用fuck指令
    │
    ▼
Core 决定要调用 Fuck Capability
    │
    ▼
Supervisor 问 CapabilityRouter："谁会 Fuck Capability？"
    │
    ▼
CapabilityRouter 查表："Worker A 会"
    │
    ▼
Supervisor 给 Worker A 发消息："帮我执行 Fuck Capability，参数是..."
    │
    ▼
Worker A 调用对应的方法，拿到结果
    │
    ▼
结果原路返回给 Core
```

### 代码层面的对应关系

```python
# Core/插件 中这样调用
result = await ctx.llm.chat("你好")

# 实际发生了什么：
# 1. ctx.llm.chat → 调用 llm.chat 这个 capability
# 2. CapabilityRouter 找到对应的 Worker
# 3. 发消息给 Worker 进程
# 4. Worker 进程执行 LLM 客户端的 chat 方法
# 5. 结果返回
```

---

## 冲突处理：同名能力怎么办？

两个插件都注册了 `echo` 能力，会怎样？

| 情况 | 处理方式 |
|------|---------|
| 保留命名空间 (`system.*`, `internal.*`) | 后注册的会被拒绝 |
| 普通冲突 | 自动加前缀：`echo` → `plugin_b.echo` |

**建议**：给自己的能力加上插件名前缀，如 `my_plugin.echo`，避免冲突。

---

## 关键数据结构

### 能力描述符 (CapabilityDescriptor)

描述一个能力长什么样：

```python
{
    "name": "my_plugin.calculate",     # 能力名称
    "description": "执行数学计算",      # 描述
    "input_schema": {...},             # 输入格式（JSON Schema）
    "output_schema": {...},            # 输出格式（JSON Schema）
}
```

### 握手消息 (InitializeMessage)

Worker 向 Supervisor 汇报自己有什么：

```python
{
    "protocol_version": "4",
    "handlers": [...],           # 我能处理哪些命令/消息
    "provided_capabilities": [...]  # 我提供哪些能力
}
```

---

## 内置能力速查

这些是 AstrBot 已经提供的能力，你的插件可以直接调用：

| 命名空间 | 能力 | 用途 |
|---------|------|------|
| `llm.*` | `chat`, `stream_chat` | AI 对话 |
| `platform.*` | `send`, `send_image` | 发送消息 |
| `db.*` | `get`, `set`, `watch` | 数据存储 |
| `memory.*` | `search`, `save` | 记忆系统 |
| `system.*` | `get_data_dir` | 系统功能 |

---

## 时序图

```
Core          Supervisor       WorkerSession      Worker进程
 │                │                  │                │
 │                │   启动 Worker     │                │
 │                │─────────────────►│                │
 │                │                  │   创建进程     │
 │                │                  │───────────────►│
 │                │                  │                │
 │                │                  │   加载插件     │
 │                │                  │                │──┐
 │                │                  │                │◄─┘
 │                │                  │                │
 │                │                  │  Initialize    │
 │                │                  │◄───────────────│
 │                │                  │                │
 │                │  注册能力         │                │
 │                │◄─────────────────│                │
 │                │                  │                │
 │  调用能力      │                  │                │
 │───────────────►│                  │                │
 │                │                  │                │
 │                │  Invoke          │                │
 │                │─────────────────►│                │
 │                │                  │───────────────►│
 │                │                  │                │
 │                │                  │    执行方法    │
 │                │                  │                │──┐
 │                │                  │                │◄─┘
 │                │                  │                │
 │                │                  │  Result        │
 │                │                  │◄───────────────│
 │                │                  │                │
 │  返回结果      │                  │                │
 │◄───────────────│                  │                │
```

---

## 相关源码

| 文件 | 职责 |
|------|------|
| `runtime/loader.py` | 插件发现与加载 |
| `runtime/bootstrap.py` | Supervisor/Worker 启动 |
| `runtime/capability_router.py` | 能力路由（主进程侧） |
| `runtime/capability_dispatcher.py` | 能力分发（Worker侧） |
| `runtime/handler_dispatcher.py` | Handler 分发 |
| `runtime/peer.py` | 进程间通信 |
