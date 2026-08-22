import inspect
import os
import re
import shutil
import time
import zipfile
from pathlib import Path

import certifi
import httpx

from astrbot.core import logger
from astrbot.core.repository import GitHubRepository
from astrbot.core.utils.io import ensure_dir, on_error
from astrbot.core.utils.version_comparator import VersionComparator

__all__ = ["ReleaseInfo"]


class ReleaseInfo:
    """Describe a repository release exposed by an updater.

    Args:
        version: Release tag used as an update target.
        published_at: Publication timestamp supplied by the release source.
        body: Release notes supplied by the release source.
    """

    version: str
    published_at: str
    body: str

    def __init__(
        self,
        version: str = "",
        published_at: str = "",
        body: str = "",
    ) -> None:
        self.version = version
        self.published_at = published_at
        self.body = body

    def __str__(self) -> str:
        return (
            f"\n{self.body}\n\nVersion: {self.version} | "
            f"Published at: {self.published_at}"
        )


class _RepoZipUpdater:
    """Download and apply ZIP updates from repository hosting providers."""

    def __init__(
        self,
        verify: str | bool | None = None,
    ) -> None:
        """Initialize the shared repository update workflow.

        Args:
            verify: TLS certificate verification configuration for HTTPX.
        """
        self._rm_on_error = on_error
        self._httpx_verify = certifi.where() if verify is None else verify

    def _create_httpx_client(self, timeout: float = 30.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            trust_env=True,
            verify=self._httpx_verify,
        )

    @staticmethod
    def _truncate_response_body(body: str, max_len: int = 1000) -> str:
        if len(body) <= max_len:
            return body
        return body[:max_len] + "...[truncated]"

    async def _fetch_repository_default_branch(
        self,
        repository: GitHubRepository,
    ) -> str | None:
        """Fetch the default branch for a repository.

        Args:
            repository: Parsed GitHub repository.

        Returns:
            The default branch name, or None if it cannot be resolved.
        """
        url = repository.default_branch_api_url
        try:
            async with self._create_httpx_client(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                repo_info = response.json()
        except Exception as exc:
            logger.debug(
                "Failed to get the default %s branch for %s/%s: %s",
                "github",
                repository.owner,
                repository.name,
                exc,
            )
            return None

        default_branch = str(repo_info.get("default_branch") or "").strip()
        return default_branch or None

    async def _resolve_repository_source(
        self,
        repo_url: str,
    ) -> GitHubRepository:
        """Resolve a repository URL to a downloadable source archive.

        Args:
            repo_url: Repository URL, optionally with an explicit tree branch.

        Returns:
            Resolved provider adapter and repository branch.

        Raises:
            ValueError: If the repository URL is unsupported or invalid.
        """
        repository = GitHubRepository.parse(repo_url)
        if repository.branch:
            return repository

        default_branch = await self._fetch_repository_default_branch(repository)
        branch = default_branch or "main"
        if not default_branch:
            logger.info(
                "Could not get the default %s branch for %s/%s; trying %s.",
                "github",
                repository.owner,
                repository.name,
                branch,
            )
        return GitHubRepository(
            repository.owner,
            repository.name,
            branch,
        )

    async def _download_file(
        self,
        url: str,
        path: str,
        timeout: float = 1800.0,
        progress_callback=None,
    ) -> None:
        target_path = Path(path)
        ensure_dir(target_path.parent)

        async def _emit_progress(payload: dict) -> None:
            if not progress_callback:
                return
            result = progress_callback(payload)
            if inspect.isawaitable(result):
                await result

        try:
            async with self._create_httpx_client(timeout=timeout) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    headers = getattr(response, "headers", {})
                    total_size = int(headers.get("content-length", 0))
                    downloaded_size = 0
                    start_time = time.time()
                    await _emit_progress(
                        {
                            "url": url,
                            "downloaded": 0,
                            "total": total_size,
                            "percent": 0,
                            "speed": 0,
                        },
                    )
                    with target_path.open("wb") as file:
                        async for chunk in response.aiter_bytes(8192):
                            file.write(chunk)
                            downloaded_size += len(chunk)
                            elapsed_time = max(time.time() - start_time, 1)
                            await _emit_progress(
                                {
                                    "url": url,
                                    "downloaded": downloaded_size,
                                    "total": total_size,
                                    "percent": downloaded_size / total_size
                                    if total_size > 0
                                    else 0,
                                    "speed": downloaded_size / 1024 / elapsed_time,
                                },
                            )
                    await _emit_progress(
                        {
                            "url": url,
                            "downloaded": downloaded_size,
                            "total": total_size,
                            "percent": 1,
                            "speed": 0,
                        },
                    )
        except Exception as e:
            logger.error(f"Failed to download file: {url} -> {target_path}: {e}")
            if self._rm_on_error and target_path.exists():
                target_path.unlink()
            raise

    async def _fetch_release_info(self, url: str, latest: bool = True) -> list:
        """请求版本信息。
        返回一个列表，每个元素是一个字典，包含版本号、发布时间、更新内容、commit hash等信息。
        """
        try:
            async with self._create_httpx_client() as client:
                response = await client.get(url)
                response.raise_for_status()
                result = response.json()
            if not result:
                return []
            ret = []
            for release in result:
                ret.append(
                    {
                        "version": release["name"],
                        "published_at": release["published_at"],
                        "body": release["body"],
                        "tag_name": release["tag_name"],
                        "zipball_url": release["zipball_url"],
                    },
                )
        except httpx.HTTPStatusError as e:
            response_body = ""
            if e.response is not None:
                response_body = self._truncate_response_body(e.response.text)
                logger.error(
                    f"Request to {url} failed with status "
                    f"{e.response.status_code}; response: {response_body}",
                )
            raise Exception("Failed to parse release information.") from e
        except Exception as e:
            logger.error(f"An error occurred while parsing release information: {e}")
            raise Exception("Failed to parse release information.") from e
        return ret

    def _compare_version(self, v1: str, v2: str) -> int:
        """Semver 版本比较"""
        return VersionComparator.compare_version(v1, v2)

    async def _check_update(
        self,
        url: str,
        current_version: str,
        consider_prerelease: bool = True,
    ) -> ReleaseInfo | None:
        update_data = await self._fetch_release_info(url)

        sel_release_data = None
        if consider_prerelease:
            tag_name = update_data[0]["tag_name"]
            sel_release_data = update_data[0]
        else:
            for data in update_data:
                # 跳过带有 alpha、beta 等预发布标签的版本
                if re.search(
                    r"[\-_.]?(alpha|beta|rc|dev)[\-_.]?\d*$",
                    data["tag_name"],
                    re.IGNORECASE,
                ):
                    continue
                tag_name = data["tag_name"]
                sel_release_data = data
                break

        if not sel_release_data or not tag_name:
            logger.error("No suitable release was found.")
            return None

        if self._compare_version(current_version, tag_name) >= 0:
            return None
        return ReleaseInfo(
            version=tag_name,
            published_at=sel_release_data["published_at"],
            body=sel_release_data["body"],
        )

    async def _download_repository(
        self, target_path: str, repo_url: str, proxy=""
    ) -> None:
        repository = await self._resolve_repository_source(repo_url)

        logger.info(f"Downloading update for {repository.name} ...")
        logger.info(
            "Downloading %s/%s from %s branch %s",
            repository.owner,
            repository.name,
            "github",
            repository.branch,
        )
        release_url = repository.archive_url

        if proxy:
            proxy = proxy.rstrip("/")
            release_url = f"{proxy}/{release_url}"
            logger.info(
                f"A mirror is configured; downloading the {repository.owner}/"
                f"{repository.name} source "
                f"from the mirror: {release_url}",
            )

        await self._download_file(release_url, target_path + ".zip")

    def _extract_archive(self, zip_path: str, target_dir: str) -> None:
        """解压缩文件, 并将压缩包内**第一个**文件夹内的文件移动到 target_dir"""
        ensure_dir(target_dir)
        with zipfile.ZipFile(zip_path, "r") as z:
            update_dir = self._resolve_archive_root_dir(z.namelist())
            z.extractall(target_dir)
        logger.debug(f"Finished extracting archive: {zip_path}")

        self._finalize_extracted_archive(zip_path, target_dir, update_dir)

    @staticmethod
    def _resolve_archive_root_dir(entries: list[str]) -> str:
        normalized_entries = [os.path.normpath(entry) for entry in entries]
        portable_entries = [entry.replace("\\", "/") for entry in normalized_entries]
        root_candidates: list[str] = []

        for raw_entry, normalized_entry, portable_entry in zip(
            entries, normalized_entries, portable_entries
        ):
            if normalized_entry == ".":
                continue

            has_children = any(
                other_entry != portable_entry
                and other_entry.startswith(f"{portable_entry}/")
                for other_entry in portable_entries
            )
            if raw_entry.endswith(("/", "\\")) or has_children:
                root_candidates.append(normalized_entry)
                continue

            parent_portable, _, _ = portable_entry.rpartition("/")
            if not parent_portable:
                return ""
            root_candidates.append(parent_portable.replace("/", os.sep))

        if not root_candidates:
            return ""
        return os.path.commonpath(root_candidates)

    def _finalize_extracted_archive(
        self,
        zip_path: str,
        target_dir: str,
        update_dir: str,
    ) -> None:
        target_root_path = os.path.normpath(target_dir)

        def _join_under_root(root: str, *parts: str) -> str:
            path = os.path.normpath(os.path.join(root, *parts))
            try:
                if os.path.commonpath([root, path]) != root:
                    raise ValueError("path escapes root directory")
            except ValueError as exc:
                raise ValueError("path escapes root directory") from exc
            return path

        if not update_dir:
            try:
                os.remove(zip_path)
            except Exception:
                logger.warning(
                    f"Failed to delete the update file; delete it manually: {zip_path}"
                )
            return

        update_root_path = _join_under_root(target_root_path, update_dir)

        files = os.listdir(update_root_path)
        for f in files:
            update_item_path = _join_under_root(update_root_path, f)
            target_item_path = _join_under_root(target_root_path, f)
            if os.path.isdir(update_item_path):
                if os.path.exists(target_item_path):
                    shutil.rmtree(target_item_path, onerror=on_error)
            elif os.path.exists(target_item_path):
                os.remove(target_item_path)
            shutil.move(update_item_path, target_root_path)

        try:
            logger.debug(
                f"Deleting temporary update files: {zip_path} and {update_root_path}"
            )
            shutil.rmtree(update_root_path, onerror=on_error)
            os.remove(zip_path)
        except Exception:
            logger.warning(
                "Failed to delete the update files; delete them manually: "
                f"{zip_path} and {update_root_path}"
            )

    def _format_name(self, name: str) -> str:
        return name.replace("-", "_").lower()
