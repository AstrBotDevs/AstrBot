import inspect
import os
import sys
import traceback
import uuid
import shutil
import yaml
import logging

from util.updator.plugin_updator import PluginUpdator
from util.io import remove_dir, download_file
from types import ModuleType
from type.types import Context
from type.plugin import *
from type.register import *
from util.log import LogManager
from logging import Logger
from pip import main as pip_main

logger: Logger = LogManager.GetLogger(log_name='astrbot')

class PluginManager():
    def __init__(self, context: Context):
        self.updator = PluginUpdator()
        self.plugin_store_path = self.updator.get_plugin_store_path()
        self.context = context

    def get_classes(self, arg: ModuleType):
        classes = []
        clsmembers = inspect.getmembers(arg, inspect.isclass)
        for (name, _) in clsmembers:
            if name.lower().endswith("plugin") or name.lower() == "main":
                classes.append(name)
                break
        return classes

    def get_modules(self, path):
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
    
    def get_plugin_modules(self):
        plugins = []
        try:
            plugin_dir = self.plugin_store_path
            if os.path.exists(plugin_dir):
                plugins = self.get_modules(plugin_dir)
                return plugins
        except BaseException as e:
            raise e
        
    def check_plugin_dept_update(self, target_plugin: str = None):
        plugin_dir = self.plugin_store_path
        if not os.path.exists(plugin_dir):
            return False
        to_update = []
        if target_plugin:
            to_update.append(target_plugin)
        else:
            for p in self.context.cached_plugins:
                to_update.append(p.root_dir_name)
        for p in to_update:
            plugin_path = os.path.join(plugin_dir, p)
            if os.path.exists(os.path.join(plugin_path, "requirements.txt")):
                pth = os.path.join(plugin_path, "requirements.txt")
                logger.info(f"正在检查更新插件 {p} 的依赖: {pth}")
                self.update_plugin_dept(os.path.join(plugin_path, "requirements.txt"))

    def update_plugin_dept(self, path):
        pip_main(['install', '-r', path, '--trusted-host', 'mirrors.aliyun.com', '-i', 'https://mirrors.aliyun.com/pypi/simple/'])
        # mirror = "https://mirrors.aliyun.com/pypi/simple/"
        # py = sys.executable
        # cmd = f"{py} -m pip install -r {path} -i {mirror} --trusted-host mirrors.aliyun.com"
        # if break_system_package:
        #     cmd += " --break-system-package"
        # process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True)
        
        # while True:
        #     output = process.stdout.readline()
        #     err = process.stderr.readline()
        #     if err:
        #         err = err.strip()
        #         logger.error(err)
        #         if "no such option: --break-system-package" in err:
        #             self.update_plugin_dept(path, break_system_package=False)
        #             break
        #     if output == '' and process.poll() is not None:
        #         break
        #     if output:
        #         output = output.strip()
        #         if output.startswith("Requirement already satisfied"):
        #             continue
        #         if output.startswith("Using cached"):
        #             continue
        #         if output.startswith("Looking in indexes"):
        #             continue
        #         logger.info(output)
            
        # rc = process.poll()
        
        
    async def install_plugin(self, repo_url: str):
        ppath = self.plugin_store_path

        # we no longer use Git anymore :)
        # Repo.clone_from(repo_url, to_path=plugin_path, branch='master')
        
        plugin_path = await self.updator.update(repo_url)
        with open(os.path.join(plugin_path, "REPO"), "w", encoding='utf-8') as f:
            f.write(repo_url)
            
        # self.check_plugin_dept_update()

        return plugin_path
        # ok, err = self.plugin_reload()
        # if not ok:
        #     raise Exception(err)
        
    async def download_from_repo_url(self, target_path: str, repo_url: str):
        repo_namespace = repo_url.split("/")[-2:]
        author = repo_namespace[0]
        repo = repo_namespace[1]

        logger.info(f"正在下载插件 {repo} ...")
        release_url = f"https://api.github.com/repos/{author}/{repo}/releases"
        releases = await self.updator.fetch_release_info(url=release_url)
        if not releases:
            # download from the default branch directly. 
            logger.warn(f"未在插件 {author}/{repo} 中找到任何发布版本，将从默认分支下载。")
            release_url = f"https://github.com/{author}/{repo}/archive/refs/heads/master.zip"
        else:
            release_url = releases[0]['zipball_url']

        await download_file(release_url, target_path + ".zip")

    def get_registered_plugin(self, plugin_name: str) -> RegisteredPlugin:
        for p in self.context.cached_plugins:
            if p.metadata.plugin_name == plugin_name:
                return p
    
    def uninstall_plugin(self, plugin_name: str):
        plugin = self.get_registered_plugin(plugin_name)
        if not plugin:
            raise Exception("插件不存在。")
        root_dir_name = plugin.root_dir_name
        ppath = self.plugin_store_path
        self.context.cached_plugins.remove(plugin)
        if not remove_dir(os.path.join(ppath, root_dir_name)):
            raise Exception("移除插件成功，但是删除插件文件夹失败。您可以手动删除该文件夹，位于 addons/plugins/ 下。")

    async def update_plugin(self, plugin_name: str):
        plugin = self.get_registered_plugin(plugin_name)
        if not plugin:
            raise Exception("插件不存在。")
        
        await self.updator.update(plugin)
        
    def plugin_reload(self):
        cached_plugins = self.context.cached_plugins
        plugins = self.get_plugin_modules()
        if plugins is None:
            return False, "未找到任何插件模块"
        fail_rec = ""

        registered_map = {}
        for p in cached_plugins:
            registered_map[p.module_path] = None

        for plugin in plugins:
            try:
                p = plugin['module']
                module_path = plugin['module_path']
                root_dir_name = plugin['pname']
                
                logger.info(f"正在加载插件 {root_dir_name} ...")

                # self.check_plugin_dept_update(target_plugin=root_dir_name)
                
                try:
                    module = __import__("data.plugins." +
                                        root_dir_name + "." + p, fromlist=[p])
                except (ModuleNotFoundError, ImportError) as e:
                    # 尝试安装插件依赖
                    logger.error(f"尝试安装插件依赖。")
                    self.check_plugin_dept_update(target_plugin=root_dir_name)
                    module = __import__("data.plugins." +
                                        root_dir_name + "." + p, fromlist=[p])

                cls = self.get_classes(module)
                
                try:
                    # 尝试传入 ctx
                    obj = getattr(module, cls[0])(context=self.context)
                except TypeError:
                    obj = getattr(module, cls[0])()
                except BaseException as e:
                    raise e

                metadata = None

                plugin_path = os.path.join(self.plugin_store_path, root_dir_name)
                metadata = self.load_plugin_metadata(plugin_path=plugin_path, plugin_obj=obj)
                
                logger.info(f"插件 {metadata.plugin_name}({metadata.author}) 加载成功。")

                if module_path not in registered_map:
                    cached_plugins.append(RegisteredPlugin(
                        metadata=metadata,
                        plugin_instance=obj,
                        module=module,
                        module_path=module_path,
                        root_dir_name=root_dir_name
                    ))
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
        
    def install_plugin_from_file(self, zip_file_path: str):
        # try to unzip
        temp_dir = os.path.join(os.path.dirname(zip_file_path), str(uuid.uuid4()))
        self.updator.unzip_file(zip_file_path, temp_dir)
        # check if the plugin has metadata.yaml
        if not os.path.exists(os.path.join(temp_dir, "metadata.yaml")):
            remove_dir(temp_dir)
            raise Exception("插件缺少 metadata.yaml 文件。")
        
        metadata = self.load_plugin_metadata(temp_dir)
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
        
        # self.check_plugin_dept_update()

        # ok, err = self.plugin_reload()
        # if not ok:
        #     raise Exception(err)

    def load_plugin_metadata(self, plugin_path: str, plugin_obj = None) -> PluginMetadata:
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
                plugin_type=PluginType.COMMON if 'plugin_type' not in metadata else PluginType(metadata['plugin_type']),
                author=metadata['author'],
                desc=metadata['desc'],
                version=metadata['version'],
                repo=metadata['repo'] if 'repo' in metadata else None
            )
            
        return metadata