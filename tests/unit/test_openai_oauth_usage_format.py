import unittest

from astrbot.core.provider.oauth.openai_oauth_usage_format import format_usage


class UsageFormatTests(unittest.TestCase):
    def test_success_formats_windows_and_beijing_reset(self):
        text = format_usage(
            {
                "status": "success",
                "cached": True,
                "observed_at": "2026-09-26T15:09:57+00:00",
                "plan_type": "pro",
                "windows": [
                    {
                        "limit_id": "codex",
                        "name": None,
                        "used_percent": 61,
                        "remaining_percent": 39,
                        "window_seconds": 604800,
                        "reset_at": 1791019226,
                    }
                ],
            }
        )
        self.assertIn("已用 61%，剩余 39%", text)
        self.assertIn("7 天", text)
        self.assertIn("2026-10-03 17:20:26", text)
        self.assertIn("北京时间", text)
        self.assertIn("缓存", text)

    def test_missing_fields_never_look_like_zero(self):
        text = format_usage(
            {
                "status": "success",
                "windows": [{"used_percent": None, "remaining_percent": None}],
            }
        )
        self.assertIn("未知", text)
        self.assertNotIn("0%", text)
        self.assertIn("未返回", format_usage({"status": "success", "windows": []}))

    def test_failure_is_explicit_without_raw_error(self):
        text = format_usage({"status": "reauth_required", "error": "secret"})
        self.assertIn("凭据", text)
        self.assertNotIn("secret", text)
        self.assertNotIn("已用", text)

    def test_permission_rejections_are_distinct(self):
        self.assertIn("管理员", format_usage({"status": "not_admin"}))
        self.assertIn("此群聊", format_usage({"status": "group_not_allowed"}))
