# Proactive Capabilities

AstrBot introduces a Proactive Agent system, enabling AstrBot to not only respond passively to users but also schedule future tasks and proactively execute them at specified times, delivering results (text, images, files, etc.) to users.

![](https://files.astrbot.app/docs/source/images/proactive-agent/image.png)

This is currently an **experimental feature** and not yet stable.

## Future Tasks (FutureTask)

The Main Agent can now manage a global **Cron Job List**, setting tasks for its future self.

### Features

- **Self-Wakeup**: AstrBot automatically wakes up at the scheduled time to execute tasks.
- **Task Feedback**: After execution, AstrBot reports the results back to the task creator.
- **WebUI Management**: You can view, edit, or delete scheduled tasks in the "Future Tasks" page of the WebUI.

### How to Use

> [!TIP]
> First, ensure that "Proactive Capabilities" is enabled in the configuration.

The Main Agent has the ability to manage scheduled tasks. You can tell it:

- "Remind me to have a meeting at 8 AM tomorrow."
- "Summarize this week's work log every Friday at 5 PM."
- "Set a timer for 10 minutes."

The Main Agent will call built-in scheduling tools to arrange these plans.

You can view and manage all future tasks by clicking **Future Tasks** in the left navigation bar of the AstrBot WebUI.

![](https://files.astrbot.app/docs/source/images/proactive-agent/image-1.png)

### Time zones

Agent-created tasks use the active profile's `timezone` when it is set to an IANA time-zone name such as `Asia/Shanghai`. Recurring schedules and naive one-time timestamps are interpreted in that time zone, and task times shown in Agent responses are converted to it. If the setting is empty or invalid, the system time zone is used; an invalid value is not persisted as the task time zone. You can also provide an explicit offset in a one-time ISO timestamp, for example `2026-02-02T08:00:00+08:00`.

### Supported Platforms

Tasks can be created from any platform session, but the result can be delivered back only through adapters that implement proactive sending. Current built-in adapters include:

- Telegram
- OneBot v11 (aiocqhttp and NapCat)
- Slack
- Feishu (Lark)
- Discord
- Misskey
- Satori
- KOOK
- LINE
- Mattermost
- DingTalk
- WeCom (application mode only; customer service mode is not supported)
- WeCom Smart Bot
- Personal WeChat
- WebChat
- QQ Official Bot (WebSocket and Webhook)

This list follows the built-in adapters that currently provide a concrete `send_by_session()` implementation; metadata alone is not sufficient to prove delivery support. Platform APIs, permissions, reply windows, and stored session routing still apply. For example, WeCom Smart Bot needs an outbound message-push Webhook, Personal WeChat needs a valid session context token, and QQ Official Bot needs usable cached session state. WeChat Official Account is not listed because its adapter explicitly rejects proactive sends. Plugin-provided adapters must implement `send_by_session()` themselves.

## Sending Multimedia Messages

To make it easier for Agents to send images, audio, video, and other files directly to users, AstrBot provides a `send_message_to_user` tool by default.

### Features

- **Direct Sending**: Agents can send generated or retrieved multimedia files directly to users without complex text conversions.
- **Multiple Formats**: Supports images, files, audio, video, etc.
