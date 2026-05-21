---
name: {{skill_name}}
description: Work on the {{display_name}} plugin scaffold with {{agent_display_name}}.
---

# {{display_name}} Plugin Guide

Use this skill when working inside the plugin created by `astr init --agents {{agent_name}}`.

## Workspace
- Plugin root: `{{plugin_root}}`
- Skill directory: `{{skill_dir_name}}`
- Plugin package: `{{plugin_name}}`
- Main class: `{{class_name}}`

## Expectations
- Read `{{plugin_root}}/plugin.yaml` and `{{plugin_root}}/main.py` before editing behavior.
- Keep handler names, config keys, and user-facing command text stable unless the user asks to change them.
- Prefer focused changes that match the generated plugin layout instead of broad rewrites.
- Run the smallest relevant validation after behavior changes.

## Validation
- `uv run astr validate --plugin-dir {{plugin_root}}`
- Add or run focused tests when the request changes behavior.
- Keep new comments in English.

## Delivery
- Summarize what changed, why it changed, and which checks were run.
- Call out any follow-up work or remaining risks if the requested change cannot be completed fully.
