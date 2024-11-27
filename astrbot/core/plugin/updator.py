import os, zipfile, shutil

from ..updator import RepoZipUpdator
from core.utils.io import remove_dir, on_error
from ..plugin import RegisteredPlugin
from typing import Union
from core import logger

class PluginUpdator(RepoZipUpdator):
    def __init__(self, repo_mirror: str = "") -> None:
        super().__init__(repo_mirror)
        self.plugin_store_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../data/plugins"))
        
    def get_plugin_store_path(self) -> str:
        return self.plugin_store_path

    async def update(self, plugin: Union[RegisteredPlugin, str]) -> str:
        repo_url = None
        
        if not isinstance(plugin, str):
            plugin_path = os.path.join(self.plugin_store_path, plugin.root_dir_name)
            if not os.path.exists(os.path.join(plugin_path, "REPO")):
                raise Exception("插件更新信息文件 `REPO` 不存在，请手动升级，或者先卸载然后重新安装该插件。")
            
            with open(os.path.join(plugin_path, "REPO"), "r", encoding='utf-8') as f:
                repo_url = f.read()
        else:
            repo_url = plugin
            plugin_path = os.path.join(self.plugin_store_path, self.format_repo_name(repo_url))
            
        logger.info(f"正在更新插件，路径: {plugin_path}，仓库地址: {repo_url}")
        await self.download_from_repo_url(plugin_path, repo_url)
        
        try:
            remove_dir(plugin_path)
        except BaseException as e:
            logger.error(f"删除旧版本插件 {plugin.metadata.plugin_name} 文件夹失败: {str(e)}，使用覆盖安装。")
        
        self.unzip_file(plugin_path + ".zip", plugin_path)
        
        return plugin_path

    def unzip_file(self, zip_path: str, target_dir: str):
        os.makedirs(target_dir, exist_ok=True)
        update_dir = ""
        logger.info(f"解压文件: {zip_path}")
        with zipfile.ZipFile(zip_path, 'r') as z:
            update_dir = z.namelist()[0]
            z.extractall(target_dir)

        avoid_dirs = ["logs", "data", "configs", "temp_plugins", update_dir]

        files = os.listdir(os.path.join(target_dir, update_dir))
        for f in files:
            logger.info(f"移动更新文件/目录: {f}")
            if os.path.isdir(os.path.join(target_dir, update_dir, f)):
                if f in avoid_dirs: continue
                if os.path.exists(os.path.join(target_dir, f)):
                    shutil.rmtree(os.path.join(target_dir, f), onerror=on_error)
            else:
                if os.path.exists(os.path.join(target_dir, f)):
                    os.remove(os.path.join(target_dir, f))
            shutil.move(os.path.join(target_dir, update_dir, f), target_dir)
        
        try:
            logger.info(f"删除临时更新文件: {zip_path} 和 {os.path.join(target_dir, update_dir)}")
            shutil.rmtree(os.path.join(target_dir, update_dir), onerror=on_error)
            os.remove(zip_path)
        except:
            logger.warning(f"删除更新文件失败，可以手动删除 {zip_path} 和 {os.path.join(target_dir, update_dir)}")
