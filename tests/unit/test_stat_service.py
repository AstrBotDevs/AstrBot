import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from astrbot.core.db.po import PlatformStat
from astrbot.dashboard.services import stat_service
from astrbot.dashboard.services.stat_service import StatService


@pytest.mark.asyncio
async def test_sqlite_get_platform_stats_returns_platform_stat_rows(temp_db):
    await temp_db.insert_platform_stats(
        "qq-main",
        "onebot",
        count=2,
        timestamp=datetime(2026, 6, 30, 1, 0, 0),
    )

    rows = await temp_db.get_platform_stats(offset_sec=10 * 365 * 24 * 3600)

    assert len(rows) == 1
    assert isinstance(rows[0], PlatformStat)
    assert rows[0].platform_id == "qq-main"
    assert rows[0].platform_type == "onebot"
    assert rows[0].count == 2


@pytest.mark.asyncio
async def test_stat_service_get_stat_accepts_unix_second_timestamps(
    astrbot_config,
    monkeypatch: pytest.MonkeyPatch,
):
    timestamp = int(time.time()) - 120
    db_helper = SimpleNamespace(
        get_platform_stats=lambda _offset_sec: None,
    )

    async def _get_platform_stats(_offset_sec: int):
        return [
            SimpleNamespace(
                platform_id="qq-main",
                platform_type="onebot",
                count=4,
                timestamp=timestamp,
            )
        ]

    db_helper.get_platform_stats = _get_platform_stats

    class _ScalarResult:
        def scalar_one(self):
            return 4

    class _Session:
        async def execute(self, _query):
            return _ScalarResult()

    @asynccontextmanager
    async def _get_db():
        yield _Session()

    db_helper.get_db = _get_db
    monkeypatch.setattr(
        "astrbot.dashboard.services.stat_service.psutil.Process",
        lambda: SimpleNamespace(
            cpu_percent=lambda interval=0.5: 25.0,
            memory_info=lambda: SimpleNamespace(rss=256 << 20),
        ),
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.stat_service.psutil.cpu_count",
        lambda: 2,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.stat_service.psutil.virtual_memory",
        lambda: SimpleNamespace(total=1024 << 20),
    )

    service = StatService(
        db_helper,
        SimpleNamespace(),
        astrbot_config,
        demo_mode=False,
        start_time=timestamp - 3600,
        html_renderer=SimpleNamespace(get_runtime_stats=lambda: {}),
        plugin_catalog=SimpleNamespace(all=lambda: ()),
        platform_manager=SimpleNamespace(get_platform_count=lambda: 1),
    )

    data = await service.get_stat(offset_sec=3600)

    assert data["message_count"] == 4
    assert data["platform"] == [
        {
            "name": "qq-main",
            "count": 4,
            "timestamp": timestamp,
        }
    ]
    assert data["cpu_percent"] == 12.5


@pytest.mark.asyncio
async def test_stat_service_get_stat_message_count_includes_history_outside_window(
    temp_db,
    monkeypatch: pytest.MonkeyPatch,
):
    now = datetime.now()
    await temp_db.insert_platform_stats(
        "qq-main", "onebot", count=3, timestamp=now - timedelta(hours=1)
    )
    await temp_db.insert_platform_stats(
        "qq-main", "onebot", count=5, timestamp=now - timedelta(days=2)
    )

    monkeypatch.setattr(
        "astrbot.dashboard.services.stat_service.psutil.Process",
        lambda: SimpleNamespace(
            cpu_percent=lambda interval=0.5: 0.0,
            memory_info=lambda: SimpleNamespace(rss=256 << 20),
        ),
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.stat_service.psutil.cpu_count",
        lambda: 1,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.stat_service.psutil.virtual_memory",
        lambda: SimpleNamespace(total=1024 << 20),
    )

    service = StatService(
        temp_db,
        SimpleNamespace(),
        {},
        demo_mode=False,
        start_time=int(time.time()) - 3600,
        html_renderer=SimpleNamespace(get_runtime_stats=lambda: {}),
        plugin_catalog=SimpleNamespace(all=lambda: ()),
        platform_manager=SimpleNamespace(get_platform_count=lambda: 1),
    )

    data = await service.get_stat(offset_sec=86400)

    assert data["message_count"] == 8
    assert len(data["platform"]) == 1
    assert data["platform"][0]["name"] == "qq-main"
    assert data["platform"][0]["count"] == 3


def test_stat_service_get_first_notice_uses_only_supported_locales(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "FIRST_NOTICE.md").write_text("Chinese notice", encoding="utf-8")
    (tmp_path / "FIRST_NOTICE.en-US.md").write_text("English notice", encoding="utf-8")
    monkeypatch.setattr(stat_service, "get_astrbot_path", lambda: str(tmp_path))

    service = object.__new__(StatService)

    assert service.get_first_notice("zh-CN") == {"content": "Chinese notice"}
    assert service.get_first_notice("en-US") == {"content": "English notice"}
    assert service.get_first_notice(None) == {"content": "Chinese notice"}


def test_running_time_components_and_timestamp_coercion():
    assert StatService.get_running_time_components(3661) == {
        "hours": 1,
        "minutes": 1,
        "seconds": 1,
    }
    naive = datetime(2026, 1, 2, 3, 4, 5)
    aware = StatService._ensure_aware_utc(naive)
    assert aware.tzinfo is not None
    already = StatService._ensure_aware_utc(aware)
    assert already.tzinfo is not None
    from_seconds = StatService._coerce_platform_stat_timestamp(1_700_000_000)
    assert from_seconds.tzinfo is not None
    from_ms = StatService._coerce_platform_stat_timestamp(1_700_000_000_000)
    assert from_ms.year >= 2023
    from_numeric_str = StatService._coerce_platform_stat_timestamp("1700000000")
    assert from_numeric_str.tzinfo is not None
    from_iso = StatService._coerce_platform_stat_timestamp("2026-01-02T03:04:05Z")
    assert from_iso.year == 2026
    with pytest.raises(ValueError):
        StatService._coerce_platform_stat_timestamp("   ")
    with pytest.raises(TypeError):
        StatService._coerce_platform_stat_timestamp(None)


@pytest.mark.asyncio
async def test_stat_service_start_time_changelog_and_restart(tmp_path, monkeypatch):
    core = SimpleNamespace(restart=lambda: None)
    service = StatService(
        SimpleNamespace(),
        core,
        {"dashboard": {"username": "astrbot"}},
        demo_mode=True,
        start_time=123,
        html_renderer=SimpleNamespace(
            get_runtime_stats=lambda: {"renders": 1},
        ),
        plugin_catalog=SimpleNamespace(all=lambda: ()),
        platform_manager=SimpleNamespace(get_platform_count=lambda: 0),
    )
    assert service.get_start_time() == {"start_time": 123}
    assert service.get_t2i_runtime_stats() == {"renders": 1}

    with pytest.raises(stat_service.StatServiceError):
        await service.restart_core()

    monkeypatch.setattr(stat_service, "get_astrbot_path", lambda: str(tmp_path))
    with pytest.raises(stat_service.StatServiceError, match="required"):
        service.get_changelog(None)
    with pytest.raises(stat_service.StatServiceError, match="Invalid"):
        service.get_changelog("../etc/passwd")
    with pytest.raises(stat_service.StatServiceError, match="not found"):
        service.get_changelog("9.9.9")
    changelogs = tmp_path / "changelogs"
    changelogs.mkdir()
    (changelogs / "v1.2.3.md").write_text("notes", encoding="utf-8")
    (changelogs / "readme.txt").write_text("skip", encoding="utf-8")
    assert service.get_changelog("v1.2.3")["content"] == "notes"
    assert "1.2.3" in service.list_changelog_versions()["versions"]
    assert service.get_first_notice("zh-CN") == {"content": None}


@pytest.mark.asyncio
async def test_provider_token_ranking_includes_umo_display_names(temp_db):
    aliased_umo = "qq:GroupMessage:group-1"
    raw_umo = "webchat:FriendMessage:session-2"
    await temp_db.insert_provider_stat(
        umo=aliased_umo,
        provider_id="provider-1",
        stats={"token_usage": {"input_other": 3, "input_cached": 4, "output": 5}},
    )
    await temp_db.insert_provider_stat(
        umo=raw_umo,
        provider_id="provider-1",
        stats={"token_usage": {"input_other": 1, "input_cached": 1, "output": 1}},
    )
    await temp_db.upsert_umo_alias(
        umo=aliased_umo,
        creator_sender_id="creator-1",
        auto_name="研发群",
        user_alias="产品讨论群",
    )

    service = StatService(
        temp_db,
        SimpleNamespace(),
        {
            "platform": [{"id": "qq", "type": "qq_official"}],
            "dashboard": {"username": "astrbot"},
        },
        demo_mode=False,
        start_time=int(time.time()) - 3600,
        html_renderer=SimpleNamespace(get_runtime_stats=lambda: {}),
        plugin_catalog=SimpleNamespace(all=lambda: ()),
        platform_manager=SimpleNamespace(get_platform_count=lambda: 1),
    )
    result = await service.get_provider_token_stats(1)

    assert result["range_by_umo"] == [
        {
            "umo": aliased_umo,
            "display_name": "产品讨论群",
            "platform_type": "qq_official",
            "tokens": 12,
        },
        {
            "umo": raw_umo,
            "display_name": raw_umo,
            "platform_type": "webchat",
            "tokens": 3,
        },
    ]
