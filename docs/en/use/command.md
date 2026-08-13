# Built-in Commands

AstrBot commands are registered through the plugin system. Built-in commands now follow a consistent CLI convention: a singular noun root command, a full-word verb subcommand, and long options. Examples include `/plugin list`, `/conversation create`, and `/provider set llm 1`.

Use `/help` to show enabled root commands. Use `/help --image` or `/help -i` for image-formatted help. If the wake prefix changes, replace `/` in every example with the configured prefix.

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

## Command Reference

### Help

- `/help`: Show enabled root commands and version information.
- `/help --image` or `/help -i`: Generate image-formatted help.

### Session Information

- `/session info`: Show the UMO, user ID, platform ID, message type, and session ID.
- `/session name`: Show the current auto name and saved alias; admin permission is required.
- `/session name <name>`: Set the current UMO display alias; admin permission is required. `GreedyStr` allows spaces.

The user ID from `/session info` can be granted a session-scoped administrator binding with `/admin grant`. With group `unique_session` enabled, the command also reports the group ID used for allowlists.

### Conversations

- `/conversation create`: Create and switch to a new conversation.
- `/conversation reset`: Clear the current context and corresponding third-party Agent Runner state.
- `/conversation stats`: Show input, cached-input, and output token statistics.
- `/conversation history [--page N|-p N]`: Show conversation history.
- `/conversation list [--page N|-p N]`: List conversations.
- `/conversation switch <index>`: Switch to a listed conversation.
- `/conversation rename <new-title>`: Rename the current conversation; spaces are accepted.
- `/conversation delete`: Delete the current conversation.
- `/conversation create-for <session-id>`: Create a conversation for another group session; admin permission is required.

`reset` and `delete` may require admin permission in groups without session isolation. Dashboard command permissions take precedence over defaults.

### Running Tasks

- `/task stop`: Stop running Agent or third-party Agent Runner tasks in the current session without deleting history.

### Providers and Models

- `/provider list`: List LLM, TTS, and STT Providers, the current selections, and reachability status.
- `/provider set llm <index>`: Select an LLM Provider.
- `/provider set tts <index>`: Select a TTS Provider.
- `/provider set stt <index>`: Select an STT Provider.
- `/model list`: List models available from the current LLM Provider.
- `/model set <name-or-index>`: Select a model; a name can also resolve to another configured Provider.

These commands require admin permission.

### Session Variables

- `/variable set <key> <value>`: Set an Agent Runner input variable.
- `/variable unset <key>`: Remove an input variable.

### LLM Chat State

- `/chat status`: Show whether LLM chat is enabled for the current session.
- `/chat enable`: Enable LLM chat for the current session.
- `/chat disable`: Disable LLM chat for the current session.

These commands require admin permission. Both `enable` and `disable` are idempotent.

### Administrators

- `/admin list`: List the administrator user IDs active in the current configuration.
- `/admin grant <user-id>`: Grant AstrBot administrator permission.
- `/admin revoke <user-id>`: Revoke AstrBot administrator permission.

All three subcommands require admin permission.

### Personas

- `/persona status`: Show the default Persona and the Persona effectively used by the current conversation.
- `/persona list`: List Personas.
- `/persona show <persona_id>`: Show a Persona's system prompt.
- `/persona set <persona_id>`: Select a Persona for the current conversation.
- `/persona unset`: Explicitly select no Persona for the current conversation.

Persona subcommands require admin permission. Entering `/persona` alone displays the subcommand tree.

### Plugins

- `/plugin list`: List loaded plugins.
- `/plugin show <plugin-name>`: Show plugin version, author, and registered commands.
- `/plugin enable <plugin-name>`: Enable a plugin; admin permission is required.
- `/plugin disable <plugin-name>`: Disable a plugin; admin permission is required.
- `/plugin install <repository-url>`: Install a plugin; admin permission is required.

Plugin load, unload, reload, enable, and disable operations immediately rebuild the command catalog and refresh enabled Telegram/Discord native command surfaces.
