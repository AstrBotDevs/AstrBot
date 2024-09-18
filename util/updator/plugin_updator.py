import os, zipfile, shutil

from util.updator.zip_updator import RepoZipUpdator
from util.io import remove_dir
from type.register import RegisteredPlugin
from typing import Union
from SparkleLogging.utils.core import LogManager
from logging import Logger
from util.io import on_error

logger: Logger = LogManager.GetLogger(log_name='astrbot')


class PluginUpdator(RepoZipUpdator):
    def __init__(self) -> None:
        self.plugin_store_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../data/plugins"))
        
    def get_plugin_store_path(self) -> str:
        return self.plugin_store_path

    def update(self, plugin: Union[RegisteredPlugin, str]) -> str:
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
        self.download_from_repo_url(plugin_path, repo_url)
        
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
        # copy addons/plugins to the target_dir temporarily
        # if os.path.exists(os.path.join(target_dir, "addons/plugins")):
        #     logger.info("备份插件目录：从 addons/plugins 到 temp_plugins")
        #     shutil.copytree(os.path.join(target_dir, "addons/plugins"), "temp_plugins")

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
        
        # move back
        # if os.path.exists("temp_plugins"):
        #     logger.info("恢复插件目录：从 temp_plugins 到 addons/plugins")
        #     shutil.rmtree(os.path.join(target_dir, "addons/plugins"), onerror=on_error)
        #     shutil.move("temp_plugins", os.path.join(target_dir, "addons/plugins"))
        
        try:
            logger.info(f"删除临时更新文件: {zip_path} 和 {os.path.join(target_dir, update_dir)}")
            shutil.rmtree(os.path.join(target_dir, update_dir), onerror=on_error)
            os.remove(zip_path)
        except:
            logger.warn(f"删除更新文件失败，可以手动删除 {zip_path} 和 {os.path.join(target_dir, update_dir)}")
