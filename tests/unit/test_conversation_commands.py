from types import SimpleNamespace

import pytest

from astrbot.core.star.plugin_context import ConversationCapability


def _execution(
    *,
    session_get,
    session_remove,
    provider_config,
    agent_runner_type="deerflow",
):
    return SimpleNamespace(
        astrbot_config_mgr=SimpleNamespace(
            get_conf=lambda _umo: {
                "provider_settings": {
                    "agent_runner_type": agent_runner_type,
                    "deerflow_agent_runner_provider_id": "deerflow-runner",
                }
            }
        ),
        preferences=SimpleNamespace(
            session_get=session_get,
            session_remove=session_remove,
        ),
        provider_manager=SimpleNamespace(
            get_provider_config_by_id=lambda provider_id, merged=False: (
                provider_config if merged else {"id": provider_id}
            )
        ),
    )


@pytest.mark.asyncio
async def test_reset_session_state_deletes_deerflow_thread_before_local_state(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[object] = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        async def delete_thread(self, thread_id: str, timeout_s: float = 20):
            calls.append(("delete", thread_id, timeout_s))

        async def close(self):
            calls.append(("close",))

    async def fake_session_get(*args, **kwargs):
        _ = args, kwargs
        return "thread-123"

    async def fake_session_remove(umo, key):
        calls.append(("remove", "umo", umo, key))

    monkeypatch.setattr(
        "astrbot.core.agent.runners.deerflow.deerflow_api_client.DeerFlowAPIClient",
        FakeClient,
    )

    capability = ConversationCapability(
        _execution(
            session_get=fake_session_get,
            session_remove=fake_session_remove,
            provider_config={
                "id": "deerflow-runner",
                "deerflow_api_base": "http://127.0.0.1:2026",
                "deerflow_api_key": "token",
                "deerflow_auth_header": "",
                "proxy": "",
            },
        ),
        SimpleNamespace(),
        None,
    )
    await capability.reset_session_state("umo-1")

    assert ("delete", "thread-123", 20) in calls
    assert ("remove", "umo", "umo-1", "deerflow_thread_id") in calls
    assert calls.index(("delete", "thread-123", 20)) < calls.index(
        ("remove", "umo", "umo-1", "deerflow_thread_id")
    )


@pytest.mark.asyncio
async def test_reset_session_state_removes_local_state_when_deerflow_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[object] = []

    class FakeClient:
        def __init__(self, **kwargs):
            _ = kwargs

        async def delete_thread(self, thread_id: str, timeout_s: float = 20):
            _ = thread_id, timeout_s
            raise RuntimeError("gateway down")

        async def close(self):
            calls.append(("close",))

    async def fake_session_get(*args, **kwargs):
        _ = args, kwargs
        return "thread-456"

    async def fake_session_remove(umo, key):
        calls.append(("remove", "umo", umo, key))

    monkeypatch.setattr(
        "astrbot.core.agent.runners.deerflow.deerflow_api_client.DeerFlowAPIClient",
        FakeClient,
    )

    capability = ConversationCapability(
        _execution(
            session_get=fake_session_get,
            session_remove=fake_session_remove,
            provider_config={
                "id": "deerflow-runner",
                "deerflow_api_base": "http://127.0.0.1:2026",
                "deerflow_api_key": "",
                "deerflow_auth_header": "",
                "proxy": "",
            },
        ),
        SimpleNamespace(),
        None,
    )
    await capability.reset_session_state("umo-2")

    assert ("remove", "umo", "umo-2", "deerflow_thread_id") in calls


@pytest.mark.asyncio
async def test_reset_session_state_removes_local_state_when_deerflow_client_init_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[object] = []

    class FakeClient:
        def __init__(self, **kwargs):
            _ = kwargs
            raise RuntimeError("invalid deerflow config")

    async def fake_session_get(*args, **kwargs):
        _ = args, kwargs
        return "thread-789"

    async def fake_session_remove(umo, key):
        calls.append(("remove", "umo", umo, key))

    monkeypatch.setattr(
        "astrbot.core.agent.runners.deerflow.deerflow_api_client.DeerFlowAPIClient",
        FakeClient,
    )

    capability = ConversationCapability(
        _execution(
            session_get=fake_session_get,
            session_remove=fake_session_remove,
            provider_config={
                "id": "deerflow-runner",
                "deerflow_api_base": "http://127.0.0.1:2026",
                "deerflow_api_key": "",
                "deerflow_auth_header": "",
                "proxy": "",
            },
        ),
        SimpleNamespace(),
        None,
    )
    await capability.reset_session_state("umo-3")

    assert ("remove", "umo", "umo-3", "deerflow_thread_id") in calls
