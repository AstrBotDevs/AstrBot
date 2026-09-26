import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from astrbot.core.config.default import CONFIG_METADATA_3, DEFAULT_CONFIG
from astrbot.core.provider.oauth.openai_oauth_usage_service import (
    OpenAIOAuthUsageService,
)


class UsageServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = SimpleNamespace(
            provider_config={"type": "openai_oauth_chat_completion"}
        )
        self.profiles = {
            "test:FriendMessage:1": {
                "admins_id": ["admin-1"],
                "provider_settings": {"codex_oauth_usage": {"enabled": True}},
            },
            "test:GroupMessage:2": {
                "admins_id": ["admin-2"],
                "provider_settings": {"codex_oauth_usage": {"enabled": True}},
            },
        }
        self.context = SimpleNamespace(
            get_config=Mock(side_effect=lambda *, umo: self.profiles[umo]),
            get_using_provider_async=AsyncMock(return_value=self.provider),
            get_provider_by_id=Mock(return_value=self.provider),
        )
        self.reader = SimpleNamespace(
            read=AsyncMock(return_value={"status": "success", "windows": []}),
            close=AsyncMock(),
        )
        self.service = OpenAIOAuthUsageService(self.context, self.reader)
        self.sender_id = "admin-1"
        self.event = SimpleNamespace(
            is_admin=lambda: True,
            is_private_chat=lambda: True,
            get_sender_id=lambda: self.sender_id,
            unified_msg_origin="test:FriendMessage:1",
        )

    def settings(self, umo="test:FriendMessage:1"):
        return self.profiles[umo]["provider_settings"]["codex_oauth_usage"]

    def test_new_profile_defaults_do_not_advertise_legacy_group_allowlist(self):
        self.assertEqual(
            DEFAULT_CONFIG["provider_settings"]["codex_oauth_usage"],
            {"enabled": True, "provider_id": ""},
        )
        items = CONFIG_METADATA_3["ai_group"]["metadata"]["ai"]["items"]
        self.assertNotIn("provider_settings.codex_oauth_usage.group_allowlist", items)

    async def test_admin_private_uses_current_profile_provider(self):
        result = await self.service.run(self.event)
        self.assertEqual(result["status"], "success")
        self.reader.read.assert_awaited_once_with(self.provider)
        self.context.get_using_provider_async.assert_awaited_once_with(
            self.event.unified_msg_origin
        )
        self.assertTrue(
            all(
                call.kwargs == {"umo": self.event.unified_msg_origin}
                for call in self.context.get_config.call_args_list
            )
        )

    async def test_profile_isolation_and_default_settings(self):
        self.profiles["test:FriendMessage:1"] = {
            "admins_id": ["admin-1"],
            "provider_settings": {},
        }
        self.settings("test:GroupMessage:2")["enabled"] = False
        self.assertEqual((await self.service.run(self.event))["status"], "success")
        self.event.unified_msg_origin = "test:GroupMessage:2"
        self.assertEqual((await self.service.run(self.event))["status"], "disabled")
        self.assertEqual(self.reader.read.await_count, 1)

    async def test_non_admin_is_distinct_and_never_resolves_provider(self):
        self.event.is_admin = lambda: False
        self.assertEqual((await self.service.run(self.event))["status"], "not_admin")
        self.context.get_using_provider_async.assert_not_awaited()
        self.reader.read.assert_not_awaited()

    async def test_admin_group_ignores_legacy_allowlist(self):
        self.event.is_private_chat = lambda: False
        self.event.unified_msg_origin = "test:GroupMessage:2"
        self.sender_id = "admin-2"
        self.settings("test:GroupMessage:2")["group_allowlist"] = ["2"]
        self.assertEqual((await self.service.run(self.event))["status"], "success")
        self.settings("test:GroupMessage:2")["group_allowlist"] = []
        self.assertEqual((await self.service.run(self.event))["status"], "success")

    async def test_non_admin_group_cannot_query_even_with_legacy_allowlist(self):
        self.event.is_private_chat = lambda: False
        self.event.is_admin = lambda: False
        self.event.unified_msg_origin = "test:GroupMessage:2"
        self.sender_id = "admin-2"
        self.settings("test:GroupMessage:2")["group_allowlist"] = [
            self.event.unified_msg_origin
        ]
        self.assertEqual((await self.service.run(self.event))["status"], "not_admin")
        self.reader.read.assert_not_awaited()

    async def test_only_builtin_oauth_provider_can_be_queried(self):
        self.provider.provider_config["type"] = (
            "oauth_plug_openai_codex_chat_completion"
        )
        self.assertEqual(
            (await self.service.run(self.event))["status"], "not_oauth_provider"
        )
        self.reader.read.assert_not_awaited()

    async def test_fixed_target_avoids_chat_model_lookup(self):
        self.settings()["provider_id"] = "openai_oauth/gpt-6-sol"
        self.context.get_using_provider_async.side_effect = RuntimeError(
            "no chat model"
        )
        self.assertEqual((await self.service.run(self.event))["status"], "success")
        self.context.get_provider_by_id.assert_called_once_with(
            "openai_oauth/gpt-6-sol"
        )
        self.context.get_using_provider_async.assert_not_awaited()

    async def test_missing_fixed_target_never_falls_back(self):
        self.settings()["provider_id"] = "missing"
        self.context.get_provider_by_id.return_value = None
        self.assertEqual(
            (await self.service.run(self.event))["status"], "provider_not_found"
        )
        self.context.get_using_provider_async.assert_not_awaited()
        self.reader.read.assert_not_awaited()

    async def test_missing_default_provider_is_reported(self):
        self.context.get_using_provider_async.return_value = None
        self.assertEqual(
            (await self.service.run(self.event))["status"], "provider_not_found"
        )
        self.reader.read.assert_not_awaited()

    async def test_target_change_during_lookup_hides_old_account(self):
        self.settings()["provider_id"] = "openai_oauth/gpt-6-sol"

        def lookup(_provider_id):
            self.settings()["provider_id"] = "openai_oauth/gpt-6-luna"
            return self.provider

        self.context.get_provider_by_id.side_effect = lookup
        self.assertEqual(
            (await self.service.run(self.event))["status"], "authorization_changed"
        )
        self.reader.read.assert_not_awaited()

    async def test_target_change_during_request_hides_old_result(self):
        self.settings()["provider_id"] = "openai_oauth/gpt-6-sol"

        async def read(_provider):
            self.settings()["provider_id"] = "openai_oauth/gpt-6-luna"
            return {"status": "success"}

        self.reader.read.side_effect = read
        self.assertEqual(
            (await self.service.run(self.event))["status"], "authorization_changed"
        )

    async def test_permission_revoked_during_request_hides_result(self):
        async def read(_provider):
            self.event.is_admin = lambda: False
            return {"status": "success"}

        self.reader.read.side_effect = read
        self.assertEqual((await self.service.run(self.event))["status"], "not_admin")

    async def test_profile_group_admin_revoked_during_request(self):
        self.event.is_private_chat = lambda: False
        self.event.unified_msg_origin = "test:GroupMessage:2"
        self.sender_id = "admin-2"

        async def read(_provider):
            self.profiles["test:GroupMessage:2"]["admins_id"] = []
            return {"status": "success"}

        self.reader.read.side_effect = read
        self.assertEqual((await self.service.run(self.event))["status"], "not_admin")

    async def test_each_profile_uses_its_current_admin_list(self):
        self.assertEqual((await self.service.run(self.event))["status"], "success")
        self.event.unified_msg_origin = "test:GroupMessage:2"
        self.event.is_private_chat = lambda: False
        self.assertEqual((await self.service.run(self.event))["status"], "not_admin")
        self.sender_id = "admin-2"
        self.assertEqual((await self.service.run(self.event))["status"], "success")

    async def test_missing_or_invalid_current_admin_list_denies(self):
        for admin_ids in (None, "admin-1", []):
            self.profiles["test:FriendMessage:1"]["admins_id"] = admin_ids
            self.assertEqual(
                (await self.service.run(self.event))["status"], "not_admin"
            )
        self.reader.read.assert_not_awaited()

    async def test_disabled_and_closed_never_query(self):
        self.settings()["enabled"] = False
        self.assertEqual((await self.service.run(self.event))["status"], "disabled")
        self.settings()["enabled"] = True
        await self.service.close()
        self.assertEqual((await self.service.run(self.event))["status"], "closed")
        self.reader.close.assert_awaited_once()
        self.reader.read.assert_not_awaited()

    async def test_lookup_failure_is_redacted(self):
        self.context.get_using_provider_async.side_effect = RuntimeError(
            "secret-account"
        )
        self.assertEqual(await self.service.run(self.event), {"status": "unavailable"})
