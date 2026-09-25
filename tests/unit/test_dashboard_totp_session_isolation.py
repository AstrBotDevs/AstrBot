import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from astrbot.core.utils import totp
from astrbot.dashboard.services import auth_service
from astrbot.dashboard.services.auth_service import AuthService
from astrbot.dashboard.services.config_service import ConfigProfileService

OLD = {"code": "dummy-old-code"}
NEW = {"secret": "dummy-new-key", "code": "dummy-new-code"}


@pytest.fixture
def rotation(monkeypatch):
    """Test internal session IDs; mock only crypto/replay/randomness, not state."""
    clock = [1000.0]
    monkeypatch.setattr(totp, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(totp, "_totp_rotation_states", {})
    valid_codes = {
        ("dummy-old-key", OLD["code"]),
        (NEW["secret"], NEW["code"]),
        ("dummy-other-key", "dummy-other-code"),
    }
    consume = AsyncMock(side_effect=lambda key, code: (key, code) in valid_codes)
    monkeypatch.setattr(totp, "consume_totp_code", consume)
    monkeypatch.setattr(auth_service, "consume_totp_code", consume)
    monkeypatch.setattr(auth_service.pyotp, "random_base32", lambda: NEW["secret"])
    monkeypatch.setattr(
        auth_service, "generate_recovery_code", lambda: ("dummy-recovery", "dummy-hash")
    )
    dashboard = {
        "username": "dummy-user",
        "jwt_secret": "dummy-test-signing-key-not-for-real-use",
        "totp": {
            "enable": True,
            "secret": "dummy-old-key",
            "recovery_code_hash": "dummy-old-hash",
        },
    }
    return AuthService(db=None, config={"dashboard": dashboard}), clock


async def prepare_pending(service, session, request=NEW):
    assert (await service.totp_setup(OLD, session_id=session)).status == "ok"
    assert (await service.totp_setup(request, session_id=session)).status == "ok"


@pytest.mark.asyncio
async def test_other_session_cannot_clear_or_consume_single_use_authorization(rotation):
    service, _clock = rotation
    assert (await service.totp_setup(OLD, session_id="A")).status == "ok"
    rejected = await service.totp_setup({"code": "invalid"}, session_id="B")
    assert rejected.status == "error"
    assert (await service.totp_setup(NEW, session_id="B")).status == "error"
    assert (await service.totp_setup(NEW, session_id="A")).status == "ok"
    assert (await service.totp_setup(NEW, session_id="A")).status == "error"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session", "key", "code", "expected"),
    [
        ("A", NEW["secret"], NEW["code"], True),
        ("B", NEW["secret"], NEW["code"], False),
        (None, NEW["secret"], NEW["code"], False),
        ("A", "different-key", NEW["code"], False),
        ("A", None, NEW["code"], False),
        ("A", NEW["secret"], "invalid", False),
        (None, None, OLD["code"], True),
        ("B", None, OLD["code"], True),
    ],
)
async def test_pending_requires_owner_and_key_but_current_code_still_works(
    rotation, session, key, code, expected
):
    service, _clock = rotation
    await prepare_pending(service, "A")
    accepted = await ConfigProfileService._verify_config_2fa(
        service.config, code, session_id=session, pending_secret=key
    )
    assert accepted is expected


@pytest.mark.asyncio
async def test_pending_states_coexist_and_cleanup_only_affects_owner(rotation):
    service, _clock = rotation
    other = {"secret": "dummy-other-key", "code": "dummy-other-code"}
    await prepare_pending(service, "A")
    await prepare_pending(service, "B", other)
    for cleared in (False, True):
        if cleared:
            totp.set_pending_totp_secret(None, session_id="B")
        for session, request in (("A", NEW), ("B", other)):
            accepted = await ConfigProfileService._verify_config_2fa(
                service.config,
                request["code"],
                session_id=session,
                pending_secret=request["secret"],
            )
            assert accepted is (session == "A" or not cleared)


@pytest.mark.asyncio
async def test_authorization_expires(rotation):
    service, clock = rotation
    assert (await service.totp_setup(OLD, session_id="A")).status == "ok"
    clock[0] += totp._TOTP_ROTATION_TTL_SECONDS
    assert (await service.totp_setup(NEW, session_id="A")).status == "error"


@pytest.mark.asyncio
async def test_pending_does_not_extend_original_authorization_expiry(rotation):
    service, clock = rotation
    assert (await service.totp_setup(OLD, session_id="A")).status == "ok"
    clock[0] += totp._TOTP_ROTATION_TTL_SECONDS - 1
    assert (await service.totp_setup(NEW, session_id="A")).status == "ok"
    clock[0] += 1
    accepted = await ConfigProfileService._verify_config_2fa(
        service.config, NEW["code"], session_id="A", pending_secret=NEW["secret"]
    )
    assert accepted is False


@pytest.mark.asyncio
async def test_missing_session_cannot_create_shared_authorization(rotation):
    service, _clock = rotation
    assert (await service.totp_setup(OLD)).status == "error"
    totp.set_rotation_verified(True)
    assert totp.consume_rotation_verified() is False
    totp.set_pending_totp_secret(NEW["secret"])
    accepted = await ConfigProfileService._verify_config_2fa(
        service.config, NEW["code"], pending_secret=NEW["secret"]
    )
    assert accepted is False


@pytest.mark.asyncio
@pytest.mark.parametrize("session", [None, "A"])
async def test_initial_setup_does_not_require_rotation_authorization(rotation, session):
    service, _clock = rotation
    service.config["dashboard"]["totp"]["enable"] = False
    assert (await service.totp_setup({}, session_id=session)).status == "ok"
    assert (await service.totp_setup(NEW, session_id=session)).status == "ok"


def test_same_second_credentials_have_distinct_session_identity(rotation):
    service, _clock = rotation
    issued_at = datetime.datetime(2030, 1, 1, tzinfo=datetime.timezone.utc)
    with patch.object(
        auth_service.datetime, "datetime", wraps=datetime.datetime
    ) as clock:
        clock.now.return_value = issued_at
        distinct = service.generate_jwt("dummy-user") != service.generate_jwt(
            "dummy-user"
        )
    assert distinct, "Credentials issued in the same second need distinct identities"
