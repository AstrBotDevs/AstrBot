# GitHub Project synchronization

## Behavior

Each run builds a read-only plan first. Issue/PR events reconcile only their direct
associations; six-hour schedule and manual dispatch run full scans. Manual dispatch
and local runs preview by default; manual `apply` must be selected. Sync never edits
or deletes source Issues/PRs.

- Required single-select `Status`: `Todo`, `In progress`, `Needs verification`,
  `Done`, `Cancelled`, `Closed unmerged`. Required single-select `交付进度`:
  `未关联实现`, `尚未合入`, `已合入待发布`, `已发布`. Required text fields:
  `实现关联`, `发布版本`, `发布说明`.
- Open issues start Todo. Linked active PRs mean In progress; merge alone means
  Needs verification, not acceptance. Closed issues are Done unless GitHub close
  reason is NOT_PLANNED (Cancelled). Closed unmerged PRs are not Done. Reopened
  terminal items return to Todo. Preserve manually selected nonterminal status
  without implementation. Optional labels `status:needs-info` and
  `status:needs-verification` override inferred open-issue progress. `needs-info`
  intentionally wins in Status even with a merged PR (Todo + 已合入待发布); the
  fields represent acceptance and delivery separately.
- Associate same-repository issues using closing references or standalone
  `Ref(s)`, `Fix(es/ed)`, `Close(d)`, or `Resolve(s/d)` lines. Incidental mentions,
  code fences, and cross-repository references do not establish a link. A reference
  line containing `Fixes #12, and see #99 for context` links both same-repo issues;
  keep unrelated numbers off reference lines to avoid unintended associations.
- Delivery requires every associated implementation PR to be merged, every merge
  commit to be reachable from the trusted default branch, and every such commit
  to be contained in the earliest published stable release. Drafts/prereleases do
  not count. Populate PR links and actual release tag/URL, never guess a version.
- Issue/PR lifecycle events read only their subject and bounded linked issues/PRs,
  including old/new body references and previously stored implementation links.
  Fork-origin PR events are skipped to avoid spending an Actions run per fork event;
  the scheduled reconciliation still observes their final repository-visible state.
  They do not scan repository Issues, PRs, Project items, or releases. Six-hour
  scheduled and manual runs do full reconciliation; changes discovered only by
  broad push/release scans wait until the next scheduled or manual run.
- Full scans include open issues/all PRs, tracked and linked closed issues, and
  all items closed on or after Project creation. This durable boundary recovers
  replaced/failed events without unrelated older closed history. For an older
  Project, preview catch-up before writes. Skip archived items and draft issues.
- Release version verification runs only during full scans. Event runs defer it to
  the next full scan, while preserving an existing published result when its
  implementation links are unchanged.
- Validate the Project schema/options and calculate all changes before writing;
  skip unchanged values and clear stale text. Paginate every GraphQL connection,
  reject stalled cursors, and serialize runs. Apply mode prints the plan first;
  on failure it reports confirmed, outcome-unknown and unattempted mutation counts,
  with affected item/field, so partial writes can be reconciled.
- Privileged jobs run trusted default-branch code only, use full Git history/tags,
  and never execute PR code. PR tests use no Project secret.

Run offline tests and checks:

```sh
python -I tests/test_sync_github_project.py -v
python -I tests/test_project_delivery.py -v
python -I tests/test_project_events.py -v
uv run ruff format --check scripts/sync_github_project.py tests/test_sync_github_project.py tests/test_project_delivery.py
uv run ruff check scripts/sync_github_project.py
```

## Configuration

Set these repository Actions variables:

| Variable | Value |
| --- | --- |
| `ASTRBOT_PROJECT_ID` | Destination Projects v2 node ID (`PVT_...`); required to enable |
| `ASTRBOT_PROJECT_STATUS_OPEN` | Open-state option name; default `Todo` |
| `ASTRBOT_PROJECT_STATUS_DONE` | Closed/merged-state option name; default `Done` |
| `ASTRBOT_PROJECT_STATUS_MAP` | Optional JSON object mapping remaining canonical Status values to existing option labels |

Example map when an existing Project uses translated Status labels:

```json
{"In progress":"进行中","Needs verification":"待验证","Cancelled":"已取消","Closed unmerged":"已关闭未合入"}
```

Before enabling synchronization, create the `project-sync` GitHub Environment
under repository Settings → Environments. Select **Selected branches and tags**
and add exactly one **branch** rule for the default branch (`master` currently).
Do not allow tags, wildcard branches, or all protected branches. Use required
reviewers where available and limit who can change environment protection rules.
The workflow's inline branch check is defense in depth, not the credential boundary.

Only after those rules are configured, add the **environment secret**
`ASTRBOT_PROJECT_ENV_TOKEN` with project write access and repository Issue/PR read
access. Never define this secret at repository or organization scope; remove any
old repository/organization `ASTRBOT_PROJECT_TOKEN` used for this integration.
The workflow maps the environment secret to the script's `ASTRBOT_PROJECT_TOKEN`
process variable; local runs continue using that process variable. No fallback to
the old secret exists. YAML cannot create or enforce these server-side rules.
If environment protection is unavailable, leave synchronization disabled.

For example, use a classic personal access token with the `project` scope,
owned by an account that can edit the destination project. Honor any organization
SSO authorization and token restrictions. The repository `GITHUB_TOKEN` is not
used for project mutations.
The Project must contain all five fields and options listed above. Do not use this
credential in ordinary pull request test jobs.

Branch protection evaluates the triggering workflow ref, not the checked-out ref.
Release events use tag refs, and PR-target events against non-default branches may
therefore be rejected by this default-branch-only Environment. Do not add tag or
branch exceptions to bypass that restriction: the next default-branch push,
six-hour scheduled run, or default-branch manual dispatch reconciles their state.
Test that a non-default dispatch is denied before using a live credential.

Both workflows pin checkout/setup-python to full commit SHAs verified against
their official repositories. Existing weekly Dependabot updates propose SHA
changes for review; keep the immutable pins when updating Actions.

To resolve an organization project's node ID, replace `PROJECT_NUMBER` with the
number from its GitHub URL (not its node ID):

```sh
gh auth refresh -s project
gh api graphql -f query='query($owner: String!, $number: Int!) {
  organization(login: $owner) { projectV2(number: $number) { id } }
}' -f owner=AstrBotDevs -F number=PROJECT_NUMBER --jq '.data.organization.projectV2.id'
```

Merge to the default branch, configure the fields and secret, then preview with
manual dispatch before selecting `apply`. Verify an Issue→PR→merge→stable release
path plus a fork PR. A mutation can partially apply; rerunning or waiting for the
next schedule reconciles current state. Remove `ASTRBOT_PROJECT_ID` to disable.

## Boundaries

- Always: pass GraphQL variables separately, paginate connections, fail on API
  errors, use timeouts, preview before manual writes, test without credentials.
- Ask first: cross-repository links, legacy backfill, additional tracking fields,
  changing automatic Status rules, creating credentials or a Project.
- Never: commit secrets, check out PR head code in the privileged workflow,
  modify issue/PR state, delete project items, commit or push without permission.

Unrelated items closed before Project creation are intentionally not imported. Coordinate any
native Project automation that writes these same fields. GitHub Actions and live
API validation require maintainer configuration after merge.

## API reference

GitHub's official "Using the API to manage Projects" documentation describes
ProjectV2 field lookup, `addProjectV2ItemById` (including existing-item reuse),
and `updateProjectV2ItemFieldValue`:
https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects
