# 插件可视化视图

在插件中提供 HTML 界面，并通过 Bridge 与 AstrBot 通信。根据界面的使用位置选择 metadata 中的 `target`：

| 界面 | `target` | 适用场景 | 打开方式 |
| --- | --- | --- | --- |
| [独立插件页面](./plugin-page.md) | `plugin_page` | 设置、管理面板、日志 | WebUI 插件入口 |
| [消息交互组件](./chat-message.md) | `chat_message` | 结果列表、选择器、确认表单 | 命令、消息处理器或工具返回 `event.view_result()` |
| [工作台页面](./workbench.md) | `chat_workbench` | 文件预览、笔记、会话分析 | `event.view_result()` |
| [双入口工作台](./workbench.md#注册常驻页面) | `chat_workbench_with_launcher` | 笔记、会话分析 | `event.view_result()` 或工作台「＋」入口 |

## 注册视图

在插件的 `metadata.yaml` 中通过 `views` 声明视图。`name` 在插件内唯一，入口固定为 `views/<name>/index.html`，无需声明 `entry`。Python 只负责创建视图、处理 action 或提供 Web API。

```yaml
views:
  - name: context_usage
    target: chat_workbench_with_launcher
    title: 上下文用量
    description: 查看当前会话的 token 使用情况
```

`target` 默认是 `plugin_page`，保留旧页面声明的行为。消息组件填写 `chat_message`；只由插件打开的工作台填写 `chat_workbench`；同时允许从「＋」打开的工作台填写 `chat_workbench_with_launcher`。所有 ChatUI target 都不会出现在独立插件页面列表中，未声明的目录仍自动发现为独立页面。

`title`、`description` 是默认文案；i18n 按字段覆盖，规则见[视图文案](./bridge.md#view-labels)。`version` 默认为 `1`；`actions` 声明消息实例允许调用的 action，默认为空。独立页面不声明 actions。

如果只需要几个配置项，使用[插件配置](../plugin-config.md)即可。

## 选择交互方式

- **消息组件、消息创建的工作台页面**：使用 `bridge.view.action()` 调用 `@filter.ui_action`，通过 `event.view_result(data=...)` 更新视图数据。
- **独立页面、常驻工作台页面**：使用 `bridge.apiGet()`、`apiPost()` 等调用插件的[后端 Web API](./web-api.md)。

所有界面共享[Bridge API](./bridge.md)中的初始化、主题和国际化接口。各宿主支持的操作见[能力表](./bridge.md#capabilities)。

::: details 文档入口调整

| 原入口 | 当前入口 |
| --- | --- |
| 插件可视化视图（`plugin-pages.md`） | 本节下的「独立插件页面」「共享 Bridge API」「后端 Web API」 |
| ChatUI 交互卡片（`chatui-views.md`） | 本节下的「消息交互组件」「工作台页面」 |

旧链接保留跳转。
:::
