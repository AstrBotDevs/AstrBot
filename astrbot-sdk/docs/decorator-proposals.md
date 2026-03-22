# AstrBot SDK 装饰器改进提案

> 本文档基于当前 SDK 已有公开 API、客户端契约和运行时约束整理。
> 目标不是罗列“能不能做”，而是判断哪些场景适合做声明式语法糖，哪些其实是在引入新的运行时能力。

## 目录

- [设计原则](#设计原则)
- [现状概览](#现状概览)
- [候选提案矩阵](#候选提案矩阵)
- [推荐优先实现](#推荐优先实现)
- [可做但需约束](#可做但需约束)
- [实现模式](#实现模式)

---

## 设计原则

### 装饰器的职责边界

- 装饰器优先做“声明元数据”的语法糖，不应偷偷改变已有运行时语义。
- 如果一个提案需要引入新的生命周期、资源所有权、并发控制或安全确认，它就不再是薄语法糖，而是新的运行时能力。
- 首版实现优先覆盖“当前已有稳定 API 的声明式封装”，避免一上来就把文档写成运行时重构方案。

### 评估标准

一个候选装饰器如果同时满足以下条件，才适合优先落地：

- 有明确的现有 API 作为等价实现。
- 不会隐藏关键清理步骤或安全边界。
- 不会和已有装饰器形成语义重叠或冲突。
- 失败时能够明确暴露错误，而不是静默吞掉。

---

## 现状概览

### 已有装饰器

| 装饰器 | 用途 | 位置 |
|--------|------|------|
| `@on_command` | 命令触发 | `decorators.py` |
| `@on_message` | 消息触发 | `decorators.py` |
| `@on_event` | 事件触发 | `decorators.py` |
| `@on_schedule` | 定时任务触发 | `decorators.py` |
| `@conversation_command` | 会话命令 | `decorators.py` |
| `@require_admin` / `@admin_only` | 管理员权限 | `decorators.py` |
| `@platforms` | 平台过滤 | `decorators.py` |
| `@message_types` | 消息类型过滤 | `decorators.py` |
| `@group_only` / `@private_only` | 聊天类型过滤 | `decorators.py` |
| `@rate_limit` / `@cooldown` | 限流 | `decorators.py` |
| `@priority` | 执行优先级 | `decorators.py` |
| `@provide_capability` | 能力导出 | `decorators.py` |
| `@register_llm_tool` | LLM 工具注册 | `decorators.py` |
| `@register_agent` | Agent 注册 | `decorators.py` |
| `@acknowledge_global_mcp_risk` | 允许变更全局 MCP 状态的显式确认 | `decorators.py` |
| `@session_waiter` | 多轮消息等待 | `session_waiter.py` |

### 当前相关 API 事实

- `ctx.http.register_api()` 的本质是注册 `route -> capability` 映射，`handler=` 也只是从 `@provide_capability` 元数据解析 capability 名称。
- `ctx.register_task()` 当前负责启动后台任务，并在任务取消或失败时记录日志；它不负责统一追踪任务所有权，也不会自动在插件停止时回收任务。
- `session_waiter` 已经存在，推荐搭配 `await ctx.register_task(waiter(...), "...")` 使用；直接 `await` 会阻塞当前 dispatch。
- `ctx.metadata.get_plugin_config()` 是当前插件配置的读取入口。
- `ctx.mcp.register_global_server()` 受显式风险确认约束，全局 MCP 操作不能被装饰器静默绕过。
- `ctx.register_skill()` 当前需要显式的 `name/path/description`，不是“给某个函数打标记”就能完成。

---

## 候选提案矩阵

| 优先级 | 装饰器 | 当前判断 | 类型 | 备注 |
|--------|--------|----------|------|------|
| ⭐⭐⭐⭐⭐ | `@http_api` | 推荐 | 薄语法糖 | 应建立在现有 HTTP capability 契约之上 |
| ⭐⭐⭐⭐ | `@validate_config` | 推荐 | 薄语法糖 | 应基于 `ctx.metadata.get_plugin_config()` |
| ⭐⭐⭐ | `@require_permission` | 推荐 | 能力增强 | 扩展现有权限元数据体系 |
| ⭐⭐⭐ | `@on_provider_change` | 可做 | 轻量运行时封装 | 本质是 hook 的注册与自动解绑 |
| ⭐⭐⭐ | `@register_skill` | 可做但受限 | 轻量运行时封装 | 必须显式解决 `path` 来源 |
| ⭐⭐⭐⭐ | `@background_task` | 可做但不是薄糖 | 新运行时能力 | 需要任务所有权和停止时回收策略 |
| ⭐⭐⭐⭐ | `@mcp_server` | 可做但需强约束 | 新运行时能力 | 全局 MCP 必须保留风险确认边界 |

---

## 推荐优先实现

### 1. `@http_api`

**定位**: 为现有 HTTP capability 注册流程提供声明式入口。

#### 为什么适合优先做

- 当前已经有稳定的 `ctx.http.register_api()` / `ctx.http.unregister_api()`。
- 当前已经有 `@provide_capability` 元数据体系可复用。
- 注册与解绑点明确，容易在插件生命周期内做自动化。

#### 首版设计建议

- 不要偷偷生成不可见的 capability 名称。
- 首版应要求显式 `capability_name`，或者要求与 `@provide_capability` 叠加使用。
- 自动化的范围只限于“收集元数据并在生命周期里注册/解绑路由”。

#### 推荐写法

```python
@http_api(
    route="/my-api",
    methods=["GET", "POST"],
    capability_name="my_plugin.http_handler",
    description="我的 API",
)
async def handle_http_request(self, request_id: str, payload: dict, cancel_token):
    return {"status": 200, "body": {"result": "ok"}}
```

#### 等价手动实现

```python
@provide_capability(
    name="my_plugin.http_handler",
    description="处理 HTTP 请求",
)
async def handle_http_request(self, request_id: str, payload: dict, cancel_token):
    return {"status": 200, "body": {"result": "ok"}}

async def on_start(self, ctx):
    await ctx.http.register_api(
        route="/my-api",
        methods=["GET", "POST"],
        handler=self.handle_http_request,
        description="我的 API",
    )

async def on_stop(self, ctx):
    await ctx.http.unregister_api("/my-api")
```

#### 实现约束

- 自动注册失败时必须抛错，不应静默跳过。
- 自动解绑失败至少要记录日志。
- 文档里要明确这是 HTTP capability 的装饰器，而不是任意异步函数都能暴露成 API。

---

### 2. `@validate_config`

**定位**: 为启动期配置校验提供声明式入口。

#### 为什么适合优先做

- 当前已有稳定的配置读取入口 `ctx.metadata.get_plugin_config()`。
- 配置校验是纯前置逻辑，天然适合声明式元数据。
- 失败行为明确，应直接抛出配置错误。

#### 推荐写法

```python
class MyConfig(BaseModel):
    api_key: str
    timeout: int = Field(default=30, gt=0)


@validate_config(model=MyConfig)
async def on_start(self, ctx):
    pass
```

#### 首版边界

- 首版只做校验，不修改 `Context` 公共 API 形状。
- 如需缓存校验后的配置，建议挂到插件实例私有属性，而不是新增隐式 `ctx.get_validated_config()`。
- 支持 Pydantic 模型优先于自定义 dict schema，可减少自造轮子。

---

### 3. `@require_permission`

**定位**: 在现有 `@require_admin` 基础上扩展权限表达能力。

#### 为什么适合做

- 权限要求本质上是 handler 元数据，适合与现有装饰器体系统一。
- 可以逐步演进，不需要一次性覆盖所有复杂权限模型。

#### 推荐方向

- `@require_permission("moderator")`
- `@require_users("user1", "user2")`
- `@require_any(...)` / `@require_all(...)`

#### 约束

- 首版不要把权限校验函数做成任意闭包黑盒，否则测试和序列化边界会迅速恶化。
- 先支持可静态描述的权限元数据，再考虑可执行自定义校验。

---

### 4. `@on_provider_change`

**定位**: 封装 `ctx.provider_manager.register_provider_change_hook()` 的注册和解绑。

#### 为什么可以做

- 现有 API 已经稳定。
- 注册与解绑必须成对出现，适合交给生命周期自动管理。

#### 推荐写法

```python
@on_provider_change(provider_types=["chat"])
async def handle_provider_change(self, provider_id: str, provider_type, umo):
    pass
```

#### 实现约束

- 运行时必须自动保存 hook task，并在插件停止时注销。
- 回调异常要保留现有日志语义，不能因为装饰器而吞错。

---

## 可做但需约束

### 1. `@background_task`

这个提案有价值，但不能假装它只是 `ctx.register_task()` 的别名。

#### 根本问题

- 当前 `ctx.register_task()` 只负责启动任务和记录日志。
- 自动在 `on_stop()` 取消任务，需要新增“任务归属”和“生命周期回收”机制。
- 如果支持 `on_error="restart"`，那已经是 supervisor 级策略，不是装饰器元数据而已。

#### 结论

- 可以做。
- 但应被标记为“新增运行时能力”，而不是“低复杂度语法糖”。

---

### 2. `@mcp_server`

这个提案也有价值，但需要明确区分本地 MCP 和全局 MCP。

#### 根本问题

- 本地 MCP 注册更接近自动化封装。
- 全局 MCP 注册受显式风险确认保护，不能因为加了装饰器就绕过 `@acknowledge_global_mcp_risk`。

#### 结论

- 本地 MCP 自动注册可以优先考虑。
- 全局 MCP 自动注册必须要求插件类显式声明风险确认。

---

### 3. `@register_skill`

这个提案可以做，但首版必须先收紧模型。

- 当前注册 skill 需要 `name`、`path`、`description`。
- `path` 是核心输入，不能省略，也不应依赖脆弱的隐式推导。
- 因此更适合做类级或模块级声明，而不是方法级“注册一个 handler 就自动成为 skill”。

#### 推荐写法

```python
@register_skill(
    name="my_skill",
    path="skills/my_skill",
    description="我的技能",
)
class MyPlugin(Star):
    pass
```

#### 实现约束

- 首版必须要求显式 `path`。
- 注册失败时应直接抛错。
- 插件停止时应自动注销已注册 skill。

---

## 实现模式

### 通用原则

- 装饰器负责挂元数据，不负责直接执行副作用。
- `Star` 子类收集元数据。
- 运行时在明确的生命周期钩子里统一注册和解绑。

### 元数据示例

```python
def http_api(
    *,
    route: str,
    capability_name: str,
    methods: list[str] | None = None,
    description: str = "",
):
    def decorator(func):
        func.__astrbot_http_api__ = {
            "route": route,
            "capability_name": capability_name,
            "methods": methods or ["GET"],
            "description": description,
        }
        return func

    return decorator
```

### 收集示例

```python
class Star:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.__http_apis__ = []
        for name, attr in cls.__dict__.items():
            if hasattr(attr, "__astrbot_http_api__"):
                cls.__http_apis__.append((name, attr.__astrbot_http_api__))
```

### 生命周期注册示例

```python
async def setup_plugin(star: Star, ctx: Context):
    for _method_name, meta in star.__http_apis__:
        await ctx.http.register_api(
            route=meta["route"],
            handler_capability=meta["capability_name"],
            methods=meta["methods"],
            description=meta["description"],
        )


async def teardown_plugin(star: Star, ctx: Context):
    for _method_name, meta in star.__http_apis__:
        await ctx.http.unregister_api(meta["route"])
```

### 不该在装饰器里做的事

- 隐式生成外部不可见的 capability 名称。
- 在导入时直接发起注册请求。
- 静默吞掉注册、解绑、校验失败。
- 绕过全局 MCP 风险确认。

---

## 实施建议

### 阶段一

1. `@http_api`
2. `@validate_config`
3. `@require_permission`
4. `@on_provider_change`

### 阶段二

5. `@background_task`
6. `@mcp_server`
7. `@register_skill`

---

## 文档更新记录

| 日期 | 内容 |
|------|------|
| 2026-03-22 | 重写提案，按当前 SDK 事实区分“薄语法糖”和“新增运行时能力” |
