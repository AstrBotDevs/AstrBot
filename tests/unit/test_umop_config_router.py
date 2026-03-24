"""Tests for UmopConfigRouter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.umop_config_router import UmopConfigRouter


@pytest.fixture
def mock_sp():
    """Create a mock SharedPreferences."""
    sp = AsyncMock()
    sp.get_async = AsyncMock(return_value={})
    sp.global_put = AsyncMock()
    return sp


@pytest.fixture
def router(mock_sp):
    """Create an UmopConfigRouter instance."""
    return UmopConfigRouter(mock_sp)


class TestSplitUmo:
    """Tests for _split_umo static method."""

    def test_valid_umo_three_parts(self):
        """Split a valid UMO with three parts."""
        result = UmopConfigRouter._split_umo("telegram:private:12345")
        assert result == ("telegram", "private", "12345")

    def test_valid_umo_with_colons_in_session(self):
        """UMO with colon in session_id (split on 3 parts max)."""
        result = UmopConfigRouter._split_umo("discord:group:channel:123")
        assert result == ("discord", "group", "channel:123")

    def test_valid_umo_empty_parts(self):
        """UMO with empty parts."""
        result = UmopConfigRouter._split_umo("telegram::user_456")
        assert result == ("telegram", "", "user_456")

    def test_valid_umo_all_empty(self):
        """UMO with all empty parts."""
        result = UmopConfigRouter._split_umo("::")
        assert result == ("", "", "")

    def test_two_parts_returns_none(self):
        """UMO with only two parts is invalid."""
        result = UmopConfigRouter._split_umo("telegram:private")
        assert result is None

    def test_one_part_returns_none(self):
        """UMO with only one part is invalid."""
        result = UmopConfigRouter._split_umo("telegram")
        assert result is None

    def test_non_string_returns_none(self):
        """UMO that is not a string returns None."""
        assert UmopConfigRouter._split_umo(None) is None
        assert UmopConfigRouter._split_umo(123) is None

    def test_four_parts_returns_three(self):
        """UMO with four parts splits to three (last keeps colon)."""
        result = UmopConfigRouter._split_umo("a:b:c:d")
        assert result == ("a", "b", "c:d")


class TestIsUmoMatch:
    """Tests for _is_umo_match method."""

    def test_exact_match(self):
        """Exact UMO matches."""
        router = UmopConfigRouter(MagicMock())
        router.umop_to_conf_id = {}
        assert (
            router._is_umo_match("telegram:private:123", "telegram:private:123") is True
        )

    def test_wildcard_platform(self):
        """Wildcard '*' in pattern matches any platform."""
        router = UmopConfigRouter(MagicMock())
        router.umop_to_conf_id = {}
        assert router._is_umo_match("*:group:456", "telegram:group:456") is True
        assert router._is_umo_match("*:group:456", "discord:group:456") is True

    def test_wildcard_type(self):
        """Wildcard in type position matches any type."""
        router = UmopConfigRouter(MagicMock())
        router.umop_to_conf_id = {}
        assert router._is_umo_match("telegram:*:123", "telegram:private:123") is True
        assert router._is_umo_match("telegram:*:123", "telegram:group:123") is True

    def test_wildcard_session(self):
        """Wildcard in session position matches any session."""
        router = UmopConfigRouter(MagicMock())
        router.umop_to_conf_id = {}
        assert (
            router._is_umo_match("telegram:private:*", "telegram:private:123") is True
        )
        assert (
            router._is_umo_match("telegram:private:*", "telegram:private:abc") is True
        )

    def test_fnmatch_patterns(self):
        """fnmatch-style patterns work."""
        router = UmopConfigRouter(MagicMock())
        router.umop_to_conf_id = {}
        assert router._is_umo_match("telegram:group:*", "telegram:group:123") is True
        assert router._is_umo_match("*:private:*", "telegram:private:123") is True
        assert router._is_umo_match("*:private:*", "discord:private:456") is True

    def test_empty_pattern_matches_empty(self):
        """Empty string in pattern matches empty string."""
        router = UmopConfigRouter(MagicMock())
        router.umop_to_conf_id = {}
        assert router._is_umo_match("telegram::123", "telegram::123") is True

    def test_non_matching_pattern(self):
        """Pattern that doesn't match returns False."""
        router = UmopConfigRouter(MagicMock())
        router.umop_to_conf_id = {}
        assert (
            router._is_umo_match("telegram:private:123", "discord:private:123") is False
        )
        assert (
            router._is_umo_match("telegram:private:123", "telegram:group:123") is False
        )

    def test_invalid_patternUMO(self):
        """Invalid pattern UMO returns False."""
        router = UmopConfigRouter(MagicMock())
        router.umop_to_conf_id = {}
        assert router._is_umo_match("invalid", "telegram:private:123") is False

    def test_invalid_targetUMO(self):
        """Invalid target UMO returns False."""
        router = UmopConfigRouter(MagicMock())
        router.umop_to_conf_id = {}
        assert router._is_umo_match("telegram:private:123", "invalid") is False

    def test_both_invalid_return_false(self):
        """Both invalid UMOs return False."""
        router = UmopConfigRouter(MagicMock())
        router.umop_to_conf_id = {}
        assert router._is_umo_match("invalid", "also_invalid") is False


class TestGetConfIdForUmop:
    """Tests for get_conf_id_for_umop method."""

    @pytest.mark.asyncio
    async def test_finds_matching_route(self, router):
        """Returns conf_id for matching pattern."""
        router.umop_to_conf_id = {
            "telegram:private:*": "config_1",
            "discord:group:*": "config_2",
        }
        result = router.get_conf_id_for_umop("telegram:private:123")
        assert result == "config_1"

    @pytest.mark.asyncio
    async def test_finds_matching_route_group(self, router):
        """Returns conf_id for group message."""
        router.umop_to_conf_id = {
            "telegram:group:*": "group_config",
        }
        result = router.get_conf_id_for_umop("telegram:group:456")
        assert result == "group_config"

    @pytest.mark.asyncio
    async def test_wildcard_pattern_matches(self, router):
        """Wildcard pattern matches correctly."""
        router.umop_to_conf_id = {
            "*:private:*": "any_private",
        }
        result = router.get_conf_id_for_umop("discord:private:789")
        assert result == "any_private"

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self, router):
        """No matching pattern returns None."""
        router.umop_to_conf_id = {
            "telegram:private:*": "config_1",
        }
        result = router.get_conf_id_for_umop("discord:group:999")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_routing_table(self, router):
        """Empty routing table returns None."""
        router.umop_to_conf_id = {}
        result = router.get_conf_id_for_umop("telegram:private:123")
        assert result is None


class TestUpdateRoutingData:
    """Tests for update_routing_data method."""

    @pytest.mark.asyncio
    async def test_valid_routing_update(self, router, mock_sp):
        """Valid routing dict is stored and persisted."""
        new_routing = {
            "telegram:private:*": "config_telegram",
            "discord:group:*": "config_discord",
        }
        await router.update_routing_data(new_routing)
        assert router.umop_to_conf_id == new_routing
        mock_sp.global_put.assert_called_once_with("umop_config_routing", new_routing)

    @pytest.mark.asyncio
    async def test_invalid_key_raises(self, router):
        """Invalid UMO key raises ValueError."""
        new_routing = {
            "invalid_umo": "config_1",
        }
        with pytest.raises(ValueError, match="umop keys must be"):
            await router.update_routing_data(new_routing)

    @pytest.mark.asyncio
    async def test_one_invalid_key_raises(self, router):
        """One invalid key among valid keys raises ValueError."""
        new_routing = {
            "telegram:private:*": "config_1",
            "invalid": "config_2",
        }
        with pytest.raises(ValueError, match="umop keys must be"):
            await router.update_routing_data(new_routing)


class TestUpdateRoute:
    """Tests for update_route method."""

    @pytest.mark.asyncio
    async def test_valid_route_update(self, router, mock_sp):
        """Valid umo and conf_id updates route and persists."""
        await router.update_route("telegram:group:*", "new_config")
        assert router.umop_to_conf_id["telegram:group:*"] == "new_config"
        mock_sp.global_put.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_umo_raises(self, router):
        """Invalid UMO raises ValueError."""
        with pytest.raises(ValueError, match="umop must be a string"):
            await router.update_route("invalid", "conf")

    @pytest.mark.asyncio
    async def test_invalid_type_raises(self, router):
        """Invalid type raises ValueError."""
        with pytest.raises(ValueError, match="umop must be a string"):
            await router.update_route("only_two_parts", "conf")


class TestDeleteRoute:
    """Tests for delete_route method."""

    @pytest.mark.asyncio
    async def test_delete_existing_route(self, router, mock_sp):
        """Deleting existing route removes it and persists."""
        router.umop_to_conf_id = {
            "telegram:private:*": "config_1",
            "discord:group:*": "config_2",
        }
        await router.delete_route("telegram:private:*")
        assert "telegram:private:*" not in router.umop_to_conf_id
        assert "discord:group:*" in router.umop_to_conf_id
        mock_sp.global_put.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_route_no_persist(self, router, mock_sp):
        """Deleting non-existent route does NOT call persist (early return)."""
        router.umop_to_conf_id = {}
        await router.delete_route("telegram:private:*")
        mock_sp.global_put.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_invalid_umo_raises(self, router):
        """Deleting invalid UMO raises ValueError."""
        with pytest.raises(ValueError, match="umop must be a string"):
            await router.delete_route("invalid")


class TestInitialize:
    """Tests for initialize method."""

    @pytest.mark.asyncio
    async def test_initialize_loads_routing_table(self, router, mock_sp):
        """initialize loads routing table from SharedPreferences."""
        mock_sp.get_async.return_value = {
            "telegram:private:*": "loaded_config",
        }
        await router.initialize()
        assert router.umop_to_conf_id == {
            "telegram:private:*": "loaded_config",
        }
