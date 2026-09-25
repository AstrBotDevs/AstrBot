import asyncio
import hashlib
import os
import shutil
import tarfile
import tempfile
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import parse_qs, unquote, urldefrag, urljoin, urlsplit

from packaging.utils import InvalidSdistFilename, parse_sdist_filename
from packaging.version import Version

from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.dashboard_assets import (
    _download_package,
    _extract_package,
    _get_bundled_dist_path,
    _is_dist_compatible,
    _is_dist_complete,
    _read_dashboard_version,
    _should_use_bundled_dist,
)
from astrbot.core.desktop_runtime import is_desktop_managed_backend
from astrbot.core.repository import GitHubRepository
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_path,
    get_astrbot_temp_path,
)
from astrbot.core.utils.io import ensure_dir, remove_dir

from .zip_updater import ReleaseInfo, _RepoZipUpdater

__all__ = ["AstrBotUpdater", "UpdateProgress", "UpdateProgressCallback"]


@dataclass(frozen=True, slots=True)
class UpdateProgress:
    """Observable progress for an AstrBot update.

    Args:
        stage: Current update stage.
        status: Current stage status.
        message: Human-readable progress message.
        overall_percent: Overall update progress from 0 to 100.
        downloaded_bytes: Downloaded bytes during a download stage.
        total_bytes: Expected total bytes when supplied by the server.
        speed_kib_per_second: Current download speed in KiB/s.
    """

    stage: Literal["dashboard", "core", "verify", "apply"]
    status: Literal["running", "done"]
    message: str
    overall_percent: int
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed_kib_per_second: float | None = None


UpdateProgressCallback = Callable[[UpdateProgress], Awaitable[None]]


class _SourceDistributionLinks(HTMLParser):
    """Collect non-yanked download links from a PyPI Simple HTML index."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        href = attributes.get("href")
        if tag == "a" and href and "data-yanked" not in attributes:
            self.links.append(href)


class AstrBotUpdater(_RepoZipUpdater):
    """Expose the complete, high-level AstrBot Core update operations."""

    def __init__(
        self,
        verify: str | bool | None = None,
    ) -> None:
        """Initialize the AstrBot core updater.

        Args:
            verify: TLS certificate verification configuration for HTTPX.
        """
        super().__init__(verify=verify)
        self._main_path = get_astrbot_path()
        self._release_api = "https://api.soulter.top/releases"
        self._repository_url = "https://github.com/AstrBotDevs/AstrBot"
        self._core_package_base_url = (
            "https://astrbot-registry.soulter.top/download/astrbot-core"
        )

    def _build_core_package_url(self, version: str | None) -> str | None:
        """Build the hosted core package URL for a release tag.

        Args:
            version: Release tag, such as ``v4.26.0``.

        Returns:
            Public package URL, or None when hosted package download is disabled.
        """

        if not version or not str(version).startswith("v"):
            return None

        base_url = os.environ.get(
            "ASTRBOT_CORE_PACKAGE_BASE_URL",
            self._core_package_base_url,
        ).strip()
        if not base_url:
            return None
        return f"{base_url.rstrip('/')}/{version}/source.zip"

    async def check_update(
        self,
        consider_prerelease: bool = True,
    ) -> ReleaseInfo | None:
        """Check whether a newer AstrBot release is available.

        Args:
            consider_prerelease: Whether prerelease versions may be selected.

        Returns:
            The newer release, or None when the current version is up to date.
        """
        return await self._check_update(
            self._release_api,
            VERSION,
            consider_prerelease,
        )

    async def get_releases(self) -> list[ReleaseInfo]:
        """Fetch available AstrBot releases.

        Returns:
            Releases in upstream order, including prereleases. Each item contains
            the update target version, publication timestamp, and release notes.
        """
        releases = await self._fetch_release_info(self._release_api)
        return [
            ReleaseInfo(
                version=release["tag_name"],
                published_at=release["published_at"],
                body=release["body"],
            )
            for release in releases
        ]

    async def update(
        self,
        version: str | None = None,
        proxy: str = "",
        progress_callback: UpdateProgressCallback | None = None,
    ) -> None:
        """Download, validate, and apply matching Core and Dashboard packages.

        Args:
            version: Release tag or commit hash. None selects the latest release.
            proxy: Optional URL-prefix mirror.
            progress_callback: Optional asynchronous progress observer. Observer
                failures are logged and do not interrupt the update.

        Returns:
            None.

        Raises:
            Exception: If either package cannot be prepared or applied.
        """

        async def emit_progress(
            stage: Literal["dashboard", "core", "verify", "apply"],
            status: Literal["running", "done"],
            message: str,
            percent: int,
            download: dict | None = None,
        ) -> None:
            if not progress_callback:
                return
            event = UpdateProgress(
                stage=stage,
                status=status,
                message=message,
                overall_percent=percent,
                downloaded_bytes=(
                    int(download.get("downloaded") or 0) if download else None
                ),
                total_bytes=int(download.get("total") or 0) if download else None,
                speed_kib_per_second=(
                    float(download.get("speed") or 0) if download else None
                ),
            )
            try:
                await progress_callback(event)
            except Exception:
                logger.exception("AstrBot update progress observer failed.")

        async def dashboard_progress(payload: dict) -> None:
            await emit_progress(
                "dashboard",
                "running",
                "正在下载 WebUI...",
                int(float(payload.get("percent") or 0) * 45),
                payload,
            )

        async def core_progress(payload: dict) -> None:
            await emit_progress(
                "core",
                "running",
                "正在下载 AstrBot 项目代码...",
                45 + int(float(payload.get("percent") or 0) * 45),
                payload,
            )

        if os.environ.get("ASTRBOT_CLI") or os.environ.get("ASTRBOT_LAUNCHER"):
            raise RuntimeError(
                "You are running AstrBot via CLI; use pip or uv tool upgrade "
                "to update AstrBot."
            )

        target_version = version
        target_release = None
        if not target_version or target_version == "latest":
            releases = await self._fetch_release_info(self._release_api)
            if not releases:
                raise RuntimeError("No AstrBot release is available.")
            target_release = releases[0]
            target_version = target_release["tag_name"]
            if self._compare_version(VERSION, target_version) >= 0:
                raise RuntimeError("AstrBot is already up to date.")

        update_temp_parent = Path(get_astrbot_temp_path()) / "updates"
        if update_temp_parent.is_symlink():
            update_temp_parent.unlink()
        update_temp_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        update_temp_parent.chmod(0o700)

        with tempfile.TemporaryDirectory(
            prefix="project-update-",
            dir=update_temp_parent,
        ) as update_temp_dir_name:
            update_temp_dir = Path(update_temp_dir_name)
            dashboard_zip_path = update_temp_dir / "dashboard.zip"
            core_zip_path = update_temp_dir / "core.zip"

            mirror_prepared = False
            if target_version.startswith("v"):
                await emit_progress(
                    "dashboard",
                    "running",
                    "Checking the PyPI mirror for the update...",
                    0,
                )
                mirror_prepared = await self._download_pypi_package(
                    target_version,
                    core_zip_path,
                    dashboard_zip_path,
                    progress_callback=dashboard_progress,
                )
            if mirror_prepared:
                await emit_progress(
                    "dashboard", "done", "Bundled WebUI prepared from PyPI.", 45
                )
                await emit_progress(
                    "core", "done", "AstrBot source prepared from PyPI.", 90
                )
            else:
                if target_version.startswith("v") and target_release is None:
                    releases = await self._fetch_release_info(self._release_api)
                    target_release = next(
                        (
                            release
                            for release in releases
                            if release["tag_name"] == target_version
                        ),
                        None,
                    )
                    if target_release is None:
                        raise RuntimeError(
                            f"No update package was found for version {target_version}."
                        )

                await emit_progress(
                    "dashboard",
                    "running",
                    "正在下载 WebUI...",
                    0,
                )
                await _download_package(
                    path=str(dashboard_zip_path),
                    version=target_version,
                    proxy=proxy,
                    progress_callback=dashboard_progress,
                    extract=False,
                    allow_insecure_ssl_fallback=False,
                )
                await emit_progress(
                    "dashboard",
                    "done",
                    "WebUI 下载完成。",
                    45,
                )

                await emit_progress(
                    "core",
                    "running",
                    "正在下载 AstrBot 项目代码...",
                    45,
                )
                await self._download_core_package(
                    latest=False,
                    version=target_version,
                    proxy=proxy,
                    path=core_zip_path,
                    progress_callback=core_progress,
                    release_data=target_release,
                )
                await emit_progress(
                    "core",
                    "done",
                    "项目代码下载完成。",
                    90,
                )

            await emit_progress(
                "verify",
                "running",
                "下载完成，正在校验更新包...",
                90,
            )

            def verify_packages() -> None:
                for zip_path in (dashboard_zip_path, core_zip_path):
                    with zipfile.ZipFile(zip_path, "r") as archive:
                        corrupt_member = archive.testzip()
                    if corrupt_member:
                        raise ValueError(f"更新包校验失败: {corrupt_member}")

            await asyncio.to_thread(verify_packages)
            await emit_progress(
                "verify",
                "done",
                "更新包校验完成。",
                91,
            )

            await emit_progress(
                "apply",
                "running",
                "下载完成，正在应用更新...",
                91,
            )
            await asyncio.to_thread(self._apply_core_package, core_zip_path)
            await asyncio.to_thread(
                _extract_package,
                dashboard_zip_path,
                Path(get_astrbot_data_path()),
                target_version if len(target_version) != 40 else None,
            )
            await emit_progress(
                "apply",
                "done",
                "更新文件应用完成。",
                92,
            )

    async def _download_pypi_package(
        self,
        version: str,
        core_zip_path: Path,
        dashboard_zip_path: Path,
        progress_callback=None,
    ) -> bool:
        """Prepare a matching source distribution and its bundled Dashboard.

        Args:
            version: Target release tag.
            core_zip_path: Temporary destination for the existing Core apply flow.
            dashboard_zip_path: Temporary destination for the Dashboard apply flow.
            progress_callback: Download progress observer.

        Returns:
            Whether both packages are validated and ready. Mirror failures return
            False so the caller can use the existing update sources.
        """
        index_url = "https://mirrors.cernet.edu.cn/pypi/web/simple/astrbot/"
        source_path = core_zip_path.with_suffix(".tar.gz")
        try:
            target = Version(version)
            async with self._create_httpx_client(timeout=10.0) as client:
                response = await client.get(index_url)
                response.raise_for_status()
            parser = _SourceDistributionLinks()
            parser.feed(response.text)
            for link in parser.links:
                url = urljoin(str(response.url), link)
                parsed = urlsplit(url)
                filename = PurePosixPath(unquote(parsed.path)).name
                if parsed.scheme != "https" or not filename.endswith(".tar.gz"):
                    continue
                try:
                    name, candidate = parse_sdist_filename(filename)
                except InvalidSdistFilename:
                    continue
                if name != "astrbot" or candidate != target:
                    continue
                digest = parse_qs(parsed.fragment).get("sha256", [""])[0]
                if len(digest) != 64 or any(
                    char not in "0123456789abcdef" for char in digest.lower()
                ):
                    raise ValueError("PyPI source link has no valid SHA-256 digest")
                logger.info("Downloading AstrBot source and WebUI from %s", url)
                await self._download_file(
                    urldefrag(url)[0],
                    str(source_path),
                    timeout=60.0,
                    progress_callback=progress_callback,
                )
                await asyncio.to_thread(
                    self._prepare_pypi_package,
                    source_path,
                    digest,
                    version,
                    core_zip_path,
                    dashboard_zip_path,
                )
                return True
            logger.info("AstrBot %s is not available in the PyPI mirror.", version)
        except Exception as exc:
            logger.warning(
                "PyPI update package failed: %s. Falling back to the existing "
                "Core and Dashboard download sources.",
                exc,
            )
        finally:
            source_path.unlink(missing_ok=True)
        core_zip_path.unlink(missing_ok=True)
        dashboard_zip_path.unlink(missing_ok=True)
        return False

    @staticmethod
    def _prepare_pypi_package(
        source_path: Path,
        expected_digest: str,
        version: str,
        core_zip_path: Path,
        dashboard_zip_path: Path,
    ) -> None:
        """Validate an sdist and stage ZIPs for the existing update application.

        Args:
            source_path: Downloaded tar.gz source distribution.
            expected_digest: SHA-256 advertised by the mirror index.
            version: Target release tag.
            core_zip_path: Prepared Core ZIP destination.
            dashboard_zip_path: Prepared Dashboard ZIP destination.

        Raises:
            ValueError: If the archive hash, paths, metadata, or assets are invalid.
        """
        digest = hashlib.sha256()
        with source_path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected_digest.lower():
            raise ValueError("PyPI source archive SHA-256 mismatch")

        with tempfile.TemporaryDirectory(
            prefix="pypi-source-", dir=source_path.parent
        ) as staging_name:
            staging = Path(staging_name)
            with tarfile.open(source_path, "r:gz") as archive:
                members = archive.getmembers()
                roots: set[str] = set()
                seen: set[PurePosixPath] = set()
                for member in members:
                    path = PurePosixPath(member.name)
                    if (
                        not path.parts
                        or path.is_absolute()
                        or ".." in path.parts
                        or "\\" in member.name
                        or ":" in member.name
                        or not (member.isfile() or member.isdir())
                        or path in seen
                    ):
                        raise ValueError(f"Unsafe PyPI archive member: {member.name}")
                    roots.add(path.parts[0])
                    seen.add(path)
                if len(roots) != 1:
                    raise ValueError("PyPI source archive must have one root directory")
                root_name = roots.pop()
                name, source_version = parse_sdist_filename(f"{root_name}.tar.gz")
                if name != "astrbot" or source_version != Version(version):
                    raise ValueError("PyPI source directory does not match the release")

                # Copy only regular files; never follow archive links or execute code.
                for member in members:
                    destination = staging.joinpath(*PurePosixPath(member.name).parts)
                    if member.isdir():
                        destination.mkdir(parents=True, exist_ok=True)
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with (
                        archive.extractfile(member) as source,
                        destination.open("wb") as output,
                    ):
                        shutil.copyfileobj(source, output)

            root = staging / root_name
            for required in (
                "PKG-INFO",
                "main.py",
                "pyproject.toml",
                "requirements.txt",
                "astrbot/__init__.py",
            ):
                if not (root / required).is_file():
                    raise ValueError(f"PyPI source archive is missing {required}")
            with (root / "PKG-INFO").open("rb") as metadata_file:
                metadata = BytesParser().parse(metadata_file, headersonly=True)
            if str(metadata.get("Name", "")).lower() != "astrbot" or Version(
                str(metadata.get("Version", ""))
            ) != Version(version):
                raise ValueError("PyPI source metadata does not match the release")
            dashboard = root / "astrbot" / "dashboard" / "dist"
            if not _is_dist_compatible(dashboard, version):
                raise ValueError("PyPI source has an incomplete or mismatched WebUI")

            shutil.make_archive(
                str(core_zip_path.with_suffix("")), "zip", staging, root_name
            )
            shutil.make_archive(
                str(dashboard_zip_path.with_suffix("")), "zip", dashboard.parent, "dist"
            )

    async def ensure_dashboard(self) -> Path:
        """Ensure acceptable Dashboard assets exist for the active runtime.

        Desktop-managed runtimes only receive assets matching the running Core.
        Standalone runtimes retain the legacy offline fallback to a structurally
        complete ``data/dist`` when a matching package cannot be prepared.

        Returns:
            Directory containing the Dashboard assets to serve.

        Raises:
            Exception: If no acceptable Dashboard can be prepared.
        """
        data_dist_path = Path(get_astrbot_data_path()) / "dist"
        bundled_dist = _get_bundled_dist_path()
        if _is_dist_compatible(data_dist_path, VERSION):
            return data_dist_path
        if not data_dist_path.exists() and _is_dist_compatible(
            bundled_dist,
            VERSION,
        ):
            return bundled_dist

        if _should_use_bundled_dist(data_dist_path, VERSION):
            try:
                remove_dir(str(data_dist_path))
                shutil.copytree(bundled_dist, data_dist_path)
                return data_dist_path
            except Exception as exc:
                logger.warning(
                    "Failed to replace the managed Dashboard with bundled assets: %s",
                    exc,
                )
                return bundled_dist

        existing_version = _read_dashboard_version(data_dist_path)
        try:
            await _download_package(
                version=f"v{VERSION}",
                allow_insecure_ssl_fallback=False,
            )
        except Exception:
            if not is_desktop_managed_backend() and _is_dist_complete(data_dist_path):
                logger.warning(
                    "Using existing standalone Dashboard %s because a compatible "
                    "package could not be prepared for v%s.",
                    existing_version or "unknown",
                    VERSION,
                )
                return data_dist_path
            raise

        if not _is_dist_compatible(data_dist_path, VERSION):
            raise RuntimeError(
                f"Downloaded Dashboard is not compatible with AstrBot v{VERSION}"
            )
        return data_dist_path

    async def _download_core_package(
        self,
        latest=True,
        version=None,
        proxy="",
        path: str | Path = "temp.zip",
        progress_callback=None,
        release_data: dict | None = None,
    ) -> Path:
        """Download an AstrBot core update package without applying it.

        Args:
            latest: Whether to download the latest release.
            version: Specific release tag or commit hash to download.
            proxy: Optional URL-prefix mirror for the archive request.
            path: Destination zip path.
            progress_callback: Optional callback for download progress payloads.
            release_data: Previously resolved metadata for the target release.

        Returns:
            Path to the downloaded update package.

        Raises:
            Exception: If update metadata cannot resolve a package URL.
        """

        file_url = None

        if os.environ.get("ASTRBOT_CLI") or os.environ.get("ASTRBOT_LAUNCHER"):
            raise Exception(
                "Error: You are running AstrBot via CLI, please use `pip` or `uv tool upgrade` to update AstrBot."
            )  # 避免版本管理混乱

        target_version = None
        if latest:
            update_data = await self._fetch_release_info(self._release_api)
            if not update_data:
                raise RuntimeError("No AstrBot release is available.")
            latest_version = update_data[0]["tag_name"]
            if self._compare_version(VERSION, latest_version) >= 0:
                raise Exception("AstrBot is already up to date.")
            target_version = latest_version
            file_url = update_data[0]["zipball_url"]
        elif str(version).startswith("v"):
            if release_data is None:
                update_data = await self._fetch_release_info(self._release_api)
                release_data = next(
                    (data for data in update_data if data["tag_name"] == version),
                    None,
                )
            if release_data is None or release_data["tag_name"] != version:
                raise Exception(f"No update package was found for version {version}.")
            target_version = release_data["tag_name"]
            file_url = release_data["zipball_url"]
        else:
            if len(str(version)) != 40:
                raise Exception("The commit hash must be 40 characters long.")
            repository = GitHubRepository.parse(self._repository_url)
            file_url = repository.revision_archive_url(str(version))
        logger.info(f"Preparing to update AstrBot Core to version {version}")

        if proxy:
            proxy = proxy.removesuffix("/")
            file_url = f"{proxy}/{file_url}"

        zip_path = Path(path)
        ensure_dir(zip_path.parent)
        hosted_package_url = self._build_core_package_url(target_version)
        if hosted_package_url:
            try:
                logger.info(
                    "Attempting to download the AstrBot Core update package from "
                    f"hosted storage first: {hosted_package_url}"
                )
                await self._download_file(
                    hosted_package_url,
                    str(zip_path),
                    progress_callback=progress_callback,
                )
                if not zipfile.is_zipfile(zip_path):
                    raise RuntimeError(
                        "Downloaded hosted package is not a valid ZIP file"
                    )
                return zip_path
            except Exception as exc:
                logger.warning(
                    "Failed to download the AstrBot Core update package from hosted "
                    f"storage: {exc}. Falling back to the current update source."
                )

        await self._download_file(
            file_url,
            str(zip_path),
            progress_callback=progress_callback,
        )
        return zip_path

    def _apply_core_package(self, zip_path: str | Path) -> None:
        """Apply a previously downloaded AstrBot core update package.

        Args:
            zip_path: Core update zip archive path.

        Returns:
            None.

        Raises:
            Exception: If the archive cannot be extracted or applied.
        """

        logger.info("AstrBot Core update package downloaded; extracting the archive.")
        self._extract_archive(str(zip_path), self._main_path)
