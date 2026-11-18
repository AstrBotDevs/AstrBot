"""The two user-adjustable weixin_oc timeouts must not disable the HTTP timeout.

``weixin_oc_long_poll_timeout_ms`` and ``weixin_oc_api_timeout_ms`` are the only
personal-WeChat fields the dashboard exposes for tuning (see
``tests/test_weixin_oc_config_metadata.py``), and its numeric field writes ``0``
when the box is cleared (``toNumber`` maps ``parseFloat('')`` to ``0``).  Aiohttp
treats ``ClientTimeout(total=0)`` as "no timeout" -- measured here: a request that
sleeps 0.4 s returns 200 with ``total=0`` and raises ``TimeoutError`` with
``total=0.001`` -- so a cleared field leaves the receive loop waiting on a single
stalled ``getupdates`` connection forever, which is exactly the case its
``except asyncio.TimeoutError`` retry branch exists for.
"""

import asyncio

import pytest

from astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter import (
    WeixinOCAdapter,
)

DEFAULTS = {
    "weixin_oc_qr_poll_interval": 1,
    "weixin_oc_long_poll_timeout_ms": 35_000,
    "weixin_oc_api_timeout_ms": 120_000,
}
MINIMUM_TIMEOUT_MS = 1_000


def _adapter(**overrides) -> WeixinOCAdapter:
    config = {"id": "weixin_oc_test", **overrides}
    return WeixinOCAdapter(config, {"settings": {}}, asyncio.Queue())


@pytest.mark.parametrize(
    ("config_key", "value", "attr"),
    [
        ("weixin_oc_api_timeout_ms", 0, "api_timeout_ms"),
        ("weixin_oc_long_poll_timeout_ms", 0, "long_poll_timeout_ms"),
        ("weixin_oc_api_timeout_ms", -1, "api_timeout_ms"),
        ("weixin_oc_long_poll_timeout_ms", -35_000, "long_poll_timeout_ms"),
        ("weixin_oc_api_timeout_ms", 200, "api_timeout_ms"),
    ],
)
def test_timeouts_below_the_floor_are_clamped(config_key, value, attr):
    adapter = _adapter(**{config_key: value})

    assert getattr(adapter, attr) == MINIMUM_TIMEOUT_MS
    if attr == "api_timeout_ms":
        assert adapter.client.api_timeout_ms == MINIMUM_TIMEOUT_MS


def test_a_tuned_value_is_kept():
    adapter = _adapter(
        weixin_oc_api_timeout_ms=5_000,
        weixin_oc_long_poll_timeout_ms=45_000,
    )
    assert adapter.api_timeout_ms == 5_000
    assert adapter.long_poll_timeout_ms == 45_000


def test_unset_fields_keep_the_documented_defaults():
    adapter = _adapter()
    assert adapter.api_timeout_ms == DEFAULTS["weixin_oc_api_timeout_ms"]
    assert adapter.long_poll_timeout_ms == DEFAULTS["weixin_oc_long_poll_timeout_ms"]
    assert adapter.qr_poll_interval == DEFAULTS["weixin_oc_qr_poll_interval"]


def test_a_non_numeric_field_does_not_kill_the_platform_adapter():
    """PlatformManager.initialize only logs a bare `invalid literal ...`."""
    adapter = _adapter(
        weixin_oc_api_timeout_ms="",
        weixin_oc_long_poll_timeout_ms=None,
        weixin_oc_qr_poll_interval="",
    )
    assert adapter.api_timeout_ms == DEFAULTS["weixin_oc_api_timeout_ms"]
    assert adapter.long_poll_timeout_ms == DEFAULTS["weixin_oc_long_poll_timeout_ms"]
    assert adapter.qr_poll_interval == DEFAULTS["weixin_oc_qr_poll_interval"]
