# Changelog

## Unreleased

### Plugin Environment Grouping

v4 runtime now manages plugin Python environments as shared groups instead of
always creating one `.venv` per plugin.

Behavior changes:

- Plugins are planned together before startup.
- Plugins are grouped by `runtime.python` first, then by dependency
  compatibility.
- Compatible plugins share one interpreter environment under
  `.astrbot/envs/<group_id>`.
- Incompatible plugins are split into separate groups automatically.
- Each plugin still runs in its own worker process. Only the Python
  environment is shared.

Environment planning details:

- Group planning writes artifacts to `.astrbot/groups/`, `.astrbot/locks/`,
  and `.astrbot/envs/`.
- Lockfiles are generated from grouped `requirements.txt` inputs.
- Exact pinned requirements such as `package==1.2.3` use a fast compatibility
  check before falling back to `uv pip compile`.
- If a plugin cannot produce a valid lockfile even when isolated, that plugin
  is skipped without blocking other plugins.

Compatibility notes:

- Existing plugin manifest structure is unchanged.
- Existing `PluginEnvironmentManager.prepare_environment(plugin)` call sites
  remain valid.
- Shared environments still use `--system-site-packages` in this phase to
  reduce regressions for plugins that implicitly rely on host packages.
- Legacy plugin-local `.venv` directories and `.astrbot-worker-state.json`
  files are no longer part of the active v4 environment path, but they are not
  deleted automatically.

Operational notes:

- Startup now performs a planning step before worker launch.
- Shared environment state is tracked with `.group-venv-state.json` inside
  each grouped environment.
- Stale `.astrbot` group artifacts are cleaned up on replanning.
