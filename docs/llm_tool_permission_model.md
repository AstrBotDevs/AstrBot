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

权限优先级：

1. WebUI 覆盖配置；
2. 工具自身声明；
3. 全局未声明工具默认策略。

### 3. 请求阶段过滤 tool schema

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

### 4. 执行阶段二次兜底校验

在 `ToolLoopAgentRunner._handle_function_tools()` 中，在构造 `valid_params` 与真正执行工具前增加权限检查。

这样即使出现：

- 历史上下文残留；
- 请求层过滤遗漏；
- 外部伪造 tool_call；
- 工具 schema 模式切换；

执行层仍然可以兜底拒绝未授权调用。

注意：无 `event` 的系统任务 / cron / 后台任务不应简单视为普通用户，否则可能误伤内部系统上下文。建议有 `event` 时严格走 `event.is_admin()`，无 `event` 时单独识别系统上下文。

### 5. 高危框架工具默认收紧

建议默认标记为 `admin`：

- Handoff tools / sub-agent transfer tools；
- MCP tools；
- FutureTaskTool / cron 管理工具；
- 文件改写、shell、浏览器控制等高危工具。

### 6. WebUI 提供工具权限管理

希望 WebUI 工具管理页展示：

- 工具名；
- 来源：builtin / plugin / mcp / unknown；
- 当前有效权限；
- permission key；
- 是否启用；
- 可编辑权限：`member` / `admin` / `disabled`。

修改后持久化到配置中，例如：

```json
{
  "provider_settings": {
    "undeclared_llm_tool_permission": "member",
    "llm_tool_permission_overrides": {
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
