"""
Configuration CLI for AstrBot.

This module provides:
- secure hashing utilities for the dashboard password (argon2)
- legacy compatibility helpers (md5 / sha256 hex digests)
- validators for commonly configurable items
- click CLI group with `set`, `get`, and `password` subcommands

Notes:
- The secure hasher uses `argon2.PasswordHasher`.
- Legacy checks are provided to detect pre-v3 default hashes.
"""

from __future__ import annotations

import binascii
import hashlib
import json
import zoneinfo
from collections.abc import Callable
from typing import Any

import click

from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.utils.astrbot_path import astrbot_paths

# Provide type-safe placeholders for optional argon2 imports so static analysis / type checkers
# do not assume the symbols always exist at import time.
PasswordHasher: Any = None
argon2_exceptions: Any = None
_HAS_ARGON2 = False

try:
    # Import argon2 at runtime if available. Use the module import path and getattr to avoid
    # static-analysis import errors and to allow graceful fallback when argon2 isn't installed.
    import argon2 as _argon2  # type: ignore

    PasswordHasher = getattr(_argon2, "PasswordHasher", None)
    argon2_exceptions = getattr(_argon2, "exceptions", None)
    _HAS_ARGON2 = PasswordHasher is not None and callable(PasswordHasher)
except Exception:
    # Argon2 may be broken on some Python/platform combinations.
    PasswordHasher = None
    argon2_exceptions = None
    _HAS_ARGON2 = False


# Instantiate a module-level hasher (argon2 when available, else None).
# When argon2 is unavailable we will use PBKDF2-HMAC-SHA256 as a deterministic secure fallback.
_PASSWORD_HASHER: Any = None
if _HAS_ARGON2 and PasswordHasher is not None and callable(PasswordHasher):
    try:
        _PASSWORD_HASHER = PasswordHasher()
    except Exception:
        # If construction fails for any reason, fall back to PBKDF2 mode.
        _PASSWORD_HASHER = None
        _HAS_ARGON2 = False
if not _HAS_ARGON2:
    _PASSWORD_HASHER = None
    # PBKDF2 fallback parameters (kept stable for deterministic stored hash format)
    PBKDF2_SALT = b"astrbot-dashboard"
    PBKDF2_ITER = 200_000

# Plaintext default dashboard password used on first-deploy / demo environments.
# This mirrors the default username "astrbot" from DEFAULT_CONFIG.
# NOTE: this is a documented default for new deployments; production installs should change it.
DEFAULT_DASHBOARD_PASSWORD = "astrbot"

# Legacy default password digests (hex) for compatibility checks in other modules.
DEFAULT_DASHBOARD_PASSWORD_MD5 = hashlib.md5(
    DEFAULT_DASHBOARD_PASSWORD.encode("utf-8")
).hexdigest()
DEFAULT_DASHBOARD_PASSWORD_SHA256 = hashlib.sha256(
    DEFAULT_DASHBOARD_PASSWORD.encode("utf-8")
).hexdigest()

# A secure default hash for the default password.
# If argon2 is available we generate an argon2 encoded hash. Otherwise we use a
# stable PBKDF2-HMAC-SHA256 encoded string format:
#   pbkdf2_sha256$<iterations>$<salt_hex>$<digest_hex>


if _HAS_ARGON2 and _PASSWORD_HASHER is not None:
    try:
        DEFAULT_DASHBOARD_PASSWORD_HASH = _PASSWORD_HASHER.hash(
            DEFAULT_DASHBOARD_PASSWORD
        )
    except Exception:
        # Fall back to PBKDF2 if argon2 unexpectedly fails at runtime.
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            DEFAULT_DASHBOARD_PASSWORD.encode("utf-8"),
            PBKDF2_SALT,
            PBKDF2_ITER,
        )
        DEFAULT_DASHBOARD_PASSWORD_HASH = f"pbkdf2_sha256${PBKDF2_ITER}${binascii.hexlify(PBKDF2_SALT).decode()}${dk.hex()}"
else:
    dk = hashlib.pbkdf2_hmac(
        "sha256", DEFAULT_DASHBOARD_PASSWORD.encode("utf-8"), PBKDF2_SALT, PBKDF2_ITER
    )
    DEFAULT_DASHBOARD_PASSWORD_HASH = f"pbkdf2_sha256${PBKDF2_ITER}${binascii.hexlify(PBKDF2_SALT).decode()}${dk.hex()}"


# --- Password hashing & validation utilities ---


def hash_dashboard_password_secure(value: str) -> str:
    """
    Hash the dashboard password for storage.

    Preferred: Argon2 encoded string (if argon2 available).
    Fallback: PBKDF2-HMAC-SHA256 encoded string in the format:
        pbkdf2_sha256$<iterations>$<salt_hex>$<digest_hex>
    """
    import binascii

    if _HAS_ARGON2 and _PASSWORD_HASHER is not None:
        try:
            return _PASSWORD_HASHER.hash(value)
        except Exception as e:
            # Surface a ClickException for CLI users while allowing fallback below.
            # Do not silently swallow unexpected errors.
            raise click.ClickException(
                f"Failed to hash password securely (argon2): {e!s}"
            )

    # PBKDF2 fallback (deterministic encoded string)
    dk = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), PBKDF2_SALT, PBKDF2_ITER)
    return f"pbkdf2_sha256${PBKDF2_ITER}${binascii.hexlify(PBKDF2_SALT).decode()}${dk.hex()}"


def verify_dashboard_password(value: str, stored_hash: str) -> bool:
    """
    Verify a plaintext password `value` against a stored hash.

    Supports:
    - Argon2 encoded hashes (preferred when available)
    - PBKDF2-HMAC-SHA256 encoded strings created by the fallback
      format: pbkdf2_sha256$<iterations>$<salt_hex>$<digest_hex>
    - Legacy SHA-256 and MD5 hexadecimal digests for backward compatibility.
    """
    import binascii

    if not stored_hash:
        return False

    # Argon2 encoded hashes start with $argon2 (only valid if argon2 available)
    if (
        stored_hash.startswith("$argon2")
        and _HAS_ARGON2
        and _PASSWORD_HASHER is not None
    ):
        try:
            return _PASSWORD_HASHER.verify(stored_hash, value)
        except Exception as e:
            # argon2 verification mismatch or errors: return False for mismatch,
            # raise for unexpected exceptions to avoid silent failures.
            # Be defensive when accessing exception type/name to avoid attribute errors.
            # If argon2_exceptions module is available prefer isinstance check.
            if argon2_exceptions is not None:
                vm = getattr(argon2_exceptions, "VerifyMismatchError", None)
                if vm is not None and isinstance(e, vm):
                    return False
            cls = getattr(e, "__class__", None)
            if (
                cls is not None
                and getattr(cls, "__name__", "") == "VerifyMismatchError"
            ):
                return False
            raise click.ClickException(f"Password verification failure (argon2): {e!s}")

    # PBKDF2 fallback format: pbkdf2_sha256$iters$salt_hex$digest_hex
    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _, iters_s, salt_hex, digest_hex = stored_hash.split("$", 3)
            iters = int(iters_s)
            salt = binascii.unhexlify(salt_hex)
            expected = digest_hex.lower()
            dk = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt, iters)
            return dk.hex() == expected
        except Exception:
            return False

    # Legacy hex digests: support both sha256 (64 hex chars) and md5 (32 hex chars)
    value_l = value.encode("utf-8")
    s = stored_hash.lower()
    if len(s) == 64 and all(ch in "0123456789abcdef" for ch in s):
        return hashlib.sha256(value_l).hexdigest() == s
    if len(s) == 32 and all(ch in "0123456789abcdef" for ch in s):
        return hashlib.md5(value_l).hexdigest() == s

    # Unknown format
    return False


def is_dashboard_password_hash(value: str) -> bool:
    """
    Heuristic: return True if `value` looks like a supported dashboard password hash.
    """
    if not isinstance(value, str) or not value:
        return False
    if value.startswith("$argon2"):
        return True
    value_l = value.lower()
    if len(value_l) == 64 and all(ch in "0123456789abcdef" for ch in value_l):
        return True
    if len(value_l) == 32 and all(ch in "0123456789abcdef" for ch in value_l):
        return True
    return False


# --- Validators for CLI configuration items ---


def _validate_log_level(value: str) -> str:
    value_up = value.upper()
    allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if value_up not in allowed:
        raise click.ClickException(
            "Log level must be one of DEBUG/INFO/WARNING/ERROR/CRITICAL"
        )
    return value_up


def _validate_dashboard_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise click.ClickException("Port must be a number")
    if port < 1 or port > 65535:
        raise click.ClickException("Port must be in range 1-65535")
    return port


def _validate_dashboard_username(value: str) -> str:
    if value is None or value.strip() == "":
        raise click.ClickException("Username cannot be empty")
    return value.strip()


def _validate_dashboard_password(value: str) -> str:
    if value is None or value == "":
        raise click.ClickException("Password cannot be empty")
    # Return a secure stored representation (argon2 encoded)
    return hash_dashboard_password_secure(value)


def _validate_timezone(value: str) -> str:
    try:
        zoneinfo.ZoneInfo(value)
    except Exception:
        raise click.ClickException(
            f"Invalid timezone: {value}. Please use a valid IANA timezone name"
        )
    return value


def _validate_callback_api_base(value: str) -> str:
    if not (value.startswith("http://") or value.startswith("https://")):
        raise click.ClickException(
            "Callback API base must start with http:// or https://"
        )
    return value


CONFIG_VALIDATORS: dict[str, Callable[[str], Any]] = {
    "timezone": _validate_timezone,
    "log_level": _validate_log_level,
    "dashboard.port": _validate_dashboard_port,
    "dashboard.username": _validate_dashboard_username,
    "dashboard.password": _validate_dashboard_password,
    "callback_api_base": _validate_callback_api_base,
}


# --- Config file helpers ---


def _load_config() -> dict[str, Any]:
    """
    Load or initialize the CLI config file (data/cmd_config.json).
    Ensures the astrbot root is valid before proceeding.
    """
    root = astrbot_paths.root
    if not astrbot_paths.is_root:
        raise click.ClickException(
            f"{root} is not a valid AstrBot root directory. Use 'astrbot init' to initialize"
        )

    config_path = astrbot_paths.data / "cmd_config.json"
    if not config_path.exists():
        # Write DEFAULT_CONFIG to disk if file missing
        config_path.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )

    try:
        return json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise click.ClickException(f"Failed to parse config file: {e!s}")


def _save_config(config: dict[str, Any]) -> None:
    config_path = astrbot_paths.data / "cmd_config.json"
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8-sig"
    )


def ensure_config_file() -> dict[str, Any]:
    return _load_config()


def _set_nested_item(obj: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur = obj
    for part in parts[:-1]:
        if part not in cur:
            cur[part] = {}
        elif not isinstance(cur[part], dict):
            raise click.ClickException(
                f"Config path conflict: {'.'.join(parts[: parts.index(part) + 1])} is not a dict"
            )
        cur = cur[part]
    cur[parts[-1]] = value


def _get_nested_item(obj: dict[str, Any], path: str) -> Any:
    parts = path.split(".")
    cur = obj
    for part in parts:
        cur = cur[part]
    return cur


# --- CLI commands ---


def prompt_dashboard_password(prompt: str = "Dashboard password") -> str:
    password = click.prompt(prompt, hide_input=True, confirmation_prompt=True, type=str)
    return _validate_dashboard_password(password)


def set_dashboard_credentials(
    config: dict[str, Any],
    *,
    username: str | None = None,
    password_hash: str | None = None,
) -> None:
    if username is not None:
        _set_nested_item(
            config, "dashboard.username", _validate_dashboard_username(username)
        )
    if password_hash is not None:
        # Security policy: disallow storing legacy hex digests via CLI.
        # Acceptable inputs from callers:
        # - Argon2 encoded hash string (starts with "$argon2")
        # - Plaintext password (will be hashed securely here)
        #
        # Rationale: legacy hex digests (md5/sha256 hex) are insecure to store and
        # lead to ambiguity in verification. Require callers to provide plaintext
        # (for secure hashing) or a properly encoded argon2 hash.
        if isinstance(password_hash, str) and password_hash.startswith("$argon2"):
            _set_nested_item(config, "dashboard.password", password_hash)
        else:
            # If caller mistakenly passed a legacy hex digest, reject with clear error.
            if is_dashboard_password_hash(password_hash) and not str(
                password_hash
            ).startswith("$argon2"):
                raise click.ClickException(
                    "Storing legacy hex password digests via CLI is disallowed. "
                    "Please provide the plaintext password (it will be hashed securely), "
                    "or provide an Argon2-encoded hash string."
                )
            # Treat value as plaintext and hash it securely
            _set_nested_item(
                config,
                "dashboard.password",
                _validate_dashboard_password(password_hash),
            )


@click.group(name="conf")
def conf() -> None:
    """
    Configuration management commands.

    Supported config keys:
    - timezone
    - log_level
    - dashboard.port
    - dashboard.username
    - dashboard.password
    - callback_api_base
    """
    pass


@conf.command(name="set")
@click.argument("key")
@click.argument("value")
def set_config(key: str, value: str) -> None:
    if key not in CONFIG_VALIDATORS:
        raise click.ClickException(f"Unsupported config key: {key}")

    config = _load_config()
    try:
        # Attempt to get old value (may raise KeyError)
        try:
            old_value = _get_nested_item(config, key)
        except Exception:
            old_value = "<not set>"

        validated_value = CONFIG_VALIDATORS[key](value)
        _set_nested_item(config, key, validated_value)
        _save_config(config)

        click.echo(f"Config updated: {key}")
        if key == "dashboard.password":
            click.echo("  Old value: ********")
            click.echo("  New value: ********")
        else:
            click.echo(f"  Old value: {old_value}")
            click.echo(f"  New value: {validated_value}")
    except KeyError:
        raise click.ClickException(f"Unknown config key: {key}")
    except click.ClickException:
        raise
    except Exception as e:
        raise click.UsageError(f"Failed to set config: {e!s}")


@conf.command(name="get")
@click.argument("key", required=False)
def get_config(key: str | None = None) -> None:
    config = _load_config()
    if key:
        if key not in CONFIG_VALIDATORS:
            raise click.ClickException(f"Unsupported config key: {key}")
        try:
            value = _get_nested_item(config, key)
            if key == "dashboard.password":
                value = "********"
            click.echo(f"{key}: {value}")
        except KeyError:
            raise click.ClickException(f"Unknown config key: {key}")
        except Exception as e:
            raise click.UsageError(f"Failed to get config: {e!s}")
    else:
        click.echo("Current config:")
        for k in CONFIG_VALIDATORS:
            try:
                v = (
                    "********"
                    if k == "dashboard.password"
                    else _get_nested_item(config, k)
                )
                click.echo(f"  {k}: {v}")
            except (KeyError, TypeError):
                # Missing or non-dict paths are simply skipped in listing
                pass


@conf.command(name="password")
@click.option("-u", "--username", type=str, help="Update dashboard username as well")
@click.option(
    "-p",
    "--password",
    type=str,
    help="Set dashboard password directly without interactive prompt",
)
def set_dashboard_password(username: str | None, password: str | None) -> None:
    """
    Interactively set dashboard password (with confirmation) or set directly with -p.

    Note: Legacy hex digests (md5/sha256 hex) provided directly are now disallowed
    for CLI storage. Acceptable inputs:
    - Plaintext password (recommended): it will be hashed securely before storage.
    - Argon2-encoded hash (advanced): stored as-is.
    """
    config = _load_config()

    if password is not None:
        # If the provided value is an Argon2 encoded hash, accept as-is.
        if isinstance(password, str) and password.startswith("$argon2"):
            password_hash = password
        else:
            # If the provided value looks like a legacy hex digest, reject and ask
            # the user to provide plaintext so we can hash it securely.
            if is_dashboard_password_hash(password) and not str(password).startswith(
                "$argon2"
            ):
                raise click.ClickException(
                    "Providing legacy hex password digests is disallowed. "
                    "Please supply the plaintext password (it will be hashed securely), "
                    "or provide an Argon2-encoded hash string."
                )
            # Otherwise treat as plaintext and hash securely
            password_hash = _validate_dashboard_password(password)
    else:
        password_hash = prompt_dashboard_password()

    set_dashboard_credentials(
        config,
        username=username.strip() if username is not None else None,
        password_hash=password_hash,
    )
    _save_config(config)

    if username is not None:
        click.echo(f"Dashboard username updated: {username.strip()}")
    click.echo("Dashboard password updated.")
