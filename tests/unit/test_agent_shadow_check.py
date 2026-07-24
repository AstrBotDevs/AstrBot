import sqlite3
import time

from scripts.agent_shadow_check import collect_shadow_metrics


def _make_databases(tmp_path):
    control = tmp_path / "control.db"
    connection = sqlite3.connect(control)
    connection.executescript(
        """
        CREATE TABLE decision_audit (
            id INTEGER PRIMARY KEY,
            created_at REAL,
            trace_id TEXT
        );
        CREATE TABLE tool_audit (
            id INTEGER PRIMARY KEY,
            created_at REAL,
            status TEXT
        );
        CREATE TABLE message_admission_audit (
            id INTEGER PRIMARY KEY,
            created_at REAL,
            outcome TEXT
        );
        CREATE TABLE capability_catalog (status TEXT);
        """
    )
    now = time.time()
    connection.execute(
        "INSERT INTO decision_audit VALUES (1, ?, ?)", (now, "trace-test")
    )
    connection.execute("INSERT INTO tool_audit VALUES (1, ?, 'completed')", (now,))
    connection.execute(
        "INSERT INTO message_admission_audit VALUES (1, ?, 'admitted')", (now,)
    )
    connection.execute("INSERT INTO capability_catalog VALUES ('active')")
    connection.commit()
    connection.close()

    evidence = tmp_path / "evidence.db"
    connection = sqlite3.connect(evidence)
    connection.executescript(
        """
        CREATE TABLE tool_attempts (
            attempt_id TEXT PRIMARY KEY,
            status TEXT,
            started_at REAL
        );
        CREATE TABLE evidence_records (
            attempt_id TEXT,
            captured_at REAL
        );
        """
    )
    connection.execute(
        "INSERT INTO tool_attempts VALUES ('attempt-1', 'success', ?)", (now,)
    )
    connection.execute("INSERT INTO evidence_records VALUES ('attempt-1', ?)", (now,))
    connection.commit()
    connection.close()
    return control, evidence


def test_shadow_metrics_are_conservative_and_link_evidence(tmp_path) -> None:
    control, evidence = _make_databases(tmp_path)

    metrics = collect_shadow_metrics(
        hours=1,
        control_db=control,
        evidence_db=evidence,
    )

    assert metrics["acceptance"]["shadow_events"] == "pass"
    assert metrics["acceptance"]["trace_linkage"] == "pass"
    assert metrics["acceptance"]["evidence_chain"] == "pass"
    assert metrics["acceptance"]["top3_tool_recall"] == "insufficient_data"


def test_shadow_metrics_do_not_pass_without_events(tmp_path) -> None:
    metrics = collect_shadow_metrics(
        hours=1,
        control_db=tmp_path / "missing-control.db",
        evidence_db=tmp_path / "missing-evidence.db",
    )

    assert metrics["acceptance"]["shadow_events"] == "insufficient_data"


def test_shadow_metrics_use_plan_and_delivery_telemetry(tmp_path) -> None:
    control = tmp_path / "control.db"
    connection = sqlite3.connect(control)
    now = time.time()
    connection.executescript(
        """
        CREATE TABLE decision_audit (
            id INTEGER PRIMARY KEY,
            created_at REAL,
            trace_id TEXT,
            allowed_tools TEXT,
            candidate_tools TEXT,
            tool_required INTEGER
        );
        CREATE TABLE tool_audit (
            id INTEGER PRIMARY KEY,
            created_at REAL,
            trace_id TEXT,
            tool_name TEXT,
            status TEXT
        );
        CREATE TABLE message_admission_audit (
            id INTEGER PRIMARY KEY,
            created_at REAL,
            outcome TEXT
        );
        CREATE TABLE capability_catalog (status TEXT);
        CREATE TABLE message_delivery_audit (
            id INTEGER PRIMARY KEY,
            created_at REAL,
            status TEXT,
            duplicate INTEGER
        );
        """
    )
    connection.execute(
        "INSERT INTO decision_audit VALUES (1, ?, ?, ?, ?, 1)",
        (
            now,
            "trace-1",
            '["weather_lookup", "anysearch_search"]',
            '["weather_lookup", "anysearch_search"]',
        ),
    )
    connection.execute(
        "INSERT INTO tool_audit VALUES (1, ?, ?, ?, 'completed')",
        (now, "trace-1", "weather_lookup"),
    )
    connection.execute(
        "INSERT INTO message_admission_audit VALUES (1, ?, 'admitted')", (now,)
    )
    connection.execute("INSERT INTO capability_catalog VALUES ('active')")
    connection.execute(
        "INSERT INTO message_delivery_audit VALUES (1, ?, 'sent', 0)", (now,)
    )
    connection.commit()
    connection.close()

    metrics = collect_shadow_metrics(hours=1, control_db=control)

    assert metrics["acceptance"]["top3_tool_recall"] == "pass"
    assert metrics["acceptance"]["duplicate_or_empty_replies"] == "pass"
    assert metrics["top3_tool_recall"] == 1.0
