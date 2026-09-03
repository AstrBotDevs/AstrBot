# 接入 DeerFlow

在 v4.19.2 及之后，AstrBot 支持接入 [DeerFlow](https://github.com/bytedance/deer-flow) Agent Runner。

当前适配面向 DeerFlow **2.0 `main` 分支**。DeerFlow 官方已将原始 Deep Research 框架迁移到 `main-1.x` 分支持续维护，因此如果你使用的是 2.0，请以 `main` 分支文档和后端 API 为准。

## 预备工作：部署 DeerFlow

如果你还没有部署 DeerFlow，请先参考 DeerFlow 官方文档完成安装和启动：

- [DeerFlow GitHub 仓库](https://github.com/bytedance/deer-flow)
- [DeerFlow 官方网站](https://deerflow.tech/)
- [DeerFlow 配置文档](https://github.com/bytedance/deer-flow/blob/main/backend/docs/CONFIGURATION.md)

请确认 DeerFlow 已正常启动，并且 AstrBot 可以访问 DeerFlow 的网关地址。默认情况下，DeerFlow 网关地址为 `http://127.0.0.1:2026`。

> [!TIP]
> - `API Base URL` 必须以 `http://` 或 `https://` 开头。
> - 如果 AstrBot 与 DeerFlow 运行在不同容器或主机上，请将 `127.0.0.1` 替换为 DeerFlow 实际可访问的内网地址、主机名或域名。

## 在 AstrBot 中配置 DeerFlow

在 WebUI 中，点击「模型提供商」->「新增提供商」，选择「Agent 执行器」，选择「DeerFlow」，进入 DeerFlow 的配置页面。

填写以下配置项：

- `API Base URL`：DeerFlow API 网关地址，默认为 `http://127.0.0.1:2026`
- `DeerFlow API Key`：可选。若你的 DeerFlow 网关使用 Bearer 鉴权，可在此填写
- `Authorization Header`：可选。自定义 Authorization 请求头，优先级高于 `DeerFlow API Key`
- `Assistant ID`：对应 DeerFlow 2.0 LangGraph 的 `assistant_id`，默认为 `lead_agent`
- `模型名称覆盖`：可选。覆盖 DeerFlow 默认模型
- `启用思考模式`：是否启用 DeerFlow 的思考模式
- `启用计划模式`：对应 DeerFlow 2.0 运行时 `config.configurable.is_plan_mode`
- `启用子智能体`：对应 DeerFlow 2.0 运行时 `config.configurable.subagent_enabled`
- `子智能体最大并发数`：对应 DeerFlow 2.0 运行时 `config.configurable.max_concurrent_subagents`，仅在启用子智能体时生效，默认 `3`
- `递归深度上限`：对应 LangGraph 的 `recursion_limit`，默认 `1000`

填写完成后点击「保存」。

> [!TIP]
> - 如果 DeerFlow 侧已经配置了默认模型，可以将 `模型名称覆盖` 留空。
> - 只有在 DeerFlow 侧已经启用了相应能力时，才建议开启 `计划模式` 或 `子智能体` 相关选项。
> - AstrBot 会同时发送 DeerFlow 2.0 推荐的 `config.configurable` 运行时参数，并保留兼容字段，便于对接上游近期版本。

## 选择 Agent 执行器

进入左边栏配置页面，点击「Agent 执行方式」，选择「DeerFlow」，然后在下方出现的新的配置项中选择你刚刚创建的 DeerFlow Agent 执行器提供商 ID，点击右下角「保存」，即可完成配置。

## 常见检查项

如果请求没有正常通过 DeerFlow 执行，请优先检查以下内容：

- DeerFlow 服务是否已经正常启动
- `API Base URL` 是否能从 AstrBot 所在环境访问
- 鉴权配置是否填写正确
- `Assistant ID` 是否与 DeerFlow 中实际可用的 assistant 一致
- 如果通过 `/reset`、`/new`、`/del` 重置 DeerFlow 会话，AstrBot 会尝试同步清理 DeerFlow 远端 thread；若 DeerFlow 网关不可达，则只会清理 AstrBot 本地会话标识
