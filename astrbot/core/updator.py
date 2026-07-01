import os
import sys
import time
import zipfile
from pathlib import Path

import psutil

from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.desktop_runtime import (
    DESKTOP_MANAGED_RESTART_MESSAGE,
    is_desktop_managed_backend,
)
from astrbot.core.utils.astrbot_path import get_astrbot_path
from astrbot.core.utils.io import ensure_dir

from .zip_updator import ReleaseInfo, RepoZipUpdator


class AstrBotUpdator(RepoZipUpdator):
    """AstrBot 更新器，继承自 RepoZipUpdator 类
    该类用于处理 AstrBot 的更新操作
    功能包括检查更新、下载更新文件、解压缩更新文件等
    """

    def __init__(self, repo_mirror: str = "", verify: str | bool | None = None) -> None:
        super().__init__(repo_mirror, verify=verify)
        self.MAIN_PATH = get_astrbot_path()
        self.ASTRBOT_RELEASE_API = "https://api.soulter.top/releases"
        self.CORE_PACKAGE_BASE_URL = (
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
            self.CORE_PACKAGE_BASE_URL,
        ).strip()
        if not base_url:
            return None
        return f"{base_url.rstrip('/')}/{version}/source.zip"

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
        if is_desktop_managed_backend():
            logger.error(DESKTOP_MANAGED_RESTART_MESSAGE)
            raise RuntimeError(DESKTOP_MANAGED_RESTART_MESSAGE)

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

    async def update(
        self,
        reboot=False,
        latest=True,
        version=None,
        proxy="",
        progress_callback=None,
    ) -> None:
        zip_path = await self.download_update_package(
            latest=latest,
            version=version,
            proxy=proxy,
            progress_callback=progress_callback,
        )
        self.apply_update_package(zip_path)

        if reboot:
            self._reboot()

    async def download_update_package(
        self,
        latest=True,
        version=None,
        proxy="",
        path: str | Path = "temp.zip",
        progress_callback=None,
    ) -> Path:
        """Download an AstrBot core update package without applying it.

        Args:
            latest: Whether to download the latest release.
            version: Specific release tag or commit hash to download.
            proxy: Optional GitHub proxy prefix.
            path: Destination zip path.
            progress_callback: Optional callback for download progress payloads.

        Returns:
            Path to the downloaded update package.

        Raises:
            Exception: If update metadata cannot resolve a package URL.
        """

        update_data = await self.fetch_release_info(self.ASTRBOT_RELEASE_API, latest)
        file_url = None

        if os.environ.get("ASTRBOT_CLI") or os.environ.get("ASTRBOT_LAUNCHER"):
            raise Exception(
                "Error: You are running AstrBot via CLI, please use `pip` or `uv tool upgrade` to update AstrBot."
            )  # 避免版本管理混乱

        target_version = None
        if latest:
            latest_version = update_data[0]["tag_name"]
            if self.compare_version(VERSION, latest_version) >= 0:
                raise Exception("当前已经是最新版本。")
            target_version = latest_version
            file_url = update_data[0]["zipball_url"]
        elif str(version).startswith("v"):
            # 更新到指定版本
            for data in update_data:
                if data["tag_name"] == version:
                    target_version = data["tag_name"]
                    file_url = data["zipball_url"]
            if not file_url:
                raise Exception(f"未找到版本号为 {version} 的更新文件。")
        else:
            if len(str(version)) != 40:
                raise Exception("commit hash 长度不正确，应为 40")
            file_url = f"https://github.com/AstrBotDevs/AstrBot/archive/{version}.zip"
        logger.info(f"准备更新至指定版本的 AstrBot Core: {version}")

        if proxy:
            proxy = proxy.removesuffix("/")
            file_url = f"{proxy}/{file_url}"

        zip_path = Path(path)
        ensure_dir(zip_path.parent)
        hosted_package_url = self._build_core_package_url(target_version)
        if hosted_package_url:
            try:
                logger.info(
                    f"优先从托管存储下载 AstrBot Core 更新包: {hosted_package_url}"
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
                    f"从托管存储下载 AstrBot Core 更新包失败: {exc}，"
                    "将回退到当前更新源。"
                )

        await self._download_file(
            file_url,
            str(zip_path),
            progress_callback=progress_callback,
        )
        return zip_path

    def apply_update_package(self, zip_path: str | Path) -> None:
        """Apply a previously downloaded AstrBot core update package.

        Args:
            zip_path: Core update zip archive path.

        Returns:
            None.

        Raises:
            Exception: If the archive cannot be extracted or applied.
        """

        logger.info("下载 AstrBot Core 更新文件完成，正在执行解压...")
        self.unzip_file(str(zip_path), self.MAIN_PATH)
