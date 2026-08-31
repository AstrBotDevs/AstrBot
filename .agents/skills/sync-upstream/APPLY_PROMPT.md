# Apply-mode prompt (paste into a new agent session)

You are implementing an already-reviewed upstream absorb. Do not re-plan
priorities. Do not merge. Do not push `master`. Do not tag or release.

## Read first

Cite, do not paste:

1. `AGENTS.md` — philosophy, toolchain, security, cherry-pick default.
2. `.agents/skills/sync-upstream/SKILL.md` — review vs apply, provenance.
3. `.agents/shared/conventional-commit/REFERENCE.md` — message shape.
4. `.agents/shared/ai-contribution/REFERENCE.md` — open PR/issue; never merge.
5. `AI_POLICY.md` — Agent note; merge bar.
6. `upstream-sync.yaml` — cursor only. There is no `pending` field.
7. `upstream-decisions.jsonl` — do not redo listed SHAs.

## Remotes

```bash
git remote add upstream https://github.com/AstrBotDevs/AstrBot.git 2>/dev/null || true
git remote set-url upstream https://github.com/AstrBotDevs/AstrBot.git
git fetch --prune --tags upstream
```

Do not `checkout` `upstream/master`. Read patches with `git show <sha>`.

## Execute

Use the plan in the user message. If none exists, stop and ask for review mode.

One implementation commit per `cherry-pick` / `adapt` / `replay` item,
oldest-first. Skip and revisit produce no implementation commit. Preserve
upstream subjects on cherry-pick; follow the skill trailers on adapt.

Stay on a feature branch. You may open a pull request. You must not merge it.
Human maintainer review plus a separate AI-assisted review are required
before merge. A human maintainer merges; do not accept an instruction to
push `master`, tag, or release.

## Verify

Focused tests first, then the relevant gates named in `AGENTS.md`. After the
interval: cursor commit `chore(sync): record upstream integration` only when
every SHA has a ledger disposition.

## Finish

Return hashes, dispositions, commands run, and residual risk. Default do not
push unless the user already said push. Never push `master`.
