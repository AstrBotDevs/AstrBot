"""Dashboard asset discovery, compatibility, and package handling."""

import re
import zipfile
from pathlib import Path

from astrbot.core import logger
from astrbot.core.config.default import VERSION
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
    return (dist_path / "index.html").is_file() and _is_version_compatible(
        _read_dashboard_version(dist_path),
        current_version,
    )


def _should_use_bundled_dist(user_dist: str | Path, current_version: str) -> bool:
    """Check whether bundled assets should replace a managed user dist.

    Args:
        user_dist: Managed Dashboard dist under the AstrBot data directory.
        current_version: Current AstrBot Core version.

    Returns:
        Whether the user dist is stale or incomplete and bundled assets match.
    """
    user_dist = Path(user_dist)
    user_version = _read_dashboard_version(user_dist)
    bundled_dist = _get_bundled_dist_path()
    if not user_dist.exists() or not _is_dist_compatible(
        bundled_dist,
        current_version,
    ):
        return False
    if user_version is None or not (user_dist / "index.html").is_file():
        return True
    return not _is_version_compatible(user_version, current_version)


def resolve_dashboard_dist(webui_dir: str | Path | None = None) -> Path | None:
    """Select the Dashboard dist that should be served.

    Args:
        webui_dir: Optional explicitly configured Dashboard directory.

    Returns:
        Explicit, managed, bundled, or stale fallback dist in priority order;
        None when an existing managed dist is incomplete.
    """
    if webui_dir and Path(webui_dir).exists():
        return Path(webui_dir).absolute()

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
        )


def _extract_package(
    zip_path: str | Path,
    extract_path: str | Path,
) -> None:
    """Safely extract a Dashboard package.

    Args:
        zip_path: Dashboard ZIP archive path.
        extract_path: Directory where package contents should be extracted.

    Raises:
        ValueError: If an archive member escapes the extraction root.
    """
    extract_root = Path(extract_path).resolve()
    ensure_dir(extract_root)
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            target_path = (extract_root / member.filename).resolve()
            if not target_path.is_relative_to(extract_root):
                raise ValueError(f"Unsafe dashboard archive path: {member.filename}")
            archive.extract(member, extract_root)
