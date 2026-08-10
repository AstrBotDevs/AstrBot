#!/usr/bin/env python3
"""Maintain the repository's append-only upstream decision ledger."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DISPOSITIONS = {"cherry-pick", "adapt", "skip", "replay", "revisit"}
STATUSES = {"active", "superseded", "deferred"}
EVENT_TYPES = {"upsert", "delete"}


class LedgerError(ValueError):
    """Raised for invalid ledger input or state."""


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_sha(value: str) -> str:
    value = value.strip().lower()
    if not SHA_RE.fullmatch(value):
        raise LedgerError(f"expected a full 40-character SHA: {value!r}")
    return value


def normalize_list(values: Iterable[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        for item in value.split(","):
            item = item.strip()
            if item and item not in result:
                result.append(item)
    return result


def validate_event(event: Any, *, line_number: int | None = None) -> None:
    where = f" on line {line_number}" if line_number else ""
    if not isinstance(event, dict):
        raise LedgerError(f"ledger event{where} must be a JSON object")
    if event.get("schema_version") != 1:
        raise LedgerError(f"unsupported schema_version{where}")
    if event.get("event_type") not in EVENT_TYPES:
        raise LedgerError(f"invalid event_type{where}")
    try:
        normalize_sha(str(event["upstream_commit"]))
    except KeyError as exc:
        raise LedgerError(f"missing upstream_commit{where}") from exc
    recorded = event.get("recorded_at_utc")
    if not isinstance(recorded, str) or not ISO_RE.fullmatch(recorded):
        raise LedgerError(f"recorded_at_utc must be UTC ISO format{where}")
    if not isinstance(event.get("revision"), int) or event["revision"] < 1:
        raise LedgerError(f"revision must be a positive integer{where}")
    if event["event_type"] == "delete":
        if not str(event.get("reason", "")).strip():
            raise LedgerError(f"delete events require reason{where}")
        return
    if not isinstance(event.get("record_id"), str) or not event["record_id"]:
        raise LedgerError(f"upsert events require record_id{where}")
    if event.get("disposition") not in DISPOSITIONS:
        raise LedgerError(f"invalid disposition{where}")
    if event.get("status", "active") not in STATUSES:
        raise LedgerError(f"invalid status{where}")
    if not str(event.get("summary", "")).strip():
        raise LedgerError(f"upsert events require summary{where}")
    for key in (
        "source_pr",
        "reason_codes",
        "affected_paths",
        "integration_commits",
        "tests",
        "supersedes",
    ):
        if key in event and (
            not isinstance(event[key], list)
            or not all(isinstance(x, str) for x in event[key])
        ):
            raise LedgerError(f"{key} must be a string array{where}")
    for key in ("source_pr", "reason_codes", "affected_paths", "tests", "supersedes"):
        for value in event.get(key, []):
            if not value.strip():
                raise LedgerError(f"{key} cannot contain empty values{where}")
    for value in event.get("integration_commits", []):
        normalize_sha(value)


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LedgerError(f"invalid JSON on line {line_number}: {exc}") from exc
            validate_event(event, line_number=line_number)
            events.append(event)
    validate_revisions(events)
    return events


def validate_revisions(events: list[dict[str, Any]]) -> None:
    revisions: dict[str, int] = {}
    record_ids: set[str] = set()
    for event in events:
        commit = event["upstream_commit"]
        revision = event["revision"]
        expected = revisions.get(commit, 0) + 1
        if revision != expected:
            raise LedgerError(
                f"revision gap for {commit}: expected {expected}, got {revision}"
            )
        revisions[commit] = revision
        record_id = event.get("record_id")
        if record_id:
            if record_id in record_ids:
                raise LedgerError(f"duplicate record_id: {record_id}")
            record_ids.add(record_id)


def latest_by_commit(events: list[dict[str, Any]]) -> dict[str, dict[str, Any] | None]:
    latest: dict[str, dict[str, Any] | None] = {}
    for event in events:
        latest[event["upstream_commit"]] = (
            None if event["event_type"] == "delete" else event
        )
    return latest


def append_event(path: Path, event: dict[str, Any]) -> None:
    validate_event(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def next_revision(events: list[dict[str, Any]], commit: str) -> int:
    return (
        max(
            (
                event["revision"]
                for event in events
                if event["upstream_commit"] == commit
            ),
            default=0,
        )
        + 1
    )


def output(value: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    elif isinstance(value, list):
        for item in value:
            print(json.dumps(item, ensure_ascii=False, sort_keys=True))
    elif isinstance(value, dict):
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(value)


def common_record_args(
    parser: argparse.ArgumentParser, *, required: bool, preserve_defaults: bool = False
) -> None:
    parser.add_argument("--commit", required=True, help="full upstream commit SHA")
    parser.add_argument(
        "--disposition", choices=sorted(DISPOSITIONS), required=required
    )
    parser.add_argument("--summary", required=required)
    optional_default = None if preserve_defaults else []
    text_default = None if preserve_defaults else ""
    parser.add_argument(
        "--status",
        choices=sorted(STATUSES),
        default=None if preserve_defaults else "active",
    )
    parser.add_argument("--source-pr", action="append", default=optional_default)
    parser.add_argument("--reason-code", action="append", default=optional_default)
    parser.add_argument(
        "--path", action="append", dest="affected_paths", default=optional_default
    )
    parser.add_argument(
        "--integration-commit", action="append", default=optional_default
    )
    parser.add_argument("--test", action="append", default=optional_default)
    parser.add_argument("--supersedes", action="append", default=optional_default)
    parser.add_argument("--fork-adaptation", default=text_default)
    parser.add_argument("--revisit-when", default=text_default)
    parser.add_argument("--notes", default=text_default)
    parser.add_argument("--source", default="manual")
    parser.add_argument("--recorded-at-utc", default=None)


def make_upsert(
    args: argparse.Namespace, events: list[dict[str, Any]], operation: str
) -> dict[str, Any]:
    commit = normalize_sha(args.commit)
    recorded = args.recorded_at_utc or now_utc()
    if not ISO_RE.fullmatch(recorded):
        raise LedgerError("--recorded-at-utc must use YYYY-MM-DDTHH:MM:SSZ")
    revision = next_revision(events, commit)
    event: dict[str, Any] = {
        "schema_version": 1,
        "event_type": "upsert",
        "operation": operation,
        "record_id": f"{recorded}-{commit[:12]}-{revision}",
        "upstream_commit": commit,
        "revision": revision,
        "recorded_at_utc": recorded,
        "source": args.source,
        "disposition": args.disposition,
        "status": args.status,
        "summary": args.summary.strip(),
    }
    optional = {
        "source_pr": normalize_list(args.source_pr),
        "reason_codes": normalize_list(args.reason_code),
        "affected_paths": normalize_list(args.affected_paths),
        "integration_commits": [
            normalize_sha(x) for x in normalize_list(args.integration_commit)
        ],
        "tests": normalize_list(args.test),
        "supersedes": [normalize_sha(x) for x in normalize_list(args.supersedes)],
    }
    event.update({key: value for key, value in optional.items() if value})
    for key in ("fork_adaptation", "revisit_when", "notes"):
        if getattr(args, key):
            event[key] = getattr(args, key).strip()
    return event


def git_log_records(repo: Path, revision_range: str) -> list[dict[str, Any]]:
    command = [
        "git",
        "-C",
        str(repo),
        "log",
        "--reverse",
        "--format=%H%x1f%B%x1e",
        revision_range,
    ]
    try:
        raw = subprocess.run(command, check=True, capture_output=True, text=True).stdout
    except subprocess.CalledProcessError as exc:
        raise LedgerError(exc.stderr.strip() or "git log failed") from exc
    records: list[dict[str, Any]] = []
    for chunk in raw.split("\x1e"):
        if "\x1f" not in chunk:
            continue
        commit, body = chunk.split("\x1f", 1)
        upstream_match = re.search(
            r"(?im)^\s*upstream(?: commit)?\s*:\s*([0-9a-f]{40})\b", body
        )
        if not upstream_match:
            continue
        classification = re.search(r"(?im)^\s*classification\s*:\s*([^\s]+)", body)
        method = re.search(r"(?im)^\s*method\s*:\s*([^\s]+)", body)
        source_pr = re.search(r"(?im)^\s*source pr\s*:\s*(.+?)\s*$", body)
        subject = body.strip().splitlines()[0] if body.strip() else commit
        disposition = classification.group(1).lower() if classification else "revisit"
        if disposition not in DISPOSITIONS:
            disposition = "revisit"
        fork_deviations = extract_section(body, "Fork deviations")
        tests = [
            line.lstrip("- ").strip()
            for line in extract_section(body, "Tests").splitlines()
            if line.lstrip().startswith("-")
        ]
        reason_codes = infer_reason_codes(body)
        records.append(
            {
                "git_commit": commit,
                "upstream_commit": upstream_match.group(1).lower(),
                "source_pr": normalize_list([source_pr.group(1)]) if source_pr else [],
                "disposition": disposition,
                "method": method.group(1) if method else "inferred",
                "summary": subject,
                "fork_deviations": fork_deviations,
                "reason_codes": reason_codes,
                "tests": tests,
            }
        )
    return records


def extract_section(body: str, heading: str) -> str:
    lines = body.splitlines()
    target = heading.casefold() + ":"
    start = next(
        (
            index + 1
            for index, line in enumerate(lines)
            if line.strip().casefold() == target
        ),
        None,
    )
    if start is None:
        return ""
    end = len(lines)
    for index in range(start, len(lines)):
        line = lines[index].strip()
        if (
            line
            and not line.startswith("-")
            and re.fullmatch(r"[A-Za-z][A-Za-z ]+:", line)
        ):
            end = index
            break
    return "\n".join(lines[start:end]).strip()


def infer_reason_codes(body: str) -> list[str]:
    lowered = body.casefold()
    matches = (
        ("security", ("security", "redact", "credential", "token")),
        ("openapi", ("openapi", "generated client")),
        ("generated-model", ("generated model", "codegen", "napcat")),
        ("docs-scope", ("bilingual", "documentation", "docs/")),
        ("toolchain", ("uv.lock", "python 3.14", "dependency")),
    )
    return [code for code, terms in matches if any(term in lowered for term in terms)]


def command_init(args: argparse.Namespace) -> None:
    if args.file.exists() and args.file.stat().st_size:
        raise LedgerError(f"ledger already exists and is non-empty: {args.file}")
    args.file.parent.mkdir(parents=True, exist_ok=True)
    args.file.touch(exist_ok=True)
    print(args.file)


def command_add_or_update(args: argparse.Namespace, operation: str) -> None:
    events = load_events(args.file)
    commit = normalize_sha(args.commit)
    current = latest_by_commit(events).get(commit)
    if operation == "add" and current is not None:
        raise LedgerError(f"active decision already exists for {commit}; use update")
    if operation == "update" and current is None:
        raise LedgerError(f"no active decision exists for {commit}; use add")
    if operation == "update":
        # Updates are patches: preserve fields that were not supplied on the
        # command line so a quick rationale correction cannot erase paths,
        # provenance, tests, or adaptation notes.
        for attribute, key in (
            ("disposition", "disposition"),
            ("summary", "summary"),
            ("status", "status"),
            ("source_pr", "source_pr"),
            ("reason_code", "reason_codes"),
            ("affected_paths", "affected_paths"),
            ("integration_commit", "integration_commits"),
            ("test", "tests"),
            ("supersedes", "supersedes"),
            ("fork_adaptation", "fork_adaptation"),
            ("revisit_when", "revisit_when"),
            ("notes", "notes"),
        ):
            if getattr(args, attribute) is None:
                setattr(
                    args,
                    attribute,
                    current.get(
                        key,
                        []
                        if attribute.endswith(
                            ("pr", "code", "paths", "commit", "test", "supersedes")
                        )
                        else "",
                    ),
                )
        if args.source == "manual" and current.get("source"):
            args.source = current["source"]
    event = make_upsert(args, events, operation)
    append_event(args.file, event)
    output(event, args.json)


def command_delete(args: argparse.Namespace) -> None:
    events = load_events(args.file)
    commit = normalize_sha(args.commit)
    if latest_by_commit(events).get(commit) is None:
        raise LedgerError(f"no active decision exists for {commit}")
    event = {
        "schema_version": 1,
        "event_type": "delete",
        "operation": "delete",
        "upstream_commit": commit,
        "revision": next_revision(events, commit),
        "recorded_at_utc": args.recorded_at_utc or now_utc(),
        "source": args.source,
        "reason": args.reason.strip(),
    }
    append_event(args.file, event)
    output(event, args.json)


def command_get(args: argparse.Namespace) -> None:
    events = load_events(args.file)
    commit = normalize_sha(args.commit)
    matches = [event for event in events if event["upstream_commit"] == commit]
    if not args.history:
        current = latest_by_commit(events).get(commit)
        if current is None:
            raise LedgerError(f"no active decision exists for {commit}")
        matches = [current]
    output(matches, args.json)


def command_list(args: argparse.Namespace) -> None:
    events = load_events(args.file)
    if args.all:
        records: list[dict[str, Any] | None] = events
    else:
        records = [
            event for event in latest_by_commit(events).values() if event is not None
        ]
    query = args.query.lower() if args.query else None
    filtered = []
    for record in records:
        if record is None:
            continue
        if args.disposition and record.get("disposition") != args.disposition:
            continue
        if args.status and record.get("status") != args.status:
            continue
        if args.commit_prefix and not record["upstream_commit"].startswith(
            args.commit_prefix.lower()
        ):
            continue
        if (
            args.source_pr
            and args.source_pr.lower()
            not in " ".join(record.get("source_pr", [])).lower()
        ):
            continue
        if args.path and not any(
            args.path.lower() in path.lower()
            for path in record.get("affected_paths", [])
        ):
            continue
        if query and query not in json.dumps(record, ensure_ascii=False).lower():
            continue
        filtered.append(record)
    filtered.sort(key=lambda record: (record["upstream_commit"], record["revision"]))
    output(filtered, args.json)


def command_validate(args: argparse.Namespace) -> None:
    events = load_events(args.file)
    print(
        f"valid: {args.file} ({len(events)} events, {len(latest_by_commit(events))} commits)"
    )


def command_import_git(args: argparse.Namespace) -> None:
    events = load_events(args.file)
    existing = latest_by_commit(events)
    imported: list[dict[str, Any]] = []
    for item in git_log_records(args.repo, args.range):
        if item["upstream_commit"] in existing:
            continue
        namespace = argparse.Namespace(
            commit=item["upstream_commit"],
            disposition=item["disposition"],
            summary=item["summary"],
            status="active",
            source_pr=item["source_pr"],
            reason_code=item["reason_codes"],
            affected_paths=[],
            integration_commit=[item["git_commit"]],
            test=item["tests"],
            supersedes=[],
            fork_adaptation=item["fork_deviations"],
            revisit_when="",
            notes=(
                "Imported from Git commit "
                f"{item['git_commit']}; review inferred fields before relying on them."
            ),
            source="git-inferred",
            recorded_at_utc=args.recorded_at_utc,
        )
        event = make_upsert(namespace, events + imported, "import")
        imported.append(event)
        existing[item["upstream_commit"]] = event
    if not args.dry_run:
        for event in imported:
            append_event(args.file, event)
    output(
        {"imported": len(imported), "dry_run": args.dry_run, "records": imported},
        args.json,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=Path("upstream-decisions.jsonl"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create an empty ledger")
    init.set_defaults(handler=command_init)

    for name in ("add", "update"):
        command = subparsers.add_parser(name, help=f"{name} a decision")
        common_record_args(
            command, required=name == "add", preserve_defaults=name == "update"
        )
        command.add_argument("--json", action="store_true")
        command.set_defaults(
            handler=lambda args, operation=name: command_add_or_update(args, operation)
        )

    delete = subparsers.add_parser("delete", help="append a tombstone; keep history")
    delete.add_argument("--commit", required=True)
    delete.add_argument("--reason", required=True)
    delete.add_argument("--source", default="manual")
    delete.add_argument("--recorded-at-utc", default=None)
    delete.add_argument("--json", action="store_true")
    delete.set_defaults(handler=command_delete)

    get = subparsers.add_parser("get", help="get the current decision or its history")
    get.add_argument("--commit", required=True)
    get.add_argument("--history", action="store_true")
    get.add_argument("--json", action="store_true")
    get.set_defaults(handler=command_get)

    listing = subparsers.add_parser("list", help="list and filter current decisions")
    listing.add_argument(
        "--all", action="store_true", help="include superseded and tombstone events"
    )
    listing.add_argument("--disposition", choices=sorted(DISPOSITIONS))
    listing.add_argument("--status", choices=sorted(STATUSES))
    listing.add_argument("--commit-prefix")
    listing.add_argument("--source-pr")
    listing.add_argument("--path")
    listing.add_argument("--query")
    listing.add_argument("--json", action="store_true")
    listing.set_defaults(handler=command_list)

    validate = subparsers.add_parser(
        "validate", help="validate ledger JSONL and revisions"
    )
    validate.set_defaults(handler=command_validate)

    importer = subparsers.add_parser(
        "import-git", help="import structured sync commit messages"
    )
    importer.add_argument("--repo", type=Path, default=Path("."))
    importer.add_argument(
        "--range", required=True, help="git revision range, for example A..B"
    )
    importer.add_argument("--recorded-at-utc", default=None)
    importer.add_argument("--dry-run", action="store_true")
    importer.add_argument("--json", action="store_true")
    importer.set_defaults(handler=command_import_git)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.handler(args)
    except (LedgerError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
