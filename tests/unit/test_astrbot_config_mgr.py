"""Mock-based unit tests for AstrBotConfigManager."""

from __future__ import annotations

import asyncio
import uuid as uuid_mod
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.astrbot_config_mgr import (
    DEFAULT_CONFIG_CONF_INFO,
    AstrBotConfigManager,
)


@pytest.fixture
def mock_default_config():
    return MagicMock()


@pytest.fixture
def mock_ucr():
    return MagicMock()


@pytest.fixture
def mock_sp():
    sp = MagicMock()
    sp.global_get = AsyncMock(return_value={})
    sp.global_put = AsyncMock()
    return sp


@pytest.fixture
def uninitialized_acm(mock_default_config, mock_ucr, mock_sp):
    """Build an uninitialized manager with all dependencies mocked."""
    return AstrBotConfigManager(mock_default_config, mock_ucr, mock_sp)


@pytest.fixture
def acm(uninitialized_acm):
    """Build a manager with its persistent profile mapping initialized."""
    uninitialized_acm.abconf_data = {}
    return uninitialized_acm


class TestAstrBotConfigManagerConstruction:
    """Construction and initialisation."""

    def test_init_stores_dependencies(
        self, acm, mock_default_config, mock_ucr, mock_sp
    ):
        assert acm.sp is mock_sp
        assert acm.ucr is mock_ucr
        assert acm.confs["default"] is mock_default_config

    def test_init_sets_abconf_data_to_none(self, uninitialized_acm):
        assert uninitialized_acm.abconf_data is None

    @pytest.mark.asyncio
    async def test_initialize_loads_mapping(
        self,
        uninitialized_acm,
        mock_sp,
    ):
        mapping = {"profile": {"path": "profile.json", "name": "Profile"}}
        mock_sp.global_get.return_value = mapping

        with patch.object(uninitialized_acm, "_load_all_configs") as load_all:
            await uninitialized_acm.initialize()

        assert uninitialized_acm.abconf_data is mapping
        mock_sp.global_get.assert_awaited_once_with("abconf_mapping", {})
        load_all.assert_called_once_with()

    def test_default_conf_property(self, acm, mock_default_config):
        assert acm.default_conf is mock_default_config


class TestGetConf:
    """get_conf method."""

    def test_get_conf_returns_default_when_umo_none(self, acm):
        conf = acm.get_conf(None)
        assert conf is acm.confs["default"]

    def test_get_conf_returns_default_when_umo_not_mapped(self, acm, mock_ucr):
        mock_ucr.get_conf_id_for_umop.return_value = None
        conf = acm.get_conf("test:group:123")
        assert conf is acm.confs["default"]

    def test_get_conf_returns_mapped(self, acm, mock_ucr):
        conf_id = "uuid-abc"
        mock_ucr.get_conf_id_for_umop.return_value = conf_id
        acm.abconf_data = {
            conf_id: {"path": "abconf_uuid-abc.json", "name": "test"},
        }
        mock_conf = MagicMock()
        acm.confs[conf_id] = mock_conf
        conf = acm.get_conf("qq:GroupMessage:456")
        assert conf is mock_conf

    def test_get_conf_fallback_when_mapped_not_loaded(
        self,
        acm,
        mock_ucr,
        mock_default_config,
    ):
        conf_id = "uuid-missing"
        mock_ucr.get_conf_id_for_umop.return_value = conf_id
        acm.abconf_data = {conf_id: {"path": "nope.json", "name": "x"}}
        conf = acm.get_conf("qq:GroupMessage:789")
        assert conf is mock_default_config


class TestGetConfInfo:
    """get_conf_info method."""

    def test_get_conf_info_returns_default_when_unmapped(self, acm, mock_ucr):
        mock_ucr.get_conf_id_for_umop.return_value = None
        info = acm.get_conf_info("qq:GroupMessage:1")
        assert info["id"] == "default"

    def test_get_conf_info_returns_mapped_meta(self, acm, mock_ucr):
        conf_id = "uuid-mapped"
        mock_ucr.get_conf_id_for_umop.return_value = conf_id
        acm.abconf_data = {
            conf_id: {"path": "cfg.json", "name": "MyCfg"},
        }
        info = acm.get_conf_info("qq:GroupMessage:2")
        assert info["id"] == conf_id
        assert info["path"] == "cfg.json"
        assert "umop" not in info


class TestGetConfList:
    """get_conf_list method."""

    def test_get_conf_list_includes_default(self, acm):
        acm.abconf_data = {}
        lst = acm.get_conf_list()
        assert DEFAULT_CONFIG_CONF_INFO in lst

    def test_get_conf_list_returns_all_abconfs(self, acm):
        acm.abconf_data = {
            "u1": {"path": "a.json", "name": "A"},
            "u2": {"path": "b.json", "name": "B"},
        }
        lst = acm.get_conf_list()
        ids = {item["id"] for item in lst}
        assert "u1" in ids
        assert "u2" in ids
        assert "default" in ids

    def test_get_conf_list_skips_non_dict(self, acm):
        acm.abconf_data = {
            "u1": {"path": "a.json", "name": "A"},
            "u2": "not a dict",
        }
        lst = acm.get_conf_list()
        assert len(lst) == 2  # only u1 + default


class TestCreateConf:
    """create_conf method."""

    @patch(
        "astrbot.core.astrbot_config_mgr.uuid.uuid4",
        return_value=uuid_mod.UUID("00000000-0000-0000-0000-000000000001"),
    )
    @patch("astrbot.core.astrbot_config_mgr.AstrBotConfig")
    @patch(
        "astrbot.core.astrbot_config_mgr.get_astrbot_config_path", return_value="/cfg"
    )
    @pytest.mark.asyncio
    async def test_create_conf_creates_and_saves(
        self,
        mock_get_path,
        mock_Config,
        mock_uuid,
        acm,
        mock_sp,
    ):
        mock_conf_instance = MagicMock()
        mock_Config.return_value = mock_conf_instance
        conf_id = await acm.create_conf(config={"key": "val"}, name="myname")
        expected_path = "/cfg/abconf_00000000-0000-0000-0000-000000000001.json"
        mock_get_path.assert_called_once_with()
        mock_Config.assert_called_once_with(
            config_path=expected_path,
            default_config={"key": "val"},
        )
        mock_conf_instance.save_config.assert_called_once_with()
        assert conf_id in acm.confs
        assert acm.confs[conf_id] is mock_conf_instance
        mock_sp.global_get.assert_awaited_once_with("abconf_mapping", {})
        mock_sp.global_put.assert_awaited_once_with(
            "abconf_mapping",
            {
                conf_id: {
                    "path": f"abconf_{conf_id}.json",
                    "name": "myname",
                },
            },
        )


class TestDeleteConf:
    """delete_conf method."""

    @pytest.mark.asyncio
    async def test_delete_conf_raises_on_default(self, acm):
        with pytest.raises(ValueError, match="不能删除默认配置文件"):
            await acm.delete_conf("default")

    @pytest.mark.asyncio
    async def test_delete_conf_returns_false_when_not_found(self, acm, mock_sp):
        result = await acm.delete_conf("nonexistent")
        assert result is False
        mock_sp.global_get.assert_awaited_once_with("abconf_mapping", {})
        mock_sp.global_put.assert_not_awaited()

    @patch("astrbot.core.astrbot_config_mgr.os.remove")
    @patch("astrbot.core.astrbot_config_mgr.os.path.exists", return_value=True)
    @patch(
        "astrbot.core.astrbot_config_mgr.get_astrbot_config_path", return_value="/cfg"
    )
    @pytest.mark.asyncio
    async def test_delete_conf_removes_file_and_mapping(
        self,
        mock_get_path,
        mock_exists,
        mock_remove,
        acm,
        mock_sp,
    ):
        conf_id = "uuid-to-delete"
        mapping = {
            conf_id: {"path": "abconf_uuid-to-delete.json", "name": "x"},
        }
        mock_sp.global_get.return_value = mapping
        acm.abconf_data = mapping

        result = await acm.delete_conf(conf_id)
        assert result is True
        mock_get_path.assert_called_once_with()
        mock_exists.assert_called_once_with("/cfg/abconf_uuid-to-delete.json")
        mock_remove.assert_called_once_with("/cfg/abconf_uuid-to-delete.json")
        mock_sp.global_put.assert_awaited_once_with("abconf_mapping", {})
        assert acm.abconf_data == {}

    @patch("astrbot.core.astrbot_config_mgr.os.path.exists", return_value=False)
    @patch(
        "astrbot.core.astrbot_config_mgr.get_astrbot_config_path", return_value="/cfg"
    )
    @pytest.mark.asyncio
    async def test_delete_conf_handles_missing_file(
        self, mock_get_path, mock_exists, acm, mock_sp
    ):
        conf_id = "uuid-missing-file"
        mapping = {conf_id: {"path": "gone.json", "name": "x"}}
        mock_sp.global_get.return_value = mapping
        acm.abconf_data = mapping
        acm.confs[conf_id] = MagicMock()

        result = await acm.delete_conf(conf_id)
        assert result is True
        mock_get_path.assert_called_once_with()
        mock_exists.assert_called_once_with("/cfg/gone.json")
        assert conf_id not in acm.confs
        mock_sp.global_put.assert_awaited_once_with("abconf_mapping", {})

    @pytest.mark.asyncio
    @patch("astrbot.core.astrbot_config_mgr.os.remove", side_effect=OSError("busy"))
    @patch("astrbot.core.astrbot_config_mgr.os.path.exists", return_value=True)
    @patch(
        "astrbot.core.astrbot_config_mgr.get_astrbot_config_path",
        return_value="/cfg",
    )
    async def test_delete_conf_preserves_state_when_file_removal_fails(
        self,
        mock_get_path,
        mock_exists,
        mock_remove,
        acm,
        mock_sp,
    ):
        conf_id = "uuid-busy"
        mapping = {conf_id: {"path": "busy.json", "name": "Busy"}}
        profile = MagicMock()
        mock_sp.global_get.return_value = mapping
        acm.abconf_data = mapping
        acm.confs[conf_id] = profile

        assert await acm.delete_conf(conf_id) is False

        mock_get_path.assert_called_once_with()
        mock_exists.assert_called_once_with("/cfg/busy.json")
        mock_remove.assert_called_once_with("/cfg/busy.json")
        assert acm.confs[conf_id] is profile
        assert acm.abconf_data is mapping
        mock_sp.global_put.assert_not_awaited()


class TestUpdateConfInfo:
    """update_conf_info method."""

    @pytest.mark.asyncio
    async def test_update_raises_on_default(self, acm):
        with pytest.raises(ValueError, match="不能更新"):
            await acm.update_conf_info("default", name="new")

    @pytest.mark.asyncio
    async def test_update_returns_false_when_not_found(self, acm, mock_sp):
        result = await acm.update_conf_info("nonexistent", name="new")
        assert result is False
        mock_sp.global_put.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_renames(self, acm, mock_sp):
        conf_id = "uuid-rename"
        mapping = {conf_id: {"path": "x.json", "name": "old"}}
        mock_sp.global_get.return_value = mapping
        acm.abconf_data = mapping
        result = await acm.update_conf_info(conf_id, name="new_name")
        assert result is True
        assert acm.abconf_data[conf_id]["name"] == "new_name"
        mock_sp.global_put.assert_awaited_once_with(
            "abconf_mapping",
            {conf_id: {"path": "x.json", "name": "new_name"}},
        )


class TestG:
    """g (generic getter) method."""

    def test_g_without_umo_uses_default(self, acm, mock_default_config):
        mock_default_config.get.return_value = "fallback"
        val = acm.g(umo=None, key="missing")
        mock_default_config.get.assert_called_with("missing", None)
        assert val == "fallback"

    def test_g_with_umo_uses_get_conf(self, acm):
        fake_conf = MagicMock()
        fake_conf.get.return_value = 42
        acm.get_conf = MagicMock(return_value=fake_conf)
        val = acm.g(umo="qq:GroupMessage:1", key="some.setting")
        assert val == 42
        fake_conf.get.assert_called_with("some.setting", None)


class TestSaveConfMapping:
    """_save_conf_mapping internal method."""

    @pytest.mark.asyncio
    async def test_save_conf_mapping_stores_and_updates_abconf_data(
        self,
        acm,
        mock_sp,
    ):
        await acm._save_conf_mapping(
            abconf_path="new.json",
            abconf_id="new-id",
            abconf_name="display",
        )
        mock_sp.global_get.assert_awaited_once_with("abconf_mapping", {})
        mock_sp.global_put.assert_awaited_once_with(
            "abconf_mapping",
            {"new-id": {"path": "new.json", "name": "display"}},
        )
        assert "new-id" in acm.abconf_data


class TestConcurrentMutations:
    """Concurrent profile changes preserve every persisted mapping."""

    @pytest.mark.asyncio
    async def test_concurrent_creates_do_not_lose_profile_mappings(
        self,
        acm,
        mock_sp,
        tmp_path,
    ):
        persisted: dict[str, dict[str, str]] = {}

        async def load_mapping(_key, _default):
            snapshot = {key: value.copy() for key, value in persisted.items()}
            await asyncio.sleep(0)
            return snapshot

        async def save_mapping(_key, mapping):
            await asyncio.sleep(0)
            persisted.clear()
            persisted.update(
                {key: value.copy() for key, value in mapping.items()},
            )

        mock_sp.global_get.side_effect = load_mapping
        mock_sp.global_put.side_effect = save_mapping
        profile_ids = [
            uuid_mod.UUID("00000000-0000-0000-0000-000000000001"),
            uuid_mod.UUID("00000000-0000-0000-0000-000000000002"),
        ]

        with (
            patch(
                "astrbot.core.astrbot_config_mgr.get_astrbot_config_path",
                return_value=str(tmp_path),
            ),
            patch("astrbot.core.astrbot_config_mgr.AstrBotConfig"),
            patch(
                "astrbot.core.astrbot_config_mgr.uuid.uuid4",
                side_effect=profile_ids,
            ),
        ):
            created_ids = await asyncio.gather(
                acm.create_conf(name="First"),
                acm.create_conf(name="Second"),
            )

        assert set(persisted) == set(created_ids)
        assert set(created_ids).issubset(acm.confs)
        assert mock_sp.global_get.await_count == 2
        assert mock_sp.global_put.await_count == 2


class TestLoadConfMappingEdgeCases:
    """_load_conf_mapping edge cases."""

    def test_load_conf_mapping_with_invalid_umo_str(self, acm, mock_ucr):
        """An invalid umo string that can't be parsed as MessageSession returns default."""
        mock_ucr.get_conf_id_for_umop.side_effect = Exception("parse error")
        info = acm._load_conf_mapping("bad_format")
        assert info["id"] == "default"

    def test_load_conf_mapping_checks_meta_is_dict(self, acm, mock_ucr):
        """If abconf metadata is not a dict, returns default."""
        conf_id = "uuid-non-dict"
        mock_ucr.get_conf_id_for_umop.return_value = conf_id
        acm.abconf_data = {conf_id: "not a dict"}
        info = acm._load_conf_mapping("qq:friend:1")
        assert info["id"] == "default"
