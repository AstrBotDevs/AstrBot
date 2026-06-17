# CLI Commands

The AstrBot CLI initializes instances, starts AstrBot, updates common config values, and manages plugins.

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
> Run the commands below from the AstrBot working directory.

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
| `astrbot conf` | Read or update common config values. |
| `astrbot password` | Change the WebUI login password interactively. |
| `astrbot plug` | Create, install, update, remove, or search plugins. |
| `astrbot help` | Show CLI help. |
| `astrbot --version` | Show the AstrBot CLI version. |

## Start AstrBot

```bash
astrbot run
```

Common options:

| Option | Purpose |
| --- | --- |
| `-p, --port <PORT>` | Set the WebUI port. |
| `-r, --reload` | Enable plugin auto-reload for plugin development. |
| `--reset-password` | Reset the WebUI initial password on startup and print the new password in startup logs. |

Examples:

```bash
astrbot run --port 6185
astrbot run --reload
astrbot run --reset-password
```

If you forget the WebUI login password, run this from the AstrBot working directory:

```bash
astrbot run --reset-password
```

AstrBot regenerates the initial password during startup and prints it in startup logs. After logging in, change the password in the WebUI immediately.

When starting directly from source, you can also run:

```bash
python main.py --reset-password
```

## Config

`astrbot conf` reads and updates common config values.

```bash
astrbot conf get
astrbot conf get dashboard.port
astrbot conf set dashboard.port 6185
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
astrbot conf set dashboard.password "new-password"
```

You can also use the dedicated interactive password command:

```bash
astrbot password
astrbot password --username admin
```

## Plugins

`astrbot plug` manages plugins under `data/plugins`.

| Command | Purpose |
| --- | --- |
| `astrbot plug list` | List installed plugins. |
| `astrbot plug list --all` | Also show uninstalled plugins. |
| `astrbot plug search <QUERY>` | Search plugins. |
| `astrbot plug install <NAME>` | Install a plugin. |
| `astrbot plug update [NAME]` | Update one plugin, or all updatable plugins if no name is given. |
| `astrbot plug remove <NAME>` | Remove an installed plugin. |
| `astrbot plug new <NAME>` | Create a new plugin from the template. |

Use a GitHub proxy when installing or updating plugins:

```bash
astrbot plug install example-plugin --proxy https://gh-proxy.example.com/
astrbot plug update --proxy https://gh-proxy.example.com/
```

Creating a new plugin asks for the author, description, version, and repository URL:

```bash
astrbot plug new my-plugin
```

## Help

Show general CLI help:

```bash
astrbot help
```

Show help for a specific command:

```bash
astrbot help run
astrbot run --help
astrbot help conf
astrbot plug --help
```

Show the version:

```bash
astrbot --version
```
