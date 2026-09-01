# Built-in Commands

AstrBot commands are registered through the plugin system. Built-in commands now follow a consistent CLI convention: a singular noun root command, a full-word verb subcommand, and long options. Examples include `/plugin list`, `/conversation create`, and `/provider set llm 1`. Former short names such as `/plugin ls`, `/op`, `/reset`, and `/flow on` are not aliases and do not match. `/help` lists currently enabled declared names, or names after an explicit Dashboard rename.

Use `/help` to show enabled root commands and their first-level subcommands. Use `/help --image` or `/help -i` for image-formatted help. If the wake prefix changes, replace `/` in every example with the configured prefix.

## Orbit Command Argument Syntax

AstrBot uses **Orbit Command Syntax** for arguments of registered commands. Orbit is not a shell and never executes a shell. Strict argument parsing starts only after a complete command, command group, or alias matches; a completely unknown root command can still reach ordinary plugin filters or the LLM.

Orbit supports a deterministic subset of POSIX quoting and escaping:

- Only ASCII spaces and tabs separate arguments.
- Everything inside single quotes is literal.
- Inside double quotes, backslash escapes only `$`, backtick, backslash, double quote, and newline. Other backslashes are preserved.
- An unquoted backslash escapes the next character; backslash-newline performs line continuation.
- Adjacent quoted and unquoted fragments form one argument, so `ab"cd"'ef'` becomes `abcdef`.
- `""` and `''` each produce an empty argument. Unicode is preserved, and command matching is case-sensitive.

Orbit performs no parameter, command, arithmetic, or tilde expansion and no globbing, redirection, pipelines, lists, or subshells. Any unescaped `$` or backtick outside single quotes, plus an unquoted word-initial `~`, `*`, `?`, `[`, `|`, `&`, `;`, `<`, `>`, `(`, `)`, word-initial `#`, or newline produces a structured syntax error.

Quote or escape these characters when they are data:

```text
/session name '$HOME'
/session name "a|b"
/session name \*.txt
/session name "C:\Users\bot"
/session name '^user#[0-9]+$'
/plugin install 'https://example.com?a=1&b=2#readme'
```

Declared options can appear before or after positional arguments and support `--name=value`. `--` stops option parsing; for example, `/session name -- -x` passes `-x` as data. Negative numeric positionals such as `-1` do not require the terminator.

## Command and LLM routing

Commands are framed by the profile's `command_prefixes` (default `["/"]`) and matched against the enabled command catalog. Command matching happens before LLM access: a matched command always wins, a bare command group shows its help, and an unknown subcommand returns an Orbit diagnostic instead of becoming an LLM prompt. Non-command messages follow the profile's `llm_access` policy. Its prefixes are complete user-typed strings; they are not automatically combined with `command_prefixes`.

Enabled command paths, aliases, descendants, and non-empty LLM prefix roots share one scoped namespace. A conflict is rejected or excluded from the runtime catalog until Dashboard rename leaves one owner, or the command-update API records a takeover. Dashboard highlights conflicts and exposes rename; it does not offer a takeover button. The built-in LLM state commands are `/llm status`, `/llm enable`, and `/llm disable`; `/chat` is not their compatibility alias.

## Command Reference

### Help

- `/help`: Show enabled root commands, first-level subcommands, and version information.
- `/help --image` or `/help -i`: Generate image-formatted help.

### Bot Presence

- `/bot status`: Show the version plus the current session, LLM, and TTS switches. Requires `session.read`.
- `/bot enable`: Enable the current session. Requires `session.manage`.
- `/bot disable`: Disable the current session. Requires `session.manage`.
- `/bot leave`: Prompt for leave confirmation. Requires `session.manage` and only works in group chats.
- `/bot leave --confirm` or `/bot leave -c`: Leave the current group after confirmation. Rejected when the platform does not declare `leave_group`.

Both `enable` and `disable` are idempotent. They write the existing `session_enabled` flag for the current UMO, same scope as `/llm`. When the session is disabled, the pipeline stops ordinary events but still allows `/bot status` and `/bot enable` so the session can be turned back on from chat. A bare `/bot` only shows the subcommand tree.

### Session Information

- `/session info`: Show the UMO, user ID, platform ID, message type, and session ID.
- `/session name`: Show the current auto name and saved alias; requires `session.manage`.
- `/session name <name>`: Set the current UMO display alias; requires `session.manage`. `GreedyStr` allows spaces.

The user ID from `/session info` can be granted current-session `session_admin` with `/admin grant`. That is not a global operator. With group `unique_session` enabled, the command also reports the group ID used for allowlists.

### Conversations

- `/conversation create`: Create and switch to a new conversation.
- `/conversation reset`: Clear the current context and corresponding third-party Agent Runner state.
- `/conversation stats`: Show input, cached-input, and output token statistics.
- `/conversation history [--page N|-p N]`: Show conversation history.
- `/conversation list [--page N|-p N]`: List conversations.
- `/conversation switch <index>`: Switch to a listed conversation.
- `/conversation rename <new-title>`: Rename the current conversation; spaces are accepted.
- `/conversation delete`: Delete the current conversation.
- `/conversation create-for <session-id>`: Create a conversation for another group session; requires `session.assign` and `session.manage`.

`reset` and `delete` may require `session.manage` in groups without session isolation. Dashboard command permissions take precedence over defaults.

### Running Tasks

- `/task stop`: Stop running Agent or third-party Agent Runner tasks in the current session without deleting history.

### Providers and Models

- `/provider list`: List LLM, TTS, and STT Providers, the current selections, and reachability status.
- `/provider set llm <index>`: Select an LLM Provider.
- `/provider set tts <index>`: Select a TTS Provider.
- `/provider set stt <index>`: Select an STT Provider.
- `/model list`: List models available from the current LLM Provider.
- `/model set <name-or-index>`: Select a model; a name can also resolve to another configured Provider.

These commands require `provider.use`. Cross-session assignment also requires `session.assign`.

### Session Variables

- `/variable set <key> <value>`: Set an Agent Runner input variable.
- `/variable unset <key>`: Remove an input variable.

### LLM Chat State

- `/llm status`: Show whether LLM chat is enabled for the current session.
- `/llm enable`: Enable LLM chat for the current session.
- `/llm disable`: Disable LLM chat for the current session.

These commands require `session.manage`. Both `enable` and `disable` are idempotent. `/llm` only controls whether the LLM is enabled; it does not change streaming mode.

### Session streaming

- `/flow enable`: Force streaming for the current session.
- `/flow disable`: Force non-streaming for the current session.
- `/flow unset`: Remove the session override and follow global `provider_settings.streaming_response`.
- `/flow status`: Show the override and effective mode.

These commands require `session.manage`. There is no argument-less toggle.

### Session administrators

- `/admin list`: List role bindings visible in the current session.
- `/admin grant <user-id>`: Grant `session_admin` for the current session, not a global operator.
- `/admin revoke <user-id>`: Revoke `session_admin` for the current session.

All three subcommands require `identity.manage`. A current session owner may manage `session_admin` and `member` in that session only and cannot delegate ownership. See [WebUI](/en/use/webui#accounts-and-authorization) for the role model.

### Personas

- `/persona status`: Show the default Persona and the Persona effectively used by the current conversation.
- `/persona list`: List Personas.
- `/persona show <persona_id>`: Show a Persona's system prompt.
- `/persona set <persona_id>`: Select a Persona for the current conversation.
- `/persona unset`: Explicitly select no Persona for the current conversation.

Persona subcommands require `agent.manage`. Entering `/persona` alone displays the subcommand tree.

### Plugins

- `/plugin list`: List loaded plugins.
- `/plugin show <plugin-name>`: Show plugin version, author, and registered commands.
- `/plugin enable <plugin-name>`: Enable a plugin; requires `extension.manage`.
- `/plugin disable <plugin-name>`: Disable a plugin; requires `extension.manage`.
- `/plugin install <repository-url>`: Install a plugin; requires `extension.plugin_install` and Dashboard step-up.

Plugin load, unload, reload, enable, and disable operations immediately rebuild the command catalog and refresh enabled Telegram/Discord native command surfaces.
