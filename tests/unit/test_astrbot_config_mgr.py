"""Mock-based unit tests for AstrBotConfigManager."""

from __future__ import annotations

import uuid as uuid_mod
from unittest.mock import MagicMock, call, patch

import pytest

from astrbot.core.astrbot_config_mgr import (
    AstrBotConfigManager,
    ConfInfo,
    DEFAULT_CONFIG_CONF_INFO,
)


@pytest.fixture
def mock_default_config():
    return MagicMock()


@pytest.fixture
def mock_ucr():
    return MagicMock()


@pytest.fixture
def mock_sp():
    return MagicMock()


@pytest.fixture
def acm(mock_default_config, mock_ucr, mock_sp):
    """Build an AstrBotConfigManager with all dependencies mocked."""
    with patch.object(AstrBotConfigManager, "_load_all_configs", return_value=None):
        acm = AstrBotConfigManager(mock_default_config, mock_ucr, mock_sp)
    return acm


class TestAstrBotConfigManagerConstruction:
    """Construction and initialisation."""

    def test_init_stores_dependencies(self, acm, mock_default_config, mock_ucr, mock_sp):
        assert acm.sp is mock_sp
        assert acm.ucr is mock_ucr
        assert acm.confs["default"] is mock_default_config

    def test_init_sets_abconf_data_to_none(self, acm):
        assert acm.abconf_data is None

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

    def test_get_conf_returns_mapped(self, acm, mock_ucr, mock_sp):
        conf_id = "uuid-abc"
        mock_ucr.get_conf_id_for_umop.return_value = conf_id
        mock_sp.get.return_value = {conf_id: {"path": "abconf_uuid-abc.json", "name": "test"}}
        mock_conf = MagicMock()
        acm.confs[conf_id] = mock_conf
        conf = acm.get_conf("qq:group:456")
        assert conf is mock_conf

    def test_get_conf_fallback_when_mapped_not_loaded(self, acm, mock_ucr, mock_sp, mock_default_config):
        conf_id = "uuid-missing"
        mock_ucr.get_conf_id_for_umop.return_value = conf_id
        mock_sp.get.return_value = {conf_id: {"path": "nope.json", "name": "x"}}
        conf = acm.get_conf("qq:group:789")
        assert conf is mock_default_config


class TestGetConfInfo:
    """get_conf_info method."""

    def test_get_conf_info_returns_default_when_unmapped(self, acm, mock_ucr):
        mock_ucr.get_conf_id_for_umop.return_value = None
        info = acm.get_conf_info("qq:group:1")
        assert info["id"] == "default"

    def test_get_conf_info_returns_mapped_meta(self, acm, mock_ucr, mock_sp):
        conf_id = "uuid-mapped"
        mock_ucr.get_conf_id_for_umop.return_value = conf_id
        mock_sp.get.return_value = {conf_id: {"path": "cfg.json", "name": "MyCfg"}}
        info = acm.get_conf_info("qq:group:2")
        assert info["id"] == conf_id
        assert info["path"] == "cfg.json"
        assert "umop" not in info


class TestGetConfList:
    """get_conf_list method."""

    def test_get_conf_list_includes_default(self, acm):
        acm.abconf_data = {}
        lst = acm.get_conf_list()
        assert DEFAULT_CONFIG_CONF_INFO in lst

    def test_get_conf_list_returns_all_abconfs(self, acm, mock_sp):
        mock_sp.get.return_value = {
            "u1": {"path": "a.json", "name": "A"},
            "u2": {"path": "b.json", "name": "B"},
        }
        acm.abconf_data = mock_sp.get.return_value
        lst = acm.get_conf_list()
        ids = {item["id"] for item in lst}
        assert "u1" in ids
        assert "u2" in ids
        assert "default" in ids

    def test_get_conf_list_skips_non_dict(self, acm, mock_sp):
        mock_sp.get.return_value = {
            "u1": {"path": "a.json", "name": "A"},
            "u2": "not a dict",
        }
        acm.abconf_data = mock_sp.get.return_value
        lst = acm.get_conf_list()
        assert len(lst) == 2  # only u1 + default


class TestCreateConf:
    """create_conf method."""

    @patch("astrbot.core.astrbot_config_mgr.uuid.uuid4", return_value=uuid_mod.UUID("00000000-0000-0000-0000-000000000001"))
    @patch("astrbot.core.astrbot_config_mgr.AstrBotConfig")
    @patch("astrbot.core.astrbot_config_mgr.get_astrbot_config_path", return_value="/cfg")
    def test_create_conf_creates_and_saves(
        self,
        mock_get_path,
        mock_Config,
        mock_uuid,
        acm,
    ):
        mock_conf_instance = MagicMock()
        mock_Config.return_value = mock_conf_instance
        conf_id = acm.create_conf(config={"key": "val"}, name="myname")
        mock_Config.assert_called_once()
        mock_conf_instance.save_config.assert_called_once()
        assert conf_id in acm.confs
        assert acm.confs[conf_id] is mock_conf_instance


class TestDeleteConf:
    """delete_conf method."""

    def test_delete_conf_raises_on_default(self, acm):
        with pytest.raises(ValueError, match="不能删除默认配置文件"):
            acm.delete_conf("default")

    def test_delete_conf_returns_false_when_not_found(self, acm, mock_sp):
        mock_sp.get.return_value = {}
        result = acm.delete_conf("nonexistent")
        assert result is False

    @patch("astrbot.core.astrbot_config_mgr.os.remove")
    @patch("astrbot.core.astrbot_config_mgr.os.path.exists", return_value=True)
    @patch("astrbot.core.astrbot_config_mgr.get_astrbot_config_path", return_value="/cfg")
    def test_delete_conf_removes_file_and_mapping(
        self,
        mock_get_path,
        mock_exists,
        mock_remove,
        acm,
        mock_sp,
    ):
        conf_id = "uuid-to-delete"
        mock_sp.get.return_value = {conf_id: {"path": "abconf_uuid-to-delete.json", "name": "x"}}
        acm.abconf_data = mock_sp.get.return_value

        result = acm.delete_conf(conf_id)
        assert result is True
        mock_remove.assert_called_once()
        mock_sp.put.assert_called()

    @patch("astrbot.core.astrbot_config_mgr.os.path.exists", return_value=False)
    @patch("astrbot.core.astrbot_config_mgr.get_astrbot_config_path", return_value="/cfg")
    def test_delete_conf_handles_missing_file(
        self, mock_get_path, mock_exists, acm, mock_sp
    ):
        conf_id = "uuid-missing-file"
        mock_sp.get.return_value = {conf_id: {"path": "gone.json", "name": "x"}}
        acm.abconf_data = mock_sp.get.return_value
        acm.confs[conf_id] = MagicMock()

        result = acm.delete_conf(conf_id)
        assert result is True
        assert conf_id not in acm.confs


class TestUpdateConfInfo:
    """update_conf_info method."""

    def test_update_raises_on_default(self, acm):
        with pytest.raises(ValueError, match="不能更新"):
            acm.update_conf_info("default", name="new")

    def test_update_returns_false_when_not_found(self, acm, mock_sp):
        mock_sp.get.return_value = {}
        result = acm.update_conf_info("nonexistent", name="new")
        assert result is False

    def test_update_renames(self, acm, mock_sp):
        conf_id = "uuid-rename"
        mock_sp.get.return_value = {conf_id: {"path": "x.json", "name": "old"}}
        acm.abconf_data = mock_sp.get.return_value
        result = acm.update_conf_info(conf_id, name="new_name")
        assert result is True
        assert acm.abconf_data[conf_id]["name"] == "new_name"


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
        val = acm.g(umo="qq:group:1", key="some.setting")
        assert val == 42
        fake_conf.get.assert_called_with("some.setting", None)


class TestSaveConfMapping:
    """_save_conf_mapping internal method."""

    def test_save_conf_mapping_stores_and_updates_abconf_data(self, acm, mock_sp):
        mock_sp.get.return_value = {}
        acm._save_conf_mapping(abconf_path="new.json", abconf_id="new-id", abconf_name="display")
        mock_sp.put.assert_called()
        assert "new-id" in acm.abconf_data


class TestLoadConfMappingEdgeCases:
    """_load_conf_mapping edge cases."""

    def test_load_conf_mapping_with_invalid_umo_str(self, acm, mock_ucr):
        """An invalid umo string that can't be parsed as MessageSession returns default."""
        mock_ucr.get_conf_id_for_umop.side_effect = Exception("parse error")
        info = acm._load_conf_mapping("bad_format")
        assert info["id"] == "default"

    def test_load_conf_mapping_checks_meta_is_dict(self, acm, mock_ucr, mock_sp):
        """If abconf metadata is not a dict, returns default."""
        conf_id = "uuid-non-dict"
        mock_ucr.get_conf_id_for_umop.return_value = conf_id
        mock_sp.get.return_value = {conf_id: "not a dict"}
        info = acm._load_conf_mapping("qq:friend:1")
        assert info["id"] == "default"
