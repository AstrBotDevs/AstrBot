import os
import sys
import time
from json import JSONDecodeError

import aiohttp
import psutil

from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.release_constants import NIGHTLY_TAG
from astrbot.core.utils.astrbot_path import get_astrbot_path
from astrbot.core.utils.io import download_file

from .zip_updator import (
    PRERELEASE_TAG_REGEX,
    FetchReleaseError,
    ReleaseInfo,
    RepoZipUpdator,
)


class AstrBotUpdator(RepoZipUpdator):
    """AstrBot 更新器，继承自 RepoZipUpdator 类
    该类用于处理 AstrBot 的更新操作
    功能包括检查更新、下载更新文件、解压缩更新文件等
    """

    def __init__(self, repo_mirror: str = "") -> None:
        super().__init__(repo_mirror)
        self.MAIN_PATH = get_astrbot_path()
        self.ASTRBOT_RELEASE_API = "https://api.soulter.top/releases"
        self.GITHUB_RELEASE_API = (
            "https://api.github.com/repos/AstrBotDevs/AstrBot/releases"
        )
        self.NIGHTLY_TAG = NIGHTLY_TAG

    def terminate_child_processes(self) -> None:
        """终止当前进程的所有子进程
        使用 psutil 库获取当前进程的所有子进程，并尝试终止它们
        """
        try:
            parent = psutil.Process(os.getpid())
            children = parent.children(recursive=True)
            logger.info(f"正在终止 {len(children)} 个子进程。")
            for child in children:
                logger.info(f"正在终止子进程 {child.pid}")
                child.terminate()
                try:
                    child.wait(timeout=3)
                except psutil.NoSuchProcess:
                    continue
                except psutil.TimeoutExpired:
                    logger.info(f"子进程 {child.pid} 没有被正常终止, 正在强行杀死。")
                    child.kill()
        except psutil.NoSuchProcess:
            pass

    @staticmethod
    def _is_option_arg(arg: str) -> bool:
        return arg.startswith("-")

    @classmethod
    def _collect_flag_values(cls, argv: list[str], flag: str) -> str | None:
        try:
            idx = argv.index(flag)
        except ValueError:
            return None

        if idx + 1 >= len(argv):
            return None

        value_parts: list[str] = []
        for arg in argv[idx + 1 :]:
            if cls._is_option_arg(arg):
                break
            if arg:
                value_parts.append(arg)

        if not value_parts:
            return None

        return " ".join(value_parts).strip() or None

    @classmethod
    def _resolve_webui_dir_arg(cls, argv: list[str]) -> str | None:
        return cls._collect_flag_values(argv, "--webui-dir")

    def _build_frozen_reboot_args(self) -> list[str]:
        argv = list(sys.argv[1:])
        webui_dir = self._resolve_webui_dir_arg(argv)
        if not webui_dir:
            webui_dir = os.environ.get("ASTRBOT_WEBUI_DIR")

        if webui_dir:
            return ["--webui-dir", webui_dir]
        return []

    @staticmethod
    def _reset_pyinstaller_environment() -> None:
        if not getattr(sys, "frozen", False):
            return
        os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        for key in list(os.environ.keys()):
            if key.startswith("_PYI_"):
                os.environ.pop(key, None)

    def _build_reboot_argv(self, executable: str) -> list[str]:
        if os.environ.get("ASTRBOT_CLI") == "1":
            args = sys.argv[1:]
            return [executable, "-m", "astrbot.cli.__main__", *args]
        if getattr(sys, "frozen", False):
            args = self._build_frozen_reboot_args()
            return [executable, *args]
        return [executable, *sys.argv]

    @staticmethod
    def _exec_reboot(executable: str, argv: list[str]) -> None:
        if os.name == "nt" and getattr(sys, "frozen", False):
            quoted_executable = f'"{executable}"' if " " in executable else executable
            quoted_args = [f'"{arg}"' if " " in arg else arg for arg in argv[1:]]
            os.execl(executable, quoted_executable, *quoted_args)
            return
        os.execv(executable, argv)

    def _reboot(self, delay: int = 3) -> None:
        """重启当前程序
        在指定的延迟后，终止所有子进程并重新启动程序
        这里只能使用 os.exec* 来重启程序
        """
        time.sleep(delay)
        self.terminate_child_processes()
        executable = sys.executable

        try:
            self._reset_pyinstaller_environment()
            reboot_argv = self._build_reboot_argv(executable)
            self._exec_reboot(executable, reboot_argv)
        except Exception as e:
            logger.error(f"重启失败（{executable}, {e}），请尝试手动重启。")
            raise e

    async def check_update(
        self,
        url: str | None,
        current_version: str | None,
        consider_prerelease: bool = True,
    ) -> ReleaseInfo | None:
        """检查更新"""
        return await super().check_update(
            self.ASTRBOT_RELEASE_API,
            VERSION,
            consider_prerelease,
        )

    async def get_releases(self) -> list:
        return await self.fetch_release_info(self.ASTRBOT_RELEASE_API)

    @staticmethod
    def _is_expected_nightly_fetch_error(exc: BaseException) -> bool:
        expected_types = (
            TimeoutError,
            aiohttp.ClientError,
            JSONDecodeError,
            FetchReleaseError,
        )
        if isinstance(exc, expected_types):
            return True

        cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
        return isinstance(cause, expected_types)

    async def get_nightly_release(self) -> dict | None:
        nightly_release_url = f"{self.GITHUB_RELEASE_API}/tags/{self.NIGHTLY_TAG}"
        try:
            nightly_releases = await self.fetch_release_info(nightly_release_url)
        except Exception as e:
            if self._is_expected_nightly_fetch_error(e):
                logger.warning(
                    "获取 nightly 发布信息失败，跳过 nightly。"
                    f"url={nightly_release_url}, error_type={type(e).__name__}, detail={e}",
                )
                return None
            logger.exception(
                "获取 nightly 发布信息出现非预期异常。"
                f"url={nightly_release_url}, error_type={type(e).__name__}",
            )
            raise

        if not nightly_releases:
            return None
        return nightly_releases[0]

    async def get_releases_with_nightly(self) -> list:
        releases = await self.get_releases()
        nightly_release = await self.get_nightly_release()
        if nightly_release and all(
            item.get("tag_name") != self.NIGHTLY_TAG for item in releases
        ):
            releases.insert(0, nightly_release)
        return releases

    async def _resolve_latest_target(self) -> tuple[str, str]:
        releases = await self.get_releases()
        latest_release = next(
            (
                item
                for item in releases
                if (tag := item.get("tag_name", ""))
                and tag.lower() != self.NIGHTLY_TAG
                and not PRERELEASE_TAG_REGEX.search(tag)
            ),
            None,
        )
        if latest_release is None:
            raise Exception("未找到可用的发布版本。")

        latest_version = latest_release["tag_name"]
        if self.compare_version(VERSION, latest_version) >= 0:
            raise Exception("当前已经是最新版本。")
        return latest_version, latest_release["zipball_url"]

    def _resolve_nightly_target(self) -> tuple[str, str]:
        return self.NIGHTLY_TAG, (
            f"https://github.com/AstrBotDevs/AstrBot/archive/refs/tags/{self.NIGHTLY_TAG}.zip"
        )

    async def _resolve_tag_target(self, version_str: str) -> tuple[str, str]:
        releases = await self.get_releases()
        for data in releases:
            if data["tag_name"] == version_str:
                return version_str, data["zipball_url"]
        raise Exception(f"未找到版本号为 {version_str} 的更新文件。")

    def _resolve_commit_target(self, version_str: str) -> tuple[str, str]:
        if len(version_str) != 40:
            raise Exception("commit hash 长度不正确，应为 40")
        return (
            version_str,
            f"https://github.com/AstrBotDevs/AstrBot/archive/{version_str}.zip",
        )

    async def _resolve_update_target(
        self,
        latest: bool,
        version: str | None,
    ) -> tuple[str, str]:
        version_str = str(version) if version is not None else ""

        if latest:
            return await self._resolve_latest_target()

        if version_str.lower() == self.NIGHTLY_TAG:
            return self._resolve_nightly_target()

        if version_str.startswith("v"):
            return await self._resolve_tag_target(version_str)

        return self._resolve_commit_target(version_str)

    async def update(self, reboot=False, latest=True, version=None, proxy="") -> None:
        if os.environ.get("ASTRBOT_CLI") or os.environ.get("ASTRBOT_LAUNCHER"):
            raise Exception(
                "Error: You are running AstrBot via CLI, please use `pip` or `uv tool upgrade` to update AstrBot."
            )  # 避免版本管理混乱

        target_version, file_url = await self._resolve_update_target(latest, version)

        logger.info(f"准备更新至 AstrBot Core: {target_version}")

        if proxy:
            proxy = proxy.removesuffix("/")
            file_url = f"{proxy}/{file_url}"

        try:
            await download_file(file_url, "temp.zip")
            logger.info("下载 AstrBot Core 更新文件完成，正在执行解压...")
            self.unzip_file("temp.zip", self.MAIN_PATH)
        except BaseException as e:
            raise e

        if reboot:
            self._reboot()
