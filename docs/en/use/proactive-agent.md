# Proactive Capabilities

AstrBot introduces a Proactive Agent system, enabling AstrBot to not only respond passively to users but also schedule future tasks and proactively execute them at specified times, delivering results (text, images, files, etc.) to users.

![](https://files.astrbot.app/docs/source/images/proactive-agent/image.png)

Introduced in v4.14.0, this is currently an **experimental feature** and not yet stable.

## Future Tasks (FutureTask)

The Main Agent can now manage a global **Cron Job List**, setting tasks for its future self.

### Features

- **Self-Wakeup**: AstrBot automatically wakes up at the scheduled time to execute tasks.
- **Task Feedback**: After execution, AstrBot reports the results back to the task creator.
- **WebUI Management**: You can view, edit, or delete scheduled tasks in the WebUI under **Extensions → Future Tasks**.

### How to Use

> [!TIP]
> First, select the relevant profile on the `Config` page, open `AI → Capabilities → Proactive Agent`, enable the feature, and click `Save Configuration` at the bottom right.

The Main Agent has the ability to manage scheduled tasks. You can tell it:
- "Remind me to have a meeting at 8 AM tomorrow."
- "Summarize this week's work log every Friday at 5 PM."
- "Set a timer for 10 minutes."

The Main Agent will call built-in scheduling tools to arrange these plans.

You can view and manage all future tasks under **Extensions → Future Tasks** (`/cron`) in the left sidebar of the AstrBot WebUI.

### Fixed-interval tasks

Under **Extensions → Future Tasks**, create or edit a task, select **Interval** for **Execution time**, enter a positive integer and a unit (minutes, hours, or days), and save. Every 40 minutes always means 40 elapsed minutes; every 24 hours always means 24 elapsed hours, including across hour and day boundaries.

- The first run occurs one full interval after saving. Changing the interval starts a new timing period at the time of saving.
- Restarting, disabling and re-enabling, or editing other fields such as the name or note preserves the original timing anchor. Missed periods during downtime are skipped; execution resumes at the next time on the original schedule.
- A day means 24 elapsed hours. The local clock time can change across daylight saving transitions. Choose **Daily** for a fixed local time each day.
- Older interval tasks only contain a Cron expression, so their original input cannot be recovered. After upgrading, they appear as **Custom Cron** and retain their existing Cron schedule. To use a true fixed interval, edit the task, select **Interval**, and enter the intended value again; saving starts a new timing period.

The API represents intervals as `interval_seconds`, accepting positive multiples of 60 up to 2147483647 seconds. The server manages `interval_anchor_at`. An interval cannot be combined with Cron or a one-shot execution time.

### Supported Platforms

Scheduling tasks is supported on all platforms. However, due to some platforms not providing APIs for proactive message pushing, only the following platforms support AstrBot proactively pushing results to users:
- Telegram
- OneBot (QQ)
- Slack
- Feishu (Lark)
- Discord
- Misskey
- Satori

## Sending Multimedia Messages

To make it easier for Agents to send images, audio, video, and other files directly to users, AstrBot provides a `send_message_to_user` tool by default.

### Features
- **Direct Sending**: Agents can send generated or retrieved multimedia files directly to users without complex text conversions.
- **Multiple Formats**: Supports images, files, audio, video, etc.
