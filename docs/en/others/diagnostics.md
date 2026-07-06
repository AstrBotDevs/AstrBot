# Diagnostics

When AstrBot appears to slow down or get stuck without an obvious error, start with the event loop diagnostics. The event loop schedules messages, plugins, scheduled jobs, model requests, and tool calls. If it is blocked by synchronous code or cannot resume for a long time, many features can look delayed at once.

## Common Symptoms

- A group or private message reaches AstrBot, but processing continues tens of seconds or minutes later.
- Logs stop after `ready to request llm provider`, `acquired session lock for llm request`, or a tool result, then continue much later.
- A proactive or scheduled task starts, but one step in the middle takes a long time to continue.
- Multiple platforms or sessions become slow at the same time, instead of only one user's request being slow.
- CPU usage stays unusually high, or CPU usage is low but requests wait a long time for an external service.

## Diagnostic Logs

AstrBot logs event loop lag. If the lag exceeds the threshold, the main log contains an entry like:

```text
Event loop lag detected: 18.432s (threshold 15.000s).
```

If the event loop does not resume for a long time, AstrBot writes Python thread stacks to:

```text
data/logs/event_loop_watchdog.log
```

When the file exceeds 1 MB, it rotates to:

```text
data/logs/event_loop_watchdog.log.1
```

Also check the main log:

```text
data/logs/astrbot.log
```

For Docker deployments, you can also run:

```bash
docker logs <container-name>
```

## How to Investigate

1. First check whether `Event loop lag detected` appears in the logs. If it does, AstrBot's main event loop experienced visible scheduling delay.
2. Open `data/logs/event_loop_watchdog.log` and inspect the top frames. Useful clues often include plugin functions, platform adapters, MCP tools, synchronous network requests, `time.sleep()`, `subprocess.run()`, or CPU-heavy loops.
3. If there is no event loop lag log but one conversation still waits for a long time, check the model provider, proxy, network, tool timeout, or MCP server response time first.
4. If only one session is stuck, a previous request in that session may still be running. If all sessions are stuck, the event loop is more likely blocked.
5. If CPU stays at 100%, focus on the watchdog stack and MCP/plugin calls. If CPU is low, the process is more likely waiting for an external network or model service.

## What to Include in an Issue

When filing an issue, include as much of the following as possible:

- Approximate time of the incident and timezone.
- AstrBot version, deployment method (Docker, manual deployment, desktop client, etc.), and operating system.
- Trigger path: normal chat, group chat, scheduled task, MCP tool, plugin feature, etc.
- Logs from `data/logs/astrbot.log` for 1 to 3 minutes around the incident.
- `data/logs/event_loop_watchdog.log` and `data/logs/event_loop_watchdog.log.1` if they exist.
- For Docker deployments, the matching `docker logs` output.
- Installed plugin list, and whether the issue still happens after disabling third-party plugins.

Before sharing logs, redact API keys, tokens, cookies, private chat content, and other sensitive information.
