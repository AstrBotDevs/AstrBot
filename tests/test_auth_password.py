"""Import smoke tests for astrbot.core.utils.auth_password."""

import hashlib

import pytest

from astrbot.core.utils import auth_password as auth_password_module
from astrbot.core.utils.auth_password import (
    DEFAULT_DASHBOARD_PASSWORD,
    get_dashboard_login_challenge,
    hash_dashboard_password,
    is_default_dashboard_password,
    is_legacy_dashboard_password,
    normalize_dashboard_password_hash,
    validate_dashboard_password,
    verify_dashboard_login_proof,
    verify_dashboard_password,
)


class TestImports:
    def test_module_importable(self):
        assert auth_password_module is not None

    def test_constants_defined(self):
        assert DEFAULT_DASHBOARD_PASSWORD == "astrbot"

    def test_hash_callable(self):
        assert callable(hash_dashboard_password)

    def test_validate_callable(self):
        assert callable(validate_dashboard_password)

    def test_verify_callable(self):
        assert callable(verify_dashboard_password)


class TestHashDashboardPassword:
    def test_returns_string(self):
        h = hash_dashboard_password("MySecurePassword123")
        assert isinstance(h, str)
        assert len(h) > 0

    def test_raises_on_empty(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            hash_dashboard_password("")

    def test_different_passwords_different_hashes(self):
        h1 = hash_dashboard_password("MySecurePassword123")
        h2 = hash_dashboard_password("OtherSecurePass456")
        assert h1 != h2


class TestValidateDashboardPassword:
    def test_valid_password_does_not_raise(self):
        validate_dashboard_password("MySecurePass1")

    def test_raises_on_empty(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_dashboard_password("")

    def test_raises_on_too_short(self):
        with pytest.raises(ValueError, match="at least"):
            validate_dashboard_password("Short1Aa")

    def test_raises_no_uppercase(self):
        with pytest.raises(ValueError, match="uppercase"):
            validate_dashboard_password("lowercaseonly1")

    def test_raises_no_lowercase(self):
        with pytest.raises(ValueError, match="lowercase"):
            validate_dashboard_password("UPPERCASEONLY1")

    def test_raises_no_digit(self):
        with pytest.raises(ValueError, match="digit"):
            validate_dashboard_password("NoDigitsHere!")


class TestVerifyDashboardPassword:
    def test_verify_own_hash(self):
        pwd = "TestPassword123"
        h = hash_dashboard_password(pwd)
        assert verify_dashboard_password(h, pwd) is True

    def test_verify_wrong_password(self):
        h = hash_dashboard_password("TestPassword123")
        assert verify_dashboard_password(h, "WrongPassword456") is False

    def test_verify_none_stored_returns_false(self):
        assert verify_dashboard_password(None, "test") is False

    def test_verify_non_string_stored_returns_false(self):
        assert verify_dashboard_password(123, "test") is False

    def test_verify_legacy_md5(self):
        md5 = hashlib.md5(b"testpassword").hexdigest()
        assert verify_dashboard_password(md5, "testpassword") is True

    def test_verify_legacy_sha256(self):
        sha256 = hashlib.sha256(b"testpassword").hexdigest()
        assert verify_dashboard_password(sha256, "testpassword") is True


class TestNormalizeDashboardPasswordHash:
    def test_returns_hash_for_empty(self):
        result = normalize_dashboard_password_hash("")
        assert isinstance(result, str)
        assert "astrbot" not in result or verify_dashboard_password(
            result, DEFAULT_DASHBOARD_PASSWORD
        )

    def test_returns_same_for_non_empty(self):
        h = hash_dashboard_password("MySecurePassword123")
        assert normalize_dashboard_password_hash(h) == h


class TestIsDefaultDashboardPassword:
    def test_returns_true_for_default(self):
        h = hash_dashboard_password(DEFAULT_DASHBOARD_PASSWORD)
        assert is_default_dashboard_password(h) is True

    def test_returns_false_for_non_default(self):
        h = hash_dashboard_password("MySecurePassword123")
        assert is_default_dashboard_password(h) is False


class TestIsLegacyDashboardPassword:
    def test_returns_true_for_md5(self):
        md5 = "5d41402abc4b2a76b9719d911017c592"
        assert is_legacy_dashboard_password(md5) is True

    def test_returns_false_for_argon2_or_pbkdf2(self):
        h = hash_dashboard_password("MySecurePassword123")
        assert is_legacy_dashboard_password(h) is False

    def test_returns_false_for_empty(self):
        assert is_legacy_dashboard_password("") is False

    def test_returns_false_for_none(self):
        assert is_legacy_dashboard_password(None) is False


class TestGetDashboardLoginChallenge:
    def test_returns_dict_for_valid_hash(self):
        h = hash_dashboard_password("MySecurePassword123")
        challenge = get_dashboard_login_challenge(h)
        assert isinstance(challenge, dict)

    def test_raises_for_unsupported_format(self):
        with pytest.raises(ValueError, match="Unsupported"):
            get_dashboard_login_challenge("unsupported_format")


class TestVerifyDashboardLoginProof:
    def test_returns_false_for_invalid_types(self):
        assert verify_dashboard_login_proof(None, "nonce", "proof") is False
        assert verify_dashboard_login_proof("hash", None, "proof") is False
        assert verify_dashboard_login_proof("hash", "nonce", None) is False
