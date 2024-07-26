import os

from util.updator.zip_updator import RepoZipUpdator
from util.io import remove_dir
from type.plugin import PluginMetadata
from type.register import RegisteredPlugin
from typing import Union
from SparkleLogging.utils.core import LogManager
from logging import Logger

logger: Logger = LogManager.GetLogger(log_name='astrbot')


class PluginUpdator(RepoZipUpdator):
    def __init__(self) -> None:
        self.plugin_store_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../addons/plugins"))
        
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


        