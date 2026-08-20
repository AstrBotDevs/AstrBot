from types import SimpleNamespace

import pytest

from astrbot.builtin_stars.builtin_commands.commands import (
    conversation as conversation_module,
)


@pytest.mark.asyncio
async def test_clear_third_party_agent_runner_state_deletes_deerflow_thread_before_local_state(
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

    context = SimpleNamespace(
        config=SimpleNamespace(
            get=lambda **kwargs: {
                "provider_settings": {
                    "deerflow_agent_runner_provider_id": "deerflow-runner"
                }
            }
        ),
        models=SimpleNamespace(
            configuration=lambda provider_id, merged=False: (
                {
                    "id": provider_id,
                    "deerflow_api_base": "http://127.0.0.1:2026",
                    "deerflow_api_key": "token",
                    "deerflow_auth_header": "",
                    "proxy": "",
                }
                if merged
                else {"id": provider_id}
            ),
        ),
        preferences=SimpleNamespace(
            session_get=fake_session_get, session_remove=fake_session_remove
        ),
    )

    monkeypatch.setattr(conversation_module, "DeerFlowAPIClient", FakeClient)

    await conversation_module._clear_third_party_agent_runner_state(
        context,
        "umo-1",
        conversation_module.DEERFLOW_PROVIDER_TYPE,
    )

    assert ("delete", "thread-123", 20) in calls
    assert (
        "remove",
        "umo",
        "umo-1",
        conversation_module.DEERFLOW_THREAD_ID_KEY,
    ) in calls
    assert calls.index(("delete", "thread-123", 20)) < calls.index(
        ("remove", "umo", "umo-1", conversation_module.DEERFLOW_THREAD_ID_KEY)
    )


@pytest.mark.asyncio
async def test_clear_third_party_agent_runner_state_removes_local_state_when_deerflow_cleanup_fails(
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

    context = SimpleNamespace(
        config=SimpleNamespace(
            get=lambda **kwargs: {
                "provider_settings": {
                    "deerflow_agent_runner_provider_id": "deerflow-runner"
                }
            }
        ),
        models=SimpleNamespace(
            configuration=lambda provider_id, merged=False: (
                {
                    "id": provider_id,
                    "deerflow_api_base": "http://127.0.0.1:2026",
                    "deerflow_api_key": "",
                    "deerflow_auth_header": "",
                    "proxy": "",
                }
                if merged
                else {"id": provider_id}
            ),
        ),
        preferences=SimpleNamespace(
            session_get=fake_session_get, session_remove=fake_session_remove
        ),
    )

    monkeypatch.setattr(conversation_module, "DeerFlowAPIClient", FakeClient)

    await conversation_module._clear_third_party_agent_runner_state(
        context,
        "umo-2",
        conversation_module.DEERFLOW_PROVIDER_TYPE,
    )

    assert (
        "remove",
        "umo",
        "umo-2",
        conversation_module.DEERFLOW_THREAD_ID_KEY,
    ) in calls


@pytest.mark.asyncio
async def test_clear_third_party_agent_runner_state_removes_local_state_when_deerflow_client_init_fails(
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

    context = SimpleNamespace(
        config=SimpleNamespace(
            get=lambda **kwargs: {
                "provider_settings": {
                    "deerflow_agent_runner_provider_id": "deerflow-runner"
                }
            }
        ),
        models=SimpleNamespace(
            configuration=lambda provider_id, merged=False: (
                {
                    "id": provider_id,
                    "deerflow_api_base": "http://127.0.0.1:2026",
                    "deerflow_api_key": "",
                    "deerflow_auth_header": "",
                    "proxy": "",
                }
                if merged
                else {"id": provider_id}
            ),
        ),
        preferences=SimpleNamespace(
            session_get=fake_session_get, session_remove=fake_session_remove
        ),
    )

    monkeypatch.setattr(conversation_module, "DeerFlowAPIClient", FakeClient)

    await conversation_module._clear_third_party_agent_runner_state(
        context,
        "umo-3",
        conversation_module.DEERFLOW_PROVIDER_TYPE,
    )

    assert (
        "remove",
        "umo",
        "umo-3",
        conversation_module.DEERFLOW_THREAD_ID_KEY,
    ) in calls
