# Computer Use

Computer Use controls whether an Agent can execute code, access files, run Shell commands.

## Mode Selection

In WebUI, open:

- `Config -> General Config -> Use Computer Capabilities`

The key option is `Computer Use Runtime`:

- `none`: disables Computer Use; Shell, Python, filesystem, and related tools are not mounted.
- `local`: executes on the host machine where AstrBot is running. Use this when the Agent needs local files, command-line tools, or local dependencies.
- `sandbox`: executes inside an isolated sandbox. Use this when you want to reduce host risk or provide automation capabilities to multiple users.

If you are not sure which mode to choose, prefer `sandbox`. Use `local` only when direct host access is required.

## Local Mode

`local` mode mounts Computer Use tools into the host environment where AstrBot runs. The Agent can call the host Shell, host Python, and host filesystem tools.

This means the Agent's boundary is close to the AstrBot process itself. What it can access depends on the system permissions, runtime user, working directory, and operating-system restrictions of the AstrBot process.

### Workspace

In `local` mode, AstrBot prepares a workspace for each session:

```text
data/workspaces/{normalized_umo}
```

`{normalized_umo}` is derived from the current session's `unified_msg_origin`; characters unsuitable for filenames are replaced with `_`.

Relative paths passed to local filesystem tools are resolved under this workspace. For example:

```text
notes/todo.txt
```

is resolved as:

```text
data/workspaces/{normalized_umo}/notes/todo.txt
```

The local Shell tool also runs with this workspace as its current working directory.

> [!NOTE]
> The local Python tool executes code through AstrBot's current Python environment. When Python code reads or writes files, use explicit absolute paths or prepare files through filesystem tools in the workspace first.

### Local Tools

`local` mode mainly provides:

- `Shell`: executes host shell commands. Windows follows `cmd.exe` semantics; Linux/macOS follow Unix-like shell semantics.
- `Python`: executes Python code in AstrBot's current Python environment.
- `File read`: reads text, image, spreadsheet, and other supported files.
- `File write`: writes UTF-8 text files; relative paths default to the current workspace.
- `File edit`: replaces exact text in files.
- `Grep search`: searches file contents through ripgrep.

`local` mode does not mount sandbox upload/download tools, and it does not provide browser automation. Browser automation belongs to the sandbox runtime and requires a sandbox profile with the `browser` capability.

The local Shell tool includes basic blocking for dangerous commands such as `rm -rf`, `sudo`, `shutdown`, `reboot`, and `kill -9`. This is not a complete security sandbox and should not be treated as one.

### Permission Model

Computer Use uses the unified authorization service. There is no “Require AstrBot admin permission” switch. Typical actions include:

- `tool.computer_use`
- `tool.local_exec`
- `tool.python_exec`
- `tool.file_read`
- `tool.file_write`
- `tool.browser_control`

`tool.file_read` is available to current-session members and above, still subject to path limits. `tool.local_exec`, `tool.python_exec`, `tool.file_write`, `tool.browser_control`, and `tool.computer_use` are high-risk: an authenticated Dashboard-driven WebChat may use them only in its current session/config after the WebChat one-time step-up. Global control-plane actions remain Dashboard-only; anonymous WebChat, IM, plugins, agents, and API keys do not inherit Dashboard roles. Sandbox, path, Persona, and declared-tool restrictions still apply.

In `local` mode, ordinary session members may read:

- `data/skills`
- `data/plugins/*/skills` (read-only, for plugin-provided Skills)
- the current session's `data/workspaces/{normalized_umo}`
- AstrBot temporary directories
- `.astrbot` under the system temporary directory

Writes and edits remain limited to the current session workspace and temporary directories. Grant matching actions from the Dashboard [authorization page](/en/use/webui#accounts-and-authorization). `/admin grant` only creates current-session `session_admin`; it does not turn an IM user into a global operator. See [Architecture](/en/dev/architecture#unified-authorization) for the developer model.

## Sandbox Mode

`sandbox` mode runs execution actions inside an isolated environment instead of directly on the AstrBot host.

Inside the sandbox, the Agent can still use Shell, Python, and filesystem tools. If the selected sandbox profile supports the `browser` capability, AstrBot also mounts browser automation tools.

With Shipyard Neo, the sandbox workspace root is usually:

```text
/workspace
```

Filesystem tools should usually receive relative paths, for example:

```text
result.txt
```

instead of:

```text
/workspace/result.txt
```

For sandbox deployment, profiles, TTL, persistence, and browser capabilities, see [Agent Sandbox Environment](/en/use/astrbot-agent-sandbox).

> [!NOTE]
> Even in `sandbox` mode, Shell, Python, browser, and upload/download tools are still authorized as `tool.local_exec`, `tool.python_exec`, `tool.browser_control`, and `tool.file_write`. Sandboxing isolates execution but does not change authorization.

## Skills

Skills are reusable instruction bundles for Agents. They are usually stored under `data/skills`, and each Skill contains a `SKILL.md`.

The relationship between Skills and Computer Use is:

- Skills tell the Agent what to do.
- Computer Use decides whether the Agent can execute those steps.

For example, a Skill may ask the Agent to read files, run scripts, and generate a report. If `Computer Use Runtime` is `none`, the Agent may see the Skill instructions, but it cannot call Shell or Python to execute them.

In `local` mode, the Agent reads local Skills.
In `sandbox` mode, AstrBot attempts to sync local Skills into the sandbox so the Agent can execute them there.

For more details, see [Anthropic Skills](/en/use/skills).
