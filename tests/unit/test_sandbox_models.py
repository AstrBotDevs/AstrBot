import time

import pytest

from astrbot.core.computer.sandbox_models import SandboxRecord


def test_sandbox_record_round_trips_generic_capabilities_sorted():
    record = SandboxRecord.from_dict(
        {
            "sandbox_id": "sandbox-1",
            "sandbox_name": "General Sandbox",
            "provider": "generic-provider",
            "managed": True,
            "created_by_astrbot": True,
            "capabilities": ["keyboard", "shell", "filesystem", "shell"],
        }
    )

    assert record.capabilities == ["filesystem", "keyboard", "shell", "shell"]
    payload = record.to_dict()
    assert payload["sandbox_id"] == "sandbox-1"
    assert payload["retention_policy"] == "temporary"
    assert payload["status"] == "running"
    assert payload["capabilities"] == ["filesystem", "keyboard", "shell", "shell"]
    assert "booter_type" not in payload


def test_sandbox_record_aliases_owner_fields_to_created_by_fields():
    record = SandboxRecord.from_dict(
        {
            "sandbox_id": "sandbox-1",
            "sandbox_name": "General Sandbox",
            "provider": "generic-provider",
            "managed": True,
            "created_by_astrbot": True,
            "owner_user_id": "legacy-user",
            "owner_session_id": "legacy-session",
        }
    )

    payload = record.to_dict()

    assert payload["created_by_user_id"] == "legacy-user"
    assert payload["created_by_session_id"] == "legacy-session"
    assert payload["owner_user_id"] == "legacy-user"
    assert payload["owner_session_id"] == "legacy-session"


def test_sandbox_record_validates_required_strings():
    with pytest.raises(ValueError, match="sandbox_id"):
        SandboxRecord.from_dict(
            {
                "sandbox_id": "",
                "sandbox_name": "General Sandbox",
                "provider": "generic-provider",
                "managed": True,
                "created_by_astrbot": True,
            }
        )


def test_sandbox_record_reports_active_control_lease():
    now = time.time()
    record = SandboxRecord.from_dict(
        {
            "sandbox_id": "sandbox-1",
            "sandbox_name": "General Sandbox",
            "provider": "generic-provider",
            "managed": True,
            "created_by_astrbot": True,
            "controller_session_id": "session-a",
            "lease_expires_at": now + 60,
        }
    )

    assert record.has_active_lease(now=now)
    assert record.is_controlled_by("session-a", now=now)
    assert not record.is_controlled_by("session-b", now=now)
    assert not record.has_active_lease(now=now + 120)


def test_sandbox_record_migrates_legacy_booter_type_to_provider():
    record = SandboxRecord.from_dict(
        {
            "sandbox_id": "sandbox-1",
            "sandbox_name": "General Sandbox",
            "booter_type": "legacy-provider",
            "managed": True,
            "created_by_astrbot": True,
        }
    )

    payload = record.to_dict()

    assert record.provider == "legacy-provider"
    assert payload["provider"] == "legacy-provider"
    assert "booter_type" not in payload
