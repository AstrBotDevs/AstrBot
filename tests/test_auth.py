"""Ensure frontend login logic and backend argon2id verification match.

This guards against the kind of password-hash mismatch that can be
introduced when the frontend encryption/encoding logic and the backend
verification code drift apart.
"""

from astrbot.core.utils.auth_password import (
    hash_dashboard_password,
    validate_dashboard_password,
    verify_dashboard_password,
    is_default_dashboard_password,
    is_legacy_dashboard_password,
    get_dashboard_login_challenge,
    verify_dashboard_login_proof,
)


def test_password_hash_roundtrip():
    """Backend argon2id hash → verify round-trip."""
    password = "test-password-123"
    hashed = hash_dashboard_password(password)
    assert hashed.startswith("$argon2id$"), f"Expected argon2id hash, got: {hashed}"
    assert verify_dashboard_password(hashed, password)
    assert not verify_dashboard_password(hashed, "wrong-password")


def test_validate_password_strength():
    """validate_dashboard_password should reject weak passwords."""
    validate_dashboard_password("StrongPass1!")  # should not raise

    import pytest

    with pytest.raises(ValueError):
        validate_dashboard_password("short")

    with pytest.raises(ValueError):
        validate_dashboard_password("")


def test_is_default_password():
    """is_default / is_legacy detection helpers."""
    assert is_default_dashboard_password(hash_dashboard_password("astrbot"))

    # Legacy MD5-style hash detection
    assert is_legacy_dashboard_password("e99a18c428cb38d5f260853678922e03")


def test_login_challenge_argon2():
    """get_dashboard_login_challenge for argon2 returns algorithm marker."""
    password = "test-challenge-pw"
    hashed = hash_dashboard_password(password)

    challenge = get_dashboard_login_challenge(hashed)
    assert challenge == {"algorithm": "argon2"}


def test_login_challenge_pbkdf2():
    """get_dashboard_login_challenge + verify_dashboard_login_proof for PBKDF2."""
    import hashlib, hmac

    salt = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
    password = "test-pw"
    iterations = 600000
    algo = "pbkdf2_sha256"
    # Build a PBKDF2 hash matching auth_password format: algo$iterations$salt$derived_key
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), iterations)
    stored = f"{algo}${iterations}${salt}${dk.hex()}"

    challenge = get_dashboard_login_challenge(stored)
    assert challenge["algorithm"] == algo
    assert challenge["salt"] == salt
    assert challenge["iterations"] == iterations

    # The proof is HMAC-SHA256(derived_key, nonce) — the derived key IS the digest
    proof = hmac.new(
        dk,
        "any-nonce".encode(),
        hashlib.sha256,
    ).hexdigest()

    assert verify_dashboard_login_proof(stored, "any-nonce", proof)
    assert not verify_dashboard_login_proof(
        stored, "any-nonce", "invalid-proof"
    )
