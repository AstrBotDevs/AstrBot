from astrbot.core.computer.sandbox_timeouts import (
    DEFAULT_SANDBOX_LEASE_TIMEOUT_SECONDS,
    expires_at_from_timeout,
    idle_cleanup_at_from_record,
    lease_is_active,
    resolve_sandbox_timeout,
)


def test_resolve_sandbox_timeout_prefers_generic_key_over_alias():
    config = {"sandbox_ttl": 0, "cua_ttl": 3600}

    resolved = resolve_sandbox_timeout(
        config,
        "sandbox_ttl",
        aliases=("cua_ttl",),
        default=3600,
    )

    assert resolved == 0


def test_resolve_sandbox_timeout_uses_legacy_alias_when_generic_missing():
    config = {"shipyard_ttl": "120"}

    resolved = resolve_sandbox_timeout(
        config,
        "sandbox_ttl",
        aliases=("shipyard_ttl",),
        default=3600,
    )

    assert resolved == 120


def test_resolve_sandbox_timeout_falls_back_for_invalid_values():
    assert (
        resolve_sandbox_timeout(
            {"sandbox_lease_timeout": "forever"},
            "sandbox_lease_timeout",
            default=DEFAULT_SANDBOX_LEASE_TIMEOUT_SECONDS,
        )
        == DEFAULT_SANDBOX_LEASE_TIMEOUT_SECONDS
    )


def test_zero_lease_timeout_is_an_indefinite_active_lease():
    assert lease_is_active("session-a", None, now=100.0) is True
    assert lease_is_active(None, None, now=100.0) is False
    assert lease_is_active("session-a", 99.0, now=100.0) is False
    assert lease_is_active("session-a", 101.0, now=100.0) is True


def test_expires_at_from_timeout_uses_absolute_time_and_hides_zero():
    assert expires_at_from_timeout(0, now=100.0) is None
    assert expires_at_from_timeout(300, now=100.0) == 400.0


def test_idle_cleanup_at_from_record_uses_last_used_time():
    assert (
        idle_cleanup_at_from_record(last_used_at=100.0, idle_timeout=0, now=100.0)
        is None
    )
    assert (
        idle_cleanup_at_from_record(last_used_at=100.0, idle_timeout=30, now=100.0)
        == 130.0
    )
