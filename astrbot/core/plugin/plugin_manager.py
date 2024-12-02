import inspect
import os
import sys
import traceback
import uuid
import shutil
import yaml
import logging
from asyncio import Queue
from types import ModuleType
from typing import List, Awaitable
from pip import main as pip_main
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core import logger
from .context import Context
from . import RegisteredPlugin, PluginMetadata
from .updator import PluginUpdator
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.io import remove_dir

class PluginManager:
    def __init__(self, config: AstrBotConfig, event_queue: Queue, db: BaseDatabase):
        self.updator = PluginUpdator(config.plugin_repo_mirror)
        self.context = Context(event_queue, config, db)
        self.config = config
        self.plugin_store_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../data/plugins"))
        self.reserved_plugin_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../packages"))
        
    def _get_classes(self, arg: ModuleType):
        classes = []
        clsmembers = inspect.getmembers(arg, inspect.isclass)
        for (name, _) in clsmembers:
            if name.lower().endswith("plugin") or name.lower() == "main":
                classes.append(name)
                break
        return classes

    def _get_modules(self, path):
        modules = []

        dirs = os.listdir(path)
        # 遍历文件夹，找到 main.py 或者和文件夹同名的文件
        for d in dirs:
            if os.path.isdir(os.path.join(path, d)):
                if os.path.exists(os.path.join(path, d, "main.py")):
                    module_str = 'main'
                elif os.path.exists(os.path.join(path, d, d + ".py")):
                    module_str = d
                else:
                    print(f"插件 {d} 未找到 main.py 或者 {d}.py，跳过。")
                    continue
                if os.path.exists(os.path.join(path, d, "main.py")) or os.path.exists(os.path.join(path, d, d + ".py")):
                    modules.append({
                        "pname": d,
                        "module": module_str,
                        "module_path": os.path.join(path, d, module_str)
                    })
        return modules
    
    def _get_plugin_modules(self) -> List[dict]:
        plugins = []
        if os.path.exists(self.plugin_store_path):
            plugins.extend(self._get_modules(self.plugin_store_path))
        if os.path.exists(self.reserved_plugin_path):
            _p = self._get_modules(self.reserved_plugin_path)
            for p in _p:
                p['reserved'] = True
            plugins.extend(_p)
        return plugins
        
    def _check_plugin_dept_update(self, target_plugin: str = None):
        plugin_dir = self.plugin_store_path
        if not os.path.exists(plugin_dir):
            return False
        to_update = []
        if target_plugin:
            to_update.append(target_plugin)
        else:
            for p in self.context.registered_plugins:
                to_update.append(p.root_dir_name)
        for p in to_update:
            plugin_path = os.path.join(plugin_dir, p)
            if os.path.exists(os.path.join(plugin_path, "requirements.txt")):
                pth = os.path.join(plugin_path, "requirements.txt")
                logger.info(f"正在检查插件 {p} 的依赖: {pth}")
                try:
                    self._update_plugin_dept(os.path.join(plugin_path, "requirements.txt"))
                except Exception as e:
                    logger.error(f"更新插件 {p} 的依赖失败。Code: {str(e)}")

    def _update_plugin_dept(self, path):
        args = ['install', '-r', path, '--trusted-host', 'mirrors.aliyun.com', '-i', 'https://mirrors.aliyun.com/pypi/simple/']
        if self.config.pip_install_arg:
            args.extend(self.config.pip_install_arg)
        result_code = pip_main(args)
        if result_code != 0:
            raise Exception(str(result_code))  

    def _load_plugin_metadata(self, plugin_path: str, plugin_obj = None) -> PluginMetadata:
        metadata = None
        
        if not os.path.exists(plugin_path):
            raise Exception("插件不存在。")
        
        if os.path.exists(os.path.join(plugin_path, "metadata.yaml")):
            with open(os.path.join(plugin_path, "metadata.yaml"), "r", encoding='utf-8') as f:
                metadata = yaml.safe_load(f)
        elif plugin_obj:
            # 使用 info() 函数
            metadata = plugin_obj.info()
        
        if isinstance(metadata, dict):
            if 'name' not in metadata or 'desc' not in metadata or 'version' not in metadata or 'author' not in metadata:
                raise Exception("插件元数据信息不完整。")
            metadata = PluginMetadata(
                plugin_name=metadata['name'],
                author=metadata['author'],
                desc=metadata['desc'],
                version=metadata['version'],
                repo=metadata['repo'] if 'repo' in metadata else None
            )
            
        return metadata
    
    def reload(self):
        '''
        加载插件类
        '''
        registered_plugins = self.context.registered_plugins
        plugins = self._get_plugin_modules()
        if plugins is None:
            return False, "未找到任何插件模块"
        fail_rec = ""

        registered_map = {}
        for p in registered_plugins:
            registered_map[p.module_path] = None

        for plugin in plugins:
            try:
                p = plugin['module']
                module_path = plugin['module_path']
                root_dir_name = plugin['pname']
                reserved = plugin.get('reserved', False)
                
                logger.info(f"正在加载插件 {root_dir_name} ...")
                
                pre = "data.plugins." if not reserved else "packages."
                
                # 尝试导入插件模块
                try:
                    module = __import__(pre + root_dir_name + "." + p, fromlist=[p])
                except (ModuleNotFoundError, ImportError) as e:
                    # 尝试安装插件依赖
                    self._check_plugin_dept_update(target_plugin=root_dir_name)
                    module = __import__(pre + root_dir_name + "." + p, fromlist=[p])

                cls = self._get_classes(module)
                
                # 实例化插件类
                try:
                    obj = getattr(module, cls[0])(context=self.context)
                except BaseException as e:
                    logger.error(f"插件 {root_dir_name} 实例化失败。")
                    raise e
                
                # 解析插件元数据，加入注册列表
                metadata = None
                plugin_path = os.path.join(self.plugin_store_path, root_dir_name) if not reserved else os.path.join(self.reserved_plugin_path, root_dir_name)
                metadata = self._load_plugin_metadata(plugin_path=plugin_path, plugin_obj=obj)
                if module_path not in registered_map:
                    registered_plugins.append(RegisteredPlugin(
                        metadata=metadata,
                        plugin_instance=obj,
                        module=module,
                        module_path=module_path,
                        root_dir_name=root_dir_name,
                        reserved=reserved
                    ))
                    
                for command in self.context.commands_handler:
                    if self.context.commands_handler[command].plugin_name == metadata.plugin_name:
                        self.context.commands_handler[command].plugin_metadata = metadata
                for listener in self.context.listeners_handler:
                    if self.context.listeners_handler[listener].plugin_name == metadata.plugin_name:
                        self.context.listeners_handler[listener].plugin_metadata = metadata
                
                
            except BaseException as e:
                traceback.print_exc()
                fail_rec += f"加载{p}插件出现问题，原因 {str(e)}\n"

        # 清除 pip.main 导致的多余的 logging handlers
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        
        if not fail_rec:
            return True, None
        else:
            return False, fail_rec
        
    async def install_plugin(self, repo_url: str):
        plugin_path = await self.updator.update(repo_url)
        with open(os.path.join(plugin_path, "REPO"), "w", encoding='utf-8') as f:
            f.write(repo_url)
        self._check_plugin_dept_update()
        return plugin_path
    
    def uninstall_plugin(self, plugin_name: str):
        plugin = self.context.get_registered_plugin(plugin_name)
        if not plugin:
            raise Exception("插件不存在。")
        if plugin.reserved:
            raise Exception("该插件是 AstrBot 保留插件，无法卸载。")
        root_dir_name = plugin.root_dir_name
        ppath = self.plugin_store_path
        self.context.registered_plugins.remove(plugin)
        if not remove_dir(os.path.join(ppath, root_dir_name)):
            raise Exception("移除插件成功，但是删除插件文件夹失败。您可以手动删除该文件夹，位于 addons/plugins/ 下。")

    async def update_plugin(self, plugin_name: str):
        plugin = self.context.get_registered_plugin(plugin_name)
        if not plugin:
            raise Exception("插件不存在。")
        if plugin.reserved:
            raise Exception("该插件是 AstrBot 保留插件，无法更新。")
        
        await self.updator.update(plugin)
        
    def install_plugin_from_file(self, zip_file_path: str):
        # try to unzip
        temp_dir = os.path.join(os.path.dirname(zip_file_path), str(uuid.uuid4()))
        self.updator.unzip_file(zip_file_path, temp_dir)
        # check if the plugin has metadata.yaml
        if not os.path.exists(os.path.join(temp_dir, "metadata.yaml")):
            remove_dir(temp_dir)
            raise Exception("插件缺少 metadata.yaml 文件。")
        
        metadata = self._load_plugin_metadata(temp_dir)
        plugin_name = metadata.plugin_name
        if not plugin_name: 
            remove_dir(temp_dir)
            raise Exception("插件 metadata.yaml 文件中 name 字段为空。")
        plugin_name = self.updator.format_name(plugin_name)

        ppath = self.plugin_store_path
        plugin_path = os.path.join(ppath, plugin_name)
        if os.path.exists(plugin_path): 
            remove_dir(plugin_path)

        # move to the target path
        shutil.move(temp_dir, plugin_path)
        
        if metadata.repo:
            with open(os.path.join(plugin_path, "REPO"), "w", encoding='utf-8') as f:
                f.write(metadata.repo)

        # remove the temp dir
        remove_dir(temp_dir)
        
        self._check_plugin_dept_update()
        
    def get_platform_insts(self):
        return self.context.registered_platforms
    
    def get_loaded_plugins(self):
        return self.context.registered_plugins
    