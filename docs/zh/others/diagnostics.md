# 异常诊断

当 AstrBot 出现“看起来没有报错，但明显变慢或卡住”的情况时，可以先从事件循环诊断日志入手。事件循环是 AstrBot 调度消息、插件、定时任务、模型请求和工具调用的核心；如果它被同步阻塞或长期无法恢复，很多功能都会表现为延迟。

## 常见现象

- 群聊或私聊消息已经进入 AstrBot，但过了几十秒甚至几分钟才继续处理。
- 日志停在 `ready to request llm provider`、`acquired session lock for llm request`、工具调用结果之后，很久才出现下一条 Agent 日志。
- 主动任务、定时任务已经触发，但中间某一步迟迟不继续。
- 多个平台或多个会话同时变慢，而不是只有单个用户的请求慢。
- 进程 CPU 异常升高，或 CPU 不高但请求长时间等待外部服务返回。

## 查看诊断日志

AstrBot 会记录事件循环延迟。如果延迟超过阈值，主日志中会出现类似日志：

```text
Event loop lag detected: 18.432s (threshold 15.000s).
```

如果事件循环长时间没有恢复，AstrBot 会把 Python 线程栈写入：

```text
data/logs/event_loop_watchdog.log
```

该文件超过 1MB 后会轮转为：

```text
data/logs/event_loop_watchdog.log.1
```

你也可以同时查看主日志：

```text
data/logs/astrbot.log
```

如果使用 Docker 部署，也可以用：

```bash
docker logs <container-name>
```

## 排查思路

1. 先确认是否有 `Event loop lag detected` 日志。如果有，说明 AstrBot 主事件循环确实经历了明显延迟。
2. 查看 `data/logs/event_loop_watchdog.log`，关注栈顶附近正在执行的代码。常见线索包括插件函数、平台适配器、MCP 工具、同步网络请求、`time.sleep()`、`subprocess.run()`、CPU 密集循环等。
3. 如果没有事件循环延迟日志，但某次对话仍然卡很久，优先检查模型服务商、代理、网络、工具调用超时、MCP 服务响应时间。
4. 如果只有某个会话卡住，可能是该会话内前一个请求还没有结束；如果所有会话都卡住，更可能是事件循环被阻塞。
5. 如果 CPU 长时间 100%，优先关注 watchdog 栈和 MCP/插件相关调用；如果 CPU 很低，更常见的是等待外部网络或模型服务返回。

## 提交 Issue 时请附带

提交问题时，请尽量提供以下信息，方便定位：

- 问题发生的大致时间点和时区。
- AstrBot 版本、部署方式（Docker、手动部署、桌面客户端等）、操作系统。
- 触发方式：普通聊天、群聊、定时任务、MCP 工具、插件功能等。
- `data/logs/astrbot.log` 中问题发生前后 1 到 3 分钟的日志。
- `data/logs/event_loop_watchdog.log` 和 `data/logs/event_loop_watchdog.log.1`（如果存在）。
- 如果使用 Docker，请附带对应时间段的 `docker logs`。
- 已安装插件列表，以及问题是否在禁用第三方插件后仍然出现。

提交日志前请先检查并遮盖 API Key、Token、Cookie、私聊内容等敏感信息。
