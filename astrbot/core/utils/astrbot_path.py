"""Centralized AstrBot path helpers.

Project path:
- Fixed to the source tree location.

Root path:
- Defaults to the current working directory.
- Can be overridden with the ``ASTRBOT_ROOT`` environment variable.

Data subdirectories:
- Most runtime data lives under ``<root>/data``.
- A few tool-runtime files intentionally live under the system temporary
  directory as ``.astrbot``.
"""

import os
import re
import tempfile
from collections.abc import Iterable
from pathlib import Path

from astrbot.core.utils.runtime_env import is_packaged_desktop_runtime

ASTRBOT_BACKUP_DIR_ENV = "ASTRBOT_BACKUP_DIR"

_WINDOWS_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")
_WINDOWS_DRIVE_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")
_WINDOWS_INVALID_PART_CHARS = frozenset('<>:"|?*')
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)


def get_astrbot_path() -> str:
    """Return the AstrBot project source path."""
    return os.path.realpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../"),
    )


def get_astrbot_root() -> str:
    """Return the AstrBot root directory."""
    if path := os.environ.get("ASTRBOT_ROOT"):
        return os.path.realpath(path)
    if is_packaged_desktop_runtime():
        return os.path.realpath(os.path.join(os.path.expanduser("~"), ".astrbot"))
    return os.path.realpath(os.getcwd())


def get_astrbot_data_path() -> str:
    """Return the AstrBot data directory path."""
    return os.path.realpath(os.path.join(get_astrbot_root(), "data"))


def get_astrbot_config_path() -> str:
    """Return the AstrBot config directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "config"))


def get_astrbot_plugin_path() -> str:
    """Return the AstrBot plugin directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "plugins"))


def get_astrbot_builtin_plugin_path() -> str:
    """Return the AstrBot built-in plugin directory path."""
    return os.path.realpath(
        os.path.join(get_astrbot_path(), "astrbot", "builtin_stars")
    )


def get_astrbot_plugin_data_path() -> str:
    """Return the AstrBot plugin data directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "plugin_data"))


def get_astrbot_t2i_templates_path() -> str:
    """Return the AstrBot T2I templates directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "t2i_templates"))


def get_astrbot_webchat_path() -> str:
    """Return the AstrBot WebChat data directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "webchat"))


def get_astrbot_temp_path() -> str:
    """Return the AstrBot temporary data directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "temp"))


def get_astrbot_skills_path() -> str:
    """Return the AstrBot skills directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "skills"))


def get_astrbot_workspaces_path() -> str:
    """Return the AstrBot workspaces directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "workspaces"))


def get_astrbot_system_tmp_path() -> str:
    """Return the shared system temporary directory used by local tools.

    The directory is the ``.astrbot`` entry of the system temporary
    directory. When the system temporary directory is unusable, Python falls
    back to the current working directory, which is where ``astrbot init``
    leaves the ``.astrbot`` marker file. In that case a sibling directory is
    used so the marker file is never shadowed by a directory.

    Returns:
        Absolute path of the shared system temporary directory.
    """
    system_tmp = Path(tempfile.gettempdir())
    candidate = system_tmp / ".astrbot"
    if candidate.is_file():
        candidate = system_tmp / ".astrbot-tmp"
    return os.path.realpath(str(candidate))


def get_astrbot_site_packages_path() -> str:
    """Return the AstrBot third-party site-packages directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "site-packages"))


def get_astrbot_knowledge_base_path() -> str:
    """Return the AstrBot knowledge base root path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "knowledge_base"))


def get_default_astrbot_backups_path() -> str:
    """Return the default AstrBot backups directory path."""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "backups"))


def resolve_astrbot_backups_path(configured_dir: str | None = None) -> str:
    """Resolve a configured backup directory path to a canonical absolute path.

    Empty values resolve to :func:`get_default_astrbot_backups_path`. Relative
    paths are resolved under the AstrBot data directory, consistent with
    ``log_file_path`` and ``trace_db_path``.

    Args:
        configured_dir: Raw directory path from configuration or environment.

    Returns:
        Canonical absolute path of the backup directory.
    """
    raw = (configured_dir or "").strip()
    if not raw:
        return get_default_astrbot_backups_path()

    expanded = os.path.expanduser(raw)
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = Path(get_astrbot_data_path()) / candidate
    return os.path.realpath(str(candidate))


def get_astrbot_backups_path(configured_dir: str | None = None) -> str:
    """Return the effective AstrBot backups directory path.

    Precedence:
    1. ``ASTRBOT_BACKUP_DIR`` environment variable (when non-empty).
    2. ``configured_dir`` argument (when non-empty).
    3. Default ``<data>/backups`` directory.

    Args:
        configured_dir: Optional configured backup directory path.

    Returns:
        Canonical absolute path of the effective backup directory.
    """
    if env_dir := os.environ.get(ASTRBOT_BACKUP_DIR_ENV, "").strip():
        return resolve_astrbot_backups_path(env_dir)
    return resolve_astrbot_backups_path(configured_dir)


def _norm_path_for_compare(path: str | Path) -> Path:
    """Return a canonical, case-normalized Path suitable for containment checks.

    Args:
        path: Input filesystem path.

    Returns:
        Normalized ``Path`` after resolving symlinks and platform casing.
    """
    return Path(os.path.normcase(os.path.realpath(str(path))))


def _is_same_or_within(path: Path, ancestor: Path) -> bool:
    """Check whether ``path`` equals or lies inside ``ancestor``.

    Args:
        path: Candidate child path (already canonicalized).
        ancestor: Candidate parent path (already canonicalized).

    Returns:
        True if ``path`` is identical to or nested under ``ancestor``.
    """
    try:
        path.relative_to(ancestor)
        return True
    except ValueError:
        return False


def _validate_raw_backup_dir_syntax(raw: str) -> None:
    """Validate platform-specific syntax constraints for a raw backup path.

    Args:
        raw: Non-empty stripped directory path string.

    Raises:
        ValueError: If the string contains control characters, invalid Windows
            characters/device names, or cross-OS drive letters on POSIX.
    """
    if any(ord(ch) < 32 for ch in raw):
        raise ValueError("Backup directory path contains invalid control characters.")

    if os.name == "nt":
        if _WINDOWS_DRIVE_PREFIX_RE.match(raw) and not _WINDOWS_DRIVE_ABS_RE.match(raw):
            raise ValueError(
                "Drive-relative Windows paths (e.g. 'D:backups') are not supported; "
                "use a full path such as 'D:\\backups'."
            )
        candidate = Path(os.path.expanduser(raw))
        if candidate.root and not candidate.drive:
            raise ValueError(
                "Root-relative Windows paths without a drive letter (e.g. '/backups' "
                "or '\\backups') are not supported; specify a drive letter "
                "(e.g. 'D:\\backups') or a relative subdirectory."
            )
        if candidate.drive and not candidate.root:
            raise ValueError(
                "Incomplete Windows path anchor; specify a full path such as "
                "'D:\\backups' or '\\\\server\\share\\backups'."
            )
        anchor = candidate.anchor
        for part in candidate.parts:
            if part == anchor or part in ("", ".", ".."):
                continue
            if any(ch in _WINDOWS_INVALID_PART_CHARS for ch in part):
                raise ValueError(
                    f"Backup directory path contains invalid characters in '{part}'."
                )
            stem = part.rstrip(" .").split(".", 1)[0].upper()
            if stem in _WINDOWS_RESERVED_NAMES:
                raise ValueError(
                    f"Backup directory path uses a reserved Windows device name: '{part}'."
                )
    elif _WINDOWS_DRIVE_PREFIX_RE.match(raw):
        raise ValueError(
            "Windows drive-letter paths are not valid on this operating system."
        )


def _probe_directory_writable(directory: Path) -> None:
    """Ensure ``directory`` exists and accepts file creation and deletion.

    Args:
        directory: Canonical directory path to create (if absent) and probe.

    Raises:
        ValueError: If the target is an existing file, cannot be created, or
            fails the write probe.
    """
    existed = directory.exists()
    if existed and not directory.is_dir():
        raise ValueError("Backup directory path points to an existing file.")

    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(f"Cannot create backup directory: {exc}") from exc

    probe_path: str | None = None
    try:
        fd, probe_path = tempfile.mkstemp(
            dir=str(directory),
            prefix=".astrbot_backup_probe_",
            suffix=".tmp",
        )
        os.close(fd)
    except OSError as exc:
        if not existed:
            try:
                directory.rmdir()
            except OSError:
                pass
        raise ValueError(f"Backup directory is not writable: {exc}") from exc
    finally:
        if probe_path:
            try:
                os.unlink(probe_path)
            except OSError:
                pass


def validate_astrbot_backup_dir(
    raw_path: str | None,
    *,
    extra_protected_dirs: Iterable[str] = (),
    check_writable: bool = False,
) -> str:
    """Validate and normalize a backup directory path.

    Prevents dangerous configurations such as filesystem roots, the bare user
    home directory, AstrBot's root or data directory (or their ancestors), and
    any directory that overlaps with backed-up or runtime-managed data folders
    (which would otherwise cause recursive self-archiving during export or
    destructive clashes during restore/cleanup).

    Args:
        raw_path: Raw backup directory string; empty/None validates the default
            backup directory.
        extra_protected_dirs: Additional directories that must not overlap with
            the backup directory (e.g., from ``get_backup_directories()``).
        check_writable: When True, ensure the directory exists (creating it if
            necessary) and passes a real write probe.

    Returns:
        Canonical absolute path of the validated backup directory.

    Raises:
        ValueError: If the path is syntactically invalid, unsafe, overlaps a
            protected directory, points to a file, or is not writable.
    """
    if raw_path is not None and not isinstance(raw_path, str):
        raise ValueError("Backup directory must be a string.")

    raw = (raw_path or "").strip()
    if raw:
        _validate_raw_backup_dir_syntax(raw)
        resolved_str = resolve_astrbot_backups_path(raw)
    else:
        resolved_str = get_default_astrbot_backups_path()

    # Canonicalize via os.path.realpath and require a concrete filesystem root
    # anchor (/, C:\, D:\, \\server\share\) before touching the filesystem.
    canonical_str = os.path.realpath(resolved_str)
    anchor = Path(canonical_str).anchor
    if not anchor:
        raise ValueError("Backup directory cannot be a filesystem root directory.")
    if not canonical_str.startswith(anchor):
        raise ValueError("Backup directory cannot be a filesystem root directory.")

    resolved_path = Path(canonical_str)
    resolved_cmp = _norm_path_for_compare(resolved_path)

    # Reject filesystem roots (/, C:\, D:\, \\server\share\).
    if resolved_cmp == resolved_cmp.parent:
        raise ValueError("Backup directory cannot be a filesystem root directory.")

    # Reject bare user home directory (~).
    home_dir = os.path.expanduser("~")
    if home_dir and home_dir != "~":
        home_cmp = _norm_path_for_compare(home_dir)
        if resolved_cmp == home_cmp:
            raise ValueError(
                "Backup directory cannot be the user home directory itself; "
                "please choose a dedicated subdirectory."
            )

    root_cmp = _norm_path_for_compare(get_astrbot_root())
    data_cmp = _norm_path_for_compare(get_astrbot_data_path())

    # Reject AstrBot root, data directory, or any ancestor containing them.
    if _is_same_or_within(root_cmp, resolved_cmp):
        raise ValueError(
            "Backup directory cannot be the AstrBot root directory or one of its parent directories."
        )
    if _is_same_or_within(data_cmp, resolved_cmp):
        raise ValueError(
            "Backup directory cannot be the AstrBot data directory or one of its parent directories."
        )

    # Reject overlapping any backed-up or runtime-managed subdirectory to prevent
    # recursive backup archiving, destructive restore replacement, or cleaner clashes.
    astrbot_src_path = Path(get_astrbot_path())
    protected_dirs = [
        get_astrbot_plugin_path(),
        get_astrbot_plugin_data_path(),
        get_astrbot_config_path(),
        get_astrbot_t2i_templates_path(),
        get_astrbot_webchat_path(),
        get_astrbot_temp_path(),
        get_astrbot_skills_path(),
        get_astrbot_knowledge_base_path(),
        get_astrbot_workspaces_path(),
        get_astrbot_site_packages_path(),
        os.path.join(get_astrbot_data_path(), "attachments"),
        os.path.join(get_astrbot_data_path(), "logs"),
        os.path.join(get_astrbot_data_path(), "dist"),
        str(astrbot_src_path / "astrbot"),
        str(astrbot_src_path / "dashboard"),
        *extra_protected_dirs,
    ]

    for protected in protected_dirs:
        if not protected:
            continue
        protected_cmp = _norm_path_for_compare(protected)
        if _is_same_or_within(resolved_cmp, protected_cmp) or _is_same_or_within(
            protected_cmp, resolved_cmp
        ):
            raise ValueError(
                "Backup directory cannot be inside or overlap with backed-up or "
                f"managed AstrBot directories ({Path(protected).name})."
            )

    if check_writable:
        _probe_directory_writable(resolved_path)

    return canonical_str
