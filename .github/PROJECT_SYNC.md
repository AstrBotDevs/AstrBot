# GitHub Project synchronization

## Behavior

This follows Peach's event-driven plus periodic reconciliation approach. Every run
builds a read-only snapshot and full diff first. Events and the six-hour schedule
apply changes; manual dispatch and local runs preview by default. Manual `apply`
must be explicitly selected. Sync never edits or deletes source Issues/PRs.

- Required single-select `Status`: `Todo`, `In progress`, `Needs verification`,
  `Done`, `Cancelled`, `Closed unmerged`. Required single-select `交付进度`:
  `未关联实现`, `尚未合入`, `已合入待发布`, `已发布`. Required text fields:
  `实现关联`, `发布版本`, `发布说明`.
- Open issues start Todo. Linked active PRs mean In progress; merge alone means
  Needs verification, not acceptance. Closed issues are Done unless GitHub close
  reason is NOT_PLANNED (Cancelled). Closed unmerged PRs are not Done. Reopened
  terminal items return to Todo. Preserve manually selected nonterminal status
  without implementation. Optional labels `status:needs-info` and
  `status:needs-verification` override inferred open-issue progress.
- Associate same-repository issues using closing references or standalone
  `Ref(s)`, `Fix(es/ed)`, `Close(d)`, or `Resolve(s/d)` lines. Incidental mentions,
  code fences, and cross-repository references do not establish a link.
- Delivery requires every associated implementation PR to be merged, every merge
  commit to be reachable from the trusted default branch, and every such commit
  to be contained in the earliest published stable release. Drafts/prereleases do
  not count. Populate PR links and actual release tag/URL, never guess a version.
- Scan all open issues and all PRs. Also reconcile tracked closed items, linked
  closed issues, the current event subject, and all items closed on or after the
  Project's creation time. This durable boundary recovers replaced/failed event
  runs without importing unrelated items closed before the Project existed. For
  an older Project, preview this catch-up set before enabling writes. Skip
  archived items and draft issues.
- Validate the Project schema/options and calculate all changes before writing;
  skip unchanged values and clear stale text. Paginate every GraphQL connection,
  reject stalled cursors, and serialize whole-project runs.
- Privileged jobs run trusted default-branch code only, use full Git history/tags,
  and never execute PR code. PR tests use no Project secret.

Run offline tests and checks:

```sh
python -I tests/test_sync_github_project.py -v
python -I tests/test_project_delivery.py -v
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

Set the Actions secret `ASTRBOT_PROJECT_TOKEN` to a credential with project write
access and read access to this repository's issues and pull requests.
For example, use a classic personal access token with the `project` scope,
owned by an account that can edit the destination project. Honor any organization
SSO authorization and token restrictions. The repository `GITHUB_TOKEN` is not
used for project mutations.
The Project must contain all five fields and options listed above. Do not use this
credential in ordinary pull request test jobs.

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

Peach reference: [Issue #268](https://github.com/peach-mitao/peach/issues/268),
[Project Board workflow](https://github.com/peach-mitao/peach/blob/master/.github/workflows/project-board.yml),
and [reconciler](https://github.com/peach-mitao/peach/blob/master/scripts/project_board.py).
This implementation adopts event/schedule/manual reconciliation and delivery
evidence, not Peach's unrelated migration/alias configuration.
