"""A cleared Satori heartbeat field must not turn the ping loop into a busy loop.

``satori_heartbeat_interval`` and ``satori_reconnect_delay`` are declared
``"type": "int"`` with no minimum (``astrbot/core/config/default.py``), and the dashboard's numeric
field writes ``0`` when the box is cleared (``toNumber`` maps ``parseFloat('')`` to ``0``,
``dashboard/src/components/shared/ConfigItemRenderer.vue``).  Both values are consumed by
``asyncio.sleep`` -- ``heartbeat_loop`` sleeps ``self.heartbeat_interval`` between two PING frames
and the reconnect loop uses ``self.reconnect_delay`` as the base of its exponential backoff -- so a
``0`` removes the pause instead of removing the feature.  Measured against the real
``heartbeat_loop`` with ``satori_heartbeat_interval=0``: 32010 PING frames were sent over the
WebSocket in 0.2 s, while the documented default of ``10`` sent 0 in the same window.  A value that
came from a text field or a quoted config entry is worse: ``asyncio.sleep('10')`` raises
``TypeError: '<=' not supported between instances of 'str' and 'int'``, the heartbeat task's own
``except Exception`` logs it as ``心跳任务异常`` and returns, and the connection keeps running with
no heartbeat at all until the next disconnect.
"""

import asyncio

from astrbot.core.platform.sources.satori.satori_adapter import SatoriPlatformAdapter

DEFAULTS = {
    "satori_heartbeat_interval": 10,
    "satori_reconnect_delay": 5,
}


def _adapter(**overrides) -> SatoriPlatformAdapter:
    config = {"id": "satori_test", **overrides}
    return SatoriPlatformAdapter(config, {"settings": {}}, asyncio.Queue())


def test_cleared_fields_fall_back_to_a_positive_floor():
    adapter = _adapter(satori_heartbeat_interval=0, satori_reconnect_delay=0)
    assert adapter.heartbeat_interval == 1
    assert adapter.reconnect_delay == 1


def test_negative_fields_are_clamped():
    adapter = _adapter(satori_heartbeat_interval=-1, satori_reconnect_delay=-10)
    assert adapter.heartbeat_interval == 1
    assert adapter.reconnect_delay == 1


def test_a_fractional_interval_cannot_lose_the_pause():
    adapter = _adapter(satori_heartbeat_interval=0.5)
    assert adapter.heartbeat_interval == 1


def test_non_numeric_fields_do_not_kill_the_platform_adapter():
    """A value that would raise inside the heartbeat task falls back to the default."""
    adapter = _adapter(
        satori_heartbeat_interval="",
        satori_reconnect_delay=None,
    )
    assert adapter.heartbeat_interval == DEFAULTS["satori_heartbeat_interval"]
    assert adapter.reconnect_delay == DEFAULTS["satori_reconnect_delay"]


def test_a_numeric_string_is_respected():
    adapter = _adapter(satori_heartbeat_interval="30", satori_reconnect_delay="8")
    assert adapter.heartbeat_interval == 30
    assert adapter.reconnect_delay == 8


def test_a_tuned_value_is_kept():
    adapter = _adapter(satori_heartbeat_interval=60, satori_reconnect_delay=20)
    assert adapter.heartbeat_interval == 60
    assert adapter.reconnect_delay == 20


def test_unset_fields_keep_the_documented_defaults():
    adapter = _adapter()
    assert adapter.heartbeat_interval == DEFAULTS["satori_heartbeat_interval"]
    assert adapter.reconnect_delay == DEFAULTS["satori_reconnect_delay"]
