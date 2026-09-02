---
name: archify
description: Render architecture, workflow, sequence, data-flow, or lifecycle diagrams as validated standalone HTML for this AstrBot checkout. Use when the user asks to visualize runtime owners, pipeline stages, adapter-to-respond sequences, knowledge-base data flow, or agent-run states, or to convert Mermaid. Do not use for plugin scaffolding, upstream cherry-pick, or shipping diagrams in the Python package, container image, or Dashboard/docs build.
license: MIT
metadata:
  version: '2.17'
  author: tt-a1i
  based_on: Cocoon-AI/architecture-diagram-generator (MIT, v1.0)
  checkout: Xero-Team/AstrBot
  vendor_commit: 06dd052602dd9a369e4d034e24faef0917b5a60c
---

# Archify

Checkout-only maintainer renderer. Read `REFERENCE.md` before authoring. Cite
`AGENTS.md`; do not paste it.

## Locked

- CLI from the AstrBot checkout root:
  `node .agents/skills/archify/bin/archify.mjs`.
- Node 26.x from this checkout. Do not add a skill-local `node_modules` unless
  `doctor` fails without it. Runtime rendering needs no npm install.
- Write JSON IR and delivered HTML under `.tmp/archify/` (gitignored). Do not
  commit generated HTML, PNG, SVG, WebM, or share cards.
- Do not run `scripts/check-update.mjs` or download Archify updates.
- Diagrams of this repository must match current code. Use `Xero-Team/AstrBot`
  for fork-owned identity. Label `AstrBotDevs/AstrBot` only as upstream
  provenance.
- Python 3.14+, source-build `compose.yml` / `astrbot:local`, in-app docs at
  `/help/`. Brand capture is HTTPS-only.

## Open

Diagram type, scope, title, and whether motion, views, or a share card are
required. Ask only when those choices change the artifact.

## Do not

- Use this skill for plugin scaffolding or upstream cherry-pick. Those are
  `create-astrbot-plugin` and `sync-upstream`.
- Invent topology, wake policy, provider modules, or Dashboard routes.
- Point cards or labels at `docs.astrbot.app`, `soulter/astrbot`, or claim this
  fork publishes PyPI, GitHub Release, or container artifacts.
- Copy this tree into the Python sdist, wheel, runtime image, or Dashboard/docs
  build. It is a developer tool, not a product feature.
- Write disposable state into `data/`, `docs/`, or the Dashboard tree unless
  the user explicitly asked for a documentation figure. User-facing docs still
  need matching `docs/zh/` and `docs/en/` pages.
- Start `preview` or pass `--open` unless the user asked for a live window.
- Capture unpinned brand marks. Omit `brand` unless the node names a real
  product and a built-in or digest-pinned mark exists. Do not fetch `http://`
  brand URLs.

## Handoff

- Checkout overlay: `REFERENCE.md`
- Authoring: `references/authoring-contract.md`
- Delivery receipts: `references/delivery-contract.md`
- Viewer features: `references/viewer-runtime.md`
- Commit shape: `.agents/shared/conventional-commit/REFERENCE.md`

Read one matching schema in `schemas/` plus `schemas/common.schema.json` and one
matching JSON example in `examples/`. Use the example for field shape, not
facts. New workflows use `schema_version: 2`.

Suggested maps (inspect code; do not copy example facts):

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
node .agents/skills/archify/scripts/check-checkout.mjs
node .agents/skills/archify/bin/archify.mjs validate <type> .tmp/archify/<name>.json --quality showcase --json
node .agents/skills/archify/bin/archify.mjs deliver <type> .tmp/archify/<name>.json .tmp/archify/<name>.html --quality showcase --json
```

A showcase pass needs all 9 artifact checks and 0 composition errors or
warnings. Skip `visual-check` when Playwright cannot run, and say that browser
evidence was not collected. Do not call a non-zero exit success.
