# AstrBot SDK 重构架构设计 v4

---

## 一、全局架构图

```
╔══════════════════════════════════════════════════════════════════════╗
║                        插件作者的世界                                 ║
║                                                                      ║
║   class MyPlugin(Star):                                              ║
║       @on_command("hello")                                           ║
║       async def hello(self, event: MessageEvent, ctx: Context):      ║
║           reply = await ctx.llm.chat(event.text)                     ║
║           await event.reply(reply)                                   ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
         │ Star / 装饰器 / Event            │ Context / Clients
         ▼                                  ▼
┌─────────────────────┐        ┌────────────────────────────────┐
│   Handler 系统       │        │   Capability 调用系统           │
│                     │        │                                │
│ HandlerDescriptor   │        │  ctx.llm.chat()                │
│ HandlerDispatcher   │        │  ctx.memory.search()           │
│                     │        │  ctx.db.get()                  │
│ 插件 → 主进程        │        │  ctx.platform.send()           │
│ "我能响应这些事件"   │        │                                │
│                     │        │  插件 → 主进程                  │
│                     │        │  "帮我调用这个能力"             │
└──────────┬──────────┘        └──────────────┬─────────────────┘
           │                                  │
           └─────────────────┬────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                      通信层                                       │
│                                                                  │
│   所有消息统一使用 id 字段关联请求与响应                            │
│                                                                  │
│   Peer.initialize(handlers=[...])                                │
│   Peer.invoke("llm.chat", input, stream=false) → result         │
│   Peer.invoke("llm.stream_chat", input, stream=true) → event*   │
│   Peer.invoke("handler.invoke", {handler_id, event})            │
│                                                                  │
│   Transport: StdioTransport / WebSocketTransport                 │
└──────────────────────────────────────────────────────────────────┘
                              │ JSON 消息流
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                      主进程（AstrBot Core）                        │
│                                                                  │
│   CapabilityRouter  ──► "llm.chat"         ──► LLM Service       │
│                    ──► "db.get"            ──► Storage           │
│                    ──► "handler.invoke"    ──► 转发给插件         │
│                                                                  │
│   HandlerDispatcher ◄── 外部消息 ──► 匹配订阅 ──► 回调插件        │
└──────────────────────────────────────────────────────────────────┘

              ┌─────────────────────┐
              │  compat.py（旁路）   │  ← 不是核心层
              │  旧 API → 转发新 API │     新代码不感知它
              └─────────────────────┘
```

---

## 二、两个核心概念的区分

```
┌──────────────────────────────────────────────────────────────┐
│  HandlerDescriptor                                           │
│  方向：插件 ──► 主进程（initialize 时声明）                   │
│  含义：插件订阅"我能响应哪些事件"                              │
│  例子：@on_command("hello") → 订阅 /hello 命令                │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  CapabilityInvocation                                        │
│  方向：插件 ──► 主进程（运行时按需调用）                       │
│  含义：插件请求"帮我执行这个能力"                              │
│  例子：ctx.llm.chat() → invoke "llm.chat"                    │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  CapabilityDescriptor                                        │
│  方向：主进程 ──► 插件（initialize_result 时返回）            │
│  含义：主进程声明"我提供哪些能力"                              │
│  例子：{ name: "llm.chat", supports_stream: false, ... }     │
└──────────────────────────────────────────────────────────────┘
```

| | HandlerDescriptor | CapabilityDescriptor | CapabilityInvocation |
|---|---|---|---|
| 谁发 | 插件 | 主进程 | 插件 |
| 何时 | initialize 时 | initialize_result 时 | 运行时 |
| 主进程动作 | 注册订阅 | 告知可用能力 | 执行并返回结果 |

---

## 三、分层职责

```
┌─────────────────────────────────────────────────────┐
│  Layer 1：用户层                                      │
│  Star / 装饰器 / MessageEvent                        │
│  插件作者只接触这一层                                 │
│  不知道：RPC、进程、序列化、订阅协议                   │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│  Layer 2：API 层                                      │
│  Context / LLMClient / DBClient / MemoryClient       │
│  PlatformClient                                     │
│  把能力包装成类型化 API                               │
│  不知道：JSON 格式、id、transport                     │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│  Layer 3：翻译层                                      │
│  CapabilityProxy                                    │
│  API 调用 → Peer.invoke(name, input, stream)         │
│  output dict → 返回类型                              │
│  无业务逻辑，一一对应                                 │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│  Layer 4：通信层                                      │
│  Peer / Transport / Protocol Messages               │
│  可靠收发消息                                         │
│  不知道业务，只知道消息格式                            │
└─────────────────────────────────────────────────────┘

  ※ compat.py 不是第五层，是用户层和 API 层的旁路入口。
     新代码不 import 它，可整体删除。
```

---

## 四、目录结构

```
astrbot_sdk/
│
├── star.py
├── context.py
├── decorators.py
├── events.py
├── errors.py
├── compat.py               ← 旁路，不是核心层
│
├── clients/
│   ├── llm.py
│   ├── memory.py
│   ├── db.py
│   └── platform.py
│
├── runtime/
│   ├── peer.py
│   ├── transport.py
│   ├── capability_router.py
│   ├── handler_dispatcher.py
│   ├── loader.py
│   └── bootstrap.py
│
└── protocol/
    ├── messages.py          ← 所有协议消息类型
    ├── descriptors.py       ← HandlerDescriptor / CapabilityDescriptor
    └── legacy_adapter.py    ← 旧线协议翻译，只做翻译无业务逻辑
```

---

## 五、协议消息定义（完整版）

### 五条硬规则

**规则一：统一使用 `id` 字段关联所有请求与响应**
```
所有消息只用一个关联字段：id
不区分 request_id / invocation_id，全部统一成 id。
发送方生成 id，接收方响应时原样带回，双方按 id 配对。
```

**规则二：event 只用于 stream=true 的调用**
```
stream=false 的调用只能以单个 result 结束。
stream=true 的调用只能以 event 序列结束。
stream=false 的调用不得发送 event(started/delta/completed/failed)。
违反此规则的实现视为协议错误。
```

**规则三：插件 handler 回调走统一 invoke，不新增消息类型**
```
主进程触发插件处理器时：
  capability: "handler.invoke"
  input: { handler_id: str, event: { 纯数据 } }

ctx 不通过线协议传输。
ctx 由插件进程本地重建并注入处理器。
看到处理器签名有 ctx 参数，不要误以为需要从主进程发过来。
```

**规则四：cancel 是"请求停止"，不是"立即停止"**
```
收到 cancel 后：
  若调用已结束 → 忽略，不报错
  若调用仍在执行 → 尽力中断，发送统一终止态

统一终止态：
  stream=true:  event { phase: "failed", error: { code: "cancelled" } }
  stream=false: result { success: false, error: { code: "cancelled" } }

调用方收到 cancel 后必须等待终止态，不能认为发完 cancel 就已结束。
```

**规则五：initialize 失败后连接进入不可用状态**
```
initialize 失败（协议版本不兼容 / handlers 非法 / 元信息缺失）时：
  返回 result { kind: "initialize_result", success: false, error: {...} }
  连接进入不可用状态
  除关闭连接外，不得继续发送普通 invoke
  对端收到失败的 initialize_result 后应立即关闭连接
```

---

### 消息格式

**initialize**
```json
{
  "type": "initialize",
  "id": "msg_001",
  "protocol_version": "1.0",
  "peer": {
    "name": "my-plugin",
    "role": "plugin",
    "version": "1.2.0"
  },
  "handlers": [ "HandlerDescriptor ..." ],
  "metadata": {}
}
```

**initialize_result（成功）**
```json
{
  "type": "result",
  "id": "msg_001",
  "kind": "initialize_result",
  "success": true,
  "output": {
    "peer": { "name": "astrbot-core", "role": "core" },
    "capabilities": [ "CapabilityDescriptor ..." ],
    "metadata": {}
  }
}
```

**initialize_result（失败）**
```json
{
  "type": "result",
  "id": "msg_001",
  "kind": "initialize_result",
  "success": false,
  "error": {
    "code": "protocol_version_mismatch",
    "message": "服务端支持协议版本 1.0，客户端请求版本 2.0",
    "hint": "请升级 astrbot_sdk 至最新版本",
    "retryable": false
  }
}
```
※ 失败后连接进入不可用状态，对端应立即关闭连接。

**invoke（普通能力）**
```json
{
  "type": "invoke",
  "id": "msg_002",
  "capability": "llm.chat",
  "input": { "prompt": "hi", "system": null },
  "stream": false
}
```

**invoke（流式能力）**
```json
{
  "type": "invoke",
  "id": "msg_003",
  "capability": "llm.stream_chat",
  "input": { "prompt": "hi" },
  "stream": true
}
```

**invoke（handler 回调）**
```json
{
  "type": "invoke",
  "id": "msg_010",
  "capability": "handler.invoke",
  "input": {
    "handler_id": "handler_abc123",
    "event": {
      "text": "/hello",
      "user_id": "u_001",
      "group_id": null,
      "platform": "qq"
    }
  },
  "stream": false
}
```
※ input.event 只含纯数据字段。ctx 由插件进程本地构建并注入，不经过线协议传输。

**result（成功）**
```json
{
  "type": "result",
  "id": "msg_002",
  "success": true,
  "output": { "text": "你好！" }
}
```

**result（失败）**
```json
{
  "type": "result",
  "id": "msg_002",
  "success": false,
  "error": {
    "code": "llm_not_configured",
    "message": "未找到可用的大模型配置",
    "hint": "请在管理面板的「模型管理」中添加模型",
    "retryable": false
  }
}
```

**event 序列（stream=true 专用）**
```json
{ "type": "event", "id": "msg_003", "phase": "started" }
{ "type": "event", "id": "msg_003", "phase": "delta",     "data": { "text": "你" } }
{ "type": "event", "id": "msg_003", "phase": "delta",     "data": { "text": "好" } }
{ "type": "event", "id": "msg_003", "phase": "completed", "output": { "text": "你好" } }
```

**event（取消终止态）**
```json
{
  "type": "event",
  "id": "msg_003",
  "phase": "failed",
  "error": {
    "code": "cancelled",
    "message": "调用被取消",
    "hint": "",
    "retryable": false
  }
}
```

**cancel**
```json
{
  "type": "cancel",
  "id": "msg_003",
  "reason": "user_cancelled"
}
```

---

## 六、描述符定义

### HandlerDescriptor

```
HandlerDescriptor
{
  id: str                    唯一标识，主进程回调时填入 handler_id
  trigger: CommandTrigger
          | MessageTrigger
          | EventTrigger
          | ScheduleTrigger
  priority: int              默认 0，越大越先执行
  permissions: {
    require_admin: bool
    level: int
  }
}
```

trigger 判别联合：不同 type 只允许对应字段出现，其他字段必须省略。

```
CommandTrigger
{
  type: "command"
  command: str        必填
  aliases: [str]      可选，默认 []
  description: str    可选
}

MessageTrigger
{
  type: "message"
  regex: str | null   可选
  keywords: [str]     可选，默认 []
  platforms: [str]    可选，默认 []（空表示所有平台）
}

EventTrigger
{
  type: "event"
  event_type: str     必填
}

ScheduleTrigger
{
  type: "schedule"
  cron: str | null
  interval_seconds: int | null
}
规则：cron 和 interval_seconds 必须且只能有一个非 null
```

### CapabilityDescriptor

主进程在 initialize_result.output.capabilities 中返回。

```
CapabilityDescriptor
{
  name: str                         capability name，如 "llm.chat"
  description: str                  一句话说明
  input_schema: JSONSchema | null   输入结构定义
  output_schema: JSONSchema | null  输出结构定义
  supports_stream: bool             是否支持 stream=true 调用
  cancelable: bool                  是否支持 cancel
}

schema 治理规则：
  内建核心 capability（llm.* / db.* / memory.* / platform.*）
    必须提供 input_schema 和 output_schema
  兼容期或动态注册的 capability
    允许为 null，但应在路线图中补全
  不得以"动态能力"为由长期保持 null
```

示例：
```json
{
  "name": "llm.chat",
  "description": "发送对话请求，返回模型回复文本",
  "input_schema": {
    "type": "object",
    "properties": {
      "prompt":      { "type": "string" },
      "system":      { "type": "string" },
      "model":       { "type": "string" },
      "temperature": { "type": "number" }
    },
    "required": ["prompt"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "text": { "type": "string" }
    },
    "required": ["text"]
  },
  "supports_stream": false,
  "cancelable": false
}
```

---

## 七、Capability Name 约定

```
格式：{namespace}.{method}

内建 capability 列表：
  llm.chat              ctx.llm.chat()
  llm.chat_raw          ctx.llm.chat_raw()
  llm.stream_chat       ctx.llm.stream_chat()
  memory.search         ctx.memory.search()
  memory.save           ctx.memory.save()
  memory.delete         ctx.memory.delete()
  db.get                ctx.db.get()
  db.set                ctx.db.set()
  db.delete             ctx.db.delete()
  db.list               ctx.db.list()
  platform.send         ctx.platform.send()
  platform.send_image   ctx.platform.send_image()
  platform.get_members  ctx.platform.get_members()

保留命名空间（插件不可使用这些前缀）：
  handler.*             框架内部：处理器回调
  system.*              框架内部：系统级操作
  internal.*            框架内部：保留扩展

命名规则：
  全小写，点分隔命名空间，下划线分隔单词，不用驼峰
  capability name 是协议约定，手写定义，不自动从方法名推导
  方法名重构不影响协议；协议变更需同步更新方法名和文档
```

---

## 八、错误模型

```python
@dataclass
class AstrBotError(Exception):
    code: str        # 机器可读，如 "llm_not_configured"
    message: str     # 发生了什么
    hint: str        # 用户怎么修
    retryable: bool  # True = 可重试（超时、网络抖动、临时不可用）
                     # False = 重试无意义（权限不足、能力不存在、配置缺失）
```

```
可重试（retryable=true）          不可重试（retryable=false）
─────────────────────────         ────────────────────────────
CapabilityTimeout                 LLMNotConfigured
NetworkError                      CapabilityNotFound
LLMTemporaryError                 PermissionDenied
                                  LLMError（模型返回错误）
                                  InvalidInput
                                  Cancelled
                                  ProtocolVersionMismatch
```

**Star.on_error 默认兜底：**
```
AstrBotError retryable=true  → 回复"请求失败，请稍后重试"
AstrBotError retryable=false → 回复 error.hint
其他异常                     → 回复"出了点问题，请联系插件作者"
所有情况均打完整 traceback 日志
插件作者覆盖 on_error 可完全自定义
```

---

## 九、Context 设计规则

```python
class Context:

    # 第一类：插件常用能力 Client（稳定，只扩展不删除）
    llm: LLMClient
    memory: MemoryClient
    db: DBClient
    platform: PlatformClient

    # 第二类：少量基础运行时信息
    plugin_id: str
    logger: Logger       # 自动带插件名前缀
    cancel_token: ...    # 取消当前调用

    # ❌ 不直接挂顶层：
    #    tools / runtime / scheduler / http /
    #    storage / persona / workflow / config
    #    有需要时设计专属 Client 后再加
```

---

## 十、LLM Client 分层

```python
class LLMClient:

    async def chat(
        self,
        prompt: str,
        *,
        system: str | None = None,
        history: list[ChatMessage] | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """发送对话请求，返回回复文本。爱好者场景首选。"""

    async def chat_raw(
        self,
        prompt: str,
        **kwargs,
    ) -> LLMResponse:
        """返回完整响应，含 usage / finish_reason / tool_calls。"""

    async def stream_chat(
        self,
        prompt: str,
        *,
        system: str | None = None,
        history: list[ChatMessage] | None = None,
    ) -> AsyncGenerator[str, None]:
        """流式对话，逐字返回文本片段。"""
```

chat() 和 chat_raw() 是唯二入口，不再增加第三种变体。

---

## 十一、关键数据流

### 11.1 插件加载与握手

```
框架启动
  → loader.py 扫描目录，发现 Star 子类
  → 收集 __handlers__，转成 HandlerDescriptor 列表
  → Peer 发送 initialize { id: "msg_001", handlers: [...] }
  → 主进程注册事件订阅
  → 主进程返回 initialize_result { id: "msg_001",
                                    success: true,
                                    capabilities: [...] }
  → 插件 CapabilityProxy 缓存 capabilities
  → 插件就绪

握手失败时：
  → 主进程返回 initialize_result { success: false, error: {...} }
  → 连接进入不可用状态
  → 插件进程关闭连接，打错误日志
  → 不发送任何 invoke
```

### 11.2 外部消息触发处理器

```
外部用户发送 /hello
  → 主进程 HandlerDispatcher 匹配订阅
  → 主进程发送 invoke {
      id: "msg_010",
      capability: "handler.invoke",
      input: {
        handler_id: "handler_abc",
        event: { text: "/hello", user_id: "u_001", ... }
      },
      stream: false
    }
  → 插件 handler_dispatcher 找到处理器方法
  → 本地构建 ctx，注入 event 和 ctx，执行处理器
  → 处理器内调用 ctx.llm.chat()（进入 11.3）
```

注：ctx 在插件进程本地构建，不经过线协议传输。

### 11.3 非流式能力调用

```
ctx.llm.chat("hi")
  → CapabilityProxy 构造 input
  → Peer.invoke("llm.chat", {prompt:"hi"}, stream=false)  id="msg_020"
  → 发送 { type:"invoke", id:"msg_020", capability:"llm.chat",
            input:{...}, stream:false }
  ← 收到 { type:"result", id:"msg_020", success:true,
            output:{text:"你好"} }
  → 解包 output.text → 返回 str

※ stream=false 不会收到任何 event 消息
```

### 11.4 流式能力调用

```
async for chunk in ctx.llm.stream_chat("hi"):
  → Peer.invoke("llm.stream_chat", {...}, stream=true)  id="msg_030"
  ← event { id:"msg_030", phase:"started" }
  ← event { id:"msg_030", phase:"delta",     data:{text:"你"} }  → yield "你"
  ← event { id:"msg_030", phase:"delta",     data:{text:"好"} }  → yield "好"
  ← event { id:"msg_030", phase:"completed", output:{text:"你好"} }
  → 生成器结束

※ stream=true 不会收到 result 消息，只收到 event 序列
```

---

## 十二、兼容层

```
compat.py 三条铁律：
  1. 新代码不 import compat.py
  2. compat.py 只 import 新代码
  3. compat.py 里只有"转发"，无业务逻辑

旧 API 映射：

旧写法                               新写法
──────────────────────────────────────────────────────────────
CommandComponent                  →  Star
context.llm_generate(prompt)      →  ctx.llm.chat(prompt)
context.tool_loop_agent(...)      →  ctx.llm.chat_raw(...) 含 tools
context.send_message(session, mc) →  ctx.platform.send(session, text)
context.put_kv_data(key, value)   →  ctx.db.set(key, value)
context.get_kv_data(key)          →  ctx.db.get(key)
@filter.command("hello")          →  @on_command("hello")
@filter.regex("pattern")          →  @on_message(regex="pattern")
@filter.permission(ADMIN)         →  @require_admin
yield event.plain_result("hi")    →  await event.reply("hi")

deprecated warning 格式（每个方法只打一次）：
  [AstrBot] 警告：context.llm_generate() 已过时。
  请替换为：ctx.llm.chat(prompt)
  迁移文档：https://docs.astrbot.app/migration/v3

流式兼容：
  旧 yield 写法只在 compat 层兜底处理
  新 API 只推荐 AsyncGenerator，不双轨并行

legacy_adapter.py 职责边界：
  只翻译旧线协议消息 ↔ 新线协议消息
  不含业务逻辑，不被新代码 import
  生命周期结束时整个删掉，新代码零修改
```

---

## 十三、迁移计划

```
阶段 0：立骨架（当前可开始）
──────────────────────────────────────────────────────
  做什么：
  ✦ 新建 star / context / decorators / events / errors / clients
  ✦ protocol/descriptors.py 写清 HandlerDescriptor（判别联合）
       和 CapabilityDescriptor（含 schema 治理规则）
  ✦ Peer 用 mock 占位（invoke 返回假数据）
  ✦ 写 compat.py
  
  验收：
  ✦ 旧插件加载不报错
  ✦ 新写法能跑通基本流程
  ✦ IDE 对 ctx.llm / ctx.db 有完整补全


阶段 1：接通信层
──────────────────────────────────────────────────────
  做什么：
  ✦ 实现 Transport / Peer（统一 id 字段）
  ✦ 实现 capability_router + handler_dispatcher
  ✦ 实现 legacy_adapter（旧协议翻译）
  ✦ clients/ 接上真实 capability 调用
  ✦ 实现 cancel 语义（请求停止，等终止态）
  ✦ 实现 initialize 失败处理（连接不可用 + 关闭）
  
  验收：
  ✦ 端到端调用成功
  ✦ 流式响应正常，stream=false 不出现 event 消息
  ✦ initialize 失败时连接正确关闭
  ✦ retryable 错误触发自动提示，不可重试触发 hint


阶段 2：清理旧实现
──────────────────────────────────────────────────────
  做什么：
  ✦ 删除 api/star/context.py（旧 Context）
  ✦ 删除 runtime/rpc/ 旧角色划分
  ✦ 删除 runtime/stars/filter/ 旧装饰器实现
  ✦ deprecated warning 升级为更显眼提示

  验收：
  ✦ 旧插件仍通过 compat.py 运行
  ✦ 核心路径无旧抽象引用


阶段 3：废弃旧 API（下一大版本）
──────────────────────────────────────────────────────
  做什么：
  ✦ deprecated warning 变启动报错
  ✦ 生态迁移完成后删除 compat.py 和 legacy_adapter.py

  验收：
  ✦ 删除 compat.py 后新代码零修改
```

---

## 十四、设计决策记录

| 问题 | 决策 | 理由 |
|------|------|------|
| 关联字段用什么名 | 统一 `id` | 防止 request_id / invocation_id 在 initialize_result 处产生歧义 |
| event 能用于非流式吗 | 不能，硬规则 | 防止"非流式先发 started 再发 result"污染处理逻辑 |
| initialize 失败后能继续发 invoke 吗 | 不能，连接进入不可用状态 | 防止在无效连接上堆积调用 |
| handler 回调走什么机制 | handler.invoke，不新增消息类型 | 协议保持五种消息 |
| ctx 从哪来 | 插件进程本地构建，不经线协议 | ctx 含运行时状态不可序列化，且无需传输 |
| HandlerDescriptor trigger 结构 | 判别联合 | 防止大量可空字段，方便校验和类型推导 |
| CapabilityDescriptor schema 是否可为 null | 可以，但内建 capability 必须提供 | 防止所有人偷懒填 null 导致 schema 形同虚设 |
| 保留命名空间 | handler.* / system.* / internal.* | 集中声明，防止插件误用或冲突 |
| 错误模型 | code + message + hint + retryable | retryable 区分策略差异，hint 直接告诉用户怎么修 |
| cancel 语义 | 请求停止，等终止态 | 避免实现侧歧义，调用方行为确定 |
| compat 定位 | 旁路入口，不是核心层 | 新代码不感知，可整体删除 |
| Context 扩展规则 | 只放常用能力 Client + 少量运行时信息 | 防止变成圣诞树 |
| chat() 返回类型 | str；进阶用 chat_raw() | 爱好者不拆包装，进阶有专用入口，两个定死 |
| 序列化 | 默认 JSON，不用 pickle | 跨语言，安全，可观测 |

---

*本文档是代码的源头。Python SDK、通信层、主进程三端有分歧时，以本文档为准。*

*v4 修正：补充 event 只用于 stream=true 的硬规则；initialize 失败场景和连接不可用状态；ctx 不经线协议传输的明确说明；CapabilityDescriptor schema 治理规则；保留命名空间集中声明（handler.* / system.* / internal.*）；initialize_result 失败示例。*
# AstrBot SDK 重构架构设计 v4

---

## 一、全局架构图

```
╔══════════════════════════════════════════════════════════════════════╗
║                        插件作者的世界                                 ║
║                                                                      ║
║   class MyPlugin(Star):                                              ║
║       @on_command("hello")                                           ║
║       async def hello(self, event: MessageEvent, ctx: Context):      ║
║           reply = await ctx.llm.chat(event.text)                     ║
║           await event.reply(reply)                                   ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
         │ Star / 装饰器 / Event            │ Context / Clients
         ▼                                  ▼
┌─────────────────────┐        ┌────────────────────────────────┐
│   Handler 系统       │        │   Capability 调用系统           │
│                     │        │                                │
│ HandlerDescriptor   │        │  ctx.llm.chat()                │
│ HandlerDispatcher   │        │  ctx.memory.search()           │
│                     │        │  ctx.db.get()                  │
│ 插件 → 主进程        │        │  ctx.platform.send()           │
│ "我能响应这些事件"   │        │                                │
│                     │        │  插件 → 主进程                  │
│                     │        │  "帮我调用这个能力"             │
└──────────┬──────────┘        └──────────────┬─────────────────┘
           │                                  │
           └─────────────────┬────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                      通信层                                       │
│                                                                  │
│   所有消息统一使用 id 字段关联请求与响应                            │
│                                                                  │
│   Peer.initialize(handlers=[...])                                │
│   Peer.invoke("llm.chat", input, stream=false) → result         │
│   Peer.invoke("llm.stream_chat", input, stream=true) → event*   │
│   Peer.invoke("handler.invoke", {handler_id, event})            │
│                                                                  │
│   Transport: StdioTransport / WebSocketTransport                 │
└──────────────────────────────────────────────────────────────────┘
                              │ JSON 消息流
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                      主进程（AstrBot Core）                        │
│                                                                  │
│   CapabilityRouter  ──► "llm.chat"         ──► LLM Service       │
│                    ──► "db.get"            ──► Storage           │
│                    ──► "handler.invoke"    ──► 转发给插件         │
│                                                                  │
│   HandlerDispatcher ◄── 外部消息 ──► 匹配订阅 ──► 回调插件        │
└──────────────────────────────────────────────────────────────────┘

              ┌─────────────────────┐
              │  compat.py（旁路）   │  ← 不是核心层
              │  旧 API → 转发新 API │     新代码不感知它
              └─────────────────────┘
```

---

## 二、两个核心概念的区分

```
┌──────────────────────────────────────────────────────────────┐
│  HandlerDescriptor                                           │
│  方向：插件 ──► 主进程（initialize 时声明）                   │
│  含义：插件订阅"我能响应哪些事件"                              │
│  例子：@on_command("hello") → 订阅 /hello 命令                │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  CapabilityInvocation                                        │
│  方向：插件 ──► 主进程（运行时按需调用）                       │
│  含义：插件请求"帮我执行这个能力"                              │
│  例子：ctx.llm.chat() → invoke "llm.chat"                    │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  CapabilityDescriptor                                        │
│  方向：主进程 ──► 插件（initialize_result 时返回）            │
│  含义：主进程声明"我提供哪些能力"                              │
│  例子：{ name: "llm.chat", supports_stream: false, ... }     │
└──────────────────────────────────────────────────────────────┘
```

| | HandlerDescriptor | CapabilityDescriptor | CapabilityInvocation |
|---|---|---|---|
| 谁发 | 插件 | 主进程 | 插件 |
| 何时 | initialize 时 | initialize_result 时 | 运行时 |
| 主进程动作 | 注册订阅 | 告知可用能力 | 执行并返回结果 |

---

## 三、分层职责

```
┌─────────────────────────────────────────────────────┐
│  Layer 1：用户层                                      │
│  Star / 装饰器 / MessageEvent                        │
│  插件作者只接触这一层                                 │
│  不知道：RPC、进程、序列化、订阅协议                   │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│  Layer 2：API 层                                      │
│  Context / LLMClient / DBClient / MemoryClient       │
│  PlatformClient                                     │
│  把能力包装成类型化 API                               │
│  不知道：JSON 格式、id、transport                     │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│  Layer 3：翻译层                                      │
│  CapabilityProxy                                    │
│  API 调用 → Peer.invoke(name, input, stream)         │
│  output dict → 返回类型                              │
│  无业务逻辑，一一对应                                 │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│  Layer 4：通信层                                      │
│  Peer / Transport / Protocol Messages               │
│  可靠收发消息                                         │
│  不知道业务，只知道消息格式                            │
└─────────────────────────────────────────────────────┘

  ※ compat.py 不是第五层，是用户层和 API 层的旁路入口。
     新代码不 import 它，可整体删除。
```

---

## 四、目录结构

```
astrbot_sdk/
│
├── star.py
├── context.py
├── decorators.py
├── events.py
├── errors.py
├── compat.py               ← 旁路，不是核心层
│
├── clients/
│   ├── llm.py
│   ├── memory.py
│   ├── db.py
│   └── platform.py
│
├── runtime/
│   ├── peer.py
│   ├── transport.py
│   ├── capability_router.py
│   ├── handler_dispatcher.py
│   ├── loader.py
│   └── bootstrap.py
│
└── protocol/
    ├── messages.py
    ├── descriptors.py
    └── legacy_adapter.py
```

---

## 五、协议消息定义（完整版）

### 五条硬规则

**规则一：统一使用 `id` 字段关联所有请求与响应**
```
所有消息只用一个关联字段：id
不区分 request_id / invocation_id，全部统一成 id。
发送方生成 id，接收方响应时原样带回，双方按 id 配对。
```

**规则二：event 只用于 stream=true 的调用**
```
stream=false 的调用只能以单个 result 结束。
stream=true 的调用只能以 event 序列结束。
stream=false 的调用不得发送 event(started/delta/completed/failed)。
违反此规则的实现视为协议错误。
```

**规则三：插件 handler 回调走统一 invoke，不新增消息类型**
```
主进程触发插件处理器时：
  capability: "handler.invoke"
  input: { handler_id: str, event: { 纯数据 } }

ctx 不通过线协议传输。
ctx 由插件进程本地重建并注入处理器。
看到处理器签名有 ctx 参数，不要误以为需要从主进程发过来。
```

**规则四：cancel 是"请求停止"，不是"立即停止"**
```
收到 cancel 后：
  若调用已结束 → 忽略，不报错
  若调用仍在执行 → 尽力中断，发送统一终止态

统一终止态：
  stream=true:  event { phase: "failed", error: { code: "cancelled" } }
  stream=false: result { success: false, error: { code: "cancelled" } }

调用方收到 cancel 后必须等待终止态，不能认为发完 cancel 就已结束。
```

**规则五：initialize 失败后连接进入不可用状态**
```
initialize 失败（协议版本不兼容 / handlers 非法 / 元信息缺失）时：
  返回 result { kind: "initialize_result", success: false, error: {...} }
  连接进入不可用状态
  除关闭连接外，不得继续发送普通 invoke
  对端收到失败的 initialize_result 后应立即关闭连接
```

---

### 消息格式

**initialize**
```json
{
  "type": "initialize",
  "id": "msg_001",
  "protocol_version": "1.0",
  "peer": {
    "name": "my-plugin",
    "role": "plugin",
    "version": "1.2.0"
  },
  "handlers": [ "HandlerDescriptor ..." ],
  "metadata": {}
}
```

**initialize_result（成功）**
```json
{
  "type": "result",
  "id": "msg_001",
  "kind": "initialize_result",
  "success": true,
  "output": {
    "peer": { "name": "astrbot-core", "role": "core" },
    "capabilities": [ "CapabilityDescriptor ..." ],
    "metadata": {}
  }
}
```

**initialize_result（失败）**
```json
{
  "type": "result",
  "id": "msg_001",
  "kind": "initialize_result",
  "success": false,
  "error": {
    "code": "protocol_version_mismatch",
    "message": "服务端支持协议版本 1.0，客户端请求版本 2.0",
    "hint": "请升级 astrbot_sdk 至最新版本",
    "retryable": false
  }
}
```
※ 失败后连接进入不可用状态，对端应立即关闭连接。

**invoke（普通能力）**
```json
{
  "type": "invoke",
  "id": "msg_002",
  "capability": "llm.chat",
  "input": { "prompt": "hi", "system": null },
  "stream": false
}
```

**invoke（流式能力）**
```json
{
  "type": "invoke",
  "id": "msg_003",
  "capability": "llm.stream_chat",
  "input": { "prompt": "hi" },
  "stream": true
}
```

**invoke（handler 回调）**
```json
{
  "type": "invoke",
  "id": "msg_010",
  "capability": "handler.invoke",
  "input": {
    "handler_id": "handler_abc123",
    "event": {
      "text": "/hello",
      "user_id": "u_001",
      "group_id": null,
      "platform": "qq"
    }
  },
  "stream": false
}
```
※ input.event 只含纯数据字段。ctx 由插件进程本地构建并注入，不经过线协议传输。

**result（成功）**
```json
{
  "type": "result",
  "id": "msg_002",
  "success": true,
  "output": { "text": "你好！" }
}
```

**result（失败）**
```json
{
  "type": "result",
  "id": "msg_002",
  "success": false,
  "error": {
    "code": "llm_not_configured",
    "message": "未找到可用的大模型配置",
    "hint": "请在管理面板的「模型管理」中添加模型",
    "retryable": false
  }
}
```

**event 序列（stream=true 专用）**
```json
{ "type": "event", "id": "msg_003", "phase": "started" }
{ "type": "event", "id": "msg_003", "phase": "delta",     "data": { "text": "你" } }
{ "type": "event", "id": "msg_003", "phase": "delta",     "data": { "text": "好" } }
{ "type": "event", "id": "msg_003", "phase": "completed", "output": { "text": "你好" } }
```

**event（取消终止态）**
```json
{
  "type": "event",
  "id": "msg_003",
  "phase": "failed",
  "error": {
    "code": "cancelled",
    "message": "调用被取消",
    "hint": "",
    "retryable": false
  }
}
```

**cancel**
```json
{
  "type": "cancel",
  "id": "msg_003",
  "reason": "user_cancelled"
}
```

---

## 六、描述符定义

### HandlerDescriptor

```
HandlerDescriptor
{
  id: str
  trigger: CommandTrigger
          | MessageTrigger
          | EventTrigger
          | ScheduleTrigger
  priority: int
  permissions: {
    require_admin: bool
    level: int
  }
}
```

trigger 判别联合：不同 type 只允许对应字段出现，其他字段必须省略。

```
CommandTrigger
{
  type: "command"
  command: str
  aliases: [str]
  description: str
}

MessageTrigger
{
  type: "message"
  regex: str | null
  keywords: [str]
  platforms: [str]
}

EventTrigger
{
  type: "event"
  event_type: str
}

ScheduleTrigger
{
  type: "schedule"
  cron: str | null
  interval_seconds: int | null
}
```

### CapabilityDescriptor

```
CapabilityDescriptor
{
  name: str
  description: str
  input_schema: JSONSchema | null
  output_schema: JSONSchema | null
  supports_stream: bool
  cancelable: bool
}
```

schema 治理规则：
```
内建核心 capability（llm.* / db.* / memory.* / platform.*）必须提供 input_schema 和 output_schema
兼容期或动态注册的 capability 允许为 null，但应在路线图中补全
不得以“动态能力”为由长期保持 null
```

---

## 七、Capability Name 约定

```
格式：{namespace}.{method}

内建 capability 列表：
  llm.chat
  llm.chat_raw
  llm.stream_chat
  memory.search
  memory.save
  memory.delete
  db.get
  db.set
  db.delete
  db.list
  platform.send
  platform.send_image
  platform.get_members

保留命名空间：
  handler.*
  system.*
  internal.*
```

---

## 八、错误模型

```python
@dataclass
class AstrBotError(Exception):
    code: str
    message: str
    hint: str
    retryable: bool
```

---

## 九、Context 设计规则

```python
class Context:
    llm: LLMClient
    memory: MemoryClient
    db: DBClient
    platform: PlatformClient
    plugin_id: str
    logger: Logger
    cancel_token: ...
```

---

## 十、LLM Client 分层

```python
class LLMClient:
    async def chat(...) -> str: ...
    async def chat_raw(...) -> LLMResponse: ...
    async def stream_chat(...) -> AsyncGenerator[str, None]: ...
```

---

## 十一、关键数据流

- 插件启动后发送 `initialize`
- 主进程返回 `initialize_result`
- 外部消息触发 `handler.invoke`
- 非流式能力调用只返回 `result`
- 流式能力调用只返回 `event` 序列

---

## 十二、兼容层

```
compat.py 三条铁律：
  1. 新代码不 import compat.py
  2. compat.py 只 import 新代码
  3. compat.py 里只有转发，无业务逻辑
```

---

## 十三、迁移计划

- 阶段 0：立骨架
- 阶段 1：接通信层
- 阶段 2：清理旧实现
- 阶段 3：废弃旧 API

---

## 十四、设计决策记录

- 统一 `id`
- `event` 只用于 `stream=true`
- initialize 失败后连接不可用
- handler 回调走 `handler.invoke`
- ctx 在插件进程本地构建
- HandlerDescriptor 使用判别联合
- 内建 capability schema 必填
- 保留命名空间 `handler.* / system.* / internal.*`
- 错误模型固定为 `code + message + hint + retryable`
- cancel 为“请求停止，等待终止态”
- compat 是旁路，不是核心层
- Context 只挂常用 client 与少量运行时信息
- `chat()` 返回 `str`，进阶使用 `chat_raw()`
- 序列化使用 JSON，不用 pickle

---

*本文档是代码的源头。Python SDK、通信层、主进程三端有分歧时，以本文档为准。*
