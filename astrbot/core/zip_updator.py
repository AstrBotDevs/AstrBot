import inspect
import os
import re
import shutil
import time
import zipfile
from pathlib import Path
from typing import NoReturn

import certifi
import httpx

from astrbot.core import logger
from astrbot.core.utils.io import ensure_dir, on_error
from astrbot.core.utils.version_comparator import VersionComparator


class ReleaseInfo:
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


class RepoZipUpdator:
    def __init__(self, repo_mirror: str = "", verify: str | bool | None = None) -> None:
        self.repo_mirror = repo_mirror
        self.rm_on_error = on_error
        self.httpx_verify = certifi.where() if verify is None else verify

    def _create_httpx_client(self, timeout: float = 30.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            trust_env=True,
            verify=self.httpx_verify,
        )

    @staticmethod
    def _truncate_response_body(body: str, max_len: int = 1000) -> str:
        if len(body) <= max_len:
            return body
        return body[:max_len] + "...[truncated]"

    async def fetch_github_default_branch(self, author: str, repo: str) -> str | None:
        """Fetch the default branch for a GitHub repository.

        Args:
            author: GitHub repository owner.
            repo: GitHub repository name.

        Returns:
            The default branch name, or None if it cannot be resolved.
        """
        url = f"https://api.github.com/repos/{author}/{repo}"
        try:
            async with self._create_httpx_client(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                repo_info = response.json()
        except Exception as exc:
            logger.debug(
                "Failed to get the default GitHub branch for %s/%s: %s",
                author,
                repo,
                exc,
            )
            return None

        default_branch = str(repo_info.get("default_branch") or "").strip()
        return default_branch or None

    async def resolve_github_source_branch(
        self,
        repo_url: str,
    ) -> tuple[str, str, str]:
        """Resolve the GitHub branch used for repository source downloads.

        Args:
            repo_url: GitHub repository URL, optionally with a tree branch.

        Returns:
            Repository owner, name, and resolved source branch.

        Raises:
            ValueError: If the repository URL is invalid.
        """
        author, repo, branch = self.parse_github_url(repo_url)
        if branch:
            return author, repo, branch

        default_branch = await self.fetch_github_default_branch(author, repo)
        if default_branch:
            return author, repo, default_branch

        logger.info(
            "Could not get the default branch for %s/%s; trying the main branch.",
            author,
            repo,
        )
        return author, repo, "main"

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
            if self.rm_on_error and target_path.exists():
                target_path.unlink()
            raise

    async def fetch_release_info(self, url: str, latest: bool = True) -> list:
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
            # if latest:
            #     ret = self.github_api_release_parser([result[0]])
            # else:
            #     ret = self.github_api_release_parser(result)
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

    def github_api_release_parser(self, releases: list) -> list:
        """解析 GitHub API 返回的 releases 信息。
        返回一个列表，每个元素是一个字典，包含版本号、发布时间、更新内容、commit hash等信息。
        """
        ret = []
        for release in releases:
            ret.append(
                {
                    "version": release["name"],
                    "published_at": release["published_at"],
                    "body": release["body"],
                    "tag_name": release["tag_name"],
                    "zipball_url": release["zipball_url"],
                },
            )
        return ret

    def unzip(self) -> NoReturn:
        raise NotImplementedError

    async def update(self) -> NoReturn:
        raise NotImplementedError

    def compare_version(self, v1: str, v2: str) -> int:
        """Semver 版本比较"""
        return VersionComparator.compare_version(v1, v2)

    async def check_update(
        self,
        url: str,
        current_version: str,
        consider_prerelease: bool = True,
    ) -> ReleaseInfo | None:
        update_data = await self.fetch_release_info(url)

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

        if self.compare_version(current_version, tag_name) >= 0:
            return None
        return ReleaseInfo(
            version=tag_name,
            published_at=sel_release_data["published_at"],
            body=f"{tag_name}\n\n{sel_release_data['body']}",
        )

    async def download_from_repo_url(
        self, target_path: str, repo_url: str, proxy=""
    ) -> None:
        author, repo, branch = await self.resolve_github_source_branch(repo_url)

        logger.info(f"Downloading update for {repo} ...")
        logger.info(f"Downloading {author}/{repo} from branch {branch}")
        release_url = (
            f"https://github.com/{author}/{repo}/archive/refs/heads/{branch}.zip"
        )

        if proxy:
            proxy = proxy.rstrip("/")
            release_url = f"{proxy}/{release_url}"
            logger.info(
                f"A mirror is configured; downloading the {author}/{repo} source "
                f"from the mirror: {release_url}",
            )

        await self._download_file(release_url, target_path + ".zip")

    def parse_github_url(self, url: str):
        """使用正则表达式解析 GitHub 仓库 URL，支持 `.git` 后缀和 `tree/branch` 结构
        Returns:
            tuple[str, str, str]: 返回作者名、仓库名和分支名
        Raises:
            ValueError: 如果 URL 格式不正确
        """
        cleaned_url = url.rstrip("/")
        pattern = r"^https://github\.com/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_-]+)(\.git)?(?:/tree/([a-zA-Z0-9_-]+))?$"
        match = re.match(pattern, cleaned_url)

        if match:
            author = match.group(1)
            repo = match.group(2)
            branch = match.group(4)
            return author, repo, branch
        raise ValueError("Invalid GitHub URL")

    def unzip_file(self, zip_path: str, target_dir: str) -> None:
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

    def format_name(self, name: str) -> str:
        return name.replace("-", "_").lower()
