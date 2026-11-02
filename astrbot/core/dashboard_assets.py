"""Dashboard asset discovery, compatibility, and package handling."""

import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.desktop_runtime import is_desktop_managed_backend
from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_path
from astrbot.core.utils.io import download_file, ensure_dir
from astrbot.core.utils.version_comparator import VersionComparator

__all__ = [
    "get_dashboard_version",
    "resolve_dashboard_dist",
]


def _read_dashboard_version(dist_dir: str | Path) -> str | None:
    """Read the version declared by a Dashboard dist directory.

    Args:
        dist_dir: Dashboard dist directory path.

    Returns:
        Version from ``assets/version``, or None when it cannot be read.
    """
    version_file = Path(dist_dir) / "assets" / "version"
    try:
        if version_file.exists():
            return version_file.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to read WebUI version from %s: %s", version_file, exc)
    return None


def _get_bundled_dist_path() -> Path:
    """Return the Dashboard dist bundled with the AstrBot package."""
    return Path(get_astrbot_path()) / "astrbot" / "dashboard" / "dist"


def _normalize_version(version: str) -> str:
    """Normalize a Dashboard version for comparison.

    Args:
        version: Version with an optional ``v`` prefix.

    Returns:
        Version without the prefix.

    Raises:
        ValueError: If the value is not a supported semantic version.
    """
    version = version.strip()
    if version[:1].lower() == "v":
        version = version[1:]
    if not re.match(
        r"^[0-9]+(?:\.[0-9]+)*"
        r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
        r"(?:\+.+)?$",
        version,
    ):
        raise ValueError(f"invalid dashboard version: {version!r}")
    return version


def _is_version_compatible(
    dashboard_version: str | None,
    current_version: str,
) -> bool:
    """Check whether Dashboard and Core versions match.

    Args:
        dashboard_version: Version read from Dashboard assets.
        current_version: Current AstrBot Core version.

    Returns:
        Whether both versions are valid and equal.
    """
    if dashboard_version is None:
        return False
    try:
        return (
            VersionComparator.compare_version(
                _normalize_version(dashboard_version),
                _normalize_version(current_version),
            )
            == 0
        )
    except (TypeError, ValueError):
        return False


def _is_dist_compatible(dist_dir: str | Path, current_version: str) -> bool:
    """Check whether a Dashboard dist is complete and Core-compatible.

    Args:
        dist_dir: Dashboard dist directory path.
        current_version: Current AstrBot Core version.

    Returns:
        Whether the dist contains an index and a matching version.
    """
    dist_path = Path(dist_dir)
    return _is_dist_complete(dist_path) and _is_version_compatible(
        _read_dashboard_version(dist_path), current_version
    )


def _is_dist_complete(dist_dir: str | Path) -> bool:
    """Check whether a Dashboard dist has a usable local entry bundle.

    Args:
        dist_dir: Dashboard dist directory path.

    Returns:
        Whether the index references a local JavaScript entry and every local
        JavaScript or stylesheet entry exists inside the dist directory.
    """
    dist_path = Path(dist_dir)
    index_path = dist_path / "index.html"
    try:
        index_html = index_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    entry_paths: list[Path] = []
    for match in re.finditer(
        r"\b(?:src|href)\s*=\s*[\"']([^\"']+)[\"']",
        index_html,
        flags=re.IGNORECASE,
    ):
        reference = match.group(1).strip()
        if not reference or reference.startswith(("#", "//")):
            continue
        try:
            parsed = urlsplit(reference)
            if parsed.scheme or parsed.netloc:
                continue
            decoded_path = unquote(parsed.path).replace("\\", "/").lstrip("/")
        except (UnicodeError, ValueError):
            return False
        if not decoded_path.lower().endswith((".js", ".css")):
            continue
        entry_path = Path(decoded_path)
        if entry_path.is_absolute() or ".." in entry_path.parts:
            return False
        entry_paths.append(entry_path)

    if not any(path.suffix.lower() == ".js" for path in entry_paths):
        return False
    return all((dist_path / path).is_file() for path in entry_paths)


def _should_use_bundled_dist(user_dist: str | Path, current_version: str) -> bool:
    """Check whether bundled assets should replace a managed user dist.

    Args:
        user_dist: Managed Dashboard dist under the AstrBot data directory.
        current_version: Current AstrBot Core version.

    Returns:
        Whether the user dist is stale or incomplete and bundled assets match.
    """
    user_dist = Path(user_dist)
    bundled_dist = _get_bundled_dist_path()
    if not user_dist.exists() or not _is_dist_compatible(
        bundled_dist,
        current_version,
    ):
        return False
    return not _is_dist_compatible(user_dist, current_version)


def resolve_dashboard_dist(webui_dir: str | Path | None = None) -> Path | None:
    """Select the Dashboard dist that should be served.

    Args:
        webui_dir: Optional explicitly configured Dashboard directory.

    Returns:
        Explicit, managed, bundled, or stale fallback dist in priority order.
        A managed desktop backend never receives assets with a known version
        mismatch, and None is returned when no compatible fallback exists.
    """
    explicit_dist = Path(webui_dir).absolute() if webui_dir else None
    if explicit_dist is not None and explicit_dist.exists():
        if _is_dist_compatible(explicit_dist, VERSION):
            return explicit_dist

        explicit_version = _read_dashboard_version(explicit_dist)
        if is_desktop_managed_backend():
            logger.warning(
                "Refusing the explicitly configured WebUI directory in "
                "desktop-managed mode because it is incomplete or its version "
                "does not match core: %s, expected v%s (%s).",
                explicit_version or "unknown",
                VERSION,
                explicit_dist,
            )
        else:
            logger.warning(
                "Serving the explicitly configured WebUI directory even though it "
                "does not declare a version matching core: %s, expected v%s (%s). "
                "Some dashboard features may not work until matching assets are "
                "available.",
                explicit_version or "unknown",
                VERSION,
                explicit_dist,
            )
            return explicit_dist

    user_dist = Path(get_astrbot_data_path()) / "dist"
    bundled_dist = _get_bundled_dist_path()
    user_version = _read_dashboard_version(user_dist)
    if user_dist.exists() and _is_dist_compatible(user_dist, VERSION):
        return user_dist.absolute()
    if _should_use_bundled_dist(user_dist, VERSION) or _is_dist_compatible(
        bundled_dist,
        VERSION,
    ):
        logger.info("Using bundled dashboard dist: %s", bundled_dist)
        return bundled_dist
    if is_desktop_managed_backend():
        if user_dist.exists():
            logger.warning(
                "Refusing data/dist in desktop-managed mode because WebUI version "
                "does not match core: %s, expected v%s.",
                user_version or "unknown",
                VERSION,
            )
        return None
    if user_dist.exists() and (user_dist / "index.html").is_file():
        logger.warning(
            "Using existing data/dist as a fallback even though WebUI version "
            "mismatches core: %s, expected v%s. Some dashboard features may not "
            "work until matching assets are available.",
            user_version,
            VERSION,
        )
        return user_dist.absolute()
    if user_dist.exists():
        logger.warning(
            "Ignoring data/dist because WebUI files are incomplete for core v%s.",
            VERSION,
        )
        return None
    return user_dist.absolute()


async def get_dashboard_version(
    dist_dir: str | Path | None = None,
) -> str | None:
    """Return the version of explicit or currently effective Dashboard assets.

    Args:
        dist_dir: Optional Dashboard dist directory. When omitted, the managed
            and bundled assets are inspected in runtime priority order.

    Returns:
        Version declared by the selected assets, or None when it cannot be read.
    """
    if dist_dir is not None:
        return _read_dashboard_version(dist_dir)

    user_dist = Path(get_astrbot_data_path()) / "dist"
    if user_dist.exists():
        user_version = _read_dashboard_version(user_dist)
        if _is_dist_compatible(user_dist, VERSION):
            return user_version
        bundled_dist = _get_bundled_dist_path()
        if _is_dist_compatible(bundled_dist, VERSION):
            return _read_dashboard_version(bundled_dist)
        return user_version

    bundled_dist = _get_bundled_dist_path()
    if _is_dist_compatible(bundled_dist, VERSION):
        return _read_dashboard_version(bundled_dist)
    return None


async def _download_package(
    version: str,
    path: str | Path | None = None,
    extract_path: str | Path | None = None,
    proxy: str | None = None,
    progress_callback=None,
    extract: bool = True,
    allow_insecure_ssl_fallback: bool = True,
) -> None:
    """Download a Dashboard package pinned to one Core version.

    Args:
        version: Release tag or exact commit hash selected by the updater.
        path: Destination ZIP path. Defaults to the AstrBot data directory.
        extract_path: Extraction root. Defaults to the AstrBot data directory.
        proxy: Optional URL-prefix mirror for the fallback download.
        progress_callback: Internal download progress callback.
        extract: Whether to extract the downloaded package.
        allow_insecure_ssl_fallback: Whether certificate failures may retry with
            TLS verification disabled.

    Raises:
        RuntimeError: If neither source provides a valid ZIP package.
    """
    zip_path = (
        Path(path).absolute()
        if path is not None
        else Path(get_astrbot_data_path()).absolute() / "dashboard.zip"
    )
    ensure_dir(zip_path.parent)

    if len(version) != 40:
        hosted_url = (
            "https://astrbot-registry.soulter.top/download/"
            f"astrbot-dashboard/{version}/dist.zip"
        )
        logger.info("Downloading AstrBot WebUI from %s", hosted_url)
        try:
            await download_file(
                hosted_url,
                str(zip_path),
                show_progress=True,
                progress_callback=progress_callback,
                allow_insecure_ssl_fallback=allow_insecure_ssl_fallback,
            )
            if not zipfile.is_zipfile(zip_path):
                raise RuntimeError("Downloaded Dashboard package is not a valid ZIP")
        except Exception as exc:
            logger.warning(
                "Hosted Dashboard package failed: %s. Falling back to GitHub.",
                exc,
            )
            fallback_url = (
                "https://github.com/AstrBotDevs/AstrBot/releases/download/"
                f"{version}/AstrBot-{version}-dashboard.zip"
            )
            if proxy:
                fallback_url = f"{proxy.rstrip('/')}/{fallback_url}"
            await download_file(
                fallback_url,
                str(zip_path),
                show_progress=True,
                progress_callback=progress_callback,
                allow_insecure_ssl_fallback=allow_insecure_ssl_fallback,
            )
    else:
        fallback_url = (
            "https://github.com/AstrBotDevs/astrbot-release-harbour/releases/"
            f"download/release-{version}/dist.zip"
        )
        if proxy:
            fallback_url = f"{proxy.rstrip('/')}/{fallback_url}"
        logger.info("Downloading AstrBot WebUI from %s", fallback_url)
        await download_file(
            fallback_url,
            str(zip_path),
            show_progress=True,
            progress_callback=progress_callback,
            allow_insecure_ssl_fallback=allow_insecure_ssl_fallback,
        )

    if not zipfile.is_zipfile(zip_path):
        raise RuntimeError("Downloaded Dashboard package is not a valid ZIP")
    if extract:
        _extract_package(
            zip_path,
            extract_path or Path(get_astrbot_data_path()),
            expected_version=None if len(version) == 40 else version,
        )


def _extract_package(
    zip_path: str | Path,
    extract_path: str | Path,
    expected_version: str | None = None,
) -> None:
    """Safely stage, validate, and replace a Dashboard package.

    Args:
        zip_path: Dashboard ZIP archive path.
        extract_path: Directory where package contents should be extracted.
        expected_version: Optional Core version the Dashboard must match.

    Raises:
        ValueError: If an archive member escapes the staging root.
        RuntimeError: If the staged Dashboard is incomplete or mismatched.
    """
    extract_root = Path(extract_path).resolve()
    ensure_dir(extract_root)
    staging_root = Path(
        tempfile.mkdtemp(prefix=".dashboard-stage-", dir=extract_root)
    ).resolve()
    backup_dist = staging_root / "previous-dist"
    target_dist = extract_root / "dist"
    moved_existing = False
    cleanup_staging = True
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            for member in archive.infolist():
                target_path = (staging_root / member.filename).resolve()
                if not target_path.is_relative_to(staging_root):
                    raise ValueError(
                        f"Unsafe dashboard archive path: {member.filename}"
                    )
                archive.extract(member, staging_root)

        staged_dist = staging_root / "dist"
        if not _is_dist_complete(staged_dist):
            raise RuntimeError("Downloaded Dashboard package is incomplete")
        if expected_version is not None and not _is_version_compatible(
            _read_dashboard_version(staged_dist), expected_version
        ):
            raise RuntimeError(
                "Downloaded Dashboard version does not match "
                f"AstrBot {expected_version}"
            )

        if target_dist.exists() or target_dist.is_symlink():
            target_dist.replace(backup_dist)
            moved_existing = True
        try:
            staged_dist.replace(target_dist)
        except BaseException as apply_error:
            if moved_existing:
                cleanup_staging = False
                rollback_error: BaseException | str | None = None
                if target_dist.exists() or target_dist.is_symlink():
                    rollback_error = "the target path reappeared before rollback"
                else:
                    try:
                        backup_dist.replace(target_dist)
                        moved_existing = False
                        cleanup_staging = True
                    except BaseException as exc:
                        rollback_error = exc
                if moved_existing:
                    logger.critical(
                        "Dashboard replacement and rollback both failed. The "
                        "previous Dashboard remains at %s: %s",
                        backup_dist,
                        rollback_error,
                    )
                    raise RuntimeError(
                        "Dashboard replacement failed and the previous Dashboard "
                        f"must be restored from {backup_dist}"
                    ) from apply_error
            raise
    finally:
        if cleanup_staging:
            shutil.rmtree(staging_root, ignore_errors=True)
