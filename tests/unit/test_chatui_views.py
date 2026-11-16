"""Exercise view creation, isolated callbacks, persistence, and HTTP authorization."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI

from astrbot.api import chatui
from astrbot.core import chatui as core_views
from astrbot.core.chatui import ViewActionRequest, ViewError, ViewStore, resolve_view
from astrbot.core.message.components import (
    ButtonInteraction,
    Plain,
    UIInteraction,
    ViewContext,
)
from astrbot.core.pipeline.context_utils import call_handler
from astrbot.core.pipeline.process_stage.stage import ProcessStage
from astrbot.core.pipeline.waking_check.stage import WakingCheckStage
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.webchat.webchat_event import WebChatMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.filter.button_action import ButtonActionFilter
from astrbot.core.star.filter.ui_action import UIActionFilter
from astrbot.core.star.star import StarMetadata, star_map
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot.dashboard.api import chat as chat_routes
from astrbot.dashboard.api import plugins as plugin_routes
from astrbot.dashboard.api.auth import AuthContext
from astrbot.dashboard.services.chat_service import ChatService
from astrbot.dashboard.services.plugin_page_service import PluginPageService
from astrbot.dashboard.services.plugin_service import PluginService


@pytest.mark.asyncio
@pytest.mark.parametrize("with_pages", [False, True])
async def test_sidebar_plugin_list_excludes_chat_views(views, tmp_path, with_pages):
    _, _, plugin, _ = views
    plugin.root_dir_name = tmp_path.name
    if with_pages:
        for name in ("settings", "legacy"):
            entry = tmp_path / "views" / name / "index.html"
            entry.parent.mkdir(parents=True)
            entry.write_text("<html></html>", encoding="utf-8")
        plugin.star_cls.chatui_views.append(
            chatui.ViewSpec(
                name="settings",
                entry=Path("views/settings/index.html"),
                target="plugin_page",
            )
        )
    manager = SimpleNamespace(
        plugin_store_path=tmp_path.parent,
        context=SimpleNamespace(get_all_stars=lambda: [plugin]),
    )
    pages = PluginPageService(manager, config={})
    service = PluginService(None, manager)
    service.get_plugin_install_sources = AsyncMock(return_value={})
    service.resolve_plugin_logo_url = AsyncMock(return_value=None)
    service.get_plugin_installed_at = Mock(return_value=None)
    result = await plugin_routes._list_plugins(
        request=SimpleNamespace(query_params={}), service=service, page_service=pages
    )
    assert result["status"] == "ok"
    assert len(result["data"]) == 1
    assert set(result["data"][0]["pages"]) == (
        {"settings", "legacy"} if with_pages else set()
    )
    assert (await pages.resolve_plugin_page_file(plugin, "results", "")).is_file()


def test_view_targets_default_to_chat_and_validate_page_actions():
    spec = chatui.ViewSpec(name="counter", entry=Path("views/counter/index.html"))
    assert spec.target == "chat_message"
    with pytest.raises(ValueError):
        chatui.ViewSpec(name="counter", entry=spec.entry, target="sidebar")
    with pytest.raises(ValueError, match="plugin Web APIs"):
        chatui.ViewSpec(
            name="counter",
            entry=spec.entry,
            target="plugin_page",
            actions=["demo:increment"],
        )


@pytest.mark.asyncio
async def test_view_targets_select_chat_or_independent_page_host(views, tmp_path):
    store, event, plugin, record = views
    for name in ("settings", "legacy"):
        entry = tmp_path / "views" / name / "index.html"
        entry.parent.mkdir(parents=True)
        entry.write_text(f"<html><body>{name}</body></html>", encoding="utf-8")
    plugin.star_cls.chatui_views.append(
        chatui.ViewSpec(
            name="settings",
            entry=Path("views/settings/index.html"),
            target="plugin_page",
        )
    )
    plugin.root_dir_name = tmp_path.name
    pages = PluginPageService(
        SimpleNamespace(
            plugin_store_path=tmp_path.parent,
            context=SimpleNamespace(get_all_stars=lambda: [plugin]),
        ),
        config={"dashboard": {"jwt_secret": "x" * 32}},
    )
    visible = await pages.serialize_plugin_pages(plugin)
    assert {page["name"] for page in visible} == {"settings", "legacy"}
    assert await pages.serialize_plugin_page(plugin, "results") is None
    # The chat host still needs the same asset service for its iframe resources.
    assert (await pages.resolve_plugin_page_file(plugin, "results", "")).is_file()
    page = await pages.get_plugin_page_entry_config(
        plugin_name="demo", view_name="settings", username="alice", locale="en-US"
    )
    assert "/views/settings/_t/" in page["content_path"]
    assert (
        resolve_view(__name__, "settings", target="plugin_page")[1].name == "settings"
    )
    with pytest.raises(ViewError, match="not registered for chat_message"):
        store.create(
            event,
            __name__,
            event.view_result(name="settings", data={}, text="Settings"),
        )
    with pytest.raises(ViewError, match="not registered for plugin_page"):
        resolve_view(__name__, "results", target="plugin_page")
    assert store.get(record["id"])["data"] == {"items": [1, 2]}


def test_changing_a_view_to_plugin_page_invalidates_existing_chat_instances(views):
    _, _, plugin, record = views
    plugin.star_cls.chatui_views = [
        chatui.ViewSpec(
            name="results",
            entry=Path("views/results/index.html"),
            target="plugin_page",
        )
    ]
    with pytest.raises(ViewError, match="not registered for chat_message"):
        resolve_view(__name__, record["name"], record["version"])


@pytest.fixture
def views(tmp_path, monkeypatch):
    """Create an isolated plugin, event, and view database.

    Args:
        tmp_path: Temporary plugin directory.
        monkeypatch: Scoped dependency replacement.

    Returns:
        The store, event, plugin metadata, and initial snapshot.
    """
    entry = tmp_path / "views" / "results" / "index.html"
    entry.parent.mkdir(parents=True)
    entry.write_text("<html><body>Test view</body></html>", encoding="utf-8")
    spec = chatui.ViewSpec(
        name="results", entry=Path("views/results/index.html"), actions=["demo:select"]
    )
    plugin = StarMetadata(
        name="demo",
        module_path=__name__,
        module=SimpleNamespace(__file__=str(tmp_path / "main.py")),
        star_cls=SimpleNamespace(chatui_views=[spec]),
    )
    monkeypatch.setitem(star_map, __name__, plugin)
    store = ViewStore(tmp_path / "views.db")
    monkeypatch.setattr(core_views, "view_store", store)
    monkeypatch.setattr(chat_routes, "view_store", store)
    monkeypatch.setattr("astrbot.core.pipeline.process_stage.stage.view_store", store)
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "webchat"
    message.sender = MessageMember("alice", "Alice")
    message.message_id = "run-1"
    message.message = [Plain("show")]
    message.raw_message = ("alice", "session-1", {})
    event = WebChatMessageEvent(
        "show",
        message,
        PlatformMetadata(name="webchat", id="webchat", description="test"),
        "webchat!alice!session-1",
    )
    event.send = AsyncMock()
    record = store.create(
        event,
        __name__,
        event.view_result(name="results", data={"items": [1, 2]}, text="Two items"),
    )
    return store, event, plugin, record


def test_create_and_update_contract_and_button_isolation(views):
    _, event, _, record = views
    with pytest.raises(ValueError):
        event.view_result(data={})
    with pytest.raises(ValueError):
        event.view_result(name="results", data={}, text="")
    event.message_obj.message = [
        ButtonInteraction(action_id="demo:select", interaction_id="button-1")
    ]
    assert event.get_ui_interaction() is None
    assert not UIActionFilter().filter(event, {})
    event.message_obj.message = [
        UIInteraction(
            action_id="demo:select",
            interaction_id="click-1",
            view=ViewContext(
                **{
                    key: record[key]
                    for key in ("id", "name", "version", "revision", "data")
                }
            ),
        )
    ]
    assert event.get_button_interaction() is None
    assert not ButtonActionFilter().filter(event, {})
    assert UIActionFilter("demo:select").filter(event, {})
    assert not UIActionFilter("other").filter(event, {})
    assert event.view_result(data={"selected": 1}).name is None


@pytest.mark.parametrize(
    "data",
    [{"value": float("nan")}, {"value": object()}, {"large": "x" * (1024 * 1024)}],
)
def test_view_data_rejects_invalid_values(data):
    with pytest.raises((ValueError, TypeError)):
        chatui.ViewResult(name="results", data=data, text="Result")


def test_view_data_is_copied():
    data = {"items": [1]}
    result = chatui.ViewResult(name="results", data=data, text="Result")
    data["items"].append(2)
    assert result.data == {"items": [1]}


@pytest.mark.asyncio
async def test_ui_actions_only_reach_the_owning_plugin(views, monkeypatch):
    """Exclude ordinary handlers and other plugins' catch-all actions.

    Args:
        views: Isolated plugin and event.
        monkeypatch: Scoped handler discovery replacement.
    """
    _, event, _, record = views
    event.message_obj.message = [
        UIInteraction(
            action_id="demo:select",
            interaction_id="click-1",
            view=ViewContext(
                **{
                    key: record[key]
                    for key in ("id", "name", "version", "revision", "data")
                }
            ),
        )
    ]
    event.set_extra("ui_plugin_module", __name__)
    own = SimpleNamespace(
        event_filters=[UIActionFilter()],
        handler_module_path=__name__,
        handler_full_name="own",
    )
    foreign = SimpleNamespace(
        event_filters=[UIActionFilter()],
        handler_module_path="other.plugin",
        handler_full_name="foreign",
    )
    ordinary_filter = Mock()
    ordinary = SimpleNamespace(
        event_filters=[ordinary_filter],
        handler_module_path=__name__,
        handler_full_name="ordinary",
    )
    monkeypatch.setattr(
        star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *args, **kwargs: [foreign, ordinary, own],
    )
    config = {"admins_id": [], "wake_prefix": [], "plugin_set": ["*"]}
    stage = WakingCheckStage()
    stage.ctx = SimpleNamespace(
        astrbot_config=config,
        plugin_manager=SimpleNamespace(
            context=SimpleNamespace(get_config=lambda **kwargs: config)
        ),
    )
    stage.unique_session = False
    stage.ignore_bot_self_message = False
    stage.friend_message_needs_wake_prefix = False
    stage.ignore_at_all = False
    stage.disable_builtin_commands = False
    stage.no_permission_reply = True
    stage._umo_auto_name_recorder = SimpleNamespace(schedule=lambda event: None)
    await stage.process(event)
    assert event.get_extra("activated_handlers") == [own]
    ordinary_filter.filter.assert_not_called()


@pytest.mark.asyncio
async def test_command_card_falls_back_to_text_on_other_platforms(views):
    """Use the existing response pipeline when no ChatUI renderer exists.

    Args:
        views: Isolated plugin and event.
    """
    _, event, _, _ = views
    event.get_platform_name = lambda: "telegram"

    async def handler(event):
        return event.view_result(name="results", data={"items": [1]}, text="One item")

    async for _ in call_handler(event, handler):
        pass
    assert event.get_result().chain[0].text == "One item"
    event.send.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("coroutine", [False, True])
async def test_message_handlers_can_create_cards_without_tools(views, coroutine):
    store, event, _, _ = views

    async def handler(event):
        """Create a card from an ordinary event.

        Args:
            event: Source message.

        Yields:
            A named view result.
        """
        yield event.view_result(
            name="results", data={"from": "command"}, text="Command card"
        )

    async def returning_handler(event):
        """Return a card from an ordinary event.

        Args:
            event: Source message.

        Returns:
            A named view result.
        """
        return event.view_result(
            name="results", data={"from": "command"}, text="Command card"
        )

    async for _ in call_handler(event, returning_handler if coroutine else handler):
        pass
    chain = event.send.await_args.args[0]
    assert chain.type == "chatui_view"
    assert store.get(chain.chain[0].data["id"])["data"] == {"from": "command"}


@pytest.mark.asyncio
async def test_tool_returns_text_to_model_and_sends_card(views):
    from astrbot.core.astr_agent_runtime.tool_executor import FunctionToolExecutor

    _, event, _, _ = views

    async def handler(event):
        """Return a view from a tool.

        Args:
            event: Tool event.

        Returns:
            The card and model text.
        """
        return event.view_result(
            name="results", data={"secret_from_model": "display-only"}, text="Two items"
        )

    from astrbot.core.agent.tool import FunctionTool

    tool = FunctionTool(
        name="show",
        description="show",
        parameters={"type": "object", "properties": {}},
        handler=handler,
        handler_module_path=__name__,
    )
    context = SimpleNamespace(
        context=SimpleNamespace(event=event), tool_call_timeout=10
    )
    results = [
        result async for result in FunctionToolExecutor._execute_local(tool, context)
    ]
    assert results[-1].content[0].text == "Two items"
    assert "display-only" not in str(results)
    event.send.assert_awaited_once()


def test_persisted_actions_revision_and_replay(views):
    store, _, _, record = views
    request = ViewActionRequest(
        action_id="demo:select",
        interaction_id="click-1",
        expected_revision=1,
        data={"id": 1},
    )
    assert store.begin(record["id"], request) is None
    with pytest.raises(ViewError, match="already been accepted"):
        store.begin(record["id"], request)
    receipt = store.finish(record["id"], "click-1", {"selected": 1})
    restored = ViewStore(store.path)
    assert restored.get(record["id"])["revision"] == 2
    assert restored.begin(record["id"], request) == receipt
    with pytest.raises(ViewError) as conflict:
        restored.begin(
            record["id"], request.model_copy(update={"interaction_id": "click-2"})
        )
    assert conflict.value.code == "REVISION_CONFLICT"
    with pytest.raises(ViewError) as reused:
        restored.begin(record["id"], request.model_copy(update={"data": {"id": 2}}))
    assert reused.value.code == "INVALID_INPUT"
    store.delete_session("session-1")
    with pytest.raises(ViewError):
        store.get(record["id"])


@pytest.mark.asyncio
async def test_concurrent_actions_only_reserve_once(views):
    store, _, _, record = views
    requests = [
        ViewActionRequest(
            action_id="demo:select", interaction_id=f"click-{i}", expected_revision=1
        )
        for i in range(2)
    ]
    outcomes = await asyncio.gather(
        *(
            asyncio.to_thread(store.begin, record["id"], request)
            for request in requests
        ),
        return_exceptions=True,
    )
    assert sum(result is None for result in outcomes) == 1
    assert sum(isinstance(result, ViewError) for result in outcomes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_callback_commit_and_ack_precede_model_generation(views, fail):
    store, event, _, record = views
    action = ViewActionRequest(
        action_id="demo:select", interaction_id="click-1", expected_revision=1
    )
    store.begin(record["id"], action)
    event.message_obj.message = [
        UIInteraction(
            action_id=action.action_id,
            interaction_id=action.interaction_id,
            view=ViewContext(
                **{
                    key: record[key]
                    for key in ("id", "name", "version", "revision", "data")
                }
            ),
        )
    ]
    event.set_extra("activated_handlers", [object()])
    event.set_extra("ui_plugin_module", __name__)

    async def callback(event):
        """Produce staged state and model output.

        Args:
            event: Action event.

        Yields:
            State and model results.
        """
        yield event.view_result(data={"selected": 1})
        yield event.request_llm(prompt="Summarize the selection")
        if fail:
            raise ValueError("Business failure")

    ran_model = []

    async def model(event):
        """Check action receipt ordering before simulated generation.

        Args:
            event: Model request event.

        Yields:
            One completed step.
        """
        assert event.send.await_args.args[0].type == "ui_action_result"
        assert store.get(record["id"])["data"] == {"selected": 1}
        assert isinstance(event.get_extra("provider_request"), ProviderRequest)
        ran_model.append(True)
        yield

    stage = ProcessStage()
    stage.star_request_sub_stage = SimpleNamespace(process=callback)
    stage.agent_sub_stage = SimpleNamespace(process=model)
    async for _ in stage.process(event):
        pass
    receipt = event.send.await_args.args[0].chain[0].data
    assert bool(receipt["error"]) == fail
    assert bool(ran_model) != fail
    assert store.get(record["id"])["revision"] == (1 if fail else 2)


def test_disabled_version_and_escaping_resources_rejected(views, tmp_path):
    _, _, plugin, _ = views
    with pytest.raises(ViewError):
        resolve_view(__name__, "results", 2)
    plugin.activated = False
    with pytest.raises(ViewError):
        resolve_view(__name__, "results")
    plugin.activated = True
    entry = tmp_path / "views/results/index.html"
    entry.unlink()
    outside = tmp_path.parent / f"{tmp_path.name}-outside.html"
    outside.write_text("outside")
    entry.symlink_to(outside)
    with pytest.raises(ViewError):
        resolve_view(__name__, "results")


@pytest.mark.asyncio
async def test_routes_check_owner_source_and_declared_actions(views):
    store, _, plugin, record = views
    store.bind_message(record["id"], "42")
    history = SimpleNamespace(
        is_active=True,
        user_id="session-1",
        content={"message": [{"type": "view", "id": record["id"]}]},
    )
    session = SimpleNamespace(
        creator="alice", session_id="session-1", platform_id="webchat", is_group=False
    )
    context = SimpleNamespace(
        get_config=lambda **_: {"plugin_set": ["*"]}, get_all_stars=lambda: [plugin]
    )
    service = object.__new__(ChatService)
    service.db = SimpleNamespace(
        get_platform_session_by_id=AsyncMock(return_value=session),
        get_platform_message_history_by_id=AsyncMock(return_value=history),
    )
    service.core_lifecycle = SimpleNamespace(
        plugin_manager=SimpleNamespace(context=context)
    )
    service.chat_runs = {}

    async def build(username, data, **kwargs):
        """Capture the trusted event injected by the route.

        Args:
            username: Authenticated actor.
            data: Internal chat envelope.
            **kwargs: Trusted UI event parameters.

        Returns:
            A minimal acknowledged SSE stream.
        """
        assert username == "alice"
        assert isinstance(kwargs["ui_interaction"], UIInteraction)
        assert kwargs["ui_plugin_module"] == __name__
        receipt = store.finish(record["id"], kwargs["ui_interaction"].interaction_id)

        async def stream():
            yield (
                "data: "
                + json.dumps({"type": "ui_action_result", "data": receipt})
                + "\n\n"
            )

        return stream()

    service.build_chat_stream = AsyncMock(side_effect=build)
    app = FastAPI()
    app.include_router(chat_routes.router, prefix="/api/v1")
    app.dependency_overrides[chat_routes.get_service] = lambda: service
    actor = AuthContext(username="alice", scopes=["*"], via="jwt")
    app.dependency_overrides[chat_routes.require_chat_scope] = lambda: actor
    app.state.services = SimpleNamespace(
        plugin_pages=PluginPageService(
            SimpleNamespace(context=context),
            config={"dashboard": {"jwt_secret": "x" * 32}},
        )
    )
    url = f"/api/v1/chat/views/{record['id']}"
    payload = {
        "action_id": "demo:select",
        "interaction_id": "click-1",
        "expected_revision": 1,
        "data": {},
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        assert (await client.get(url)).status_code == 200
        actor = AuthContext(username="mallory", scopes=["*"], via="jwt")
        assert (await client.get(url)).status_code == 403
        assert (await client.post(url + "/actions", json=payload)).status_code == 403
        actor = AuthContext(username="alice", scopes=["*"], via="jwt")
        assert (
            await client.post(
                url + "/actions", json={**payload, "action_id": "other:admin"}
            )
        ).status_code == 403
        assert (
            await client.post(url + "/actions", json={**payload, "view": {"data": {}}})
        ).status_code == 422
        response = await client.post(url + "/actions", json=payload)
        assert response.status_code == 200
        assert "ui_action_result" in response.text
        assert (await client.post(url + "/actions", json=payload)).json()[
            "error"
        ] is None
        assert service.build_chat_stream.await_count == 1
        history.is_active = False
        assert (await client.get(url)).status_code == 404

        for code, message in (
            ("VIEW_UNAVAILABLE", "This view is unavailable."),
            ("UNKNOWN", "The view request could not be completed."),
        ):
            service.get_chat_view = AsyncMock(
                side_effect=ViewError(code, "Internal diagnostic: private/path")
            )
            for method, path, kwargs, status in (
                ("GET", url, {}, 404),
                ("POST", url + "/actions", {"json": payload}, 403),
                ("GET", url + "/actions/click-1", {}, 403),
            ):
                response = await client.request(method, path, **kwargs)
                assert response.status_code == status
                assert response.json() == {"code": code, "message": message}


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["tool_reply", "view_only", "ack_only"])
async def test_views_and_control_events_do_not_split_saved_replies(scenario):
    from datetime import datetime, timezone

    from astrbot.dashboard.services.chat_service import ChatRunState

    queue = asyncio.Queue()
    run = ChatRunState(
        run_id="view-persistence-test",
        username="alice",
        session_id="session-1",
        turn_id="turn-1",
        platform_history_id="webchat",
        back_queue=queue,
    )
    service = object.__new__(ChatService)
    service.chat_runs = {run.run_id: run}
    service.chat_runs_by_session = {run.session_id: {run.run_id}}
    service.running_convs = {}
    service.save_bot_message = AsyncMock(
        return_value=SimpleNamespace(id=42, created_at=datetime.now(timezone.utc))
    )
    events = []
    if scenario == "tool_reply":
        events.extend(
            [
                {
                    "type": "plain",
                    "chain_type": "reasoning",
                    "streaming": True,
                    "data": "Open a list",
                },
                {
                    "type": "plain",
                    "chain_type": "tool_call",
                    "streaming": True,
                    "data": json.dumps({"id": "tool-1", "name": "open_reading_list"}),
                },
            ]
        )
    if scenario != "ack_only":
        events.append({"type": "view", "data": {"id": "reading", "name": "reading"}})
    events.extend(
        [
            {
                "type": "ui_action_result",
                "data": {"snapshot": {"revision": 2, "data": {}}},
            },
            {"type": "run_started", "data": {"run_id": run.run_id}},
        ]
    )
    if scenario == "tool_reply":
        events.extend(
            [
                {
                    "type": "plain",
                    "chain_type": "tool_call_result",
                    "streaming": True,
                    "data": json.dumps({"id": "tool-1", "result": "List created"}),
                },
                {
                    "type": "plain",
                    "chain_type": "agent_stats",
                    "data": json.dumps({"duration": 3}),
                },
                {
                    "type": "plain",
                    "streaming": True,
                    "data": "Your reading list is ready.",
                },
                {
                    "type": "complete",
                    "streaming": True,
                    "data": "Your reading list is ready.",
                },
            ]
        )
    events.append({"type": "end"})
    for event in events:
        queue.put_nowait(event)
    await service._consume_chat_run(run)
    if scenario == "ack_only":
        service.save_bot_message.assert_not_awaited()
        return
    service.save_bot_message.assert_awaited_once()
    saved = service.save_bot_message.await_args.args
    parts = saved[1]
    assert sum(part["type"] == "view" for part in parts) == 1
    if scenario == "tool_reply":
        assert any(part["type"] == "tool_call" for part in parts)
        assert parts[-1] == {"type": "plain", "text": "Your reading list is ready."}
        assert saved[2] == {"duration": 3}
    assert run.status == "completed"
