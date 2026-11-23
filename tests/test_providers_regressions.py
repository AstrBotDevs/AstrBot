"""Provider lifecycle transactions run through the real manager and provider bases."""

import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

import astrbot.core.provider.manager as manager_module
from astrbot.core.provider.entities import LLMResponse, ProviderMetaData, ProviderType
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.provider import (
    DecisionProvider,
    EmbeddingProvider,
    Provider,
    RerankProvider,
    STTProvider,
    TTSProvider,
)
from astrbot.core.provider.register import provider_cls_map

KINDS = [
    (ProviderType.CHAT_COMPLETION, Provider, "provider_insts", "curr_provider_inst"),
    (
        ProviderType.SPEECH_TO_TEXT,
        STTProvider,
        "stt_provider_insts",
        "curr_stt_provider_inst",
    ),
    (
        ProviderType.TEXT_TO_SPEECH,
        TTSProvider,
        "tts_provider_insts",
        "curr_tts_provider_inst",
    ),
    (ProviderType.EMBEDDING, EmbeddingProvider, "embedding_provider_insts", None),
    (ProviderType.RERANK, RerankProvider, "rerank_provider_insts", None),
    (
        ProviderType.DECISION,
        DecisionProvider,
        "decision_provider_insts",
        "curr_decision_provider_inst",
    ),
]


class _LifecycleProbe:
    def __init__(self, config, settings):
        super().__init__(config, settings)
        self.initialize_calls = 0
        self.terminate_calls = 0
        self.ready = False
        self.closed = False
        self.release = asyncio.Event()
        self.set_model(config.get("model", "old"))
        self.instances.append(self)

    async def initialize(self):
        self.initialize_calls += 1
        mode = self.provider_config.get("initialize_mode")
        if mode == "fail":
            raise RuntimeError("candidate initialization failed")
        if mode == "wait":
            self.started.set()
            await self.release.wait()
        self.ready = True

    async def terminate(self):
        self.terminate_calls += 1
        self.closed = True
        if self.provider_config.get("terminate_failure"):
            raise RuntimeError("provider termination failed")

    def use(self):
        assert self.ready and not self.closed
        return self.get_model()

    def get_current_key(self):
        return "local-key"

    def set_key(self, key):
        self.key = key

    async def get_models(self):
        return [self.get_model()]

    async def text_chat(self, **kwargs):
        return LLMResponse(role="assistant", completion_text=self.use())

    async def get_text(self, audio_url):
        return self.use()

    async def get_audio(self, text):
        return self.use()

    async def get_embedding(self, text):
        return [1.0]

    async def get_embeddings(self, texts):
        return [[1.0] for _ in texts]

    def get_dim(self):
        return 1

    async def rerank(self, query, documents, top_n=None):
        return []

    async def ask(self, questions, state=None, **kwargs):
        return {}


class _Config(dict):
    def __init__(self, **values):
        super().__init__(values)
        self.save_config = Mock()


@pytest_asyncio.fixture(params=KINDS, ids=lambda case: case[0].value)
async def lifecycle(request, monkeypatch):
    kind, base, list_name, default_name = request.param
    instances = []
    started = asyncio.Event()
    adapter = f"test_transaction_{kind.value}"
    probe = type(
        "RecordingProvider",
        (_LifecycleProbe, base),
        {"instances": instances, "started": started},
    )
    metadata = ProviderMetaData(
        id="default",
        model=None,
        type=adapter,
        desc="Local lifecycle probe",
        provider_type=kind,
        cls_type=probe,
    )
    monkeypatch.setitem(provider_cls_map, adapter, metadata)
    old_config = {
        "id": "original",
        "type": adapter,
        "provider_type": kind.value,
        "enable": True,
        "model": "old",
    }
    config = _Config(
        provider=[copy.deepcopy(old_config)],
        provider_sources=[],
        provider_settings={},
        provider_stt_settings={"enable": True, "provider_id": "original"},
        provider_tts_settings={"enable": True, "provider_id": "original"},
        agent={"runtime": "astrbot", "config": {"model": {"provider_id": "original"}}},
    )
    tools = SimpleNamespace(
        init_mcp_clients=AsyncMock(), disable_mcp_server=AsyncMock()
    )
    monkeypatch.setattr(manager_module, "llm_tools", tools)
    monkeypatch.setattr(manager_module, "astrbot_config", config)

    async def preference(*args, default=None, **kwargs):
        return default

    monkeypatch.setattr(
        manager_module,
        "sp",
        SimpleNamespace(
            get_async=AsyncMock(side_effect=preference), put_async=AsyncMock()
        ),
    )
    manager = ProviderManager(
        SimpleNamespace(
            confs={"default": config},
            default_conf=config,
            get_conf=lambda umo=None: config,
        ),
        SimpleNamespace(),
        SimpleNamespace(default_persona="default"),
    )
    monkeypatch.setattr(manager, "dynamic_import_provider", Mock())
    await manager.load_provider(old_config)
    old = manager.inst_map["original"]
    state = SimpleNamespace(
        manager=manager,
        config=config,
        old_config=old_config,
        old=old,
        instances=instances,
        started=started,
        list_name=list_name,
        default_name=default_name,
        tools=tools,
    )
    try:
        yield state
    finally:
        await manager.terminate()


def _replacement(state, **changes):
    return {**state.old_config, "model": "new", **changes}


def _assert_previous_provider_remains_live(state):
    assert state.config["provider"] == [state.old_config]
    assert state.manager.providers_config == [state.old_config]
    assert state.manager.inst_map == {"original": state.old}
    assert getattr(state.manager, state.list_name) == [state.old]
    if state.default_name:
        assert getattr(state.manager, state.default_name) is state.old
    assert state.old.use() == "old"
    assert state.old.initialize_calls == 1
    assert state.old.terminate_calls == 0


@pytest.mark.asyncio
async def test_failed_update_initialization_preserves_config_instance_and_defaults(
    lifecycle,
):
    state = lifecycle

    with pytest.raises(Exception, match="candidate initialization failed"):
        await state.manager.update_provider(
            "original", _replacement(state, initialize_mode="fail")
        )

    _assert_previous_provider_remains_live(state)
    state.config.save_config.assert_not_called()
    assert len(state.instances) == 2
    assert state.instances[-1].initialize_calls == 1
    assert state.instances[-1].terminate_calls == 1


@pytest.mark.asyncio
async def test_failed_update_save_discards_the_candidate_and_restores_configuration(
    lifecycle,
):
    state = lifecycle
    state.config.save_config.side_effect = OSError("config persistence failed")

    with pytest.raises(OSError, match="config persistence failed"):
        await state.manager.update_provider("original", _replacement(state))

    _assert_previous_provider_remains_live(state)
    state.config.save_config.assert_called_once_with()
    assert state.instances[-1].initialize_calls == 1
    assert state.instances[-1].terminate_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement_id", ["original", "renamed"])
async def test_successful_update_saves_and_swaps_once_before_retiring_old_provider(
    lifecycle, replacement_id
):
    state = lifecycle
    observed_during_save = []

    def save():
        observed_during_save.append(
            (dict(state.manager.inst_map), state.old.closed, state.instances[-1].ready)
        )

    state.config.save_config.side_effect = save
    replacement = _replacement(state, id=replacement_id)

    await state.manager.update_provider("original", replacement)

    new = state.instances[-1]
    state.config.save_config.assert_called_once_with()
    assert observed_during_save == [({"original": state.old}, False, True)]
    assert state.config["provider"] == [replacement]
    assert state.manager.providers_config == [replacement]
    assert state.manager.inst_map == {replacement_id: new}
    assert getattr(state.manager, state.list_name) == [new]
    if state.default_name:
        assert getattr(state.manager, state.default_name) is new
    assert new.use() == "new"
    assert new.initialize_calls == 1
    assert new.terminate_calls == 0
    assert state.old.terminate_calls == 1


@pytest.mark.asyncio
async def test_pending_update_keeps_old_provider_usable_until_candidate_is_ready(
    lifecycle,
):
    state = lifecycle
    task = asyncio.create_task(
        state.manager.update_provider(
            "original", _replacement(state, initialize_mode="wait")
        )
    )
    try:
        await asyncio.wait_for(state.started.wait(), 3)
        _assert_previous_provider_remains_live(state)
        state.config.save_config.assert_not_called()
        state.instances[-1].release.set()
        await asyncio.wait_for(task, 3)
        assert state.manager.inst_map["original"].use() == "new"
        assert state.old.terminate_calls == 1
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_update_cleans_candidate_without_touching_the_old_provider(
    lifecycle,
):
    state = lifecycle
    task = asyncio.create_task(
        state.manager.update_provider(
            "original", _replacement(state, initialize_mode="wait")
        )
    )
    try:
        await asyncio.wait_for(state.started.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        _assert_previous_provider_remains_live(state)
        state.config.save_config.assert_not_called()
        assert state.instances[-1].terminate_calls == 1
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_disabling_a_provider_persists_before_removing_the_live_instance(
    lifecycle,
):
    state = lifecycle
    observed = []
    state.config.save_config.side_effect = lambda: observed.append(state.old.use())
    replacement = _replacement(state, enable=False)

    await state.manager.update_provider("original", replacement)

    assert observed == ["old"]
    state.config.save_config.assert_called_once_with()
    assert state.config["provider"] == [replacement]
    assert state.manager.inst_map == {}
    assert getattr(state.manager, state.list_name) == []
    if state.default_name:
        assert getattr(state.manager, state.default_name) is None
    assert len(state.instances) == 1
    assert state.old.terminate_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["import", "missing_class"])
async def test_adapter_resolution_failure_cannot_replace_a_working_provider(
    lifecycle, failure, monkeypatch
):
    state = lifecycle
    if failure == "import":
        state.manager.dynamic_import_provider.side_effect = ImportError(
            "missing adapter"
        )
    else:
        monkeypatch.delitem(provider_cls_map, state.old_config["type"])

    with pytest.raises(Exception):
        await state.manager.update_provider("original", _replacement(state))

    _assert_previous_provider_remains_live(state)
    state.config.save_config.assert_not_called()
    assert len(state.instances) == 1


@pytest.mark.asyncio
async def test_duplicate_provider_id_is_rejected_before_initialization(lifecycle):
    state = lifecycle

    with pytest.raises(ValueError, match="already exists"):
        await state.manager.create_provider(_replacement(state))

    _assert_previous_provider_remains_live(state)
    state.config.save_config.assert_not_called()
    assert len(state.instances) == 1


@pytest.mark.asyncio
async def test_failed_create_rolls_back_configuration_and_disposes_partial_instance(
    lifecycle,
):
    state = lifecycle

    with pytest.raises(Exception, match="candidate initialization failed"):
        await state.manager.create_provider(
            _replacement(state, id="new", initialize_mode="fail")
        )

    _assert_previous_provider_remains_live(state)
    state.config.save_config.assert_not_called()
    assert state.instances[-1].terminate_calls == 1


@pytest.mark.asyncio
async def test_failed_create_save_leaves_no_registered_or_configured_candidate(
    lifecycle,
):
    state = lifecycle
    state.config.save_config.side_effect = OSError("config persistence failed")

    with pytest.raises(OSError, match="config persistence failed"):
        await state.manager.create_provider(_replacement(state, id="new"))

    _assert_previous_provider_remains_live(state)
    state.config.save_config.assert_called_once_with()
    assert state.instances[-1].terminate_calls == 1


@pytest.mark.asyncio
async def test_cancelled_create_rolls_back_configuration_and_cleans_the_candidate(
    lifecycle,
):
    state = lifecycle
    task = asyncio.create_task(
        state.manager.create_provider(
            _replacement(state, id="new", initialize_mode="wait")
        )
    )
    try:
        await asyncio.wait_for(state.started.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        _assert_previous_provider_remains_live(state)
        state.config.save_config.assert_not_called()
        assert state.instances[-1].terminate_calls == 1
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_loading_an_already_registered_id_does_not_initialize_it_twice(lifecycle):
    state = lifecycle

    await state.manager.load_provider(state.old_config)

    assert state.instances == [state.old]
    _assert_previous_provider_remains_live(state)


@pytest.mark.asyncio
async def test_terminate_provider_removes_every_category_reference_exactly_once(
    lifecycle,
):
    state = lifecycle

    await state.manager.terminate_provider("original")
    await state.manager.terminate_provider("original")

    assert state.manager.inst_map == {}
    assert getattr(state.manager, state.list_name) == []
    if state.default_name:
        assert getattr(state.manager, state.default_name) is None
    assert state.old.terminate_calls == 1


@pytest.mark.asyncio
async def test_shutdown_deduplicates_list_and_map_references_and_is_repeatable(
    lifecycle,
):
    state = lifecycle
    state.manager.inst_map["alias"] = state.old

    await state.manager.terminate()
    await state.manager.terminate()

    assert state.old.terminate_calls == 1
    assert state.manager._get_all_provider_instances() == []
    assert state.manager.inst_map == {}


@pytest.mark.asyncio
async def test_one_termination_error_does_not_leak_the_remaining_instances(lifecycle):
    state = lifecycle
    await state.manager.load_provider(_replacement(state, id="second"))
    state.old.provider_config["terminate_failure"] = True

    await state.manager.terminate()

    assert [instance.terminate_calls for instance in state.instances] == [1, 1]
    assert all(instance.closed for instance in state.instances)
    assert state.manager._get_all_provider_instances() == []


@pytest.mark.asyncio
async def test_repeated_initialize_keeps_one_provider_and_shutdown_drains_mcp_task(
    lifecycle,
):
    state = lifecycle
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def init_mcp():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    state.tools.init_mcp_clients.side_effect = init_mcp
    await state.manager.initialize()
    await asyncio.wait_for(started.wait(), 3)
    await state.manager.initialize()

    assert state.instances == [state.old]
    assert state.old.initialize_calls == 1
    state.tools.init_mcp_clients.assert_awaited_once_with()

    await state.manager.terminate()

    assert stopped.is_set()
    assert state.manager._mcp_init_task is None
    assert state.old.terminate_calls == 1


@pytest.mark.asyncio
async def test_failed_disabled_update_keeps_the_original_provider_live(lifecycle):
    state = lifecycle
    state.config.save_config.side_effect = OSError("config persistence failed")

    with pytest.raises(OSError, match="config persistence failed"):
        await state.manager.update_provider(
            "original", _replacement(state, enable=False)
        )

    _assert_previous_provider_remains_live(state)
    assert state.instances == [state.old]
    state.config.save_config.assert_called_once_with()


@pytest.mark.asyncio
async def test_successful_create_publishes_after_save_without_changing_the_current_provider(
    lifecycle,
):
    state = lifecycle
    observed = []
    state.config.save_config.side_effect = lambda: observed.append(
        (dict(state.manager.inst_map), state.instances[-1].ready)
    )
    new_config = _replacement(state, id="second")

    await state.manager.create_provider(new_config)

    new = state.instances[-1]
    assert observed == [({"original": state.old}, True)]
    state.config.save_config.assert_called_once_with()
    assert state.config["provider"] == [state.old_config, new_config]
    assert state.manager.inst_map == {"original": state.old, "second": new}
    assert getattr(state.manager, state.list_name) == [state.old, new]
    if state.default_name:
        assert getattr(state.manager, state.default_name) is state.old
    assert state.old.use() == "old"
    assert new.use() == "new"
    assert [instance.initialize_calls for instance in state.instances] == [1, 1]
    assert [instance.terminate_calls for instance in state.instances] == [0, 0]


@pytest.mark.asyncio
async def test_overlapping_updates_serialize_preparation_and_publish_one_instance(
    lifecycle,
):
    state = lifecycle
    first = asyncio.create_task(
        state.manager.update_provider(
            "original", _replacement(state, model="first", initialize_mode="wait")
        )
    )
    second_entered = asyncio.Event()

    async def update_second():
        second_entered.set()
        await state.manager.update_provider(
            "original", _replacement(state, model="second")
        )

    second = None
    try:
        await asyncio.wait_for(state.started.wait(), 3)
        first_candidate = state.instances[-1]
        second = asyncio.create_task(update_second())
        await asyncio.wait_for(second_entered.wait(), 3)
        assert state.instances == [state.old, first_candidate]
        assert state.manager.inst_map == {"original": state.old}
        state.config.save_config.assert_not_called()
        first_candidate.release.set()
        await asyncio.wait_for(asyncio.gather(first, second), 3)
    finally:
        for instance in state.instances:
            instance.release.set()
        tasks = [task for task in (first, second) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    final = state.instances[-1]
    assert state.manager.inst_map == {"original": final}
    assert getattr(state.manager, state.list_name) == [final]
    assert final.use() == "second"
    assert state.config["provider"][0]["model"] == "second"
    assert state.config.save_config.call_count == 2
    assert [instance.initialize_calls for instance in state.instances] == [1, 1, 1]
    assert [instance.terminate_calls for instance in state.instances] == [1, 1, 0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first_operation", "second_operation"),
    [("load", "load"), ("create", "load"), ("load", "create")],
)
async def test_concurrent_first_registration_publishes_only_one_instance(
    lifecycle, first_operation, second_operation
):
    state = lifecycle
    first_config = _replacement(
        state, id="second", model="first", initialize_mode="wait"
    )
    first_method = getattr(state.manager, f"{first_operation}_provider")
    second_method = getattr(state.manager, f"{second_operation}_provider")
    first = asyncio.create_task(first_method(first_config))
    second_entered = asyncio.Event()

    async def register_second():
        second_entered.set()
        await second_method(_replacement(state, id="second", model="other"))

    second = None
    try:
        await asyncio.wait_for(state.started.wait(), 3)
        candidate = state.instances[-1]
        second = asyncio.create_task(register_second())
        await asyncio.wait_for(second_entered.wait(), 3)
        assert state.instances == [state.old, candidate]
        assert state.manager.inst_map == {"original": state.old}
        candidate.release.set()
        outcomes = await asyncio.wait_for(
            asyncio.gather(first, second, return_exceptions=True), 3
        )
    finally:
        for instance in state.instances:
            instance.release.set()
        tasks = [task for task in (first, second) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    assert outcomes[0] is None
    if second_operation == "create":
        assert isinstance(outcomes[1], ValueError)
        assert "already exists" in str(outcomes[1])
    else:
        assert outcomes[1] is None
    assert state.instances == [state.old, candidate]
    assert state.manager.inst_map == {"original": state.old, "second": candidate}
    assert getattr(state.manager, state.list_name) == [state.old, candidate]
    assert candidate.use() == "first"
    assert state.config.save_config.call_count == (first_operation == "create")


@pytest.mark.asyncio
async def test_cancelled_first_load_releases_the_waiting_registration(lifecycle):
    state = lifecycle
    first = asyncio.create_task(
        state.manager.load_provider(
            _replacement(state, id="second", initialize_mode="wait")
        )
    )
    second_entered = asyncio.Event()

    async def register_second():
        second_entered.set()
        await state.manager.load_provider(
            _replacement(state, id="second", model="survivor")
        )

    second = None
    try:
        await asyncio.wait_for(state.started.wait(), 3)
        failed_candidate = state.instances[-1]
        second = asyncio.create_task(register_second())
        await asyncio.wait_for(second_entered.wait(), 3)
        assert state.instances == [state.old, failed_candidate]
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        await asyncio.wait_for(second, 3)
    finally:
        for instance in state.instances:
            instance.release.set()
        tasks = [task for task in (first, second) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    survivor = state.instances[-1]
    assert failed_candidate.terminate_calls == 1
    assert state.manager.inst_map == {"original": state.old, "second": survivor}
    assert getattr(state.manager, state.list_name) == [state.old, survivor]
    assert survivor.use() == "survivor"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["error", "cancel"])
async def test_failed_standalone_termination_leaves_no_stale_registration(
    lifecycle, monkeypatch, failure
):
    state = lifecycle
    entered = asyncio.Event()
    release = asyncio.Event()
    cleaned = asyncio.Event()

    async def terminate_old():
        state.old.terminate_calls += 1
        entered.set()
        try:
            await release.wait()
            raise RuntimeError("termination failed after retirement")
        finally:
            state.old.closed = True
            cleaned.set()

    monkeypatch.setattr(state.old, "terminate", terminate_old)
    task = asyncio.create_task(state.manager.terminate_provider("original"))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        assert state.manager.inst_map == {}
        assert getattr(state.manager, state.list_name) == []
        if state.default_name:
            assert getattr(state.manager, state.default_name) is None
        if failure == "cancel":
            task.cancel()
            expected_error = asyncio.CancelledError
        else:
            release.set()
            expected_error = RuntimeError
        with pytest.raises(expected_error):
            await asyncio.wait_for(task, 3)
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert cleaned.is_set()
    await state.manager.terminate_provider("original")
    assert state.old.terminate_calls == 1
    await state.manager.load_provider(_replacement(state))
    replacement = state.instances[-1]
    assert replacement is not state.old
    assert state.manager.inst_map == {"original": replacement}
    assert getattr(state.manager, state.list_name) == [replacement]
    assert replacement.use() == "new"


@pytest.mark.asyncio
async def test_replacement_is_visible_inside_old_provider_termination(
    lifecycle, monkeypatch
):
    state = lifecycle
    observed = []

    async def observe_retirement():
        state.old.terminate_calls += 1
        replacement = state.manager.inst_map["renamed"]
        observed.append(replacement)
        assert replacement.ready
        assert state.manager.inst_map == {"renamed": replacement}
        assert getattr(state.manager, state.list_name) == [replacement]
        if state.default_name:
            assert getattr(state.manager, state.default_name) is replacement
        assert state.config["provider"][0]["id"] == "renamed"
        state.config.save_config.assert_called_once_with()
        state.old.closed = True

    monkeypatch.setattr(state.old, "terminate", observe_retirement)
    await state.manager.update_provider("original", _replacement(state, id="renamed"))
    assert observed == [state.instances[-1]]
    assert state.old.terminate_calls == 1
    assert state.old.closed


@pytest.mark.asyncio
async def test_delete_waits_for_reload_then_removes_the_reloaded_instance(lifecycle):
    state = lifecycle
    reload_task = asyncio.create_task(
        state.manager.reload(_replacement(state, initialize_mode="wait"))
    )
    delete_entered = asyncio.Event()

    async def delete_reloaded():
        delete_entered.set()
        await state.manager.delete_provider("original")

    delete_task = None
    try:
        await asyncio.wait_for(state.started.wait(), 3)
        candidate = state.instances[-1]
        delete_task = asyncio.create_task(delete_reloaded())
        await asyncio.wait_for(delete_entered.wait(), 3)
        assert not delete_task.done()
        candidate.release.set()
        await asyncio.wait_for(asyncio.gather(reload_task, delete_task), 3)
    finally:
        for instance in state.instances:
            instance.release.set()
        tasks = [task for task in (reload_task, delete_task) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    assert state.manager.inst_map == {}
    assert getattr(state.manager, state.list_name) == []
    if state.default_name:
        assert getattr(state.manager, state.default_name) is None
    assert state.config["provider"] == []
    assert state.config.save_config.call_count == 1
    assert state.old.terminate_calls == 1
    assert candidate.terminate_calls == 1
