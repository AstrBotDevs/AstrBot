import os
import psutil
import sys
import time
from .zip_updator import ReleaseInfo, RepoZipUpdator
from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.utils.io import download_file


class AstrBotUpdator(RepoZipUpdator):
    def __init__(self, repo_mirror: str = "") -> None:
        super().__init__(repo_mirror)
        self.MAIN_PATH = os.path.abspath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../")
        )
        self.ASTRBOT_RELEASE_API = "https://api.soulter.top/releases"

    def terminate_child_processes(self):
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
        py = sys.executable
        time.sleep(delay)
        self.terminate_child_processes()
        py = py.replace(" ", "\\ ")
        try:
            os.execl(py, py, *sys.argv)
        except Exception as e:
            logger.error(f"重启失败（{py}, {e}），请尝试手动重启。")
            raise e

    async def check_update(self, url: str, current_version: str) -> ReleaseInfo:
        return await super().check_update(self.ASTRBOT_RELEASE_API, VERSION)

    async def get_releases(self) -> list:
        return await self.fetch_release_info(self.ASTRBOT_RELEASE_API)

    async def update(self, reboot=False, latest=True, version=None, proxy=""):
        update_data = await self.fetch_release_info(self.ASTRBOT_RELEASE_API, latest)
        file_url = None

        if latest:
            latest_version = update_data[0]["tag_name"]
            if self.compare_version(VERSION, latest_version) >= 0:
                raise Exception("当前已经是最新版本。")
            file_url = update_data[0]["zipball_url"]
        elif str(version).startswith("v"):
            # 更新到指定版本
            logger.info(f"正在更新到指定版本: {version}")
            for data in update_data:
                if data["tag_name"] == version:
                    file_url = data["zipball_url"]
            if not file_url:
                raise Exception(f"未找到版本号为 {version} 的更新文件。")
        else:
            if len(str(version)) != 40:
                raise Exception("commit hash 长度不正确，应为 40")
            logger.info(f"正在尝试更新到指定 commit: {version}")
            file_url = "https://github.com/Soulter/AstrBot/archive/" + version + ".zip"

        if proxy:
            proxy = proxy.removesuffix("/")
            file_url = f"{proxy}/{file_url}"

        try:
            await download_file(file_url, "temp.zip")
            self.unzip_file("temp.zip", self.MAIN_PATH)
        except BaseException as e:
            raise e

        if reboot:
            self._reboot()
