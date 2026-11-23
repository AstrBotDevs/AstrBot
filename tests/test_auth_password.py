"""Behavioral tests for password storage and dashboard login proofs."""

import hashlib
import hmac

import pytest

from astrbot.core.utils import auth_password as auth_password_module
from astrbot.core.utils.auth_password import (
    DEFAULT_DASHBOARD_PASSWORD,
    generate_dashboard_password,
    get_dashboard_login_challenge,
    hash_dashboard_password,
    is_default_dashboard_password,
    is_legacy_dashboard_password,
    normalize_dashboard_password_hash,
    validate_dashboard_password,
    verify_dashboard_login_proof,
    verify_dashboard_password,
)


def test_generated_password_satisfies_the_complexity_policy():
    password = generate_dashboard_password()

    assert len(password) == 24
    assert password.isascii()
    assert password.isalnum()
    assert validate_dashboard_password(password) is None


class TestHashDashboardPassword:
    def test_hash_encodes_a_known_salted_password(self, monkeypatch):
        salt = "00112233445566778899aabbccddeeff"
        monkeypatch.setattr(
            auth_password_module.secrets, "token_hex", lambda size: salt
        )

        stored = hash_dashboard_password("TestPassword123")

        assert stored == (
            f"pbkdf2_sha256$600000${salt}$"
            "06dfd6262177e1aba57d36e7dd80fe0936a8a51d7c590dd258015a29d3235c87"
        )
        assert verify_dashboard_password(stored, "TestPassword123") is True

    def test_same_password_uses_fresh_salt(self, monkeypatch):
        salts = iter(
            ["00112233445566778899aabbccddeeff", "ffeeddccbbaa99887766554433221100"]
        )
        monkeypatch.setattr(
            auth_password_module.secrets, "token_hex", lambda size: next(salts)
        )

        first = hash_dashboard_password("TestPassword123")
        second = hash_dashboard_password("TestPassword123")

        assert first != second
        assert verify_dashboard_password(second, "TestPassword123") is True

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
        assert DEFAULT_DASHBOARD_PASSWORD == "astrbot"
        assert result != DEFAULT_DASHBOARD_PASSWORD
        assert verify_dashboard_password(result, DEFAULT_DASHBOARD_PASSWORD) is True

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
    def test_pbkdf2_challenge_exposes_only_public_parameters(self):
        salt = "00112233445566778899aabbccddeeff"
        digest = "06dfd6262177e1aba57d36e7dd80fe0936a8a51d7c590dd258015a29d3235c87"

        challenge = get_dashboard_login_challenge(
            f"pbkdf2_sha256$600000${salt}${digest}"
        )

        assert challenge == {
            "algorithm": "pbkdf2_sha256",
            "iterations": 600000,
            "salt": salt,
        }
        assert digest not in repr(challenge)

    @pytest.mark.parametrize(
        ("stored", "expected"),
        [
            ("5d41402abc4b2a76b9719d911017c592", {"algorithm": "legacy_md5"}),
            ("$argon2id$v=19$m=65536,t=3,p=4$salt$digest", {"algorithm": "argon2"}),
        ],
    )
    def test_legacy_challenge_selects_the_compatible_algorithm(self, stored, expected):
        assert get_dashboard_login_challenge(stored) == expected

    def test_raises_for_unsupported_format(self):
        with pytest.raises(ValueError, match="Unsupported"):
            get_dashboard_login_challenge("unsupported_format")


class TestVerifyDashboardLoginProof:
    @pytest.mark.parametrize("legacy", [False, True])
    def test_valid_proof_authenticates_the_secret_and_exact_nonce(self, legacy):
        digest = "06dfd6262177e1aba57d36e7dd80fe0936a8a51d7c590dd258015a29d3235c87"
        md5 = hashlib.md5(b"TestPassword123").hexdigest()
        stored = md5 if legacy else f"pbkdf2_sha256$600000$00112233${digest}"
        proof_key = md5.encode() if legacy else bytes.fromhex(digest)
        nonce = "dashboard-challenge-123"
        proof = hmac.new(proof_key, nonce.encode(), hashlib.sha256).hexdigest()
        wrong_proof = hmac.new(
            b"wrong-secret", nonce.encode(), hashlib.sha256
        ).hexdigest()

        assert verify_dashboard_login_proof(stored, nonce, proof) is True
        assert verify_dashboard_login_proof(stored, nonce, proof.upper()) is True
        assert verify_dashboard_login_proof(stored, "another-challenge", proof) is False
        assert verify_dashboard_login_proof(stored, nonce, wrong_proof) is False

    def test_returns_false_for_invalid_types(self):
        assert verify_dashboard_login_proof(None, "nonce", "proof") is False
        assert verify_dashboard_login_proof("hash", None, "proof") is False
        assert verify_dashboard_login_proof("hash", "nonce", None) is False

    @pytest.mark.parametrize(
        "stored",
        [
            "unsupported",
            "pbkdf2_sha256$600000$salt",
            "pbkdf2_sha256$600000$salt$not-hex",
        ],
    )
    def test_returns_false_for_malformed_hashes(self, stored):
        assert verify_dashboard_login_proof(stored, "nonce", "proof") is False
