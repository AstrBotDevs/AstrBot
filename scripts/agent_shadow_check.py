"""Evaluate the Agent Control Plane shadow window without exposing message text.

The command is intentionally conservative: an empty or incomplete window is
reported as ``insufficient_data`` instead of being treated as a passing run.
It reads only the hash-based audit stores and never executes a plugin, model,
SQL supplied by a user, or a pending operation.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTROL_DB = ROOT / "data/plugin_data/astrbot_plugin_semantic_router/agent_control.db"
EVIDENCE_DB = ROOT / "data/agent_evidence.db"
ROLLOUT_MARKER = (
    ROOT
    / "data/plugin_data/astrbot_plugin_semantic_router/.unified_tool_shadow_rollout_epoch"
)


def _connect(path: Path) -> sqlite3.Connection | None:
    """Open an audit database when it exists.

    Args:
        path: Local audit database path.

    Returns:
        A row-producing SQLite connection, or ``None`` when the database is
        not present yet.
    """

    if not path.exists():
        return None
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _count(connection: sqlite3.Connection, table: str, since: float) -> int:
    """Count rows in a fixed, internal audit table after a timestamp."""

    allowed = {
        "decision_audit",
        "tool_audit",
        "message_admission_audit",
        "agent_runs",
        "tool_attempts",
        "evidence_records",
    }
    if table not in allowed:
        raise ValueError(f"unsupported audit table: {table}")
    return int(
        connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE created_at >= ?"  # noqa: S608
            if table not in {"tool_attempts", "evidence_records"}
            else f"SELECT COUNT(*) FROM {table} WHERE started_at >= ?"
            if table == "tool_attempts"
            else f"SELECT COUNT(*) FROM {table} WHERE captured_at >= ?",
            (since,),
        ).fetchone()[0]
    )


def collect_shadow_metrics(
    *,
    hours: float = 24.0,
    control_db: Path = CONTROL_DB,
    evidence_db: Path = EVIDENCE_DB,
    rollout_marker: Path | None = None,
) -> dict[str, Any]:
    """Collect conservative metrics for one shadow observation window.

    Args:
        hours: Observation window length, bounded to 1--168 hours.
        control_db: Control-plane SQLite database path.
        evidence_db: Hash-only Agent evidence database path.
        rollout_marker: Optional deployment timestamp file. Older audit rows
            are excluded when this marker exists.

    Returns:
        JSON-safe metrics. Values under ``acceptance`` are ``pass``,
        ``fail`` or ``insufficient_data``.
    """

    bounded_hours = max(1.0, min(float(hours), 168.0))
    since = time.time() - bounded_hours * 3600
    marker = rollout_marker or control_db.parent / ".unified_tool_shadow_rollout_epoch"
    if marker.exists():
        try:
            since = max(since, float(marker.read_text(encoding="ascii").strip()))
        except (OSError, ValueError):
            result_marker_note = "invalid_rollout_marker"
        else:
            result_marker_note = ""
    else:
        result_marker_note = ""
    result: dict[str, Any] = {
        "window_hours": bounded_hours,
        "since": since,
        "acceptance": {},
        "notes": [],
    }
    if result_marker_note:
        result["notes"].append(result_marker_note)
    result["rollout_since"] = since
    control = _connect(control_db)
    evidence = _connect(evidence_db)
    try:
        if control is None:
            result["notes"].append("control_plane_database_missing")
            result["acceptance"]["shadow_events"] = "insufficient_data"
            return result

        decisions = _count(control, "decision_audit", since)
        tool_rows = control.execute(
            """
            SELECT status, COUNT(*) AS count FROM tool_audit
            WHERE created_at >= ? GROUP BY status
            """,
            (since,),
        ).fetchall()
        admissions = control.execute(
            """
            SELECT outcome, COUNT(*) AS count FROM message_admission_audit
            WHERE created_at >= ? GROUP BY outcome
            """,
            (since,),
        ).fetchall()
        capabilities = control.execute(
            "SELECT status, COUNT(*) AS count FROM capability_catalog GROUP BY status"
        ).fetchall()
        trace_columns = {
            str(row[1])
            for row in control.execute("PRAGMA table_info(decision_audit)").fetchall()
        }
        linked_decisions = 0
        if "trace_id" in trace_columns:
            linked_decisions = int(
                control.execute(
                    """
                    SELECT COUNT(*) FROM decision_audit
                    WHERE created_at >= ? AND trace_id <> ''
                    """,
                    (since,),
                ).fetchone()[0]
            )
        result["decisions"] = decisions
        result["tools"] = {str(row["status"]): int(row["count"]) for row in tool_rows}
        result["admissions"] = {
            str(row["outcome"]): int(row["count"]) for row in admissions
        }
        result["capabilities"] = {
            str(row["status"]): int(row["count"]) for row in capabilities
        }
        result["trace_link_rate"] = linked_decisions / decisions if decisions else None

        tool_total = sum(result["tools"].values())
        failed_tools = sum(
            count
            for status, count in result["tools"].items()
            if status in {"failed", "empty", "timeout"}
        )
        result["tool_failure_rate"] = failed_tools / tool_total if tool_total else None
        result["acceptance"]["shadow_events"] = (
            "pass" if decisions > 0 else "insufficient_data"
        )
        result["acceptance"]["trace_linkage"] = (
            "pass"
            if decisions > 0 and linked_decisions == decisions
            else "fail"
            if decisions > 0
            else "insufficient_data"
        )
        result["acceptance"]["tool_failure_rate"] = (
            "pass"
            if tool_total and failed_tools / tool_total <= 0.05
            else "fail"
            if tool_total
            else "insufficient_data"
        )

        decision_columns = {
            str(row[1])
            for row in control.execute("PRAGMA table_info(decision_audit)").fetchall()
        }
        if (
            "candidate_tools" in decision_columns
            and "tool_required" in decision_columns
        ):
            planned_rows = control.execute(
                """
                SELECT trace_id, allowed_tools, candidate_tools, tool_required
                FROM decision_audit
                WHERE created_at >= ? AND tool_required = 1 AND trace_id <> ''
                """,
                (since,),
            ).fetchall()
            matched = 0
            for decision in planned_rows:
                try:
                    candidates = json.loads(
                        decision["candidate_tools"] or decision["allowed_tools"] or "[]"
                    )
                except (TypeError, ValueError):
                    candidates = []
                if not isinstance(candidates, list):
                    candidates = []
                candidates = [str(item) for item in candidates[:3] if str(item)]
                actual = (
                    control.execute(
                        """
                    SELECT 1 FROM tool_audit
                    WHERE trace_id = ? AND created_at >= ?
                      AND status IN ('authorized', 'completed', 'error', 'shadow_observed')
                      AND tool_name IN ({}) LIMIT 1
                    """.format(",".join("?" for _ in candidates)),
                        (str(decision["trace_id"]), since, *candidates),
                    ).fetchone()
                    if candidates
                    else None
                )
                if actual:
                    matched += 1
            planned_count = len(planned_rows)
            result["top3_tool_recall"] = (
                matched / planned_count if planned_count else None
            )
            result["acceptance"]["top3_tool_recall"] = (
                "pass"
                if planned_count and matched / planned_count >= 0.95
                else "fail"
                if planned_count
                else "insufficient_data"
            )
        else:
            result["top3_tool_recall"] = None
            result["acceptance"]["top3_tool_recall"] = "insufficient_data"
            result["notes"].append("top3_tool_recall_requires_plan_columns")

        delivery_table = {
            str(row[1])
            for row in control.execute(
                "PRAGMA table_info(message_delivery_audit)"
            ).fetchall()
        }
        if {"status", "duplicate"}.issubset(delivery_table):
            delivery_rows = control.execute(
                """
                SELECT status, duplicate FROM message_delivery_audit
                WHERE created_at >= ?
                """,
                (since,),
            ).fetchall()
            empty_or_failed = sum(
                1 for row in delivery_rows if str(row["status"]) in {"empty", "failed"}
            )
            duplicates = sum(1 for row in delivery_rows if int(row["duplicate"] or 0))
            result["delivery_rows"] = len(delivery_rows)
            result["empty_replies"] = empty_or_failed
            result["duplicate_replies"] = duplicates
            result["acceptance"]["duplicate_or_empty_replies"] = (
                "pass"
                if delivery_rows and not empty_or_failed and not duplicates
                else "fail"
                if delivery_rows
                else "insufficient_data"
            )
        else:
            result["acceptance"]["duplicate_or_empty_replies"] = "insufficient_data"
            result["notes"].append("platform_send_audit_table_missing")

        if evidence is None:
            result["acceptance"]["evidence_chain"] = "insufficient_data"
        else:
            attempts = evidence.execute(
                """
                SELECT attempt_id, status FROM tool_attempts
                WHERE started_at >= ?
                """,
                (since,),
            ).fetchall()
            successful = [
                row["attempt_id"]
                for row in attempts
                if row["status"] in {"success", "direct_sent"}
            ]
            if successful:
                placeholders = ",".join("?" for _ in successful)
                evidence_count = int(
                    evidence.execute(
                        f"SELECT COUNT(DISTINCT attempt_id) FROM evidence_records "
                        f"WHERE captured_at >= ? AND attempt_id IN ({placeholders})",  # noqa: S608
                        (since, *successful),
                    ).fetchone()[0]
                )
                result["evidence_chain_rate"] = evidence_count / len(successful)
                result["acceptance"]["evidence_chain"] = (
                    "pass" if evidence_count == len(successful) else "fail"
                )
            else:
                result["evidence_chain_rate"] = None
                result["acceptance"]["evidence_chain"] = "insufficient_data"
    finally:
        if control is not None:
            control.close()
        if evidence is not None:
            evidence.close()
    return result


def main() -> int:
    """Run the shadow audit and return a conservative process status."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--control-db", type=Path, default=CONTROL_DB)
    parser.add_argument("--evidence-db", type=Path, default=EVIDENCE_DB)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Recheck the same rolling shadow window until the watch duration elapses.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=60.0,
        help="Seconds between shadow checks when --watch is enabled.",
    )
    parser.add_argument(
        "--watch-duration-hours",
        type=float,
        default=24.0,
        help="How long --watch should observe before returning a final status.",
    )
    args = parser.parse_args()
    interval_seconds = max(10.0, min(float(args.interval_seconds), 3600.0))
    watch_duration_seconds = max(
        interval_seconds,
        min(float(args.watch_duration_hours), 168.0) * 3600.0,
    )
    watch_deadline = time.monotonic() + watch_duration_seconds
    metrics: dict[str, Any] = {}
    while True:
        metrics = collect_shadow_metrics(
            hours=args.hours,
            control_db=args.control_db,
            evidence_db=args.evidence_db,
        )
        if args.json:
            print(json.dumps(metrics, ensure_ascii=False, default=str), flush=True)
        else:
            print(f"Shadow window: {metrics['window_hours']:.1f}h")
            for key, value in metrics.get("acceptance", {}).items():
                print(f"{key}: {value}")
            print(f"decisions: {metrics.get('decisions', 0)}")
            print(f"tools: {metrics.get('tools', {})}")
            if metrics.get("notes"):
                print("notes: " + "; ".join(metrics["notes"]))

        if not args.watch or time.monotonic() >= watch_deadline:
            break
        time.sleep(min(interval_seconds, max(0.0, watch_deadline - time.monotonic())))

    statuses = set(metrics.get("acceptance", {}).values())
    if "fail" in statuses:
        return 1
    if "insufficient_data" in statuses:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
