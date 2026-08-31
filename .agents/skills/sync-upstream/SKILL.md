---
name: sync-upstream
description: Review and integrate AstrBot upstream/master changes into the Xero-Team/AstrBot fork while maintaining a searchable decision ledger and provenance-preserving per-commit history. Use for upstream synchronization, cherry-pick planning, manual adaptation, skipped-commit review, conflict handling, sync commit author/message policy, or updates to upstream-sync.yaml.
---

# Sync AstrBot upstream

Use this skill to keep the fork's upstream cursor and integration decisions
auditable without repeatedly loading the entire sync history into context.
Treat `AGENTS.md` as the policy source of truth and
`upstream-decisions.jsonl` as the durable decision ledger.

Cite `.agents/shared/ai-contribution/REFERENCE.md` and `AI_POLICY.md` when
opening a branch, Issue, or PR. Paste-ready apply prompt:
`APPLY_PROMPT.md` in this folder.

## Locked

- Default method is **cherry-pick**, not merge of `upstream/master`.
- One implementation commit per absorbed upstream commit. Skip/revisit make
  none.
- Preserve upstream subjects on `cherry-pick -x`. Adapt uses upstream author
  plus hyphenated trailers.
- Python 3.14+, no legacy shims, source-build compose, in-app `/help/` docs.
- Do not merge the resulting PR, push `master`, tag, or release. A human
  maintainer does those actions; do not treat a verbal exception as
  authorization.

## Open

Which commits to absorb in this window, and whether to open the PR in this
session, unless the user already froze the plan in this conversation.

## Do not

- `git merge` / `rebase` onto `upstream/master`.
- Combine several upstream feature/fix commits into one implementation commit.
- Re-run an interval whose SHAs are already in the ledger.
- File a public security Issue for an upstream vuln; follow `SECURITY.md`.
- Invent a `pending` field in `upstream-sync.yaml`. Apply only the plan the
  user approved in this conversation.

## Handoff

- Commit messages: `.agents/shared/conventional-commit/REFERENCE.md`.
- Agent merge bar: `.agents/shared/ai-contribution/REFERENCE.md`.
- Apply paste prompt: `.agents/skills/sync-upstream/APPLY_PROMPT.md`.

## Operating modes

- **Review mode (default):** inspect the repository, fetch and compare
  `upstream/master`, classify every pending commit, query prior decisions, and
  return a focused plan. Do not cherry-pick, edit files, commit, or push.
- **Apply mode:** enter only after the user explicitly asks to execute the
  approved plan. Apply commits oldest-first, one at a time, and record each
  final decision. Stay on a feature branch. You may open a pull request. Do
  not merge, push `master`, release, or tag.

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

## Integration commit strategy

In apply mode, create at most one implementation commit for each upstream
commit with disposition `cherry-pick`, `adapt`, or `replay`. Process them in
oldest-first topological order. Do not combine several upstream feature or fix
commits into one implementation commit. Commits with disposition `skip` or
`revisit` produce no implementation commit.

Preserve the upstream subject verbatim whenever possible, including its
Conventional Commit type, scope, description, and existing `(#number)` PR
suffix. If the upstream subject has no PR suffix, do not invent one. Change a
subject only when the fork's user-visible semantics materially differ, and
explain that change in the commit body.

Generated or rewritten messages must follow
`.agents/shared/conventional-commit/REFERENCE.md`, including
`AI-Generated: true` and a UTC `Generated-At:` footer from
`date -u '+%Y-%m-%dT%H:%M:%SZ'`. Do not rewrite a preserved upstream
subject to satisfy that reference. Do not add AI metadata to a message
that `git cherry-pick -x` kept verbatim.

Use the following method for each disposition:

- `cherry-pick`: use `git cherry-pick -x <full-upstream-sha>`. This preserves
  the upstream author and records Git's standard `(cherry picked from commit
...)` provenance line. Do not duplicate that line with another
  `Upstream-Commit` trailer unless a conflict or message rewrite removes it.
- `adapt`: apply the behavior manually against the current fork boundaries,
  then commit with `git commit --author="<upstream author>"`. Preserve the
  upstream subject and add the trailers below.
- `replay`: use only when the ledger explicitly authorizes replay. Treat it as
  a manual adaptation for author and provenance purposes, and cite the
  authorizing historical record in the body or trailers.

For adapted, replayed, or conflict-rewritten commits, use standard Git
trailers with hyphenated tokens:

```text
Upstream-Commit: <full upstream SHA>
Upstream-Author: <name> <email>
Upstream-PR: AstrBotDevs#<number>
Sync-Disposition: adapt
Fork-Adaptation: <concise explanation of the fork-specific implementation>
Tested: <focused validation command>
```

Omit a trailer when its value is unavailable; never use non-standard tokens
with spaces such as `Source PR`. Keep `Signed-off-by` separate from sync
provenance and do not add it unless repository policy or the user explicitly
requires a developer certificate.

Recommended adapted-commit shape:

```text
<upstream subject>

<optional fork-specific explanation>

Upstream-Commit: <full upstream SHA>
Upstream-Author: <name> <email>
Upstream-PR: AstrBotDevs#<number>
Sync-Disposition: adapt
Fork-Adaptation: <what changed for this fork>
Tested: <command>
AI-Generated: true
Generated-At: <UTC ISO 8601 timestamp>
```

The final cursor update is a separate metadata-only commit with subject
`chore(sync): record upstream integration`. Generate that message from
the conventional-commit reference, including a body and AI footers. Do
not hide implementation changes inside this cursor commit. A
release/version bump that is intentionally skipped still advances the
cursor only after its `skip` decision is recorded and the skip rationale
is written to `upstream-sync.yaml`.

After each implementation commit, verify the mapping before moving on:

```bash
git show -s --format='%H%n%an <%ae>%n%cn <%ce>%n%s%n%B' HEAD
git show --stat --oneline HEAD
```

The integration commit must be attributable to exactly one upstream SHA, and
its author must be the upstream author for `cherry-pick`, `adapt`, and
`replay` unless the user explicitly directs otherwise. The fork maintainer is
normally the committer.

## Conflict and duplicate handling

Never resolve a conflict by blindly choosing ours or theirs. Pause the
sequence, inspect the conflicting path and the missing context, and identify
possible prerequisite commits before editing:

```bash
git log HEAD..<upstream_sha>^ -- <conflicted-path>
git log -G'<relevant-symbol-or-string>' HEAD..<upstream_sha>^ -- <conflicted-path>
```

If the conflict is a mechanical context adjustment and preserves upstream
behavior, continue the `cherry-pick`; inspect the final message and add an
`Upstream-Commit` trailer if Git did not retain `-x` provenance. If the
resolution changes behavior to fit fork architecture, classify the result as
`adapt`, preserve the upstream author with `--author`, and record the reason in
`Fork-Adaptation`. If the prerequisite or intended behavior cannot be
established, run `git cherry-pick --abort` and use `revisit` rather than
guessing.

Before creating a new implementation commit, check whether the change was
already integrated under a different fork commit:

```bash
git cherry upstream/master
git log --all --grep='Upstream-Commit: <full-upstream-sha>' --format='%H %s'
```

An already-equivalent patch needs an explicit ledger decision and provenance;
do not create a duplicate implementation commit merely because the SHA differs.

## Fork-specific gates

Before accepting a decision, check the affected contract:

- update `pyproject.toml`, `requirements.txt`, and `uv.lock` together for
  runtime Python dependencies;
- update OpenAPI source, generated Dashboard client, public JSON, call sites,
  and tests together for Dashboard protocol changes;
- update both `docs/en/` and `docs/zh/` for user-visible behavior;
- keep documentation in-app at `/help/`; do not restore `Dockerfile.docs`, a
  docs Compose service, or `docs.astrbot.app` links;
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

## Verify

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
