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
- `/reset`: Reset the current conversation's LLM context.
- `/stop`: Stop Agent tasks currently running in the current session.
- `/new`: Create and switch to a new conversation.
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

Some commands require AstrBot admin permission, such as `/dashboard_update`, `/op`, `/deop`, `/provider`, `/model`, and `/persona`.

You can use `/sid` to get a user ID, then add it in WebUI under `Config -> Other Config -> Admin ID`.
