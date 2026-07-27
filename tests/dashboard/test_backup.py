"""Import smoke tests for the backup route module.

Verifies that the ``BackupRoute`` class and key standalone utilities from
``backup.py`` can be imported without errors.
"""

# ---------------------------------------------------------------------------
# backup.py — BackupRoute, helpers and constants
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.backup import (
    BackupRoute,               # noqa: F401
    CHUNK_SIZE,                # noqa: F401
    UPLOAD_EXPIRE_SECONDS,     # noqa: F401
    generate_unique_filename,  # noqa: F401
    secure_filename,           # noqa: F401
)


def test_backup_route_class():
    assert BackupRoute is not None


def test_chunk_size_constant():
    assert CHUNK_SIZE == 1024 * 1024


def test_upload_expire_seconds_constant():
    assert UPLOAD_EXPIRE_SECONDS == 3600


def test_secure_filename_is_callable():
    assert callable(secure_filename)


def test_generate_unique_filename_is_callable():
    assert callable(generate_unique_filename)


def test_secure_filename_sanitizes_path_traversal():
    result = secure_filename("../../etc/passwd")
    assert ".." not in result
    assert "passwd" not in result


def test_secure_filename_removes_hidden_prefix():
    result = secure_filename(".hidden.zip")
    assert not result.startswith(".")


def test_generate_unique_filename_appends_timestamp():
    result = generate_unique_filename("backup.zip")
    assert result.startswith("backup_")
    assert result.endswith(".zip")
    assert "_20" in result  # timestamp year prefix
