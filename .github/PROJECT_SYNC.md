# GitHub Project synchronization

The `Sync GitHub Project` workflow updates Project status and release tracking from repository issues and pull requests. It does not edit or delete source issues or PRs. Manual dispatch and local runs preview changes by default.

## Configure the integration

1. Create these fields in the destination Projects v2 project:

   | Field | Type | Required options |
   | --- | --- | --- |
   | `Status` | Single select | `Todo`, `In progress`, `Needs verification`, `Done`, `Cancelled`, `Closed unmerged` |
   | `交付进度` | Single select | `未关联实现`, `尚未合入`, `已合入待发布`, `已发布` |
   | `实现关联`, `发布版本`, `发布说明` | Text | — |

2. Under **Settings → Environments**, create `project-sync`. Choose **Selected branches and tags** and allow exactly the default branch (`master`), using a branch rule. Do not allow tags or wildcard branches. Use required reviewers where available and restrict changes to these rules. If environment protection is unavailable, leave synchronization disabled.
3. After configuring protection, add the **environment secret** `ASTRBOT_PROJECT_ENV_TOKEN` with Project write and repository Issue/PR read access. For example, use a classic personal access token with `project` scope from an account that can edit the Project, subject to organization SSO and token policies. Do not store it as a repository or organization secret; remove any old `ASTRBOT_PROJECT_TOKEN` secret at those scopes.
4. Set the repository Actions variables below. Setting `ASTRBOT_PROJECT_ID` enables the workflow.

   | Variable | Value |
   | --- | --- |
   | `ASTRBOT_PROJECT_ID` | Destination Project node ID (`PVT_...`) |
   | `ASTRBOT_PROJECT_STATUS_OPEN` | Open-state label; defaults to `Todo` |
   | `ASTRBOT_PROJECT_STATUS_DONE` | Closed/merged-state label; defaults to `Done` |
   | `ASTRBOT_PROJECT_STATUS_MAP` | Optional JSON map from other canonical Status values to existing labels |

For translated labels, a status map can be:

```json
{"In progress":"进行中","Needs verification":"待验证","Cancelled":"已取消","Closed unmerged":"已关闭未合入"}
```

To look up an organization Project's node ID, replace `PROJECT_NUMBER` with the number in its URL:

```sh
gh auth refresh -s project
gh api graphql -f query='query($owner: String!, $number: Int!) {
  organization(login: $owner) { projectV2(number: $number) { id } }
}' -f owner=AstrBotDevs -F number=PROJECT_NUMBER --jq '.data.organization.projectV2.id'
```

The workflow maps the environment secret to the script's `ASTRBOT_PROJECT_TOKEN` process variable. Local runs use that variable too. The repository `GITHUB_TOKEN` is not used for Project writes.

## Preview and apply

After merging the workflow to the default branch, run it manually on that branch with `apply` unchecked. Review the plan, then run with `apply` selected. Verify an issue → PR → merge → stable release sequence and a fork PR.

Before using a live credential, verify that dispatch from a non-default branch is denied. Environment protection checks the triggering workflow ref, not the checked-out ref. Do not add branch exceptions for rejected PR-target events; the next scheduled or default-branch manual run reconciles them.

Remove `ASTRBOT_PROJECT_ID` to disable synchronization. Coordinate any native Project automation that writes the same fields.

## Synchronization rules

| Situation | Result |
| --- | --- |
| Open issue without an implementation | `Todo`; preserve a manually selected nonterminal status |
| Linked active PR | `In progress` |
| Linked merged PR | `Needs verification`; merging does not imply acceptance |
| Closed issue | `Done`, or `Cancelled` for `NOT_PLANNED` |
| Closed unmerged PR | `Closed unmerged` |
| Reopened terminal item | `Todo` |

For open issues, `status:needs-info` and `status:needs-verification` override inferred progress. `needs-info` takes precedence even with a merged PR; acceptance status and delivery progress are separate fields.

Issues are linked through closing references or standalone `Ref(s)`, `Fix(es/ed)`, `Close(d)`, or `Resolve(s/d)` lines. Keep unrelated issue numbers off those lines: `Fixes #12, and see #99 for context` links both. Incidental mentions, code fences, and cross-repository references do not establish links.

A delivery is released only when all associated implementation PRs are merged, their commits are reachable from the default branch, and a published stable release contains all those commits. The earliest qualifying release supplies the version and URL; drafts and prereleases do not count.

## Schedule and recovery

- Issue and same-repository PR events reconcile the changed item and its linked items. Fork PR events are skipped; full scans include their repository-visible state.
- Scheduled runs every six hours and manual runs perform full reconciliation, including release verification. Event runs preserve an existing release result while implementation links are unchanged.
- Full scans include open issues, all PRs, tracked or linked closed issues, and items closed since Project creation. Archived items and draft issues are skipped. Preview catch-up before applying to an older Project.
- Each run validates the schema and prints its plan before writing. Runs are serialized and have a 120-minute total timeout. API errors or missing fetched tags stop the run.
- A failed apply reports confirmed, outcome-unknown, and unattempted writes. Rerun or wait for the next scheduled scan to reconcile partial changes. The Actions log shows scan progress.

Privileged runs use default-branch code and full Git history and tags. Never check out PR code or expose the Project token in PR test jobs. Keep Actions pinned to immutable commit SHAs when updating them.

## Local validation

Run the offline checks without credentials:

```sh
uv run --no-project python -I tests/test_sync_github_project.py -v
uv run --no-project python -I tests/test_project_events.py -v
uv run ruff format --check scripts/sync_github_project.py tests/test_sync_github_project.py tests/test_project_events.py
uv run ruff check scripts/sync_github_project.py
```

See GitHub's [Projects API guide](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects) for field lookup and item mutations.
