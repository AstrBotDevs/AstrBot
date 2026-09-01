# AI contribution reference

Policy source: `/AI_POLICY.md`. Commit-message source:
`.agents/shared/conventional-commit/REFERENCE.md`. Do not paste those files
into a prompt; cite them.

## Load this when

The agent will commit, push, open an Issue, open a Pull Request, comment on
review, or decide whether a change is ready to merge.

## Locked

- Agents **may** maintain the repository: edit, run checks, commit, push
  feature branches, open development Issues/PRs, comment, and request review.
- Agents **must not** merge PRs, push `master`, force-push protected branches,
  tag, publish releases, change branch protection or secrets, or file a public
  security report. A human maintainer does those actions. Do not treat a
  verbal exception as authorization.
- A PR lands only after a **human maintainer** review **and** a separate
  **AI-assisted review** on that PR. The authoring agent's write-up is not
  that review.
- English Conventional Commits. AI-finalized messages need `AI-Generated: true`
  and UTC `Generated-At:` from `date -u '+%Y-%m-%dT%H:%M:%SZ'`.
- Human authors add `## Human note` in their own words. Agent authors add
  `## Agent note`. Never fabricate the other. Open PRs with the typed
  template under `.github/PULL_REQUEST_TEMPLATE/` (`feat.md`, `fix.md`,
  `docs.md`; `perf`/`style` → `refactor.md`; `build`/`ops`/`test` →
  `chore.md`).
- Cite `AGENTS.md`, named skills, and named docs. Do not dump them.

## Open

Which feature branch, how many commits, and whether to open the PR in this
session are open unless the user already decided. Prefer one concern per
commit.

## Do not

- Merge, even when CI is green.
- Claim a check passed unless this session ran it or a linked CI run did.
- Restore legacy shims, Python 3.10-3.13 fallbacks, or upstream publish/docs
  URLs as fork artifacts.
- Skip bilingual docs for user-visible behavior.

## Handoff

- Commit message shape: `.agents/shared/conventional-commit/REFERENCE.md`.
- Upstream absorb: `.agents/skills/sync-upstream/SKILL.md`.
- Plugin packages: `.agents/skills/create-astrbot-plugin/SKILL.md`.
- Merge decision: stop and name the human maintainer. Do not self-merge.
