'''
插件工具函数
'''
import os
import inspect
try:
    import git.exc
    from git.repo import Repo
except ImportError:
    pass
import shutil
from pip._internal import main as pipmain
import importlib
import stat


# 找出模块里所有的类名
def get_classes(p_name, arg):
    classes = []
    clsmembers = inspect.getmembers(arg, inspect.isclass)
    for (name, _) in clsmembers:
        # print(name, p_name)
        if p_name.lower() == name.lower()[:-6] or name.lower() == "main":
            classes.append(name)
            break
    return classes

# 获取一个文件夹下所有的模块, 文件名和文件夹名相同
def get_modules(path):
    modules = []
    for root, dirs, files in os.walk(path):
        # 获得所在目录名
        p_name = os.path.basename(root)
        for file in files:
            """
            与文件夹名（不计大小写）相同或者是main.py的，都算启动模块
            """
            if file.endswith(".py") and not file.startswith("__") and (p_name.lower() == file[:-3].lower() or file[:-3].lower() == "main"):
                modules.append({
                    "pname": p_name,
                    "module": file[:-3],
                })
    return modules

def get_plugin_store_path():
    if os.path.exists("addons/plugins"):
        return "addons/plugins"
    elif os.path.exists("QQChannelChatGPT/addons/plugins"):
        return "QQChannelChatGPT/addons/plugins"
    elif os.path.exists("AstrBot/addons/plugins"):
        return "AstrBot/addons/plugins"
    else:
        raise FileNotFoundError("插件文件夹不存在。")

def plugin_reload(self, cached_plugins: dict, target: str = None, all: bool = False):
    plugins = self.get_plugin_modules()
    if plugins is None:
        return False, "未找到任何插件模块"
    fail_rec = ""
    for plugin in plugins:
        try:
            p = plugin['module']
            root_dir_name = plugin['pname']
            if p not in cached_plugins or p == target or all:
                module = __import__("addons.plugins." + root_dir_name + "." + p, fromlist=[p])
                if p in cached_plugins:
                    module = importlib.reload(module)
                cls = get_classes(p, module)
                obj = getattr(module, cls[0])()
                try:
                    info = obj.info()
                    if 'name' not in info or 'desc' not in info or 'version' not in info or 'author' not in info:
                        fail_rec += f"载入插件{p}失败，原因: 插件信息不完整\n"
                        continue
                    if isinstance(info, dict) == False:
                        fail_rec += f"载入插件{p}失败，原因: 插件信息格式不正确\n"
                        continue
                except BaseException as e:
                    fail_rec += f"调用插件{p} info失败, 原因: {str(e)}\n"
                    continue
                cached_plugins[info['name']] = {
                    "module": module,
                    "clsobj": obj,
                    "info": info,
                    "name": info['name'],
                    "root_dir_name": root_dir_name,
                }
        except BaseException as e:
            fail_rec += f"加载{p}插件出现问题，原因 {str(e)}\n"
    if fail_rec == "":
        return True, None
    else:
        return False, fail_rec

def install_plugin(repo_url: str, cached_plugins: dict):
    ppath = get_plugin_store_path()
    # 删除末尾的 /
    if repo_url.endswith("/"):
        repo_url = repo_url[:-1]
    # 得到 url 的最后一段
    d = repo_url.split("/")[-1]
    # 转换非法字符：-
    d = d.replace("-", "_")
    # 创建文件夹
    plugin_path = os.path.join(ppath, d)
    if os.path.exists(plugin_path):
        shutil.rmtree(plugin_path)
    Repo.clone_from(repo_url, to_path=plugin_path, branch='master')
    # 读取插件的requirements.txt
    if os.path.exists(os.path.join(plugin_path, "requirements.txt")):
        if pipmain(['install', '-r', os.path.join(plugin_path, "requirements.txt")]) != 0:
            raise Exception("插件的依赖安装失败, 需要您手动 pip 安装对应插件的依赖。")
    ok, err = plugin_reload(cached_plugins, target=d)
    if not ok: raise Exception(err)

def uninstall_plugin(plugin_name: str, cached_plugins: dict):
    if plugin_name not in cached_plugins:
        raise Exception("插件不存在。")
    root_dir_name = cached_plugins[plugin_name]["root_dir_name"]
    ppath = get_plugin_store_path()
    del cached_plugins[plugin_name]
    if not remove_dir(os.path.join(ppath, root_dir_name)):
        raise Exception("移除插件成功，但是删除插件文件夹失败。您可以手动删除该文件夹，位于 addons/plugins/ 下。")

def update_plugin(plugin_name: str, cached_plugins: dict):
    if plugin_name not in cached_plugins:
        raise Exception("插件不存在。")
    ppath = get_plugin_store_path()
    root_dir_name = cached_plugins[plugin_name]["root_dir_name"]
    plugin_path = os.path.join(ppath, root_dir_name)
    repo = Repo(path = plugin_path)
    repo.remotes.origin.pull()
    # 读取插件的requirements.txt
    if os.path.exists(os.path.join(plugin_path, "requirements.txt")):
        if pipmain(['install', '-r', os.path.join(plugin_path, "requirements.txt")]) != 0:
            raise Exception("插件依赖安装失败, 需要您手动pip安装对应插件的依赖。")
    ok, err = plugin_reload(cached_plugins, target=plugin_name)
    if not ok: raise Exception(err)

def remove_dir(self, file_path) -> bool:
    try_cnt = 50
    while try_cnt > 0:
        if not os.path.exists(file_path):
            return False
        try:
            shutil.rmtree(file_path)
            return True
        except PermissionError as e:
            err_file_path = str(e).split("\'", 2)[1]
            if os.path.exists(err_file_path):
                os.chmod(err_file_path, stat.S_IWUSR)
            try_cnt -= 1