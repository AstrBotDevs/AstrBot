# LLM Tools 统一权限模型提案

## 背景

AstrBot 中插件 tools、MCP tools、Handoff tools 以及部分内置 tools 最终都会进入 LLM tool-calling 工具集合。当前第三方工具的权限控制主要依赖插件或工具开发者自行在 handler 内实现。

如果插件开发者忘记在工具内部检查管理员权限，普通用户可能通过自然语言诱导 LLM 调用高危工具。对于文件读写、命令执行、浏览器控制、MCP 外部能力、定时任务等工具，这会带来宿主机与账号安全风险。

## 当前问题

当前权限控制存在几个结构性问题：

1. 第三方插件工具没有统一鉴权入口。
2. MCP tools 默认缺少 AstrBot 侧统一权限模型。
3. LLM 请求构建阶段会把可用工具 schema 注入给模型，普通用户可能看到不应看到的高危工具 schema。
4. 执行阶段缺少对所有 LLM tools 的统一兜底校验。
5. WebUI 无法按工具维度调整 `member` / `admin` / `disabled` 权限。

因此，第三方 tool 是否安全主要取决于插件开发者是否主动写二次鉴权。

## 目标

希望 AstrBot 为所有 LLM tools 提供统一、可配置、向后兼容的权限模型。

建议权限级别：

```text
member     所有人可用
admin      仅 AstrBot 管理员可用
disabled   完全禁用，LLM 不可见，也不可执行
```

## 建议设计

### 1. 为 FunctionTool 增加 permission 字段

建议在 `FunctionTool` 中增加：

```python
permission: str | None = None
```

含义：

- `None`：工具未显式声明权限，走全局默认策略；
- `member`：所有用户可用；
- `admin`：仅管理员可用；
- `disabled`：完全禁用。

使用 `None` 而不是直接默认 `member`，可以让旧插件统一受全局默认策略控制，方便后续渐进式收紧。

### 2. 增加统一权限决策模块

建议新增类似模块：

```text
astrbot/core/agent/tool_permission.py
```

职责：

- 标准化权限值；
- 生成稳定 permission key；
- 解析工具最终生效权限。

建议 key 格式：

```text
builtin:{tool_name}
plugin:{handler_module_path}:{tool_name}
mcp:{server_name}:{tool_name}
unknown:{tool_name}
```

其中插件工具的 key 生成需要明确兜底策略：

1. 优先使用 `handler_module_path`。
2. 如果 `handler_module_path` 为空，尝试使用插件注册名、插件 root dir 或 Star metadata 中可稳定识别插件身份的字段。
3. 如果仍然无法确认来源，则退化为 `unknown:{tool_name}`，而不是生成 `plugin:None:{tool_name}`。
4. 对 `unknown` 来源工具，WebUI 应明确展示其来源未知，管理员可以手动调整权限，但实现侧应避免多个未知来源同名工具互相覆盖。

权限优先级：

1. WebUI 覆盖配置；
2. 工具自身声明；
3. 全局未声明工具默认策略。

### 3. 权限配置存储位置

工具权限不建议存放在 `provider_settings` 内。

原因是工具权限与具体 LLM Provider 无关。用户切换 OpenAI、Claude、Ollama 或其它模型提供商时，不应该导致工具权限配置变化或需要重新配置。

建议将工具权限配置放在全局配置的独立字段中，例如：

```json
{
  "llm_tool_permission_settings": {
    "undeclared_default": "member",
    "overrides": {
      "mcp:playwright:browser_navigate": "admin",
      "plugin:plugins.example.main:write_file": "admin",
      "builtin:future_task": "admin"
    }
  }
}
```

如果 AstrBot 需要支持不同 UMO / channel / workspace 使用不同配置，则建议沿用现有 `get_config(umo=...)` 的配置解析方式，在每个会话配置中保存自己的 `llm_tool_permission_settings`。

也就是说：

- 配置字段不归属于 provider；
- 权限解析可以按当前 UMO 读取对应配置；
- permission key 本身保持稳定，不携带 UMO；
- 覆盖表的来源由当前会话配置决定，避免多租户 / 多空间场景下来源不清。

### 4. 请求阶段过滤 tool schema

在 LLM 请求真正发出前，根据当前事件用户权限过滤 `req.func_tool`。

建议位置：

```text
_plugin_tool_fix(event, req)
之后
AgentRunner.reset / provider request 之前
```

期望行为：

- `disabled` 工具永远不注入给 LLM；
- 非管理员用户看不到 `admin` 工具 schema；
- 管理员可以看到 `member` 和 `admin` 工具；
- 从源头降低 prompt injection 和 schema 暴露风险。

过滤时必须避免原地修改共享 ToolSet。

建议实现要求：

- 不要直接修改全局 `provider_manager.llm_tools.func_list`；
- 不要原地裁剪可能被多个请求共享的 `ToolSet.tools`；
- 应构造请求局部 `ToolSet` 副本，或在过滤前进行深拷贝；
- 最终仅替换当前请求的 `req.func_tool`。

这样可以避免普通用户请求过滤工具时影响管理员请求，或并发请求之间互相污染。

### 5. 执行阶段二次兜底校验

在 `ToolLoopAgentRunner._handle_function_tools()` 中，在构造 `valid_params` 与真正执行工具前增加权限检查。

这样即使出现：

- 历史上下文残留；
- 请求层过滤遗漏；
- 外部伪造 tool_call；
- 工具 schema 模式切换；

执行层仍然可以兜底拒绝未授权调用。

建议行为：

- `disabled`：永远拒绝；
- `admin + 普通用户`：拒绝；
- `admin + 管理员`：允许；
- `member`：允许继续执行；
- 无法确认上下文安全性时：拒绝。

### 6. 系统上下文的安全识别

无 `event` 的系统任务 / cron / 后台任务不应简单视为普通用户，否则可能误伤内部系统上下文。

但也不应简单通过 `event is None` 就放行 admin 工具，否则未来如果存在可被外部构造的无事件调用路径，可能形成绕过。

建议引入明确的受信任系统上下文机制，例如：

```python
trusted_system_context: bool = False
```

或类似不可由用户输入伪造的内部标志，例如 `TrustedToolContext` / `SystemContextToken`。

建议规则：

1. 有 `event` 时，严格使用 `event.is_admin()` 判断。
2. 无 `event` 时，只有当 run context 显式带有内部可信标志，才视为系统上下文。
3. 该可信标志只能由 Cron、系统主动任务、内部 runner 等框架代码设置，不能从用户 prompt、tool args 或外部请求参数中读取。
4. 如果既没有 `event`，也没有可信系统标志，则拒绝执行 `admin` 工具。

这样既能避免误伤系统任务，又能避免把 `event is None` 变成权限绕过条件。

### 7. 与工具内部鉴权的关系

统一权限模型不应替代工具 handler 内部的业务校验。

建议采用“最小权限优先 / 任一拒绝即拒绝”的策略：

- 统一权限模型负责 LLM schema 可见性与执行前基础权限兜底；
- 工具 handler 内部仍可根据业务场景执行更细粒度检查；
- 如果统一权限允许，但 handler 内部拒绝，则最终拒绝；
- 如果统一权限拒绝，则不应进入 handler；
- 对高危工具，建议同时保留 handler 内部鉴权作为纵深防御。

也就是说，统一权限模型是框架级最低安全线，工具内部鉴权是业务级补充安全线。

### 8. 高危框架工具默认收紧

建议默认标记为 `admin`：

- Handoff tools / sub-agent transfer tools；
- MCP tools；
- FutureTaskTool / cron 管理工具；
- 文件改写、shell、浏览器控制等高危工具。

旧插件为了兼容可以默认 `member`，但建议 WebUI 中清晰展示未声明权限的工具，并允许管理员手动调整。

### 9. WebUI 提供工具权限管理

希望 WebUI 工具管理页展示：

- 工具名；
- 来源：builtin / plugin / mcp / unknown；
- 当前有效权限；
- permission key；
- 是否启用；
- 可编辑权限：`member` / `admin` / `disabled`。

修改后持久化到 `llm_tool_permission_settings`，而不是 provider 专用配置。

示例：

```json
{
  "llm_tool_permission_settings": {
    "undeclared_default": "member",
    "overrides": {
      "mcp:playwright:browser_navigate": "admin",
      "plugin:plugins.example.main:write_file": "admin",
      "builtin:future_task": "admin"
    }
  }
}
```

## 预期收益

- 第三方插件即使遗漏鉴权，也有后端统一兜底；
- 普通用户不会看到高危工具 schema；
- MCP、插件、内置工具可以统一治理；
- 管理员可以在 WebUI 中动态调整工具权限；
- 旧插件保持兼容，未声明权限时默认按全局策略处理；
- 后续可以逐步将高危工具默认上调为 `admin`。

## 兼容性建议

MVP 阶段可先做：

1. `FunctionTool.permission: str | None = None`；
2. 新增 `tool_permission.py`；
3. 执行层权限兜底；
4. WebUI 工具列表返回 `permission` / `permission_key`；
5. 插件文档补充权限声明方式。

请求层过滤、WebUI set-permission 接口和高危工具默认收紧可以作为后续迭代补齐。