---
name: sync-upstream
description: Review and integrate AstrBot upstream/master changes into the Xero-Team/AstrBot fork while maintaining a searchable decision ledger. Use for upstream synchronization, cherry-pick planning, manual adaptation, skipped-commit review, conflict handling, or updates to upstream-sync.yaml.
---

# Sync AstrBot upstream

Use this skill to keep the fork's upstream cursor and integration decisions
auditable without repeatedly loading the entire sync history into context.
Treat `AGENTS.md` as the policy source of truth and
`upstream-decisions.jsonl` as the durable decision ledger.

## Operating modes

- **Review mode (default):** inspect the repository, fetch and compare
  `upstream/master`, classify every pending commit, query prior decisions, and
  return a focused plan. Do not cherry-pick, edit files, commit, or push.
- **Apply mode:** enter only after the user explicitly asks to execute the
  approved plan. Apply commits oldest-first, one at a time, and record each
  final decision. Do not push, merge, release, or tag unless separately asked.

## Preflight

1. Read the upstream-synchronization, generated-artifact, security, and
   toolchain rules in the repository `AGENTS.md`.
2. Inspect `git status --short --branch` and remotes. Do not silently stash,
   reset, checkout, or discard unrelated work.
3. Verify the `upstream` URL and branch from `upstream-sync.yaml`, then fetch:

   ```bash
   git fetch --prune --tags upstream
   ```

4. Inspect the interval and historical decisions with the bundled tools:

   ```bash
   python .agents/skills/sync-upstream/scripts/inspect_upstream.py
   python .agents/skills/sync-upstream/scripts/upstream_decisions.py list --query "..."
   ```

   The inspector validates that the full marker is an ancestor of
   `upstream/master`. If it is not, stop and report the history mismatch.

## Commit decision workflow

For each commit from the marker to the fetched upstream head, in oldest-first
topological order:

1. Read the commit, patch, changed paths, source PR, and relevant current fork
   implementation.
2. Query the ledger by exact SHA, source PR, affected path, and feature terms.
3. Reuse a prior decision only when the current fork architecture and policies
   still match. Mark it `revisit` when the architecture, security posture,
   generated contract, or toolchain has changed.
4. Choose exactly one disposition:
   - `cherry-pick`: the upstream commit is compatible as-is;
   - `adapt`: implement the behavior against current fork boundaries;
   - `skip`: intentionally exclude it and state why;
   - `replay`: apply a historical upstream commit only when the repository
     record explicitly authorizes replay;
   - `revisit`: defer because an earlier decision is no longer reliable.
5. In apply mode, cherry-pick compatible commits with provenance, and manually
   adapt the rest. Never resolve a conflict by blindly choosing ours/theirs.
   Stop on an unresolved conflict and show the user the exact state.

Use reason codes such as `security`, `fork-architecture`, `no-legacy`,
`python-314`, `toolchain`, `source-build`, `openapi`, `generated-model`,
`docs-scope`, and `release-policy` so future searches remain cheap.

## Fork-specific gates

Before accepting a decision, check the affected contract:

- update `pyproject.toml`, `requirements.txt`, and `uv.lock` together for
  runtime Python dependencies;
- update OpenAPI source, generated Dashboard client, public JSON, call sites,
  and tests together for Dashboard protocol changes;
- update both `docs/en/` and `docs/zh/` for user-visible behavior;
- regenerate NapCat models only through `make napcat-check`;
- preserve Python 3.14+, the security invariants, current ownership boundaries,
  source-build deployment, and the no-legacy policy;
- if a release/version change is absorbed, update the synchronized version
  files and only the changelog entries actually included by the fork.

## Ledger operations

Initialize the ledger when the first decision is ready:

```bash
python .agents/skills/sync-upstream/scripts/upstream_decisions.py init
```

Add or revise a decision without loading the ledger into context:

```bash
python .agents/skills/sync-upstream/scripts/upstream_decisions.py add \
  --commit <full-sha> --disposition adapt --summary "..." \
  --source-pr 123 --reason-code security --path astrbot/core/... \
  --fork-adaptation "..." --integration-commit <full-sha>

python .agents/skills/sync-upstream/scripts/upstream_decisions.py update \
  --commit <full-sha> --disposition revisit --summary "..." \
  --reason-code fork-architecture --revisit-when "..."
```

Query current decisions, full event history, or validate the append-only log:

```bash
python .agents/skills/sync-upstream/scripts/upstream_decisions.py get --commit <sha>
python .agents/skills/sync-upstream/scripts/upstream_decisions.py get --commit <sha> --history
python .agents/skills/sync-upstream/scripts/upstream_decisions.py list --path dashboard/src
python .agents/skills/sync-upstream/scripts/upstream_decisions.py validate
```

Use `delete --reason` only to append a tombstone; never remove historical JSONL
lines. Use `import-git --range <old>..<new>` to recover structured decisions
from existing sync commit messages. Imported records are marked as inferred
and must be reviewed before being treated as authoritative.

## Version and changelog finalization

After the audited upstream interval has been integrated, finish the release
metadata before advancing the cursor:

1. Read the version represented by the absorbed upstream release. Keep the
   fork's `[project].version` in `pyproject.toml` and `astrbot.__version__`
   synchronized with that version; do not hardcode the derived
   `astrbot/core/config/default.py` value.
2. Create or update `changelogs/vX.Y.Z.md` for that version. Include only
   changes actually absorbed by this fork, group them by user-visible impact,
   and call out manual adaptations, skipped upstream work, and fork-specific
   deviations. Do not copy upstream release text wholesale or claim artifacts
   that this fork does not publish.
3. If the reviewed interval contains no upstream release/version change, do
   not invent a new version; still write the changelog entry required for the
   absorbed fork changes when the repository's release convention calls for
   one.

## Cursor and verification

Advance `upstream-sync.yaml` only after every commit in the audited interval has
an explicit disposition and the implementation/skip rationale is complete. Use
the full `git rev-parse upstream/master` SHA, UTC time, source PR provenance,
and an honest summary of adaptations, skips, replays, conflicts, and tests.
If the interval is incomplete, leave the cursor unchanged.

Run focused tests first, then the relevant repository gates (`make check`,
`make quality`, Dashboard build, or docs build). Finish with a concise mapping
of upstream commits to dispositions, changed files, checks run, and residual
risk. Do not claim that an upstream commit was integrated merely because it was
reviewed or recorded.

## Bundled tools

- `scripts/inspect_upstream.py`: read-only cursor/ref validation and pending
  commit report, with optional JSON output.
- `scripts/upstream_decisions.py`: append-only JSONL ledger CLI for init, add,
  update, soft-delete, get, list/filter, validation, and Git-history import.

Both tools use only the Python standard library and accept explicit paths, so
they do not add project dependencies or require loading the complete ledger.
