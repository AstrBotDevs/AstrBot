import mcp

from astrbot.core.agent.evidence_store import AgentEvidenceStore
from astrbot.core.agent.supervisor import AgentSupervisor, completion_check_for_tool
from astrbot.core.agent.tool import FunctionTool, ToolOutcome


def test_supervisor_rejects_empty_and_allows_read_only_fallback() -> None:
    decision = AgentSupervisor.check(
        ToolOutcome(status="empty", retryable=True, error_code="empty_result"),
        required_evidence=["source"],
    )

    assert decision.complete is False
    assert decision.status == "empty"
    assert decision.fallback_allowed is True
    assert decision.missing_evidence == ["source"]


def test_tool_outcome_accepts_normalized_content_fields() -> None:
    outcome = ToolOutcome(
        status="success",
        content="gold: 700",
        structured_content={"source": "official"},
    )

    assert outcome.content == "gold: 700"
    assert outcome.structured_content["source"] == "official"


def test_supervisor_requires_evidence_before_success() -> None:
    outcome = ToolOutcome(
        status="success",
        result=mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text="ok")]
        ),
    )
    missing = AgentSupervisor.check(outcome, required_evidence=["source"])
    assert missing.complete is False
    assert missing.status == "partial"

    outcome.evidence_ids.append("source")
    complete = AgentSupervisor.check(outcome, required_evidence=["source"])
    assert complete.complete is True
    assert complete.status == "completed"


def test_supervisor_accepts_verified_direct_delivery_only() -> None:
    accepted = AgentSupervisor.check(
        ToolOutcome(status="direct_sent", terminal=True, side_effect_performed=True)
    )
    rejected = AgentSupervisor.check(
        ToolOutcome(status="direct_sent", terminal=True, side_effect_performed=False)
    )

    assert accepted.complete is True
    assert rejected.complete is False


def test_completion_contract_merges_tool_and_plan_requirements() -> None:
    tool = FunctionTool(
        name="lookup",
        description="Read a fact",
        parameters={"type": "object", "properties": {}},
        evidence_requirements=["source"],
    )
    outcome = ToolOutcome(status="success", evidence_ids=["source", "freshness"])
    decision = completion_check_for_tool(
        outcome,
        tool,
        {"completion_check": {"requires_evidence": ["freshness"]}},
    )

    assert decision.complete is True


def test_completion_contract_accepts_router_evidence_classes() -> None:
    tool = FunctionTool(
        name="lookup",
        description="Read a fact",
        parameters={"type": "object", "properties": {}},
    )
    outcome = ToolOutcome(status="success", evidence_ids=["source", "freshness"])
    decision = completion_check_for_tool(
        outcome,
        tool,
        {
            "required_evidence": ["source"],
            "completion_check": {"evidence_classes": ["freshness"]},
        },
    )

    assert decision.complete is True


def test_evidence_store_closes_one_thousand_synthetic_runs(tmp_path) -> None:
    store = AgentEvidenceStore(tmp_path / "runs.db")
    for index in range(1000):
        trace_id = f"trace-{index}"
        store.start_run(
            trace_id=trace_id,
            session_id="private:test",
            principal_id="qq:test",
            goal="synthetic acceptance run",
            route="fast",
        )
        store.finish_run(trace_id, "success", final_response="ok")

    with store._connect() as connection:
        running = connection.execute(
            "SELECT COUNT(*) FROM agent_runs WHERE status = 'running'"
        ).fetchone()[0]
    assert running == 0
