# Project Structure & Testing

## plugin.yaml Schema

```yaml
# Required fields
name: astrbot_plugin_my_plugin        # Must start with astrbot_plugin_
display_name: My Plugin                # Human-readable name
desc: What the plugin does             # Short description
author: Your Name                      # Author name
version: 1.0.0                         # Semver
runtime:
  python: "3.12"                       # Python version
components:
  - class: main:MyPluginClass          # module:ClassName

# Optional fields
astrbot_version: "0.11.0"             # Minimum AstrBot version
support_platforms:                     # Platform compatibility
  - qq
  - wechat
reserved: false                        # true only for core plugins
```

Notes:
- `name` must start with `astrbot_plugin_`. The `init` command adds this prefix automatically.
- `components[].class` uses `module:ClassName` format. The module is relative to the plugin directory.
- Do not invent parallel entrypoints unless the task requires multiple components.

## File Layout

```
astrbot_plugin_my_plugin/
├── plugin.yaml              # Manifest (required)
├── main.py                  # Plugin class (required)
├── requirements.txt         # Dependencies (optional)
└── tests/
    └── test_plugin.py       # Tests (recommended)
```

## CLI Commands

All commands support two entrypoints. If `astrbot-sdk` is not on PATH, use `python -m astrbot_sdk`:

| Command | Purpose |
|---------|---------|
| `astrbot-sdk init <name>` | Scaffold new plugin |
| `astrbot-sdk validate --plugin-dir <dir>` | Validate structure, imports, handler discovery |
| `astrbot-sdk dev --local --plugin-dir <dir> --event-text "..."` | Single-shot local test |
| `astrbot-sdk dev --local --plugin-dir <dir> --interactive` | Interactive local test |
| `astrbot-sdk dev --local --plugin-dir <dir> --watch --event-text "..."` | Watch mode with auto-reload |
| `astrbot-sdk build --plugin-dir <dir>` | Package into distributable zip |

### init

- Run from the **parent** directory where the plugin folder should be created.
- Normalizes name: `quick-notes` → `astrbot_plugin_quick_notes/`.
- Do not run inside an existing plugin directory.
- Replace scaffold code with actual behavior; do not keep dead defaults.

### validate

Reports: handler count, capability count, component instances.

### dev --local

- Uses SDK's local mock core (no real AstrBot instance needed).
- `--watch` has known reload pitfalls; prefer fresh runs for subtle behavior changes.

### build

Produces `dist/<name>-<version>.zip`.

## Testing

### Black-box test with PluginHarness (preferred)

```python
from pathlib import Path

import pytest

from astrbot_sdk.testing import PluginHarness


@pytest.mark.asyncio
async def test_hello():
    plugin_dir = Path(__file__).resolve().parents[1]

    async with PluginHarness.from_plugin_dir(plugin_dir) as h:
        records = await h.dispatch_text("hello")

    assert any(r.text == "Hello!" for r in records)
```

### Custom session/user/platform

```python
async with PluginHarness.from_plugin_dir(
    plugin_dir,
    session_id="test-session",
    user_id="user-42",
    platform="qq",
    group_id="group-1",
) as h:
    records = await h.dispatch_text("hello")
```

### Override per dispatch

```python
records = await h.dispatch_text("hello", user_id="other-user", group_id="other-group")
```

### Testing capabilities

```python
result = await h.invoke_capability("my_plugin.compute", {"x": 5, "y": 3})
assert result["result"] == 8
```

### Accessing sent messages

```python
# All messages sent during harness lifetime
all_messages = h.sent_messages

# Clear between test steps
h.clear_sent_messages()
```

### RecordedSend properties

Each item in the `records` list has:
- `.text` — plain text content of the reply

### Lifecycle

`PluginHarness` as async context manager automatically calls `on_start()` on enter and `on_stop()` on exit.

## Testing Pitfalls

### NEVER use `from main import ...`

```python
# BAD — pollutes sys.modules["main"]
from main import MyPlugin

# GOOD — use PluginHarness
async with PluginHarness.from_plugin_dir(plugin_dir) as h:
    records = await h.dispatch_text("hello")
```

### Ignore cached files

When copying plugin fixtures, exclude:
- `__pycache__/`
- `*.pyc`
- `*.pyo`

### dispatch_text behavior

- Returns `list[RecordedSend]` — the messages the plugin sent in response.
- If no handler matches, behavior depends on the event type.

### Watch mode caveats

- Reload correctness depends on loader cache cleanup.
- Prefer fresh `dev --local` runs over `--watch` for subtle behavior changes.

## Validation Loop

Run after every meaningful change:

```bash
# 1. Validate structure
astrbot-sdk validate --plugin-dir <dir>

# 2. Smoke test
astrbot-sdk dev --local --plugin-dir <dir> --event-text "<sample>"

# 3. Run tests
python -m pytest tests -q

# 4. Package (if needed)
astrbot-sdk build --plugin-dir <dir>
```

If any step fails, fix before proceeding.

## Source basis

Derived from:
- `src/astrbot_sdk/cli.py`
- `src/astrbot_sdk/testing.py`
- `README.md`
- `docs/08_testing_guide.md`
