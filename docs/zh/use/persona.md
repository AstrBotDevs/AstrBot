# Persona 人格设定

Persona 决定 Agent 在一次会话中采用的系统提示词、预设对话、工具、Skills 和错误回复。你可以在 WebUI 左侧的 **人格设定** 页面创建 Persona，并用文件夹组织大量角色。

## Persona 包含什么

- **Persona ID**：唯一标识。会话、配置档、子代理和定时任务都通过它引用 Persona，因此创建后应尽量保持稳定。
- **系统提示词**：定义角色、目标、边界和回复方式。不要在其中保存密钥或其他不应发送给模型的机密。
- **自定义报错回复**：当前 Persona 的 LLM 请求失败时优先向用户发送的文本；留空则使用系统默认错误消息。
- **预设对话**：按“用户、助手”成对排列的 few-shot 示例，条数必须为偶数。它们会加入模型上下文，但不会作为真实会话消息写回历史。
- **工具 / MCP 工具**：`null` 表示允许所有当前可用工具，明确的名称列表表示只允许这些工具，空列表表示不允许工具。
- **Skills**：语义与工具相同；可以使用全部、只使用选定项或不使用任何 Skill。

工具和 Skills 是权限边界，不只是提示词优化。对 Shell、文件写入、浏览器、外部账号和管理类工具，应采用最小权限，并在模型或插件变化后重新检查选择结果。

## 哪个 Persona 会生效

本地 Agent Runner 按以下优先级解析 Persona：

1. **会话管理**中针对该消息会话设置的强制 Persona；
2. 当前对话记录选择的 Persona；
3. 当前配置档的默认 Persona：本地 Runner 读取 `agent_runner.config.persona.persona_id`，第三方 Runner 读取 `agent_runner.config.persona_id`。

会话规则适合为某个平台、群组或用户固定角色。没有强制规则时，WebChat 可以在对话级切换 Persona。显式选择“不使用 Persona”时，不会再应用配置档默认 Persona。

Persona 更新后，运行时缓存会立即刷新；通常不需要重启 AstrBot。已经保存的历史消息不会因 Persona 修改而重写，后续模型请求会使用新配置。

## 对话指令

管理员可以使用 `/persona status` 查看当前状态、`/persona list` 列出 Persona、`/persona show <persona_id>` 查看详情、`/persona set <persona_id>` 切换当前对话，或用 `/persona unset` 显式停用 Persona。仅输入 `/persona` 会显示子指令树。

## 文件夹与删除

文件夹只用于 WebUI 组织和排序，不改变 Persona 的运行权限或作用域。删除文件夹时，其中的 Persona 会移动到根目录，而不是一起删除。

删除 Persona 会移除 Persona 定义，但不会自动改写所有外部引用。删除前请检查：

- 配置档的默认 Persona；
- 会话管理规则和已有对话选择；
- 子代理、Cron 任务或插件中保存的 Persona ID；
- 与该 Persona 相关、存放在其他运行时表中的已学习数据。

## 导入与导出

Persona 卡片菜单可以导出 JSON，页面顶部可以导入 JSON。当前格式只交换：

```json
{
  "persona_id": "researcher",
  "system_prompt": "You are a careful research assistant.",
  "begin_dialogs": ["Summarize this source.", "Please provide the source."]
}
```

导出文件**不包含**工具、Skills、自定义错误回复、文件夹、排序、长期记忆或 Persona Runtime 学习数据。

导入时：

- 必须存在非空字符串 `system_prompt`；
- `begin_dialogs` 中只有字符串项会保留；
- 导入到当前打开的文件夹；
- ID 冲突时会自动追加 `_imported`、`_imported_2` 等后缀；
- 工具和 Skills 会被设置为“全部可用”。

> [!WARNING]
> Persona JSON 属于提示词输入，导入第三方文件前应先人工审阅。导入后立即重新配置工具和 Skills；否则该 Persona 会继承所有当前可用能力。导出文件也不能作为完整备份。

完整迁移应使用 AstrBot 的[运行数据备份](../deploy/astrbot/backup)，而不是只导出 Persona JSON。恢复后还应核对插件、MCP、Skills 和 Provider 是否仍存在，因为 Persona 只保存这些能力的名称引用。

## 与其他功能的关系

- [子代理编排](./subagent)：子 Agent 可以绑定 Persona，并继承其提示词、预设对话和工具；当前不会继承隔离的 Persona Skills。
- [Skills](./skills)：Persona 可以缩小当前会话可见的 Skill 集合。
- [长期记忆](./long-term-memory)：长期记忆按用户和消息会话存储，不包含在 Persona 导出文件中，也不会因为删除 Persona 而自动清除。
