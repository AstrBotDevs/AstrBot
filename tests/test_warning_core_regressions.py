"""Preserve core runtime contracts from the historical warning fixes."""

from copy import deepcopy

import numpy as np
import pytest

from astrbot.api.web import PluginMultiDict
from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage
from astrbot.core.utils.migra_helper import (
    _get_effective_provider_map,
    _get_provider_runner_type,
)

_INVALID_IDS: tuple[object, ...] = (
    None,
    "",
    False,
    0,
    7,
    ["identifier"],
    {"id": "identifier"},
)


def _assert_effective_providers(
    config: object,
    expected: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    before = deepcopy(config)
    result = _get_effective_provider_map(config)
    assert result == expected
    assert config == before
    return result


@pytest.mark.parametrize("last_value", [None, "", "last"])
def test_multidict_lookup_preserves_nullable_last_value(
    last_value: str | None,
) -> None:
    data = PluginMultiDict[str | None]([("key", "first"), ("key", last_value)])

    assert data["key"] == last_value
    assert data.get("key", "default") == last_value
    assert data.getlist("key") == ["first", last_value]
    assert "key" in data
    assert "missing" not in data
    assert data.get("missing", "default") == "default"
    with pytest.raises(KeyError) as error:
        _ = data["missing"]
    assert error.value.args == ("missing",)


@pytest.mark.parametrize("value", [None, False, 7, "invalid", [], {1: "invalid"}])
def test_legacy_provider_migration_rejects_non_mapping_inputs(value: object) -> None:
    _assert_effective_providers(value, {})
    assert _get_provider_runner_type(value) is None


def test_legacy_provider_migration_rejects_non_string_configuration_keys() -> None:
    config = {1: "invalid", "provider": [{"id": "provider"}]}
    _assert_effective_providers(config, {})

    provider = {1: "invalid", "type": "dify", "dify_api_key": "test-key"}
    before = deepcopy(provider)
    assert _get_provider_runner_type(provider) is None
    assert provider == before


@pytest.mark.parametrize("sources", [None, False, 7, "invalid", {"id": "source"}])
def test_malformed_source_collection_keeps_valid_provider_fields(
    sources: object,
) -> None:
    provider = {"id": "provider", "provider_source_id": "source", "timeout": 0}
    config = {"provider_sources": deepcopy(sources), "provider": [provider]}

    _assert_effective_providers(config, {"provider": provider})


@pytest.mark.parametrize("providers", [None, False, 7, "invalid", {"id": "provider"}])
def test_malformed_provider_collection_is_ignored(providers: object) -> None:
    config = {
        "provider_sources": [{"id": "source", "type": "dify"}],
        "provider": deepcopy(providers),
    }

    _assert_effective_providers(config, {})


@pytest.mark.parametrize("collection", ["provider_sources", "provider"])
@pytest.mark.parametrize(
    "record",
    [None, "invalid", [], {1: "invalid"}, {"id": "source", 1: "invalid"}],
)
def test_malformed_records_do_not_discard_valid_neighbors(
    collection: str, record: object
) -> None:
    source = {"id": "source", "type": "dify", "dify_api_key": "test-key"}
    provider = {"id": "provider", "provider_source_id": "source"}
    config: dict[str, list[object]] = {
        "provider_sources": [source],
        "provider": [provider],
    }
    config[collection].append(deepcopy(record))

    _assert_effective_providers(config, {"provider": {**source, **provider}})


@pytest.mark.parametrize("source_id", _INVALID_IDS)
def test_invalid_source_ids_cannot_contribute_source_fields(source_id: object) -> None:
    source_id = deepcopy(source_id)
    provider = {"id": "provider", "provider_source_id": source_id}
    config = {
        "provider_sources": [{"id": source_id, "source_only": "must not leak"}],
        "provider": [provider],
    }

    _assert_effective_providers(config, {"provider": provider})


@pytest.mark.parametrize("provider_id", _INVALID_IDS)
def test_invalid_provider_ids_are_ignored_without_losing_valid_records(
    provider_id: object,
) -> None:
    config = {
        "provider": [
            {"id": deepcopy(provider_id), "timeout": 99},
            {"id": "valid", "timeout": 0},
        ]
    }

    _assert_effective_providers(config, {"valid": {"id": "valid", "timeout": 0}})


@pytest.mark.parametrize(
    "reference", [None, False, 7, ["source"], {"id": "source"}, "missing"]
)
def test_unusable_source_reference_preserves_independent_provider_fields(
    reference: object,
) -> None:
    provider = {"id": "provider", "provider_source_id": deepcopy(reference)}
    config = {
        "provider_sources": [{"id": "source", "source_only": "must not leak"}],
        "provider": [provider],
    }

    _assert_effective_providers(config, {"provider": provider})


@pytest.mark.parametrize("field", ["type", "provider"])
@pytest.mark.parametrize("value", [None, "", False, 7, ["dify"], {"type": "dify"}])
def test_runner_type_rejects_non_string_and_empty_values(
    field: str, value: object
) -> None:
    provider = {"provider_type": "agent_runner", field: deepcopy(value)}
    before = deepcopy(provider)

    assert _get_provider_runner_type(provider) is None
    assert provider == before


@pytest.mark.parametrize("field", ["type", "provider"])
@pytest.mark.parametrize("explicit_runner", [False, True])
def test_runner_type_preserves_explicit_and_legacy_field_selection(
    field: str, explicit_runner: bool
) -> None:
    provider = {field: "dify"}
    if explicit_runner:
        provider["provider_type"] = "agent_runner"
    else:
        provider["dify_api_key"] = "test-key"

    assert _get_provider_runner_type(provider) == "dify"


def test_merged_providers_own_nested_values_and_preserve_provider_overrides() -> None:
    source = {
        "id": "source",
        "type": "dify",
        "dify_api_key": "test-key",
        "timeout": 60,
        "headers": {"tags": ["source"]},
    }
    first_provider = {
        "id": "first",
        "provider_source_id": "source",
        "timeout": 0,
        "model_config": {"tags": ["provider"]},
    }
    second_provider = {"id": "second", "provider_source_id": "source"}
    config = {
        "provider_sources": [source],
        "provider": [first_provider, second_provider],
    }
    before = deepcopy(config)
    expected_second = deepcopy({**source, **second_provider})
    result = _assert_effective_providers(
        config,
        {"first": {**source, **first_provider}, "second": expected_second},
    )
    first = result["first"]
    assert first["timeout"] == 0
    assert _get_provider_runner_type(first) == "dify"

    headers = first["headers"]
    model_config = first["model_config"]
    assert isinstance(headers, dict)
    assert isinstance(model_config, dict)
    source_tags = headers["tags"]
    provider_tags = model_config["tags"]
    assert isinstance(source_tags, list)
    assert isinstance(provider_tags, list)
    source_tags.append("changed in merged provider")
    provider_tags.append("changed in merged provider")

    assert config == before
    assert result["second"] == expected_second


@pytest.mark.asyncio
async def test_real_faiss_delete_is_idempotent_and_preserves_unrelated_ids() -> None:
    storage = EmbeddingStorage(dimension=2)
    await storage.insert_batch(
        np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32), [7, 11]
    )
    assert storage.index is not None
    assert storage.index.ntotal == 2

    for ids in ([7], [7], []):
        await storage.delete(ids)
        assert storage.index.ntotal == 1
        _, remaining_ids = await storage.search(
            np.array([0.0, 1.0], dtype=np.float32), 1
        )
        assert remaining_ids.tolist() == [[11]]

    await storage.delete([11])
    await storage.delete([11])
    await storage.delete([])
    assert storage.index.ntotal == 0
