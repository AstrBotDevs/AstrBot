"""Tests for astrbot.core.platform.manager — PlatformManager."""

import asyncio
from asyncio import Queue
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.platform.manager import PlatformManager
from astrbot.core.platform.platform import Platform, PlatformError, PlatformStatus


# ---------------------------------------------------------------------------
# A minimal concrete Platform we can wire into the manager without real I/O.
# ---------------------------------------------------------------------------
class DummyPlatform(Platform):
    """Lightweight Platform used inside manager tests."""

    def __init__(
        self,
        config: dict,
        settings: dict,
        event_queue: Queue,
        **kwargs,
    ) -> None:
        super().__init__(config, event_queue)
        self.settings = settings
        self._terminated = False

    async def run(self) -> None:
        pass

    def meta(self):
        from astrbot.core.platform.platform_metadata import PlatformMetadata
        return PlatformMetadata(
            name=self.config.get("type", "dummy"),
            description="dummy",
            id=self.config.get("id", "dummy_id"),
        )

    async def terminate(self) -> None:
        self._terminated = True
        await super().terminate()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_config() -> MagicMock:
    """A dict-like MagicMock that behaves like AstrBotConfig for key lookups."""
    cfg = MagicMock()
    cfg.__getitem__.side_effect = lambda k: {
        "platform": [],
        "platform_settings": {"unique_session": True},
    }[k]
    return cfg


@pytest.fixture
def event_queue() -> Queue:
    return Queue()


@pytest.fixture
def manager(mock_config: MagicMock, event_queue: Queue) -> PlatformManager:
    return PlatformManager(mock_config, event_queue)


# ===================================================================
# Construction
# ===================================================================

class TestConstruction:
    """PlatformManager.__init__ stores constructor arguments and initialises
    empty collections."""

    def test_stores_config(self, mock_config: MagicMock, event_queue: Queue):
        m = PlatformManager(mock_config, event_queue)
        assert m.astrbot_config is mock_config
        assert m.event_queue is event_queue

    def test_platforms_config_and_settings_are_extracted(
        self, mock_config: MagicMock, event_queue: Queue
    ):
        m = PlatformManager(mock_config, event_queue)
        assert m.platforms_config == []
        assert m.settings == {"unique_session": True}

    def test_initial_collections_are_empty(
        self, mock_config: MagicMock, event_queue: Queue
    ):
        m = PlatformManager(mock_config, event_queue)
        assert m.platform_insts == []
        assert m._inst_map == {}
        assert m._platform_tasks == {}


# ===================================================================
# _is_valid_platform_id
# ===================================================================

class TestIsValidPlatformId:
    """_is_valid_platform_id rejects None, empty, or ids containing ':'/'!'."""

    def test_valid_id(self, manager: PlatformManager):
        assert manager._is_valid_platform_id("my_platform") is True
        assert manager._is_valid_platform_id("platform123") is True

    def test_none_is_invalid(self, manager: PlatformManager):
        assert manager._is_valid_platform_id(None) is False

    def test_empty_string_is_invalid(self, manager: PlatformManager):
        assert manager._is_valid_platform_id("") is False

    def test_colon_is_invalid(self, manager: PlatformManager):
        assert manager._is_valid_platform_id("plat:form") is False

    def test_exclamation_is_invalid(self, manager: PlatformManager):
        assert manager._is_valid_platform_id("plat!form") is False


# ===================================================================
# _sanitize_platform_id
# ===================================================================

class TestSanitizePlatformId:
    """_sanitize_platform_id replaces ':'/'!' with '_'."""

    def test_clean_id_unchanged(self, manager: PlatformManager):
        result, changed = manager._sanitize_platform_id("my_platform")
        assert result == "my_platform"
        assert changed is False

    def test_colon_replaced(self, manager: PlatformManager):
        result, changed = manager._sanitize_platform_id("my:platform")
        assert result == "my_platform"
        assert changed is True

    def test_exclamation_replaced(self, manager: PlatformManager):
        result, changed = manager._sanitize_platform_id("my!platform")
        assert result == "my_platform"
        assert changed is True

    def test_both_replaced(self, manager: PlatformManager):
        result, changed = manager._sanitize_platform_id("a:b!c")
        assert result == "a_b_c"
        assert changed is True

    def test_none_returns_none_no_change(self, manager: PlatformManager):
        result, changed = manager._sanitize_platform_id(None)
        assert result is None
        assert changed is False


# ===================================================================
# get_insts
# ===================================================================

class TestGetInsts:
    """get_insts returns the internal platform_insts list."""

    def test_returns_same_list_object(self, manager: PlatformManager):
        assert manager.get_insts() is manager.platform_insts

    def test_empty_by_default(self, manager: PlatformManager):
        assert manager.get_insts() == []


# ===================================================================
# get_all_stats
# ===================================================================

class TestGetAllStats:
    """get_all_stats aggregates stats from all registered platforms."""

    def test_empty_when_no_platforms(self, manager: PlatformManager):
        stats = manager.get_all_stats()
        assert stats["platforms"] == []
        assert stats["summary"]["total"] == 0
        assert stats["summary"]["running"] == 0
        assert stats["summary"]["error"] == 0
        assert stats["summary"]["total_errors"] == 0

    def test_aggregates_mixed_statuses(self, manager: PlatformManager):
        run_mock = MagicMock(spec=Platform)
        run_mock.get_stats.return_value = {
            "id": "p1",
            "type": "mock",
            "display_name": "Mock1",
            "status": PlatformStatus.RUNNING.value,
            "started_at": None,
            "error_count": 0,
            "last_error": None,
            "unified_webhook": False,
            "meta": {},
        }
        err_mock = MagicMock(spec=Platform)
        err_mock.get_stats.return_value = {
            "id": "p2",
            "type": "mock",
            "display_name": "Mock2",
            "status": PlatformStatus.ERROR.value,
            "started_at": None,
            "error_count": 2,
            "last_error": {"message": "fail"},
            "unified_webhook": False,
            "meta": {},
        }
        manager.platform_insts = [run_mock, err_mock]

        stats = manager.get_all_stats()
        assert stats["summary"]["total"] == 2
        assert stats["summary"]["running"] == 1
        assert stats["summary"]["error"] == 1
        assert stats["summary"]["total_errors"] == 2

    def test_recovers_from_broken_platform(self, manager: PlatformManager):
        bad = MagicMock(spec=Platform)
        bad.get_stats.side_effect = Exception("oops")
        bad.config = {"id": "broken"}
        manager.platform_insts = [bad]

        stats = manager.get_all_stats()
        assert stats["summary"]["total"] == 1
        platform_info = stats["platforms"][0]
        assert platform_info["id"] == "broken"
        assert platform_info["status"] == "unknown"
        assert platform_info["type"] == "unknown"


# ===================================================================
# terminate_platform
# ===================================================================

class TestTerminatePlatform:
    """terminate_platform removes the platform from maps and calls terminate."""

    @pytest.mark.asyncio
    async def test_removes_and_terminates(self, manager: PlatformManager):
        p = DummyPlatform(
            {"id": "test_id", "type": "dummy"}, {}, Queue()
        )
        manager._inst_map["test_id"] = {
            "inst": p,
            "client_id": p.client_self_id,
        }
        manager.platform_insts.append(p)

        # Stop the underlying task machinery from actually creating tasks.
        with patch.object(manager, "_stop_platform_task", new_callable=AsyncMock):
            await manager.terminate_platform("test_id")

        assert p._terminated is True
        assert "test_id" not in manager._inst_map
        assert p not in manager.platform_insts


# ===================================================================
# terminate (all)
# ===================================================================

class TestTerminateAll:
    """terminate() cleans up all registered platforms."""

    @pytest.mark.asyncio
    async def test_terminates_all_platforms(self, manager: PlatformManager):
        p1 = DummyPlatform({"id": "p1"}, {}, Queue())
        p2 = DummyPlatform({"id": "p2"}, {}, Queue())
        manager._inst_map["p1"] = {"inst": p1, "client_id": p1.client_self_id}
        manager._inst_map["p2"] = {"inst": p2, "client_id": p2.client_self_id}
        manager.platform_insts = [p1, p2]

        with patch.object(manager, "_stop_platform_task", new_callable=AsyncMock):
            await manager.terminate()

        assert p1._terminated is True
        assert p2._terminated is True
        assert manager.platform_insts == []
        assert manager._inst_map == {}
        assert manager._platform_tasks == {}


# ===================================================================
# load_platform
# ===================================================================

class TestLoadPlatform:
    """load_platform handles disabled flag and invalid IDs."""

    @pytest.mark.asyncio
    async def test_skips_disabled_platform(self, manager: PlatformManager):
        """When enable is False, load_platform should return immediately."""
        with patch("astrbot.core.platform.manager.logger") as mock_logger:
            await manager.load_platform({"enable": False})
            # info should not have been called with the loading message
            for call in mock_logger.info.call_args_list:
                assert "Loading" not in str(call)

    @pytest.mark.asyncio
    async def test_sanitizes_invalid_platform_id(
        self, manager: PlatformManager
    ):
        """A platform ID containing ':' should be sanitized automatically."""
        platform_cfg = {
            "enable": True,
            "type": "nonexistent_type",
            "id": "bad:id",
        }
        with (
            patch.object(manager.astrbot_config, "save_config"),
            patch("astrbot.core.platform.manager.logger"),
        ):
            await manager.load_platform(platform_cfg)

        assert platform_cfg["id"] == "bad_id"

    @pytest.mark.asyncio
    async def test_logs_error_when_type_not_in_map(
        self, manager: PlatformManager
    ):
        """If the platform type is not registered, load_platform logs an error."""
        platform_cfg = {
            "enable": True,
            "type": "no_such_adapter",
            "id": "test_id",
        }
        with patch("astrbot.core.platform.manager.logger") as mock_logger:
            await manager.load_platform(platform_cfg)
            # Should have logged an error about adapter not found
            error_messages = [
                str(c) for c in mock_logger.error.call_args_list
            ]
            assert any("not found" in msg for msg in error_messages)
