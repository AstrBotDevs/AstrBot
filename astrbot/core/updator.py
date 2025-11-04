import os
import sys
import time

import psutil

from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.utils.astrbot_path import get_astrbot_path
from astrbot.core.utils.io import download_file

from .zip_updator import ReleaseInfo, RepoZipUpdator


class AstrBotUpdator(RepoZipUpdator):
    """AstrBot 更新器，继承自 RepoZipUpdator 类
    该类用于处理 AstrBot 的更新操作
    功能包括检查更新、下载更新文件、解压缩更新文件等
    """

    def __init__(self, repo_mirror: str = "") -> None:
        super().__init__(repo_mirror)
        self.MAIN_PATH = get_astrbot_path()  # 覆盖源代码
        self.ASTRBOT_RELEASE_API = "https://api.soulter.top/releases"

    def terminate_child_processes(self):
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

    def _reboot(self, delay: int = 3):
        """重启当前程序
        在指定的延迟后，终止所有子进程并重新启动程序
        这里只能使用 os.exec* 来重启程序
        """
        time.sleep(delay)
        self.terminate_child_processes()
        if os.name == "nt":
            py = f'"{sys.executable}"'
        else:
            py = sys.executable

        try:
            if "astrbot" in os.path.basename(sys.argv[0]):  # 兼容cli
                if os.name == "nt":
                    args = [f'"{arg}"' if " " in arg else arg for arg in sys.argv[1:]]
                else:
                    args = sys.argv[1:]
                os.execl(sys.executable, py, "-m", "astrbot.cli.__main__", *args)
            else:
                os.execl(sys.executable, py, *sys.argv)
        except Exception as e:
            logger.error(f"重启失败（{py}, {e}），请尝试手动重启。")
            raise e

    async def check_update(
        self,
        url: str,
        current_version: str,
        consider_prerelease: bool = True,
    ) -> ReleaseInfo:
        """检查更新"""
        return await super().check_update(
            self.ASTRBOT_RELEASE_API,
            VERSION,
            consider_prerelease,
        )

    async def get_releases(self) -> list:
        return await self.fetch_release_info(self.ASTRBOT_RELEASE_API)

    def _generate_update_instruction(
        self, latest: bool = True, version: str | None = None
    ) -> str:
        """私有辅助函数

        Args:
            latest: 是否更新到最新版本
            version: 目标版本号，如果 latest=True 则忽略

        Returns:
            str: 更新指令字符串
        """
        if latest:
            pip_cmd = "pip install git+https://github.com/AstrBotDevs/AstrBot.git"
            uv_cmd = "uv tool upgrade astrbot"
        else:
            if version:
                pip_cmd = f"pip install git+https://github.com/AstrBotDevs/AstrBot.git@{version}"
                uv_cmd = f"uv tool install --force git+https://github.com/AstrBotDevs/AstrBot.git@{version} astrbot"
            else:
                raise ValueError("当 latest=False 时，必须提供 version")

        return (
            "命令行启动时,请直接使用uv tool upgrade astrbot更新\n"
            f"或者使用此命令更新: {pip_cmd}"
            f"使用uv: {uv_cmd}"
        )

    async def update(self, reboot=False, latest=True, version=None, proxy=""):
        update_data = await self.fetch_release_info(self.ASTRBOT_RELEASE_API, latest)
        file_url = None
        if os.environ.get("ASTRBOT_CLI"):
            raise Exception(
                self._generate_update_instruction(latest, version)
            )  # 提示用户正确的更新方法

        if latest:
            latest_version = update_data[0]["tag_name"]
            if self.compare_version(VERSION, latest_version) >= 0:
                raise Exception("当前已经是最新版本。")
            file_url = update_data[0]["zipball_url"]
        elif str(version).startswith("v"):
            # 更新到指定版本
            for data in update_data:
                if data["tag_name"] == version:
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

        try:
            await download_file(file_url, "temp.zip")
            logger.info("下载 AstrBot Core 更新文件完成，正在执行解压...")
            self.unzip_file("temp.zip", self.MAIN_PATH)
        except BaseException as e:
            raise e

        if reboot:
            self._reboot()
