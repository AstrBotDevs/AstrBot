from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.dashboard.services.plugin_service import PluginService, PluginServiceError


def _registry() -> dict:
    return {
        "$meta": {"name": "test market"},
        "Alpha/astrbot_plugin_alpha": {
            "author": "Alpha",
            "name": "astrbot_plugin_alpha",
            "display_name": "Alpha Tool",
            "desc": "alpha description",
            "category": "工具",
            "stars": 10,
            "download_count": 100,
            "updated_at": "2026-01-01T00:00:00Z",
            "repo": "https://github.com/Alpha/alpha",
            "tags": ["tts"],
            "pinned": True,
        },
        "Beta/astrbot_plugin_beta": {
            "author": "Beta",
            "name": "astrbot_plugin_beta",
            "display_name": "Beta Tool",
            "desc": "beta description",
            "category": "工具",
            "stars": 30,
            "download_count": 50,
            "updated_at": "2026-03-01T00:00:00Z",
            "repo": "https://github.com/Beta/beta",
        },
        "Gamma/astrbot_plugin_gamma": {
            "author": "Gamma",
            "name": "astrbot_plugin_gamma",
            "display_name": "Gamma Plugin",
            "desc": "gamma description",
            "category": "娱乐",
            "stars": 30,
            "download_count": 50,
            "updated_at": "2026-02-01T00:00:00Z",
            "repo": "https://github.com/Gamma/gamma",
            "support_platforms": ["aiocqhttp"],
            "astrbot_version": ">=4.29",
        },
        "Delta/astrbot_plugin_delta": {
            "author": "Delta",
            "name": "astrbot_plugin_delta",
            "desc": "delta description",
            "stars": 0,
            "download_count": 0,
            "updated_at": "2025-12-01T00:00:00Z",
            "repo": "https://github.com/Delta/delta",
        },
    }


def _service() -> PluginService:
    service = PluginService(MagicMock(), MagicMock())
    service.get_online_plugins = AsyncMock(return_value=(_registry(), None))
    return service


async def _query(service: PluginService, **kwargs):
    params = {
        "custom_registry": None,
        "force_refresh": False,
        "page": None,
        "page_size": None,
        "sort": "recommended",
        "order": "desc",
        "category": None,
        "keyword": None,
    }
    params.update(kwargs)
    return await service.get_market_query(**params)


@pytest.mark.asyncio
async def test_market_without_pagination_keeps_legacy_shape():
    service = _service()

    data, message = await _query(service)

    assert data == _registry()
    assert message is None


@pytest.mark.asyncio
async def test_market_pagination_returns_items_and_total():
    service = _service()

    data, _ = await _query(service, page=1, page_size=2)

    assert data["total"] == 4
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["has_more"] is True
    assert len(data["items"]) == 2
    assert data["items"][0]["market_plugin_id"] == "Alpha/astrbot_plugin_alpha"
    assert data["meta"] == {"name": "test market"}


@pytest.mark.asyncio
async def test_market_pagination_beyond_last_page_returns_empty_items():
    service = _service()

    data, _ = await _query(service, page=5, page_size=2)

    assert data["items"] == []
    assert data["has_more"] is False
    assert data["total"] == 4


@pytest.mark.asyncio
async def test_market_sorts_by_downloads_both_orders():
    service = _service()

    desc, _ = await _query(service, page=1, page_size=4, sort="downloads")
    asc, _ = await _query(service, page=1, page_size=4, sort="downloads", order="asc")

    assert [item["download_count"] for item in desc["items"]] == [100, 50, 50, 0]
    assert [item["download_count"] for item in asc["items"]] == [0, 50, 50, 100]


@pytest.mark.asyncio
async def test_market_sort_ties_are_stable_by_market_id():
    service = _service()

    data, _ = await _query(service, page=1, page_size=4, sort="stars")

    ids = [item["market_plugin_id"] for item in data["items"]]
    assert ids[:2] == ["Beta/astrbot_plugin_beta", "Gamma/astrbot_plugin_gamma"]
    assert ids[2] == "Alpha/astrbot_plugin_alpha"
    assert ids[3] == "Delta/astrbot_plugin_delta"


@pytest.mark.asyncio
async def test_market_sorts_by_updated_author_and_name():
    service = _service()

    updated, _ = await _query(service, page=1, page_size=4, sort="updated")
    author, _ = await _query(service, page=1, page_size=4, sort="author", order="asc")
    name, _ = await _query(service, page=1, page_size=4, sort="name", order="asc")

    assert updated["items"][0]["updated_at"].startswith("2026-03")
    assert author["items"][0]["author"] == "Alpha"
    assert name["items"][0]["display_name"] == "Alpha Tool"


@pytest.mark.asyncio
async def test_market_recommended_puts_pinned_first():
    service = _service()

    data, _ = await _query(service, page=1, page_size=4)

    assert data["items"][0]["market_plugin_id"] == "Alpha/astrbot_plugin_alpha"
    assert data["items"][0]["pinned"] is True


@pytest.mark.asyncio
async def test_market_filters_by_category_with_normalization():
    service = _service()

    data, _ = await _query(service, page=1, page_size=10, category="工具")

    assert data["total"] == 2
    assert {item["author"] for item in data["items"]} == {"Alpha", "Beta"}


@pytest.mark.asyncio
async def test_market_filters_unknown_category_as_other():
    service = _service()

    data, _ = await _query(service, page=1, page_size=10, category="other")

    assert data["total"] == 1
    assert data["items"][0]["author"] == "Delta"


@pytest.mark.asyncio
async def test_market_keyword_matches_desc_tags_and_author():
    service = _service()

    by_tag, _ = await _query(service, page=1, page_size=10, keyword="tts")
    by_author, _ = await _query(service, page=1, page_size=10, keyword="gamma")
    by_desc, _ = await _query(service, page=1, page_size=10, keyword="BETA DESCRIPTION")

    assert [item["author"] for item in by_tag["items"]] == ["Alpha"]
    assert [item["author"] for item in by_author["items"]] == ["Gamma"]
    assert [item["author"] for item in by_desc["items"]] == ["Beta"]


@pytest.mark.asyncio
async def test_market_filter_without_pagination_returns_legacy_shape():
    service = _service()

    data, _ = await _query(service, keyword="tts")

    assert "$meta" in data
    assert list(data) == ["$meta", "Alpha/astrbot_plugin_alpha"]


@pytest.mark.asyncio
async def test_market_categories_counts_and_labels():
    service = _service()

    data, _ = await service.get_market_categories(custom_registry=None)

    assert data["total"] == 4
    assert data["categories"][0] == {"value": "工具", "label": "工具", "count": 2}
    assert {"value": "other", "label": "", "count": 1} in data["categories"]


@pytest.mark.asyncio
async def test_market_entry_lookup_by_id_repo_and_name():
    service = _service()

    by_id, _ = await service.get_market_entry(
        plugin_id="Alpha/astrbot_plugin_alpha",
        custom_registry=None,
    )
    by_repo, _ = await service.get_market_entry(
        plugin_id="https://github.com/Gamma/gamma",
        custom_registry=None,
    )
    by_name, _ = await service.get_market_entry(
        plugin_id="astrbot_plugin_beta",
        custom_registry=None,
    )

    assert by_id["market_plugin_id"] == "Alpha/astrbot_plugin_alpha"
    assert by_repo["market_plugin_id"] == "Gamma/astrbot_plugin_gamma"
    assert by_name["market_plugin_id"] == "Beta/astrbot_plugin_beta"


@pytest.mark.asyncio
async def test_market_entry_not_found_raises_public_error():
    service = _service()

    with pytest.raises(PluginServiceError) as exc_info:
        await service.get_market_entry(plugin_id="missing/plugin", custom_registry=None)

    assert "未找到插件" in exc_info.value.public_message


@pytest.mark.asyncio
async def test_market_query_forwards_registry_and_refresh():
    service = _service()

    await _query(
        service,
        custom_registry="https://example.com/registry.json",
        force_refresh=True,
    )

    service.get_online_plugins.assert_awaited_once_with(
        custom_registry="https://example.com/registry.json",
        force_refresh=True,
    )


@pytest.mark.asyncio
async def test_market_entries_resolve_by_id_repo_and_name():
    service = _service()

    data, _ = await service.get_market_entries(
        records=[
            {"market_plugin_id": "Alpha/astrbot_plugin_alpha"},
            {"repo": "https://github.com/Beta/beta"},
            {"name": "astrbot_plugin_gamma"},
            {"market_plugin_id": "missing/plugin"},
        ],
        custom_registry=None,
    )

    ids = [item["market_plugin_id"] if item else None for item in data["items"]]
    assert ids == [
        "Alpha/astrbot_plugin_alpha",
        "Beta/astrbot_plugin_beta",
        "Gamma/astrbot_plugin_gamma",
        None,
    ]


@pytest.mark.asyncio
async def test_market_page_only_uses_default_page_size():
    service = _service()

    data, _ = await _query(service, page=2)

    assert data["page"] == 2
    assert data["page_size"] == 9


@pytest.mark.asyncio
async def test_market_category_all_is_case_insensitive():
    service = _service()

    data, _ = await _query(service, page=1, page_size=10, category="ALL")

    assert data["total"] == 4


@pytest.mark.asyncio
async def test_market_keyword_matches_astrbot_version():
    service = _service()

    data, _ = await _query(service, page=1, page_size=10, keyword="4.29")

    assert [item["author"] for item in data["items"]] == ["Gamma"]


@pytest.mark.asyncio
async def test_market_entries_match_market_id_case_insensitively():
    service = _service()

    data, _ = await service.get_market_entries(
        records=[{"market_plugin_id": "alpha/ASTRBOT_PLUGIN_ALPHA"}],
        custom_registry=None,
    )

    assert data["items"][0]["market_plugin_id"] == "Alpha/astrbot_plugin_alpha"


@pytest.mark.asyncio
async def test_market_random_returns_requested_count_without_duplicates():
    service = _service()

    data, _ = await service.get_market_random(count=3, custom_registry=None)

    ids = [item["market_plugin_id"] for item in data["items"]]
    assert len(ids) == 3
    assert len(set(ids)) == 3


@pytest.mark.asyncio
async def test_market_random_returns_everything_when_count_is_larger():
    service = _service()

    data, _ = await service.get_market_random(count=20, custom_registry=None)

    assert len(data["items"]) == 4


@pytest.mark.asyncio
async def test_market_entries_match_repo_case_insensitively():
    service = _service()

    data, _ = await service.get_market_entries(
        records=[{"repo": "https://github.com/BETA/beta"}],
        custom_registry=None,
    )

    assert data["items"][0]["market_plugin_id"] == "Beta/astrbot_plugin_beta"


@pytest.mark.asyncio
async def test_market_entry_matches_name_case_insensitively():
    service = _service()

    data, _ = await service.get_market_entry(
        plugin_id="ASTRBOT_PLUGIN_GAMMA",
        custom_registry=None,
    )

    assert data["market_plugin_id"] == "Gamma/astrbot_plugin_gamma"


@pytest.mark.asyncio
async def test_market_sort_ignores_non_numeric_download_counts():
    service = PluginService(MagicMock(), MagicMock())
    registry = {
        "A/a": {"author": "A", "name": "a", "download_count": "many"},
        "B/b": {"author": "B", "name": "b", "download_count": 5},
    }
    service.get_online_plugins = AsyncMock(return_value=(registry, None))

    data, _ = await _query(service, page=1, page_size=10, sort="downloads")

    assert [item["name"] for item in data["items"]] == ["b", "a"]
