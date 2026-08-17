# Diagnostics

This page provides a general checklist for diagnosing AstrBot issues. When something goes wrong, first identify which stage is affected, then collect the relevant logs. This makes issue reports easier to reproduce and investigate.

## Common Issue Types

- Startup failures: the process exits after startup, WebUI is unavailable, or database/config loading fails.
- Platform connection issues: QQ, OneBot, Telegram, WeCom, or other platforms cannot connect, receive messages, or send messages.
- Model request issues: replies take too long, requests time out, 429/5xx errors appear, or the proxy/API base is unavailable.
- Plugin or MCP issues: enabling fails, tool calls fail, dependencies fail to install, or an MCP service does not respond.
- Slow tasks or abnormal CPU usage: messages, proactive tasks, or scheduled tasks start but continue much later; or the process keeps unusually high CPU usage.

## Logs to Check First

Start with the main AstrBot log:

```text
data/logs/astrbot.log
```

For Docker deployments, also check container logs:

```bash
docker logs <container-name>
```

If the issue involves slow tasks, abnormal CPU usage, or multiple sessions becoming slow at the same time, also check the event loop diagnostic logs:

```text
data/logs/event_loop_watchdog.log
data/logs/event_loop_watchdog.log.1
```

`event_loop_watchdog.log` rotates to `.1` after it exceeds 1 MB.

## General Checklist

1. Identify the time of the incident, then collect logs from 1 to 3 minutes before and after it.
2. Check the scope: all platforms, one platform, one group, one user, or one plugin.
3. For slow or missing model replies, check the model provider status, API key, API base, proxy, network, request timeout, and retry logs.
4. For plugin or MCP issues, disable recently installed or updated plugins first, then check plugin dependencies and MCP service logs.
5. For platform messaging issues, check whether the adapter is connected, platform-side settings are correct, and callback/WebSocket URLs are reachable.
6. For slow tasks or abnormal CPU usage, see "Event Loop Lag Diagnostics" below.

## Event Loop Lag Diagnostics

The event loop schedules messages, plugins, scheduled jobs, model requests, and tool calls. If it is blocked by synchronous code, many features can look delayed at once.

Common symptoms:

- Logs stop after `ready to request llm provider`, `acquired session lock for llm request`, or a tool result, then continue much later.
- A proactive or scheduled task starts, but one step in the middle takes a long time to continue.
- Multiple platforms or sessions become slow at the same time.
- CPU usage stays at 100%, or CPU usage is low but requests keep waiting for an external service.

If the main log contains the following entry, the event loop experienced visible scheduling delay:

```text
Event loop lag detected: 18.432s (threshold 15.000s).
```

If the event loop does not resume for a long time, AstrBot writes Python thread stacks to:

```text
data/logs/event_loop_watchdog.log
```

When reading this file, focus on the top frames. Useful clues often include plugin functions, platform adapters, MCP tools, synchronous network requests, `time.sleep()`, `subprocess.run()`, or CPU-heavy loops.

## What to Include in an Issue

When filing an issue, include as much of the following as possible:

- Approximate time of the incident and timezone.
- AstrBot version, deployment method (Docker, manual deployment, desktop client, etc.), and operating system.
- Trigger path: startup, normal chat, group chat, platform callback, scheduled task, MCP tool, plugin feature, etc.
- Scope: all sessions, one platform, one group, one user, or one plugin.
- Logs from `data/logs/astrbot.log` for 1 to 3 minutes around the incident.
- If the issue involves lag or abnormal CPU usage, include `data/logs/event_loop_watchdog.log` and `data/logs/event_loop_watchdog.log.1`.
- For Docker deployments, include the matching `docker logs` output.
- Installed plugin list, and whether the issue still happens after disabling third-party plugins.

Before sharing logs, redact API keys, tokens, cookies, private chat content, and other sensitive information.
