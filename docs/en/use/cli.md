# CLI Commands

The AstrBot CLI initializes runtime roots, starts AstrBot, updates common settings, and manages plugins. This fork does not publish an independent PyPI package, so this page assumes you completed the [source deployment](/en/deploy/astrbot/cli), ran `uv sync`, and execute commands from the repository root.

Tables below use `astrbot` as the command name. In a source checkout, use the complete prefix:

```bash
uv run astrbot --help
```

## Top-Level Commands

| Command                   | Purpose                                                        |
| ------------------------- | -------------------------------------------------------------- |
| `astrbot init`            | Initialize the current directory as a CLI runtime root.        |
| `astrbot run`             | Start AstrBot in the foreground.                               |
| `astrbot install-browser` | Install Playwright Chromium for local text-to-image rendering. |
| `astrbot conf`            | Read or update common config values.                           |
| `astrbot password`        | Change the WebUI login password interactively.                 |
| `astrbot plug`            | Create, install, update, remove, or search plugins.            |
| `astrbot help`            | Show CLI help.                                                 |
| `astrbot --version`       | Show the CLI version.                                          |

## Initialize and Start

For the first CLI-mode run:

```bash
uv run astrbot init
uv run astrbot run
```

`init` creates the `.astrbot` marker and `data/` subdirectories, then checks Dashboard assets. Use `astrbot init --yes` (or `-y`) only to skip its first-install directory confirmation; it does not bypass the lock, initial-password setup, or any other confirmation. The direct source entry point, `uv run main.py`, does not require this marker.

Common `run` options:

| Option              | Purpose                                                    |
| ------------------- | ---------------------------------------------------------- |
| `-p, --port <PORT>` | Temporarily override the WebUI port.                       |
| `-r, --reload`      | Enable plugin auto-reload.                                 |
| `--reset-password`  | Reset the random initial password and print it at startup. |

```bash
uv run astrbot run --port 6185
uv run astrbot run --reload
uv run astrbot run --reset-password
```

The CLI has no remote-bind shortcut. Remote access still requires `dashboard.host` or `ASTRBOT_DASHBOARD_HOST`; see [WebUI](/en/use/webui).

The source entry point also supports password reset:

```bash
uv run main.py --reset-password
```

## Local T2I Browser

Run this once before enabling T2I or plugin HTML rendering:

```bash
uv run astrbot install-browser
```

The command asks Playwright in the current Python environment to install Chromium. It does not start AstrBot.

## Configuration

```bash
uv run astrbot conf get
uv run astrbot conf get dashboard.port
uv run astrbot conf set dashboard.port 6185
```

Supported common keys include `timezone`, `log_level`, `dashboard.port`, `dashboard.username`, `dashboard.password`, and `callback_api_base`. Password updates write the current password hashes; do not generate an MD5 value manually.

The dedicated interactive command is also available:

```bash
uv run astrbot password
uv run astrbot password --username admin
```

## Plugins

```bash
uv run astrbot plug list
uv run astrbot plug list --all
uv run astrbot plug search <QUERY>
uv run astrbot plug install <MARKET_NAME>
uv run astrbot plug update [NAME]
uv run astrbot plug remove <NAME>
uv run astrbot plug new <NAME>
```

### Install from a Local Directory

Since v4.26.3, the CLI can copy a local plugin directory directly:

```bash
uv run astrbot plug install ../my-plugin
```

The directory must contain `metadata.yaml`; its `name` must be a valid single-directory name, and `data/plugins/<name>` must not already exist.

For development, editable mode creates a directory link so source changes are visible immediately:

```bash
uv run astrbot plug install --editable ../my-plugin
# Short form
uv run astrbot plug install -e ../my-plugin
```

Editable mode depends on operating-system symlink support and permissions. Do not treat the link as a complete plugin copy when publishing or moving an instance.

### Proxy

Marketplace installs and updates accept a GitHub URL-prefix mirror. It must be a validated public HTTPS origin, not a generic HTTP forward proxy:

```bash
uv run astrbot plug install example-plugin --proxy https://gh-proxy.example.com
uv run astrbot plug update --proxy https://gh-proxy.example.com
```

## Help

```bash
uv run astrbot help
uv run astrbot help run
uv run astrbot plug --help
uv run astrbot --version
```
