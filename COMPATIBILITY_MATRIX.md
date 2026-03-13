# AstrBot 兼容矩阵

`src-new/astrbot_sdk` 是 v4 真源，`src-new/astrbot` 只承担旧插件兼容门面。
本文件记录当前兼容合同，避免把整个旧 `astrBot/core` 重新搬回新架构。

## 边界

| 级别 | 路径 | 策略 |
| --- | --- | --- |
| 一级 | `astrbot.api.*` | 优先做真实兼容 |
| 二级 | `astrbot.core.*` 常见深路径 | 只有真实插件命中时才补薄 shim |
| 三级 | 旧应用内部系统 | 不做树级复刻 |

## 当前兼容面

| 模块/路径 | 状态 | 说明 |
| --- | --- | --- |
| `astrbot.api` | 真实兼容 | 根入口、常见子模块可导入 |
| `astrbot.api.all` | 真实兼容 | 聚合入口对齐旧公开面 |
| `astrbot.api.event/filter/star/platform/provider/util` | 真实兼容 | 高频插件入口已收敛到 `src-new/astrbot` facade |
| `astrbot.api.message_components` | 真实兼容 | 旧消息组件导入路径可用 |
| `astrbot.core` | 导入兼容 | `AstrBotConfig`、`sp`、`logger`、`html_renderer` 门面可导入 |
| `astrbot.core.config.*` | 导入兼容 | 当前只对齐 `AstrBotConfig` |
| `astrbot.core.message.components` | 真实兼容 | 走 v4 消息组件 compat 实现 |
| `astrbot.core.message.message_event_result` | 真实兼容 | 走 v4 事件结果 compat 实现 |
| `astrbot.core.utils.session_waiter` | 真实兼容 | 已接上真实 follow-up message 路由 |
| `astrbot.core.platform.*` | 导入兼容 / 部分真实兼容 | 高频模型与事件路径可导入，平台适配器注册仍 loud-fail |

## 兼容合同测试

以下合同由仓库内测试显式守护：

- [tests_v4/test_compatibility_contract.py](/d:/GitObjectsOwn/astrbot-sdk/tests_v4/test_compatibility_contract.py)
  - 一级：`astrbot.api`、`astrbot.api.all`、`astrbot.api.message_components`、`astrbot.api.event`、`astrbot.api.event.filter`、`astrbot.api.star`、`astrbot.api.platform`、`astrbot.api.provider`、`astrbot.api.util`
  - 二级：`astrbot.core`、`astrbot.core.config.*`、`astrbot.core.message.*`、`astrbot.core.platform.*`、`astrbot.core.utils.session_waiter`
- [tests_v4/test_external_plugin_smoke.py](/d:/GitObjectsOwn/astrbot-sdk/tests_v4/test_external_plugin_smoke.py)
  - 外部真实插件矩阵必须走 `SupervisorRuntime -> Worker -> handler.invoke` 真链路
  - 不以单独 `load_plugin()` 成功替代运行时兼容结论

## 显式未支持

以下能力仍保持 loud-fail，不伪造旧执行链：

- `astrbot.api.agent`
- `astrbot.api` / `astrbot.core` 的旧 html 渲染系统
- `register_platform_adapter`
- 旧 LLM hook / plugin hook / result decorate hook 的完整执行链

## 真实插件矩阵

矩阵清单位于 [tests_v4/external_plugin_matrix.json](/d:/GitObjectsOwn/astrbot-sdk/tests_v4/external_plugin_matrix.json)。
当前标准是：

1. 可加载
2. 可初始化
3. 至少一个代表命令在 `SupervisorRuntime -> Worker -> handler.invoke` 真链路下通过

已纳入矩阵：

- `astrbot_plugin_hapi_connector`
- `astrbot_plugin_endfield`

不 vendoring 第三方源码；测试时按需 clone。
