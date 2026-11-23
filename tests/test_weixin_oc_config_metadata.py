"""Tests for personal WeChat configuration metadata."""

from astrbot.core.config.default import PERSONAL_WECHAT_CONFIG_METADATA


def test_personal_wechat_only_exposes_user_adjustable_fields():
    """Show only the personal WeChat fields intended for user adjustment."""
    visible_fields = {
        key
        for key, metadata in PERSONAL_WECHAT_CONFIG_METADATA.items()
        if not metadata.get("invisible", False)
    }

    assert visible_fields == {
        "weixin_oc_base_url",
        "weixin_oc_long_poll_timeout_ms",
        "weixin_oc_api_timeout_ms",
    }


def test_personal_wechat_runtime_state_fields_are_hidden():
    """Hide login state persisted outside the personal WeChat template."""
    for key in (
        "weixin_oc_account_id",
        "weixin_oc_sync_buf",
        "weixin_oc_context_tokens",
    ):
        assert PERSONAL_WECHAT_CONFIG_METADATA[key]["invisible"] is True
