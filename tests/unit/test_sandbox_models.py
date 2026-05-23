import pytest

from astrbot.core.computer.sandbox_models import (
    SandboxRecord,
    SandboxRetentionPolicy,
    SandboxStatus,
)


def test_sandbox_record_round_trips_current_api_fields():
    payload = {
        "sandbox_id": "sb-1",
        "sandbox_name": "worker",
        "booter_type": "cua",
        "provider": "cua",
        "managed": True,
        "created_by_astrbot": True,
        "is_default": True,
        "owner_user_id": "user-a",
        "owner_session_id": "session-a",
        "controller_user_id": "user-b",
        "controller_session_id": "session-b",
        "lease_expires_at": 110.0,
        "last_used_at": 100.0,
        "idle_timeout": 30,
        "expires_at": 200.0,
        "retention_policy": "persistent",
        "status": "running",
        "connect_info": {"name": "worker"},
        "capabilities": ["create", "destroy"],
        "labels": {"team": "qa"},
        "notes": "hello",
    }

    record = SandboxRecord.from_dict(payload)

    assert record.retention_policy == SandboxRetentionPolicy.PERSISTENT
    assert record.status == SandboxStatus.RUNNING
    assert record.to_dict() == payload


def test_sandbox_record_defaults_match_current_registry_shape():
    record = SandboxRecord(
        sandbox_id="sb-1",
        sandbox_name="worker",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
    )

    payload = record.to_dict()

    assert payload["is_default"] is False
    assert payload["owner_user_id"] is None
    assert payload["owner_session_id"] is None
    assert payload["controller_user_id"] is None
    assert payload["controller_session_id"] is None
    assert payload["lease_expires_at"] is None
    assert payload["last_used_at"] is None
    assert payload["idle_timeout"] is None
    assert payload["expires_at"] is None
    assert payload["retention_policy"] == "temporary"
    assert payload["status"] == "running"
    assert payload["connect_info"] == {}
    assert payload["labels"] == {}
    assert payload["notes"] is None


def test_sandbox_record_detects_active_control_lease():
    record = SandboxRecord.from_dict(
        {
            "sandbox_id": "sb-1",
            "sandbox_name": "worker",
            "booter_type": "cua",
            "provider": "cua",
            "managed": True,
            "created_by_astrbot": True,
            "controller_session_id": "session-a",
            "lease_expires_at": 200.0,
        }
    )

    assert record.is_controlled_by("session-a", now=100.0) is True
    assert record.is_controlled_by("session-b", now=100.0) is False
    assert record.has_active_lease(now=201.0) is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("sandbox_id", None),
        ("sandbox_id", ""),
        ("sandbox_name", "   "),
        ("booter_type", None),
        ("provider", ""),
    ],
)
def test_sandbox_record_rejects_empty_required_string_fields(field, value):
    payload = {
        "sandbox_id": "sb-1",
        "sandbox_name": "worker",
        "booter_type": "cua",
        "provider": "cua",
        "managed": True,
        "created_by_astrbot": True,
    }
    payload[field] = value

    with pytest.raises(ValueError, match=field):
        SandboxRecord.from_dict(payload)
