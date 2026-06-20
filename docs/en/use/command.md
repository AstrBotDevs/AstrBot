# Built-in Commands

AstrBot commands are registered through the plugin system. To keep the core lightweight, only a small set of basic commands are loaded with AstrBot itself. Other management and extended commands have been moved into a separate plugin.

Use `/help` to view currently enabled commands.

> [!NOTE]
> 1. `/help`, `/set`, and `/unset` are not shown in the `/help` command list by default, but they are still available.
> 2. If you change the wake prefix and remove the default `/`, commands must use the new wake prefix as well. For example, after changing the wake prefix to `!`, use `!help` and `!reset` instead of `/help` and `/reset`.

## Core Built-in Commands

The following commands are shipped with AstrBot and loaded by default:

- `/help`: View currently enabled commands and AstrBot version information.
- `/sid`: View current message source information, including UMO, user ID, platform ID, message type, and session ID. This is commonly used when configuring admins, allowlists, or routing rules.
- `/name`: Set a display alias for the current UMO, which means one concrete group or private-chat message source on a platform, so it is easier to recognize in WebUI. This command requires admin permission.
- `/reset`: Reset the current conversation's LLM context.
- `/stop`: Stop Agent tasks currently running in the current session.
- `/new`: Create and switch to a new conversation.
- `/stats`: View token usage statistics for the current conversation.
- `/provider`: View or switch LLM Provider. This command requires admin permission.
- `/dashboard_update`: Update AstrBot WebUI. This command requires admin permission.
- `/set`: Set a session variable, commonly used for Agent Runner input variables such as Dify, Coze, or DashScope.
- `/unset`: Remove a session variable.

These commands are located in:

```text
astrbot/builtin_stars/builtin_commands
```

## Core Command Details

### `/sid`

`/sid` shows information about the current message source. It mainly returns:

- `UMO`: The unified message origin of the current message. It is commonly used for allowlists and per-session config routing.
- `UID`: The sender's user ID. It is commonly used when adding AstrBot admins.
- `Bot ID`: The platform instance ID of the current bot.
- `Message Type`: The message type, such as private chat or group chat.
- `Session ID`: The platform-side session ID.

In group chats, if `unique_session` is enabled, `/sid` also shows the current group ID. This group ID can be used to allowlist the entire group.

Common uses:

- Add an admin: run `/sid` to get the `UID`, then add it in WebUI under `Config -> Other Config -> Admin ID`.
- Configure allowlists: use `UMO` or group ID to control which sessions can use the bot.
- Configure routing rules: use `UMO` to distinguish different platforms, groups, or private chats.

### `/name`

`/name` sets a human-readable display alias for the current UMO. UMO stands for Unified Message Origin. It identifies one concrete message source in the form `platform ID:message type:session ID`, such as a QQ group, a Telegram group, or a private chat on a specific platform.

Raw UMOs are often long and are not always easy to recognize at a glance. After setting `/name`, AstrBot shows this alias first in WebUI UMO lists, session source selectors, cron delivery targets, conversation data, and other places where administrators need to identify or select a target session. This reduces the chance of choosing the wrong source when configuring routing rules, cron delivery targets, or per-session rules.

`/name` also records the readable auto name provided by the current platform when available, such as a group name in group chats or a sender nickname/ID in private chats. This lets WebUI show a readable name even when no manual alias has been set.

Usage:

- `/name <alias>`: Set or update the alias for the current UMO. This command can be used repeatedly; the latest value overwrites the previous alias.
- `/name`: With no argument, it does not modify the alias. It only shows usage, the current UMO, the current auto name, and the saved alias.

Display rules:

- If both alias and auto name exist, AstrBot displays `alias (auto name)`.
- If only the auto name exists, AstrBot displays the auto name.
- If neither exists, AstrBot displays the raw UMO.

`/name` requires admin permission.

### `/reset`

`/reset` resets the LLM context of the current session.

For AstrBot's built-in Agent Runner, it:

- Stops running tasks in the current session.
- Clears the context messages of the current conversation.
- Notifies long-term memory to clear the current session state.

For third-party Agent Runners such as `dify`, `coze`, `dashscope`, and `deerflow`, it:

- Stops running tasks in the current session.
- Removes the saved third-party conversation ID for this session, so the next turn starts a new conversation.

Permission notes:

- In private chat, regular users can use it by default.
- In group chat with `unique_session` enabled, regular users can use it by default.
- In group chat without `unique_session`, admin permission is required by default.
- If command permission settings have been customized, the actual configuration takes precedence.

### `/stop`

`/stop` stops Agent tasks currently running in the current session.

It does not clear conversation history and does not create a new conversation. It only sends a stop request to tasks currently executing in this session.

For the built-in Agent Runner, `/stop` asks the Agent Runner to stop the current task.  
For third-party Agent Runners such as `dify`, `coze`, `dashscope`, and `deerflow`, `/stop` directly stops registered running tasks in the current session.

If there are no running tasks in the current session, AstrBot will report that no task is running.

### `/stats`

`/stats` shows token usage statistics for the current conversation.

It queries the database for all Provider call records in the current conversation and displays:

- Total tokens (input + output).
- Input tokens (cached) — input tokens that were cached by the provider and skipped for billing.
- Input tokens (other) — input tokens that were not cached and billed normally.
- Output tokens — tokens generated by the model.

If you are not in a conversation, AstrBot will prompt you to create one with `/new`.

### `/provider`

`/provider` views or switches the Provider (LLM / TTS / STT) used by the current UMO.

**Viewing the Provider list:**

With no arguments, `/provider` lists all configured Providers grouped by LLM, TTS, and STT. Each Provider shows:

- An index number for switching.
- Provider ID and the model currently in use (LLM type).
- Reachability status: `✅` means the connection is healthy, `❌` means a connection failure (with an error code).
- The currently active Provider is marked with `(currently in use)` at the end.

> [!NOTE]
> Reachability checks must be enabled in WebUI under `Config -> General Config -> AI Config`, expand the "More Settings" section at the bottom, and enable "Provider Reachability Check". When disabled, reachability markers are not shown and the list loads faster.

**Switching Providers:**

Use `/provider <index>` to switch the current session's LLM Provider to the Provider at the given index in the list.

- `/provider <index>`: Switch to the LLM Provider at the given index.
- `/provider tts <index>`: Switch to the TTS Provider at the given index.
- `/provider stt <index>`: Switch to the STT Provider at the given index.

This command requires admin permission.

## Built-in Commands Extension

Other commands that were previously shipped with the core have been moved to a separate plugin:

- [builtin_commands_extension](https://github.com/AstrBotDevs/builtin_commands_extension)

This plugin provides extended commands for plugin management, Provider management, model switching, Persona management, and conversation management. Examples include:

- `/plugin`: View, enable, disable, or install plugins.
- `/op`, `/deop`: Add or remove admins.
- `/provider`: View or switch LLM Providers.
- `/model`: View or switch models.
- `/history`: View current conversation history.
- `/ls`: View the conversation list.
- `/groupnew`: Create a new conversation for a specified group.
- `/switch`: Switch to a specified conversation.
- `/rename`: Rename the current conversation.
- `/del`: Delete the current conversation.
- `/persona`: View or switch Persona.
- `/llm`: Enable or disable LLM chat.

Install or enable the `builtin_commands_extension` plugin if you need these extended commands.

## Permission Notes

Some commands require AstrBot admin permission, such as `/dashboard_update`, `/name`, `/op`, `/deop`, `/provider`, `/model`, and `/persona`.

You can use `/sid` to get a user ID, then add it in WebUI under `Config -> Other Config -> Admin ID`.
