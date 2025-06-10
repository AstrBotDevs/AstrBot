import aiohttp
import os
import re
import zipfile
import shutil

import ssl
import certifi

from astrbot.core.utils.io import on_error, download_file
from astrbot.core import logger
from astrbot.core.utils.version_comparator import VersionComparator


class ReleaseInfo:
    version: str
    published_at: str
    body: str

    def __init__(
        self, version: str = "", published_at: str = "", body: str = ""
    ) -> None:
        self.version = version
        self.published_at = published_at
        self.body = body

    def __str__(self) -> str:
        return f"\n{self.body}\n\n版本: {self.version} | 发布于: {self.published_at}"


class RepoZipUpdator:
    def __init__(self, repo_mirror: str = "") -> None:
        self.repo_mirror = repo_mirror
        self.rm_on_error = on_error

    async def fetch_release_info(self, url: str, latest: bool = True) -> list:
        """
        请求版本信息。
        返回一个列表，每个元素是一个字典，包含版本号、发布时间、更新内容、commit hash等信息。
        """
        try:
            ssl_context = ssl.create_default_context(
                cafile=certifi.where()
            )  # 新增：创建基于 certifi 的 SSL 上下文
            connector = aiohttp.TCPConnector(
                ssl=ssl_context
            )  # 新增：使用 TCPConnector 指定 SSL 上下文
            async with aiohttp.ClientSession(
                trust_env=True, connector=connector
            ) as session:
                async with session.get(url) as response:
                    # 检查 HTTP 状态码
                    if response.status != 200:
                        text = await response.text()
                        logger.error(
                            f"请求 {url} 失败，状态码: {response.status}, 内容: {text}"
                        )
                        raise Exception(f"请求失败，状态码: {response.status}")
                    result = await response.json()
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
                    }
                )
        except Exception as e:
            logger.error(f"解析版本信息时发生异常: {e}")
            raise Exception("解析版本信息失败")
        return ret

    def github_api_release_parser(self, releases: list) -> list:
        """
        解析 GitHub API 返回的 releases 信息。
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
                }
            )
        return ret

    def unzip(self):
        raise NotImplementedError()

    async def update(self):
        raise NotImplementedError()

    def compare_version(self, v1: str, v2: str) -> int:
        """Semver 版本比较"""
        return VersionComparator.compare_version(v1, v2)

    async def check_update(self, url: str, current_version: str) -> ReleaseInfo | None:
        update_data = await self.fetch_release_info(url)
        tag_name = update_data[0]["tag_name"]

        if self.compare_version(current_version, tag_name) >= 0:
            return None
        return ReleaseInfo(
            version=tag_name,
            published_at=update_data[0]["published_at"],
            body=update_data[0]["body"],
        )

    async def download_from_repo_url(self, target_path: str, repo_url: str, proxy=""):
        author, repo, branch = self.parse_github_url(repo_url)

        logger.info(f"正在下载更新 {repo} ...")

        if branch:
            logger.info(f"正在从指定分支 {branch} 下载 {author}/{repo}")
            release_url = (
                f"https://github.com/{author}/{repo}/archive/refs/heads/{branch}.zip"
            )
        else:
            try:
                release_url = f"https://api.github.com/repos/{author}/{repo}/releases"
                releases = await self.fetch_release_info(url=release_url)
            except Exception as e:
                logger.warning(
                    f"获取 {author}/{repo} 的 GitHub Releases 失败: {e}，将尝试下载默认分支"
                )
                releases = []
            if not releases:
                # 如果没有最新版本，下载默认分支
                logger.info(f"正在从默认分支下载 {author}/{repo}")
                release_url = (
                    f"https://github.com/{author}/{repo}/archive/refs/heads/master.zip"
                )
            else:
                release_url = releases[0]["zipball_url"]

        if proxy:
            proxy = proxy.rstrip("/")
            release_url = f"{proxy}/{release_url}"
            logger.info(
                f"检查到设置了镜像站，将使用镜像站下载 {author}/{repo} 仓库源码: {release_url}"
            )

        await download_file(release_url, target_path + ".zip")

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
        else:
            raise ValueError("无效的 GitHub URL")

    def unzip_file(self, zip_path: str, target_dir: str):
        """
        解压缩文件, 并将压缩包内**第一个**文件夹内的文件移动到 target_dir
        """
        os.makedirs(target_dir, exist_ok=True)
        update_dir = ""
        logger.info(f"解压文件: {zip_path}")
        with zipfile.ZipFile(zip_path, "r") as z:
            update_dir = z.namelist()[0]
            z.extractall(target_dir)

        files = os.listdir(os.path.join(target_dir, update_dir))
        for f in files:
            logger.info(f"移动更新文件/目录: {f}")
            if os.path.isdir(os.path.join(target_dir, update_dir, f)):
                if os.path.exists(os.path.join(target_dir, f)):
                    shutil.rmtree(os.path.join(target_dir, f), onerror=on_error)
            else:
                if os.path.exists(os.path.join(target_dir, f)):
                    os.remove(os.path.join(target_dir, f))
            shutil.move(os.path.join(target_dir, update_dir, f), target_dir)

        try:
            logger.info(
                f"删除临时更新文件: {zip_path} 和 {os.path.join(target_dir, update_dir)}"
            )
            shutil.rmtree(os.path.join(target_dir, update_dir), onerror=on_error)
            os.remove(zip_path)
        except BaseException:
            logger.warn(
                f"删除更新文件失败，可以手动删除 {zip_path} 和 {os.path.join(target_dir, update_dir)}"
            )

    def format_name(self, name: str) -> str:
        return name.replace("-", "_").lower()
