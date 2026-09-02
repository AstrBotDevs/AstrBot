# Skills

`.agents/skills/` is the only skill source in this repository. Each skill is a
directory with `SKILL.md` (policy) plus optional `REFERENCE.md`, `scripts/`,
and `agents/openai.yaml`.

Shared locks live under `.agents/shared/`:

| Path                               | Role                                             |
| ---------------------------------- | ------------------------------------------------ |
| `conventional-commit/REFERENCE.md` | Commit message shape                             |
| `ai-contribution/REFERENCE.md`     | What agents may open vs what they must not merge |

## Catalog

| Skill                   | Load when                                                                 |
| ----------------------- | ------------------------------------------------------------------------- |
| `sync-upstream`         | Absorb `AstrBotDevs/AstrBot` `master`                                     |
| `create-astrbot-plugin` | Create or repair a plugin (Star) package                                  |
| `archify`               | Render architecture, workflow, sequence, data-flow, or lifecycle diagrams |

Do not add a skill that only restates `AGENTS.md`. Split a skill when a
second, independently loadable workflow appears.

## `SKILL.md` contract

Frontmatter `name` and `description` must say **when to load** and **when not
to**. The body uses these headings when they apply:

- **Locked** — toolchain or behavior the agent must not change
- **Open** — product design the agent may decide
- **Do not** — hard stops
- **Handoff** — other skills or files to cite, not paste
- **Verify** — focused commands after the change

Cite `AGENTS.md` and shared references. Do not inline those files.

Plugin sibling repositories should call this checkout's
`create-astrbot-plugin/scripts/check_plugin.py` rather than vendoring a copy of
the skill.

`archify` is a vendored MIT renderer from
[tt-a1i/archify](https://github.com/tt-a1i/archify). Keep the overlay in
`archify/REFERENCE.md` and the pin in `archify/VENDOR.json`. OpenCode loads it
from `.agents/skills/archify/SKILL.md`.
