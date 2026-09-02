# Archify on this checkout

Vendored from [tt-a1i/archify](https://github.com/tt-a1i/archify) `archify/`
at the commit in `VENDOR.json`. The renderer stays MIT-licensed; keep
`LICENSE` and `THIRD_PARTY_NOTICES.md` beside it. This file is the
Xero-Team/AstrBot overlay. Cite `AGENTS.md` instead of pasting it.

This skill is a **checkout-only maintainer tool**. It must not enter the
Python sdist/wheel, the runtime image, or the Dashboard/docs production
build. Agents discover it at `.agents/skills/archify/SKILL.md`. Do not copy
it into gitignored `.opencode/`.

## Locked

- CLI from the AstrBot checkout root:
  `node .agents/skills/archify/bin/archify.mjs`. Packaged paths such as
  `schemas/`, `examples/`, `references/`, and `bin/` live under
  `.agents/skills/archify/`.
- Node 26.x from this checkout. Do not add a skill-local `node_modules`
  unless `doctor` fails without it. Runtime rendering needs no npm install.
  `package-lock.json` exists only for regenerating brand marks after a
  vendor bump.
- Write JSON IR and delivered HTML under `.tmp/archify/` (gitignored). Do
  not commit generated HTML, PNG, SVG, WebM, or share cards.
- Do not run `scripts/check-update.mjs`. Do not download or install Archify
  updates from this workflow.
- Diagrams of this repository must match current code. Cite `AGENTS.md` and
  `docs/zh/dev/architecture.md` / `docs/en/dev/architecture.md`. Use
  `Xero-Team/AstrBot` for fork-owned identity. Label `AstrBotDevs/AstrBot`
  only as upstream provenance.
- Python 3.14+, source-build `compose.yml` / `astrbot:local`, in-app docs at
  `/help/`. Do not restore legacy shims, `docs.astrbot.app`, or upstream
  images.
- `--repo-root` is this checkout when evidence-backed Architecture nodes
  must open files here.
- Brand capture accepts HTTPS URLs only. Private, loopback, and credentialed
  targets stay rejected.
- Generated HTML must not fetch Google Fonts. The template falls back to
  local JetBrains Mono and system monospace.

## Open

Diagram type, scope, title, and whether motion, views, or a share card are
required. Ask only when those choices change the artifact.

## Do not

- Use this skill for plugin scaffolding or upstream cherry-pick. Those are
  `create-astrbot-plugin` and `sync-upstream`.
- Invent topology, wake policy, provider modules, or Dashboard routes.
- Point cards or labels at `docs.astrbot.app`, `soulter/astrbot`, or claim
  this fork publishes PyPI, GitHub Release, or container artifacts.
- Ship this tree in hatch artifacts or `Dockerfile` runtime copies.
- Write disposable state into `data/`, `docs/`, or the Dashboard tree unless
  the user explicitly asked for a documentation figure. User-facing docs
  still need matching `docs/zh/` and `docs/en/` pages.
- Start `preview` or pass `--open` unless the user asked for a live window.
- Capture unpinned brand marks. Omit `brand` unless the node names a real
  product and a built-in or digest-pinned mark exists.
- Run upstream `package.json` scripts that need `../scripts/` or `test/`.
  Those paths are excluded from this vendor pin. Use `check:checkout`.

## Local patches

Recorded in `VENDOR.json` `local_patches`. Re-apply them after a vendor bump:

- `SKILL.md` is this overlay, not the upstream prompt.
- `package.json` scripts are trimmed to files that exist in this tree.
- Brand capture is HTTPS-only.
- `assets/template.html` does not load Google Fonts.

Third-party marks remain subject to `THIRD_PARTY_NOTICES.md`. Do not author a
Vue.js brand node unless that use is independently permitted.

## Handoff

- Authoring: `references/authoring-contract.md`
- Delivery receipts: `references/delivery-contract.md`
- Viewer features: `references/viewer-runtime.md`
- Commit shape: `.agents/shared/conventional-commit/REFERENCE.md`

## Verify

```bash
node .agents/skills/archify/bin/archify.mjs doctor
node .agents/skills/archify/scripts/check-checkout.mjs
node .agents/skills/archify/bin/archify.mjs validate <type> .tmp/archify/<name>.json --quality showcase --json
node .agents/skills/archify/bin/archify.mjs deliver <type> .tmp/archify/<name>.json .tmp/archify/<name>.html --quality showcase --json
node .agents/skills/archify/bin/archify.mjs visual-check .tmp/archify/<name>.html --json
```

A showcase pass needs all 9 artifact checks and 0 composition errors or
warnings. Skip `visual-check` when Playwright cannot run, and say that
browser evidence was not collected. Do not call a non-zero exit success.
`make check-archify` runs doctor plus example showcase validation; it is not
part of `make check`.
