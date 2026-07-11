# 异常诊断

本文用于整理 AstrBot 出现异常时的通用排查方法。遇到问题时，先确定问题发生在哪个阶段，再收集对应日志；这样提交 Issue 时更容易复现和定位。

## 常见问题类型

- 启动失败：进程启动后退出、WebUI 打不开、数据库或配置加载失败。
- 平台连接异常：QQ、OneBot、Telegram、企业微信等平台无法连接、收不到消息或无法发送消息。
- 模型请求异常：长时间无回复、频繁超时、报 429/5xx、代理或 API Base 不可用。
- 插件或 MCP 异常：启用失败、工具调用失败、依赖安装失败、MCP 服务无响应。
- 任务卡顿或 CPU 异常：消息、主动任务、定时任务已经触发，但中间步骤很久才继续；或进程 CPU 长时间异常升高。

## 先看哪些日志

优先查看 AstrBot 主日志：

```text
data/logs/astrbot.log
```

如果使用 Docker 部署，也可以查看容器日志：

```bash
docker logs <container-name>
```

如果问题和任务卡顿、CPU 异常、多个会话同时变慢有关，还要查看事件循环诊断日志：

```text
data/logs/event_loop_watchdog.log
data/logs/event_loop_watchdog.log.1
```

`event_loop_watchdog.log` 超过 1MB 后会轮转为 `.1`。

## 通用排查步骤

1. 确认问题发生的时间点，并截取该时间前后 1 到 3 分钟的日志。
2. 确认问题范围：是所有平台都异常，还是只有某个平台、某个群、某个用户、某个插件异常。
3. 如果是模型无回复或很慢，检查模型服务商状态、API Key、API Base、代理、网络、请求超时和重试日志。
4. 如果是插件或 MCP 问题，先禁用最近安装或更新的插件，观察问题是否消失；同时检查插件依赖和 MCP 服务日志。
5. 如果是平台收发消息异常，检查平台适配器是否已连接、平台后台配置是否正确、回调地址或 WebSocket 地址是否可访问。
6. 如果是卡顿或 CPU 异常，参考下方“事件循环卡顿诊断”。

## 事件循环卡顿诊断

事件循环负责调度消息、插件、定时任务、模型请求和工具调用。如果它被同步代码阻塞，很多功能都会表现为延迟。

常见现象：

- 日志停在 `ready to request llm provider`、`acquired session lock for llm request`、工具调用结果之后，很久才继续。
- 主动任务或定时任务已经触发，但中间某一步迟迟不继续。
- 多个平台或多个会话同时变慢。
- CPU 长时间 100%，或 CPU 不高但请求一直等待外部服务返回。

如果主日志出现以下内容，说明事件循环经历了明显延迟：

```text
Event loop lag detected: 18.432s (threshold 15.000s).
```

如果事件循环长时间没有恢复，AstrBot 会把 Python 线程栈写入：

```text
data/logs/event_loop_watchdog.log
```

查看该文件时，重点关注栈顶附近正在执行的代码。常见线索包括插件函数、平台适配器、MCP 工具、同步网络请求、`time.sleep()`、`subprocess.run()`、CPU 密集循环等。

## 提交 Issue 时请附带

提交问题时，请尽量提供以下信息：

- 问题发生的大致时间点和时区。
- AstrBot 版本、部署方式（Docker、手动部署、桌面客户端等）、操作系统。
- 触发方式：启动、普通聊天、群聊、平台回调、定时任务、MCP 工具、插件功能等。
- 影响范围：所有会话、某个平台、某个群、某个用户，还是某个插件。
- `data/logs/astrbot.log` 中问题发生前后 1 到 3 分钟的日志。
- 如果存在卡顿或 CPU 异常，请附带 `data/logs/event_loop_watchdog.log` 和 `data/logs/event_loop_watchdog.log.1`。
- 如果使用 Docker，请附带对应时间段的 `docker logs`。
- 已安装插件列表，以及问题是否在禁用第三方插件后仍然出现。

提交日志前请先检查并遮盖 API Key、Token、Cookie、私聊内容等敏感信息。
