'''
插件工具函数
'''
import os, sys
import inspect
import shutil
import stat
import traceback

try:
    from git.repo import Repo
except ImportError:
    pass
from types import ModuleType
from type.plugin import *
from type.register import *
from SparkleLogging.utils.core import LogManager
from logging import Logger
from type.types import GlobalObject

logger: Logger = LogManager.GetLogger(log_name='astrbot-core')



# 找出模块里所有的类名
def get_classes(p_name, arg: ModuleType):
    classes = []
    clsmembers = inspect.getmembers(arg, inspect.isclass)
    for (name, _) in clsmembers:
        if name.lower().endswith("plugin") or name.lower() == "main":
            classes.append(name)
            break
        # if p_name.lower() == name.lower()[:-6] or name.lower() == "main":
    return classes

# 获取一个文件夹下所有的模块, 文件名和文件夹名相同


def get_modules(path):
    modules = []

    # 得到其下的所有文件夹
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


def get_plugin_store_path():
    plugin_dir = os.path.abspath(os.path.join(os.path.abspath(__file__), "../../addons/plugins"))
    return plugin_dir

def get_plugin_modules():
    plugins = []
    try:
        plugin_dir = get_plugin_store_path()
        if os.path.exists(plugin_dir):
            plugins = get_modules(plugin_dir)
            return plugins
    except BaseException as e:
        raise e
    
def check_plugin_dept_update(cached_plugins: RegisteredPlugins, target_plugin: str = None):
    plugin_dir = get_plugin_store_path()
    if not os.path.exists(plugin_dir):
        return False
    to_update = []
    if target_plugin:
        to_update.append(target_plugin)
    else:
        for p in cached_plugins:
            to_update.append(p.root_dir_name)
    for p in to_update:
        plugin_path = os.path.join(plugin_dir, p)
        if os.path.exists(os.path.join(plugin_path, "requirements.txt")):
            pth = os.path.join(plugin_path, "requirements.txt")
            logger.info(f"正在检查更新插件 {p} 的依赖: {pth}")
            update_plugin_dept(os.path.join(plugin_path, "requirements.txt"))


def has_init_param(cls, param_name):
    try:
        # 获取 __init__ 方法的签名
        init_signature = inspect.signature(cls.__init__)
        
        # 检查参数名是否在签名中
        return param_name in init_signature.parameters
    except (AttributeError, ValueError):
        # 如果类没有 __init__ 方法或者无法获取签名
        return False

def plugin_reload(ctx: GlobalObject):
    cached_plugins = ctx.cached_plugins
    plugins = get_plugin_modules()
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

            check_plugin_dept_update(cached_plugins, root_dir_name)

            module = __import__("addons.plugins." +
                                    root_dir_name + "." + p, fromlist=[p])

            cls = get_classes(p, module)
            
            try:
                # 尝试传入 ctx
                obj = getattr(module, cls[0])(ctx=ctx)
            except:
                obj = getattr(module, cls[0])()

            metadata = None
            try:
                info = obj.info()
                if isinstance(info, dict):
                    if 'name' not in info or 'desc' not in info or 'version' not in info or 'author' not in info:
                        fail_rec += f"注册插件 {module_path} 失败，原因: 插件信息不完整\n"
                        continue
                    else:
                        metadata = PluginMetadata(
                            plugin_name=info['name'],
                            plugin_type=PluginType.COMMON if 'plugin_type' not in info else PluginType(info['plugin_type']),
                            author=info['author'],
                            desc=info['desc'],
                            version=info['version'],
                            repo=info['repo'] if 'repo' in info else None
                        )
                elif isinstance(info, PluginMetadata):
                    metadata = info
                else:
                    fail_rec += f"注册插件 {module_path} 失败，原因: info 函数返回值类型错误\n"
                    continue
            except BaseException as e:
                fail_rec += f"注册插件 {module_path} 失败, 原因: {str(e)}\n"
                continue

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
    if fail_rec == "":
        return True, None
    else:
        return False, fail_rec
    
def update_plugin_dept(path):
    mirror = "https://mirrors.aliyun.com/pypi/simple/"
    py = sys.executable
    os.system(f"{py} -m pip install -r {path} -i {mirror} --quiet")


def install_plugin(repo_url: str, ctx: GlobalObject):
    ppath = get_plugin_store_path()
    # 删除末尾的 /
    if repo_url.endswith("/"):
        repo_url = repo_url[:-1]
    # 得到 url 的最后一段
    d = repo_url.split("/")[-1]
    # 转换非法字符：-
    d = d.replace("-", "_")
    d = d.lower() # 转换为小写
    # 创建文件夹
    plugin_path = os.path.join(ppath, d)
    if os.path.exists(plugin_path):
        remove_dir(plugin_path)
    Repo.clone_from(repo_url, to_path=plugin_path, branch='master')
    ok, err = plugin_reload(ctx)
    if not ok:
        raise Exception(err)


def get_registered_plugin(plugin_name: str, cached_plugins: RegisteredPlugins) -> RegisteredPlugin:
    ret = None
    for p in cached_plugins:
        if p.metadata.plugin_name == plugin_name:
            ret = p
            break
    return ret


def uninstall_plugin(plugin_name: str, ctx: GlobalObject):
    plugin = get_registered_plugin(plugin_name, ctx.cached_plugins)
    if not plugin:
        raise Exception("插件不存在。")
    root_dir_name = plugin.root_dir_name
    ppath = get_plugin_store_path()
    ctx.cached_plugins.remove(plugin)
    if not remove_dir(os.path.join(ppath, root_dir_name)):
        raise Exception("移除插件成功，但是删除插件文件夹失败。您可以手动删除该文件夹，位于 addons/plugins/ 下。")


def update_plugin(plugin_name: str, ctx: GlobalObject):
    plugin = get_registered_plugin(plugin_name, ctx.cached_plugins)
    if not plugin:
        raise Exception("插件不存在。")
    ppath = get_plugin_store_path()
    root_dir_name = plugin.root_dir_name
    plugin_path = os.path.join(ppath, root_dir_name)
    repo = Repo(path=plugin_path)
    repo.remotes.origin.pull()
    ok, err = plugin_reload(ctx)
    if not ok:
        raise Exception(err)


def remove_dir(file_path) -> bool:
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
