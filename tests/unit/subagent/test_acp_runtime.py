"""Exercise the ACP runtime through a real stdio peer and the subagent tools."""

import asyncio
import json
import sys

import pytest
import pytest_asyncio

from astrbot.core.acp_agent_runtime import AcpAgentRuntime
from astrbot.core.agent.input import PlainInput
from astrbot.core.agent.runtime import (
    AgentInput,
    AgentPermissions,
    AgentRole,
    TurnStatus,
)
from astrbot.core.astr_agent_runtime.tools.subagent import SpawnAgentTool
from astrbot.dashboard.services.agent_config_service import AgentConfigService

# The peer writes its remote ID to the workspace so session/load must restore it.
ACP_PEER = """
import json
import sys
from pathlib import Path
from uuid import uuid4

def send(message):
    print(json.dumps({"jsonrpc": "2.0", **message}), flush=True)

pending = None
for line in sys.stdin:
    request = json.loads(line)
    method = request["method"]
    params = request.get("params", {})
    request_id = request.get("id")
    if method == "initialize":
        result = {"protocolVersion": 1, "agentCapabilities": {"loadSession": True}}
    elif method == "session/new":
        session_id = uuid4().hex
        Path(session_id).write_text("0")
        result = {"sessionId": session_id}
    elif method == "session/load":
        session_id = params["sessionId"]
        assert Path(session_id).is_file()
        send({"method": "session/update", "params": {
            "sessionId": session_id,
            "update": {"sessionUpdate": "agent_message_chunk",
                       "content": {"type": "text", "text": "old reply"}}
        }})
        result = {}
    elif method == "session/prompt":
        session_id = params["sessionId"]
        text = params["prompt"][0]["text"]
        if text == "request approval":
            send({
                "id": "permission",
                "method": "session/request_permission",
                "params": {
                    "sessionId": session_id,
                    "toolCall": {"toolCallId": "tool"},
                    "options": [
                        {"optionId": "approve", "name": "Approve", "kind": "allow_once"},
                        {"optionId": "reject", "name": "Reject", "kind": "reject_once"},
                    ],
                },
            })
            permission = json.loads(sys.stdin.readline())
            assert permission["result"]["outcome"]["optionId"] == "reject", permission
        state = Path(session_id)
        count = int(state.read_text()) + 1
        state.write_text(str(count))
        for kind, part in [
            ("agent_thought_chunk", "Thinking"),
            ("agent_message_chunk", f"{count}: "),
            ("agent_message_chunk", text),
        ]:
            send({"method": "session/update", "params": {
                "sessionId": session_id,
                "update": {"sessionUpdate": kind,
                           "content": {"type": "text", "text": part}}
            }})
        if text == "block":
            pending = request_id
            continue
        result = {"stopReason": "end_turn"}
    elif method == "session/cancel":
        send({"id": pending, "result": {"stopReason": "cancelled"}})
        pending = None
        continue
    else:
        raise AssertionError(method)
    send({"id": request_id, "result": result})
"""


@pytest_asyncio.fixture
async def acp_worker(environment, tmp_path):
    """Register a real ACP stdio launcher backed by temporary storage."""
    peer = tmp_path / "peer.py"
    peer.write_text(ACP_PEER, encoding="utf-8")
    launchers = tmp_path / "acp_agents.json"
    launchers.write_text(
        json.dumps(
            {
                "test-peer": {
                    "command": sys.executable,
                    "args": [str(peer)],
                    "cwd": str(tmp_path),
                }
            }
        ),
        encoding="utf-8",
    )
    runtime = AcpAgentRuntime(environment.db, launchers)
    environment.context.agent.register_runtime("acp", runtime)
    try:
        yield runtime, launchers
    finally:
        await environment.runtimes["acp"].close()


@pytest.mark.asyncio
async def test_acp_config_spawn_and_restore(environment, acp_worker):
    """A configured specialized agent retains its ACP session across restarts."""
    env = environment
    runtime, launchers = acp_worker
    configs = AgentConfigService(
        env.agent_configs, env.runtimes, env.context.astrbot_config_mgr
    )
    launchers.unlink()
    assert {
        "runtime": "acp",
        "config": {"command": "", "args": [], "cwd": None},
    } in configs.runtimes()
    with pytest.raises(ValueError, match="Invalid ACP configuration"):
        await configs.save(
            {"name": "Worker", "runtime": "acp"},
            dashboard_authenticated=True,
        )
    with pytest.raises(ValueError, match="working directory must be absolute"):
        await configs.save(
            {
                "name": "Worker",
                "runtime": "acp",
                "config": {"command": sys.executable, "cwd": "relative"},
            },
            dashboard_authenticated=True,
        )
    configured = await configs.save(
        {
            "name": "Worker",
            "runtime": "acp",
            "config": {
                "command": sys.executable,
                "args": [str(launchers.with_name("peer.py"))],
                "cwd": str(launchers.parent),
            },
        },
        dashboard_authenticated=True,
    )
    config_id = configured["config_id"]
    env.config["config_ids"].append(config_id)
    messages = [{"type": "plain", "text": "First"}]

    with pytest.raises(ValueError, match="require an administrator"):
        await SpawnAgentTool().call(env.wrapper, messages, config_id=config_id)

    env.root.permissions = AgentPermissions(AgentRole.ADMIN)
    spawned = json.loads(
        await SpawnAgentTool().call(env.wrapper, messages, config_id=config_id)
    )
    agent_id = spawned["agent_id"]
    await env.service.wait(env.root, [agent_id], 5000, "all")
    agent = env.store.get(agent_id, env.scope)
    assert agent.turns[0].result == "1: First"

    await runtime.close()
    restored = AcpAgentRuntime(env.db, launchers)
    env.runtimes["acp"] = restored
    with pytest.raises(ValueError, match="different message origin"):
        await restored.open_session(
            "wrong", session_id=agent.conversation_id, options={"profile": "subagent"}
        )

    await env.service.send(env.root, agent_id, [{"type": "plain", "text": "Second"}])
    await env.service.wait(env.root, [agent_id], 5000, "all")
    assert agent.turns[1].result == "2: Second"
    session = await restored.open_session(
        env.scope.umo, session_id=agent.conversation_id, options={"profile": "subagent"}
    )
    assert await session.history() == [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "1: First"},
        {"role": "user", "content": "Second"},
        {"role": "assistant", "content": "2: Second"},
    ]


@pytest.mark.asyncio
async def test_acp_cancel_and_permission_on_follow_up(environment, acp_worker):
    """Cancellation stays on the ACP session and each turn checks its caller."""
    runtime, _ = acp_worker
    env = environment
    admin = AgentPermissions(AgentRole.ADMIN)
    initial = AgentInput(env.event, admin, [PlainInput(text="block")])
    session = await runtime.open_session(
        env.scope.umo,
        options={
            "profile": "subagent",
            "config": {"launcher": "test-peer"},
        },
        input=initial,
    )

    denied = await session.run_turn(
        AgentInput(env.event, AgentPermissions(), initial.content)
    )
    assert (await denied.result()).error.code == "acp_permission_denied"
    turn = await session.run_turn(initial)
    async with asyncio.timeout(5):
        async for event in turn.events():
            if event.type == "text.delta":
                break
        await turn.cancel()
    assert (await turn.result()).status == TurnStatus.CANCELLED

    follow_up = await session.run_turn(
        AgentInput(env.event, admin, [PlainInput(text="request approval")])
    )
    assert (await asyncio.wait_for(follow_up.result(), 5)).text == "2: request approval"
