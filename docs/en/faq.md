# FAQ

## WebUI and accounts

### The WebUI shows 404 or a blank page

This fork does not publish an independent prebuilt Dashboard asset. A source deployment must build the Dashboard from the same checkout and sync it into the backend static directory:

```bash
cd dashboard
pnpm install --frozen-lockfile
pnpm build
cd ..
uv run python scripts/sync_dashboard_dist.py
```

Restart AstrBot, then force-refresh with `Ctrl+Shift+R` / `Ctrl+F5` (`Cmd+Shift+R` on macOS). Do not overwrite this fork with an upstream Dashboard build; its routes and pages may not match.

### What are the first-login credentials?

The default username is `astrbot`. First startup generates a random strong password and prints it in the startup log:

```text
➜  Initial username: astrbot
➜  Initial password: <password generated for this startup>
➜  Change it after logging in
```

There is no fixed default password. Change the initial password immediately and do not publish startup logs that contain it.

### I forgot the WebUI password

From a source checkout, run:

```bash
uv run astrbot run --reset-password
```

Or use:

```bash
uv run main.py --reset-password
```

Startup generates a new password and prints it in the log. Do not delete `pbkdf2_password` or `jwt_secret` manually, and never put a plaintext password in the configuration file.

### Why is the server IP unreachable?

The WebUI listens only on `127.0.0.1:6185` by default. Replacing `localhost` with a server IP in the browser does not change the bind address.

To allow remote connections for one process:

::: code-group

```bash [Linux / macOS]
ASTRBOT_DASHBOARD_HOST=0.0.0.0 uv run main.py
```

```powershell [Windows PowerShell]
$env:ASTRBOT_DASHBOARD_HOST = '0.0.0.0'
uv run main.py
```

:::

You can also set `dashboard.host` to `0.0.0.0` in `data/cmd_config.json`. This listens on every IPv4 interface, so configure the host firewall and preferably expose AstrBot through a trusted HTTPS reverse proxy. Enable `dashboard.trust_proxy_headers` only when that proxy overwrites client-supplied forwarding headers.

Publishing container port `6185` also requires this bind override. See [Docker Deployment](./deploy/astrbot/docker).

## Runtime data and updates

### Where is `data`?

The runtime root defaults to the process working directory, and runtime data lives at `<root>/data`. Running `uv run main.py` from the repository root normally uses `AstrBot/data`.

With `ASTRBOT_ROOT` set, data lives at `$ASTRBOT_ROOT/data`. Configuration, the SQLite database, plugins, Skills, knowledge bases, temporary files, and backups can all live there, so back up the directory as a unit before an upgrade.

This fork does not provide an independent Desktop or Launcher distribution. Directory layouts chosen by external launchers are outside this repository's guarantees.

### How do I update a source deployment?

Stop AstrBot and back up `data/`, then run:

```bash
git pull --ff-only
uv sync --locked
cd dashboard
pnpm install --frozen-lockfile
pnpm build
cd ..
uv run python scripts/sync_dashboard_dist.py
```

Read the intervening files under `changelogs/` and current unreleased commits first. Do not use `uv tool upgrade astrbot` for this fork; the `astrbot` package on PyPI is upstream. The Dashboard one-click Core updater currently has no fork release assets; do not use it to install an upstream zip.

### The main database fails to start after upgrading to 4.27.5

4.27.5 rebuilds the main SQLite schema from the current SQLModel tables. It does not run `ALTER TABLE` on an old file or migrate data. `create_all` creates missing tables only; it does not add columns or indexes to an existing `data_v4.db`.

Stop the process, back up `data/`, then delete `data/data_v4.db`, `data/data_v4.db-wal`, and `data/data_v4.db-shm` under the runtime root before starting again. Conversations, long-term memory, authorization bindings, and API keys in the old main database are not migrated. `data/knowledge_base/` is not part of this cutover. See [Project Architecture](/en/dev/architecture#main-sqlite-database).

## Agent behavior, permissions, and output

### The bot does not answer in a group

To avoid flooding group chats, mentioning the bot or replying to the bot does not wake it by default. Send a wake prefix (default `/`), or enable `platform_settings.group_wake_policy.mention_bot` / `reply_to_bot` on the current profile. Also check:

- which profile is bound to the message session;
- whether the platform and Provider are enabled;
- allowlist, administrator bypass, and rate limiting;
- `ignore_at_all`, self-message filtering, and platform permissions.

### An administrator command says permission denied

Use `/session info` to inspect the current user ID, then grant current-session `session_admin` through the Dashboard [authorization page](/en/use/webui#accounts-and-authorization) or `/admin grant`. That is not a global operator. Profiles can be bound separately to platforms, groups, or direct messages, so editing the default profile may not affect the current session.

### Older commands such as `/plugin ls` or `/reset` do nothing

Built-in commands now use full CLI paths such as `/plugin list` and `/conversation reset`. Former short names are not aliases and do not match. Use `/help` for currently enabled declared names; names after an explicit Dashboard rename still apply. See [Built-in Commands](/en/use/command).

### How do I enable Computer Use?

Under **Config → Agent Computer Use**, select:

- `local` to operate directly on the AstrBot host, only in a trusted environment;
- `sandbox` to use the configured Shipyard Neo or CUA sandbox;
- `none` to disable it, which is the default.

Computer capabilities are checked through the unified action-based authorization service (for example `tool.computer_use`, `tool.local_exec`, and `tool.file_write`). An authenticated Dashboard-driven WebChat may use instance-scoped high-risk tools in its current session/config after the WebChat one-time step-up; global control-plane actions remain Dashboard-only, and anonymous WebChat, IM, plugins, agents, and API keys do not inherit Dashboard roles. Sandboxing isolates execution but does not change authorization. See [Computer Use](./use/computer) and [Agent Sandbox](./use/astrbot-agent-sandbox).

### CJK text is garbled in T2I output

Configure an installed CJK font in the active local T2I template, for example:

```css
font-family: 'Maple Mono', 'Noto Sans CJK SC', sans-serif;
```

See [Maple Mono](https://github.com/subframe7536/maple-font). The font must also be installed inside the container when AstrBot runs in Docker.

### A Provider returns empty content

Check, in order:

1. API-key permission, balance, and quota;
2. exact API Base and model ID;
3. support for the current image, tool-call, or reasoning format;
4. proxy, DNS, TLS, and request timeout;
5. Provider test output and the original server error;
6. whether fallback models actually use independent endpoints.

Do not “fix” connectivity by disabling TLS verification. Reset the conversation or reduce retained history when appropriate, and see [Context Compression](./use/context-compress).

### A marketplace plugin fails to load after install

The Dashboard default marketplace source is upstream `AstrBotDevs/AstrBot_Plugins_Collection`, not an official market for this fork. This branch requires Python 3.14+ and does not keep legacy plugin APIs or legacy Dashboard pages. Check the plugin's `astrbot_version` and `requires.dashboard_extension` before installing. If it fails, install a known-compatible plugin by URL or inspect the load error; do not assume an upstream marketplace plugin will run here. See [Plugins](/en/use/plugin) and [Plugin development](/en/dev/star/plugin-new).

### How do I disable long-term memory?

The current source initializes long-term memory unconditionally at runtime and queues a write-back after a local Agent conversation finishes. WebUI and config profiles have no per-user or per-profile off switch. Read [Long-term memory](/en/use/long-term-memory) before handling sensitive data. A WebUI soft-delete is not data erasure.

## Plugins

### Plugin installation fails

If GitHub access is unavailable, configure an outbound HTTP proxy or download a trusted plugin archive and upload it through the WebUI. Do not install an unknown archive: plugins execute inside the AstrBot process with its Python permissions.

### `No module named 'xxx'` after installation

Common causes are a network failure, a missing `requirements.txt`, or a dependency that does not support Python 3.14. Inspect installation logs and the plugin README first. In a source development checkout, use `uv` for installation and debugging; do not mix unmanaged global `pip` packages into production.

Report a missing dependency declaration to the plugin author instead of permanently maintaining an unreproducible manual environment.

## NapCat / OneBot v11

### Recommended new setup: NapCat forward WebSocket

Use the dedicated **NapCat** adapter and let AstrBot connect to NapCat:

1. Start NapCat's forward WebSocket server. The container image with `MODE=ws` listens on `0.0.0.0:3001` by default.
2. Set the NapCat URL in AstrBot to:
   - `ws://napcat:3001` on the same Docker network;
   - `ws://127.0.0.1:3001` for processes on the same host;
   - a protected NapCat host address for separate machines, with firewall and token controls.
3. Remember that `127.0.0.1` inside a container refers only to that container.

Check Docker DNS, the TCP port, and NapCat logs from the AstrBot container. `0.0.0.0` is a server bind address, never a client destination.

### When is reverse WebSocket on 6199 used?

`6199/ws` belongs to the generic **OneBot v11 (aiocqhttp)** reverse-WebSocket path, not the recommended dedicated NapCat adapter path.

When keeping the older compose combination with `MODE=astrbot`, NapCat connects to `ws://astrbot:6199/ws`. AstrBot must use the OneBot v11 platform and bind `ws_reverse_host` to `0.0.0.0` across containers. Use loopback only when both endpoints are host processes.

Do not configure forward and reverse paths for the same NapCat instance at once, or events can be duplicated. See [NapCat](./platform/napcat) and [OneBot v11](./platform/aiocqhttp).
