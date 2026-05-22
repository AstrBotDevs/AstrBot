# CLI Commands

The AstrBot CLI initializes instances, starts AstrBot, installs background services, reads logs, updates common config values, and manages plugins.

If you install AstrBot with `uv`:

```bash
uv tool install astrbot --python 3.12
```

`uv` creates the `astrbot` executable and puts it on `PATH`. You can inspect the path with:

::: code-group

```bash [Linux / macOS]
which astrbot
```

```powershell [Windows]
where.exe astrbot
```

:::

> [!TIP]
> Run the commands below from the AstrBot working directory unless the command provides a `--workdir` option.

## Quick Start

Initialize the directory once, then start AstrBot:

```bash
astrbot init
astrbot run
```

`astrbot init` creates the data directories and configuration files required by AstrBot. After initialization, use `astrbot run` for later starts.

## Top-Level Commands

| Command | Purpose |
| --- | --- |
| `astrbot init` | Initialize the current directory as an AstrBot working directory. |
| `astrbot run` | Start AstrBot in the foreground. |
| `astrbot service` | Install and manage AstrBot as a background service. |
| `astrbot config` | Read or update common config values. |
| `astrbot password` | Change the WebUI login password interactively. |
| `astrbot plugin` | Create, install, update, remove, or search plugins. |
| `astrbot help` | Show CLI help. |
| `astrbot --version` | Show the AstrBot CLI version. |

`conf` and `plug` are compatibility aliases and still work:

```bash
astrbot conf get
astrbot plug list
```

Prefer `config` and `plugin` in new docs and scripts.

## Start AstrBot

```bash
astrbot run
```

Common options:

| Option | Purpose |
| --- | --- |
| `-p, --port <PORT>` | Set the WebUI port. |
| `-r, --reload` | Enable plugin auto-reload for plugin development. |
| `--reset-password` | Reset the WebUI initial password on startup and print the new initial password in startup logs. |

Examples:

```bash
astrbot run --port 6185
astrbot run --reload
astrbot run --reset-password
```

## Background Service

`astrbot service` installs AstrBot as a user-level background service for long-running deployments.

Each platform uses its native service manager:

| Platform | Service manager |
| --- | --- |
| Linux | `systemd --user` |
| macOS | LaunchAgent |

> [!NOTE]
> `astrbot service` is not supported on Windows. Use `astrbot run` in the foreground or another process manager.

### Install

```bash
astrbot service install --now
```

By default, this command uses the `astrbot` executable found on `PATH` and the current directory as the AstrBot working directory. `--now` starts or restarts the service after installation.

Common options:

| Option | Purpose |
| --- | --- |
| `--name <NAME>` | Service name. Default: `astrbot`. |
| `--workdir <DIR>` | AstrBot working directory. |
| `--executable <PATH>` | Path to the `astrbot` executable. |
| `--force` | Overwrite an existing service definition. |
| `--now` | Start or restart the service after installation. |

If `astrbot` is not on `PATH`, pass the executable explicitly:

```bash
astrbot service install --workdir /path/to/astrbot-root --executable /path/to/astrbot --now
```

### Manage

```bash
astrbot service start
astrbot service stop
astrbot service restart
astrbot service uninstall
```

These commands support `--name <NAME>` for non-default service names:

```bash
astrbot service restart --name astrbot-test
```

To remove a service without an interactive confirmation:

```bash
astrbot service uninstall --force
```

### Status

```bash
astrbot service status
```

The status output includes:

- Overall health.
- Current platform and service manager.
- Whether the service is installed, enabled, and running.
- AstrBot working directory.
- Dashboard port.
- WebUI URL and accessibility.

Common options:

| Option | Purpose |
| --- | --- |
| `--name <NAME>` | Service name. Default: `astrbot`. |
| `--workdir <DIR>` | AstrBot working directory used to read the port config. |
| `--timeout <SECONDS>` | WebUI health probe timeout. Default: 2 seconds. |

Example:

```bash
astrbot service status --timeout 5
```

## Logs

The CLI exposes two kinds of logs:

| Type | Command | Notes |
| --- | --- | --- |
| Service logs | `astrbot service logs` | Reads console output captured by the service manager. |
| Application log file | `astrbot service logs --source app` | Reads `data/logs/astrbot.log`; file logging must be enabled first. |

### Service Logs

```bash
astrbot service logs
astrbot service logs -n 100
astrbot service logs -f
```

Common options:

| Option | Purpose |
| --- | --- |
| `--name <NAME>` | Service name. |
| `-n, --lines <N>` | Show the latest N lines. Default: 200. |
| `-f, --follow` | Follow log output. |
| `--include-stderr` | Also show stderr logs on macOS. |

On macOS, `astrbot service logs` shows stdout logs by default, which are the `.out.log` files. Add `--include-stderr` when you also need error output.

### Application Log File

`data/logs/astrbot.log` is not written by default. Enable application file logging first, then restart AstrBot:

```bash
astrbot service logs enable
astrbot service restart
astrbot service logs --source app
```

Inspect the application log file configuration:

```bash
astrbot service logs status
```

Disable the application log file:

```bash
astrbot service logs disable
astrbot service restart
```

Use a custom application log path:

```bash
astrbot service logs enable --path logs/astrbot.log
```

Relative paths are resolved from the AstrBot data directory.

## Config

`astrbot config` reads and updates common config values.

```bash
astrbot config get
astrbot config get dashboard.port
astrbot config set dashboard.port 6185
```

Supported keys:

| Key | Description |
| --- | --- |
| `timezone` | Time zone, for example `Asia/Shanghai`. |
| `log_level` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |
| `dashboard.port` | WebUI port. |
| `dashboard.username` | WebUI username. |
| `dashboard.password` | WebUI password. |
| `callback_api_base` | Callback API base URL. Must start with `http://` or `https://`. |

Changing the dashboard password writes the current password hashes automatically:

```bash
astrbot config set dashboard.password "new-password"
```

You can also use the dedicated interactive password command:

```bash
astrbot password
astrbot password --username admin
```

## Plugins

`astrbot plugin` manages plugins under `data/plugins`.

| Command | Purpose |
| --- | --- |
| `astrbot plugin list` | List installed plugins. |
| `astrbot plugin list --all` | Also show uninstalled plugins. |
| `astrbot plugin search <QUERY>` | Search plugins. |
| `astrbot plugin install <NAME>` | Install a plugin. |
| `astrbot plugin update [NAME]` | Update one plugin, or all updatable plugins if no name is given. |
| `astrbot plugin remove <NAME>` | Remove an installed plugin. |
| `astrbot plugin new <NAME>` | Create a new plugin from the template. |

Use a GitHub proxy when installing or updating plugins:

```bash
astrbot plugin install example-plugin --proxy https://gh-proxy.example.com/
astrbot plugin update --proxy https://gh-proxy.example.com/
```

Creating a new plugin asks for the author, description, version, and repository URL:

```bash
astrbot plugin new my-plugin
```

## Help

Show general CLI help:

```bash
astrbot help
```

Show help for a specific command:

```bash
astrbot help service
astrbot service --help
astrbot service logs --help
```

Show the version:

```bash
astrbot --version
```
