# Archify on this checkout

Vendored from [tt-a1i/archify](https://github.com/tt-a1i/archify) `archify/`
at the commit in `VENDOR.json`. The renderer stays MIT-licensed; keep
`LICENSE` and `THIRD_PARTY_NOTICES.md` beside it. This file is the
Xero-Team/AstrBot overlay. Cite `AGENTS.md` instead of pasting it.

OpenCode discovers this skill at `.agents/skills/archify/SKILL.md`. Do not
copy it into gitignored `.opencode/`.

## Locked

- CLI from the AstrBot checkout root:
  `node .agents/skills/archify/bin/archify.mjs`. Packaged paths such as
  `schemas/`, `examples/`, `references/`, and `bin/` live under
  `.agents/skills/archify/`.
- Node 26.x from this checkout. Do not add a skill-local `node_modules`
  unless `doctor` fails without it. Runtime rendering needs no npm install.
- Write JSON IR and delivered HTML under `.tmp/archify/` (gitignored). Do
  not commit generated HTML, PNG, SVG, WebM, or share cards.
- `ARCHIFY_UPDATE_CHECK_DISABLED=1` for `scripts/check-update.mjs`. Do not
  download or install Archify updates from this workflow.
- Diagrams of this repository must match current code. Cite `AGENTS.md` and
  `docs/zh/dev/architecture.md` / `docs/en/dev/architecture.md`. Use
  `Xero-Team/AstrBot` for fork-owned identity. Label `AstrBotDevs/AstrBot`
  only as upstream provenance.
- Python 3.14+, source-build `compose.yml` / `astrbot:local`, in-app docs at
  `/help/`. Do not restore legacy shims, `docs.astrbot.app`, or upstream
  images.
- `--repo-root` is this checkout when evidence-backed Architecture nodes
  must open files here.

## Open

Diagram type, scope, title, and whether motion, views, or a share card are
required. Ask only when those choices change the artifact.

## Do not

- Use this skill for plugin scaffolding or upstream cherry-pick. Those are
  `create-astrbot-plugin` and `sync-upstream`.
- Invent topology, wake policy, provider modules, or Dashboard routes.
- Point cards or labels at `docs.astrbot.app`, `soulter/astrbot`, or claim
  this fork publishes PyPI, GitHub Release, or container artifacts.
- Write disposable state into `data/`, `docs/`, or the Dashboard tree unless
  the user explicitly asked for a documentation figure. User-facing docs
  still need matching `docs/zh/` and `docs/en/` pages.
- Start `preview` or pass `--open` unless the user asked for a live window.
- Capture unpinned brand marks. Omit `brand` unless the node names a real
  product and a built-in or digest-pinned mark exists.

## Handoff

- Authoring: `references/authoring-contract.md`
- Delivery receipts: `references/delivery-contract.md`
- Viewer features: `references/viewer-runtime.md`
- Commit shape: `.agents/shared/conventional-commit/REFERENCE.md`

Suggested maps for this repo (inspect code; do not copy example facts):

| Type           | Typical scope                                             |
| -------------- | --------------------------------------------------------- |
| `architecture` | Runtime owners, adapters, pipeline, Dashboard, providers  |
| `workflow`     | Pipeline stages in `astrbot/core/pipeline/stage_order.py` |
| `sequence`     | Adapter → EventBus → scheduler → Process → Respond        |
| `dataflow`     | Knowledge-base upload, vectors, compensating cleanup      |
| `lifecycle`    | Session, conversation, or agent-run states                |

Group wake is explicit (`llm_access.group`, `llm_access.reply_to_bot`,
continuation). Do not draw `platform_settings.group_wake_policy`.

## Verify

```bash
node .agents/skills/archify/bin/archify.mjs doctor
node .agents/skills/archify/bin/archify.mjs validate <type> .tmp/archify/<name>.json --quality showcase --json
node .agents/skills/archify/bin/archify.mjs deliver <type> .tmp/archify/<name>.json .tmp/archify/<name>.html --quality showcase --json
node .agents/skills/archify/bin/archify.mjs visual-check .tmp/archify/<name>.html --json
```

A showcase pass needs all 9 artifact checks and 0 composition errors or
warnings. Skip `visual-check` when Playwright cannot run, and say that
browser evidence was not collected. Do not call a non-zero exit success.
