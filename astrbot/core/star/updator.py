import os
import shutil
import zipfile

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_path
from astrbot.core.utils.io import on_error, remove_dir

from ..star.star import StarMetadata
from ..updator import RepoZipUpdator


class PluginUpdator(RepoZipUpdator):
    def __init__(self, repo_mirror: str = "", verify: str | bool | None = None) -> None:
        super().__init__(repo_mirror, verify=verify)
        self.plugin_store_path = get_astrbot_plugin_path()

    def get_plugin_store_path(self) -> str:
        return self.plugin_store_path

    async def install(self, repo_url: str, proxy="", download_url: str = "") -> str:
        _, repo_name, _ = self.parse_github_url(repo_url)
        repo_name = self.format_name(repo_name)
        plugin_path = os.path.join(self.plugin_store_path, repo_name)
        if download_url:
            logger.info(f"Downloading plugin archive for {repo_name}: {download_url}")
            await self._download_file(download_url, plugin_path + ".zip")
        else:
            await self.download_from_repo_url(plugin_path, repo_url, proxy)
        self.unzip_file(plugin_path + ".zip", plugin_path)

        return plugin_path

    async def update(self, plugin: StarMetadata, proxy="") -> str:
        repo_url = plugin.repo

        if not repo_url:
            raise Exception(f"Plugin {plugin.name} does not specify a repository URL.")

        if not plugin.root_dir_name:
            raise Exception(
                f"Plugin {plugin.name} does not specify a root directory name."
            )

        plugin_path = os.path.join(self.plugin_store_path, plugin.root_dir_name)

        logger.info(
            f"Updating plugin at path: {plugin_path}, repository URL: {repo_url}",
        )
        await self.download_from_repo_url(plugin_path, repo_url, proxy=proxy)

        try:
            remove_dir(plugin_path)
        except BaseException as e:
            logger.error(
                f"Failed to remove old plugin directory {plugin_path}: {e!s}; using overwrite installation.",
            )

        self.unzip_file(plugin_path + ".zip", plugin_path)

        return plugin_path

    def unzip_file(self, zip_path: str, target_dir: str) -> None:
        os.makedirs(target_dir, exist_ok=True)
        update_dir = ""
        logger.info(f"Extracting archive: {zip_path}")
        with zipfile.ZipFile(zip_path, "r") as z:
            update_dir = z.namelist()[0]
            z.extractall(target_dir)

        files = os.listdir(os.path.join(target_dir, update_dir))
        for f in files:
            if os.path.isdir(os.path.join(target_dir, update_dir, f)):
                if os.path.exists(os.path.join(target_dir, f)):
                    shutil.rmtree(os.path.join(target_dir, f), onerror=on_error)
            elif os.path.exists(os.path.join(target_dir, f)):
                os.remove(os.path.join(target_dir, f))
            shutil.move(os.path.join(target_dir, update_dir, f), target_dir)

        try:
            logger.info(
                f"Removing temporary files: {zip_path} and {os.path.join(target_dir, update_dir)}",
            )
            shutil.rmtree(os.path.join(target_dir, update_dir), onerror=on_error)
            os.remove(zip_path)
        except BaseException:
            logger.warning(
                f"Failed to remove update files; you can manually delete {zip_path} and {os.path.join(target_dir, update_dir)}",
            )
