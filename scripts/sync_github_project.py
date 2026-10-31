"""Synchronize issue and pull request lifecycle events to GitHub Projects v2."""

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS_OPTIONS = (
    "Todo",
    "In progress",
    "Needs verification",
    "Done",
    "Cancelled",
    "Closed unmerged",
)
DELIVERY_OPTIONS = ("未关联实现", "尚未合入", "已合入待发布", "已发布")


def connection(query, path, *, initial=None, **variables):
    """Read every page and fail if the cursor stalls.

    Args:
        query: GraphQL operation accepting a cursor variable.
        path: Keys leading to a connection in the response.
        initial: Optional first page already returned in a parent query.
        **variables: Other operation variables.

    Returns:
        All non-null connection nodes.

    Raises:
        RuntimeError: A cursor does not advance or the connection is inaccessible.
    """
    nodes, cursor, seen = [], None, set()
    while True:
        if initial is not None:
            data, initial = initial, None
        else:
            data = graphql(query, {**variables, "cursor": cursor})
            for key in path:
                data = (data or {}).get(key)
        if not isinstance(data, dict):
            raise RuntimeError("GitHub connection is inaccessible")
        nodes.extend(node for node in data["nodes"] if node)
        page = data["pageInfo"]
        if not page["hasNextPage"]:
            return nodes
        cursor = page["endCursor"]
        if not cursor or cursor in seen:
            raise RuntimeError("GitHub pagination cursor did not advance")
        seen.add(cursor)


def references(body, repository):
    """Read explicit same-repository issue reference lines, excluding code fences.

    Args:
        body: Pull request description.
        repository: Allowed owner/name.

    Returns:
        Referenced issue numbers.
    """
    found, fence = set(), None
    for line in (body or "").splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence or not re.match(
            r"^\s*(?:refs?|close[sd]?|fix(?:es|ed)?|resolve[sd]?)\s*[:：]?\s+",
            line,
            re.I,
        ):
            continue
        # Match complete URLs first so foreign URL fragments cannot become local refs.
        for match in re.finditer(
            r"https?://[^\s,<>]+|(?<![\w/#])(?:(?P<repo>[\w.-]+/[\w.-]+))?#(?P<number>[0-9]+)",
            line,
        ):
            if match["number"]:
                repo, number = match["repo"] or repository, match["number"]
            else:
                url = re.fullmatch(
                    r"https://github\.com/([\w.-]+/[\w.-]+)/issues/([0-9]+)[.)]?",
                    match[0],
                    re.I,
                )
                if not url:
                    continue
                repo, number = url.groups()
            if repo.casefold() == repository.casefold() and int(number) > 0:
                found.add(int(number))
    return found


def decide(content, current, linked):
    """Separate issue acceptance from implementation progress.

    Args:
        content: Current issue or pull request data.
        current: Existing Project field values.
        linked: Active or merged implementation pull requests.

    Returns:
        Desired Status value.
    """
    state = content["state"]
    status = current.get("Status", "Todo")
    if content["__typename"] == "PullRequest":
        status = {"OPEN": "In progress", "CLOSED": "Closed unmerged", "MERGED": "Done"}[
            state
        ]
    elif state == "CLOSED":
        status = "Cancelled" if content.get("stateReason") == "NOT_PLANNED" else "Done"
    elif status in {"Done", "Cancelled", "Closed unmerged"}:
        status = "Todo"
    elif "status:needs-verification" in content.get("labels", []):
        status = "Needs verification"
    elif "status:needs-info" in content.get("labels", []):
        status = "Todo"
    elif linked and all(pr["state"] == "MERGED" for pr in linked):
        status = "Needs verification"
    elif linked:
        status = "In progress"
    elif status not in STATUS_OPTIONS:
        status = "Todo"
    return {"Status": status}


@cache
def ancestor(commit, ref):
    """Check commit reachability without running user-controlled shell commands.

    Args:
        commit: Full implementation commit OID.
        ref: Trusted mainline OID or fully qualified release tag ref.

    Returns:
        Whether the commit is contained in the ref.

    Raises:
        ValueError: The commit or reference is invalid.
        RuntimeError: Git history is incomplete or git fails.
    """
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not (
        re.fullmatch(r"[0-9a-f]{40}", ref) or ref.startswith("refs/tags/")
    ):
        raise ValueError("Invalid implementation commit or release ref")
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, ref],
        cwd=ROOT,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(
            "Cannot verify release ancestry; fetch full history and tags"
        )
    return result.returncode == 0


def delivery(content, current, linked, releases, mainline):
    """Calculate implementation links and the earliest proven stable release.

    Args:
        content: Current source item.
        current: Existing Project values.
        linked: Associated active or merged pull requests.
        releases: Published releases with flags and timestamps.
        mainline: Trusted default-branch commit OID.

    Returns:
        Desired values for all five managed fields.
    """
    associated = [content] if content["__typename"] == "PullRequest" else linked
    merged = [pr for pr in associated if pr["state"] == "MERGED"]
    commits = {pr["mergeCommit"]["oid"] for pr in merged if pr.get("mergeCommit")}
    integrated = {commit for commit in commits if ancestor(commit, mainline)}
    all_merged = bool(associated) and len(merged) == len(associated)
    all_integrated = (
        bool(merged) and len(commits) == len(merged) and integrated == commits
    )
    published = None
    for release in sorted(
        (
            r
            for r in releases
            if not r["isDraft"] and not r["isPrerelease"] and r.get("publishedAt")
        ),
        key=lambda r: r["publishedAt"],
    ):
        if (
            all_merged
            and all_integrated
            and all(
                ancestor(commit, f"refs/tags/{release['tagName']}")
                for commit in integrated
            )
        ):
            published = release
            break
    progress = (
        "已发布"
        if published
        else "已合入待发布"
        if all_merged and all_integrated
        else "尚未合入"
        if associated
        else "未关联实现"
    )
    return {
        **decide(content, current, linked),
        "交付进度": progress,
        "实现关联": "\n".join(
            sorted({pr["url"] for pr in associated if pr.get("url")})
        ),
        "发布版本": published["tagName"] if published else "",
        "发布说明": published["url"] if published else "",
    }


def apply_plan(project, fields, plan, *, apply=False):
    """Apply only precomputed differences; preview never issues mutations.

    Args:
        project: Destination node ID.
        fields: Validated field definitions.
        plan: Source IDs, existing item IDs and changed values.
        apply: Explicit permission to write.
    """
    if not apply:
        return
    for entry in plan:
        item = entry["item"]
        if not item:
            result = graphql(
                """mutation($project: ID!, $content: ID!) {
                  addProjectV2ItemById(input: {projectId:$project, contentId:$content}) { item { id } }
                }""",
                {"project": project, "content": entry["content"]},
            )
            item = result["addProjectV2ItemById"]["item"]["id"]
        for name, value in entry["changes"].items():
            field = fields[name]
            variables = {"project": project, "item": item, "field": field["id"]}
            if value == "":
                graphql(
                    """mutation($project:ID!,$item:ID!,$field:ID!){
                      clearProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,fieldId:$field}){projectV2Item{id}}
                    }""",
                    variables,
                )
            else:
                variables["value"] = (
                    {
                        "singleSelectOptionId": next(
                            o["id"] for o in field["options"] if o["name"] == value
                        )
                    }
                    if "options" in field
                    else {"text": value}
                )
                graphql(
                    """mutation($project:ID!,$item:ID!,$field:ID!,$value:ProjectV2FieldValue!){
                      updateProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,fieldId:$field,value:$value}){projectV2Item{id}}
                    }""",
                    variables,
                )


def graphql(query, variables):
    """Execute a GitHub GraphQL request without exposing credentials in errors.

    Args:
        query: GraphQL operation text.
        variables: Separate operation variables.

    Returns:
        The response data dictionary.

    Raises:
        RuntimeError: The request fails or returns GraphQL errors.
    """
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['ASTRBOT_PROJECT_TOKEN']}",
            "Content-Type": "application/json",
            "User-Agent": "AstrBot-Project-Sync",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise RuntimeError(
            "GitHub GraphQL request failed; check connectivity and token permissions"
        ) from None
    if (
        not isinstance(result, dict)
        or result.get("errors")
        or not isinstance(result.get("data"), dict)
    ):
        raise RuntimeError(
            "GitHub GraphQL returned errors; check project and repository access"
        )
    return result["data"]


def reconcile(project, repository, *, subject=None, apply=False, status_names=None):
    """Plan a complete snapshot before performing any Project mutations.

    Args:
        project: Destination ProjectV2 node ID.
        repository: Allowed source owner/name.
        subject: Event item number to include even if closed.
        apply: Explicit permission to write.
        status_names: Canonical-to-configured Status names.

    Returns:
        JSON-serializable change plan.

    Raises:
        ValueError: Required fields, options or source states are invalid.
        RuntimeError: GitHub reads or ancestry checks fail.
    """
    status_names = status_names or dict(zip(STATUS_OPTIONS, STATUS_OPTIONS))
    definitions = connection(
        """query($project:ID!,$cursor:String){node(id:$project){... on ProjectV2{
          fields(first:100,after:$cursor){nodes{
            ... on ProjectV2Field{id name dataType}
            ... on ProjectV2SingleSelectField{id name options{id name}}
          }pageInfo{hasNextPage endCursor}}}}}""",
        ("node", "fields"),
        project=project,
    )
    fields = {}
    for field in definitions:
        if "name" not in field:
            continue
        if field["name"] in fields:
            raise ValueError("Project field names must be unique")
        fields[field["name"]] = field
    for name, required in {
        "Status": tuple(status_names.values()),
        "交付进度": DELIVERY_OPTIONS,
    }.items():
        field = fields.get(name, {})
        options = [o["name"] for o in field.get("options", [])]
        if (
            not field.get("options")
            or not set(required) <= set(options)
            or len(options) != len(set(options))
        ):
            raise ValueError(
                f"Project {name} must be single-select with all required options"
            )
    for name in ("实现关联", "发布版本", "发布说明"):
        if fields.get(name, {}).get("dataType") != "TEXT":
            raise ValueError(f"Project {name} must be a text field")
    metadata = graphql(
        """query($project:ID!){node(id:$project){... on ProjectV2{createdAt}}}""",
        {"project": project},
    )
    since = (metadata.get("node") or {}).get("createdAt")
    if not isinstance(since, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", since
    ):
        raise ValueError("Project creation time is required for closed-item recovery")
    items = connection(
        """query($project:ID!,$cursor:String){node(id:$project){... on ProjectV2{
          items(first:100,after:$cursor,archivedStates:[ARCHIVED,NOT_ARCHIVED]){nodes{
            id isArchived content{__typename ... on Issue{id} ... on PullRequest{id}}
            fieldValues(first:100){nodes{
              ... on ProjectV2ItemFieldSingleSelectValue{name field{... on ProjectV2SingleSelectField{name}}}
              ... on ProjectV2ItemFieldTextValue{text field{... on ProjectV2Field{name}}}
            }pageInfo{hasNextPage endCursor}}
          }pageInfo{hasNextPage endCursor}}}}}""",
        ("node", "items"),
        project=project,
    )
    tracked = {
        item["content"]["id"]: item
        for item in items
        if item.get("content")
        and item["content"]["__typename"] in {"Issue", "PullRequest"}
    }
    owner, name = repository.split("/")
    variables = {"owner": owner, "name": name}
    issues = connection(
        """query($owner:String!,$name:String!,$states:[IssueState!],$cursor:String){repository(owner:$owner,name:$name){
          issues(first:100,after:$cursor,states:$states){nodes{__typename id number state stateReason closedAt
            labels(first:100){nodes{name}pageInfo{hasNextPage endCursor}}}
          pageInfo{hasNextPage endCursor}}}}""",
        ("repository", "issues"),
        states=["OPEN", "CLOSED"],
        **variables,
    )
    prs = connection(
        """query($owner:String!,$name:String!,$states:[PullRequestState!],$cursor:String){repository(owner:$owner,name:$name){
          pullRequests(first:100,after:$cursor,states:$states){nodes{__typename id number state body url closedAt
            mergeCommit{oid}
            closingIssuesReferences(first:100){nodes{number repository{nameWithOwner}}
              pageInfo{hasNextPage endCursor}}
          }pageInfo{hasNextPage endCursor}}}}""",
        ("repository", "pullRequests"),
        states=["OPEN", "CLOSED", "MERGED"],
        **variables,
    )
    linked = {}
    for pr in prs:
        if pr["state"] not in {"OPEN", "MERGED", "CLOSED"}:
            raise ValueError("Unexpected pull request state")
        if pr["state"] == "CLOSED":
            continue
        closing = connection(
            """query($id:ID!,$cursor:String){node(id:$id){... on PullRequest{
              closingIssuesReferences(first:100,after:$cursor){nodes{number repository{nameWithOwner}}
              pageInfo{hasNextPage endCursor}}}}}""",
            ("node", "closingIssuesReferences"),
            initial=pr["closingIssuesReferences"],
            id=pr["id"],
        )
        numbers = {
            issue["number"]
            for issue in closing
            if issue["repository"]["nameWithOwner"].casefold() == repository.casefold()
        }
        numbers |= references(pr.get("body"), repository)
        for number in numbers:
            linked.setdefault(number, []).append(pr)
    candidates = [
        i
        for i in issues
        if i["state"] == "OPEN"
        or i["id"] in tracked
        or i["number"] == subject
        or i["number"] in linked
        or (i.get("closedAt") or "") >= since
    ]
    issue_numbers = {i["number"] for i in candidates}
    associated_ids = {
        pr["id"] for number in issue_numbers for pr in linked.get(number, [])
    }
    candidates.extend(
        pr
        for pr in prs
        if pr["state"] == "OPEN"
        or pr["id"] in tracked
        or pr["number"] == subject
        or pr["id"] in associated_ids
        or (pr.get("closedAt") or "") >= since
    )
    releases = connection(
        """query($owner:String!,$name:String!,$cursor:String){repository(owner:$owner,name:$name){
          releases(first:100,after:$cursor){nodes{tagName url publishedAt isDraft isPrerelease}
          pageInfo{hasNextPage endCursor}}}}""",
        ("repository", "releases"),
        **variables,
    )
    mainline = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    ).stdout.strip()
    plan = []
    for content in candidates:
        item = tracked.get(content["id"])
        if item and item["isArchived"]:
            continue
        if content["__typename"] == "Issue":
            if content["state"] not in {"OPEN", "CLOSED"}:
                raise ValueError("Unexpected issue state")
            labels = connection(
                """query($id:ID!,$cursor:String){node(id:$id){... on Issue{labels(first:100,after:$cursor){
                  nodes{name}pageInfo{hasNextPage endCursor}}}}}""",
                ("node", "labels"),
                initial=content["labels"],
                id=content["id"],
            )
            content["labels"] = [label["name"] for label in labels]
        current = {}
        if item:
            values = connection(
                """query($id:ID!,$cursor:String){node(id:$id){... on ProjectV2Item{
                  fieldValues(first:100,after:$cursor){nodes{
                    ... on ProjectV2ItemFieldSingleSelectValue{name field{... on ProjectV2SingleSelectField{name}}}
                    ... on ProjectV2ItemFieldTextValue{text field{... on ProjectV2Field{name}}}
                  }pageInfo{hasNextPage endCursor}}}}}""",
                ("node", "fieldValues"),
                initial=item["fieldValues"],
                id=item["id"],
            )
            current = {
                v["field"]["name"]: v.get("name", v.get("text", ""))
                for v in values
                if v.get("field")
            }
        canonical = {
            **current,
            "Status": next(
                (k for k, v in status_names.items() if v == current.get("Status")),
                "Todo",
            ),
        }
        desired = delivery(
            content, canonical, linked.get(content["number"], []), releases, mainline
        )
        desired["Status"] = status_names[desired["Status"]]
        changes = {k: v for k, v in desired.items() if current.get(k, "") != v}
        if changes or not item:
            plan.append(
                {
                    "content": content["id"],
                    "item": item["id"] if item else None,
                    "number": content["number"],
                    "changes": changes,
                }
            )
    apply_plan(project, fields, plan, apply=apply)
    return plan


def main(argv=None):
    """Validate trusted context and reconcile; default to preview.

    Args:
        argv: Optional command-line argument list.

    Raises:
        ValueError: Credentials or supported event context are missing or invalid.
        RuntimeError: Synchronization fails.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    project = os.environ.get("ASTRBOT_PROJECT_ID", "").strip()
    if not project:
        print("Project synchronization disabled: ASTRBOT_PROJECT_ID is not set")
        return
    if not os.environ.get("ASTRBOT_PROJECT_TOKEN", "").strip():
        raise ValueError(
            "ASTRBOT_PROJECT_TOKEN is required when Project sync is enabled"
        )
    repository = os.environ.get("GITHUB_REPOSITORY", "AstrBotDevs/AstrBot")
    if repository != "AstrBotDevs/AstrBot":
        raise ValueError("Unexpected repository")
    subject = None
    event_name = os.environ.get("GITHUB_EVENT_NAME")
    if event_name:
        allowed = {
            "issues": {
                "opened",
                "reopened",
                "closed",
                "labeled",
                "unlabeled",
                "edited",
            },
            "pull_request_target": {
                "opened",
                "reopened",
                "closed",
                "edited",
                "synchronize",
                "ready_for_review",
                "converted_to_draft",
            },
            "release": {"published", "edited", "deleted"},
            "push": None,
            "schedule": None,
            "workflow_dispatch": None,
        }
        if event_name not in allowed:
            raise ValueError("Unsupported GitHub event")
        event = json.loads(
            Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")
        )
        if (
            event_name != "schedule"
            and event.get("repository", {}).get("full_name") != repository
        ):
            raise ValueError("Unexpected event repository")
        default_branch = (
            os.environ.get("ASTRBOT_DEFAULT_BRANCH")
            if event_name == "schedule"
            else event["repository"]["default_branch"]
        )
        default_ref = f"refs/heads/{default_branch}"
        if (
            event_name in {"push", "workflow_dispatch", "schedule"}
            and os.environ.get("GITHUB_REF") != default_ref
        ):
            raise ValueError("Push and manual runs require the default branch")
        if (
            allowed[event_name] is not None
            and event.get("action") not in allowed[event_name]
        ):
            raise ValueError("Unexpected lifecycle action")
        if event_name in {"issues", "pull_request_target"}:
            subject = event.get(
                "issue" if event_name == "issues" else "pull_request", {}
            ).get("number")
            if type(subject) is not int or subject <= 0:
                raise ValueError("Unexpected item number")
    status_names = dict(zip(STATUS_OPTIONS, STATUS_OPTIONS))
    overrides = json.loads(os.environ.get("ASTRBOT_PROJECT_STATUS_MAP") or "{}")
    if not isinstance(overrides, dict) or not overrides.keys() <= status_names.keys():
        raise ValueError("Invalid Status mapping keys")
    status_names.update(overrides)
    for key, env in {
        "Todo": "ASTRBOT_PROJECT_STATUS_OPEN",
        "Done": "ASTRBOT_PROJECT_STATUS_DONE",
    }.items():
        if os.environ.get(env):
            status_names[key] = os.environ[env]
    if any(
        not isinstance(v, str) or not v.strip() for v in status_names.values()
    ) or len(set(status_names.values())) != len(STATUS_OPTIONS):
        raise ValueError("Status names must be nonempty and distinct")
    plan = reconcile(
        project,
        repository,
        subject=subject,
        apply=args.apply,
        status_names=status_names,
    )
    print(
        json.dumps({"apply": args.apply, "changes": plan}, ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    main()
