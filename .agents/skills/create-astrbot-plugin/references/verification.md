# Plugin verification matrix

Run checks in this order. Use a disposable AstrBot checkout or an explicitly
isolated runtime/data root for installation or reload tests; never use the
checkout's real `data/` for disposable state.

## Static contract

```bash
python .agents/skills/create-astrbot-plugin/scripts/check_plugin.py \
  --astrbot-root . <plugin-dir>
python -m compileall <plugin-dir>
```

The checker verifies:

- `metadata.yaml`, `main.py`, and `README.md` exist;
- required metadata fields are present;
- metadata name is a legal identifier matching the directory name;
- Python files parse and do not import `astrbot.core`, `astrbot.dashboard`, or `requests`;
- `_conf_schema.json`, when present, is strict JSON;
- README declares the Python floor read from the current AstrBot `pyproject.toml`.

## Formatting and focused tests

```bash
uv run ruff check <plugin-dir>
uv run ruff format --check <plugin-dir>
uv run pytest <plugin-dir>/tests -q
```

Run the test command only when the plugin has tests. Add focused tests for
Orbit quoting and unknown options, empty input, configuration defaults and
migrations, storage containment, provider unavailable/timeout/cancellation,
tool-loop limits, session timeout, and plugin hot reload as applicable.

## Runtime smoke test

```bash
uv run astrbot plug install --editable <plugin-dir>
```

Run this from the intended AstrBot checkout or a disposable checkout. The CLI
uses the current working directory to locate its root; setting `ASTRBOT_ROOT`
alone does not isolate the CLI installation path. Then load or reload the plugin
in an isolated runtime and exercise one happy path and one failure path. Verify
that `terminate()` closes clients and cancels tasks. Do not call this a platform
integration test unless the actual platform adapter was exercised.

## Handoff checklist

Report:

1. Generated or changed files.
2. AstrBot Python constraint and the exact source path used to derive it.
3. Commands and tests that passed.
4. Optional features not exercised (platform, network, provider, Dashboard).
5. Any assumptions the user must confirm before publishing.
