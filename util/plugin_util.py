'''
插件工具函数
'''
import os, sys, zipfile, shutil
import inspect
import traceback

from types import ModuleType
from type.plugin import *
from type.register import *
from SparkleLogging.utils.core import LogManager
from logging import Logger
from type.types import GlobalObject
from util.general_utils import download_file, remove_dir
from util.updator import request_release_info

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
    plugin_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../addons/plugins"))
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
    if repo_url.endswith("/"):
        repo_url = repo_url[:-1]

    repo_namespace = repo_url.split("/")[-2:]
    repo = repo_namespace[1]

    plugin_path = os.path.join(ppath, repo.replace("-", "_").lower())
    if os.path.exists(plugin_path): remove_dir(plugin_path)

    # we no longer use Git anymore :)
    # Repo.clone_from(repo_url, to_path=plugin_path, branch='master')

    download_from_repo_url(plugin_path, repo_url)
    unzip_file(plugin_path + ".zip", plugin_path)

    with open(os.path.join(plugin_path, "REPO"), "w") as f:
        f.write(repo_url)

    ok, err = plugin_reload(ctx)
    if not ok:
        raise Exception(err)
    
def download_from_repo_url(target_path: str, repo_url: str):
    repo_namespace = repo_url.split("/")[-2:]
    author = repo_namespace[0]
    repo = repo_namespace[1]

    logger.info(f"正在下载插件 {repo} ...")
    release_url = f"https://api.github.com/repos/{author}/{repo}/releases"
    releases = request_release_info(latest=True, url=release_url, mirror_url=release_url)
    if not releases:
        # download from the default branch directly. 
        logger.warn(f"未在插件 {author}/{repo} 中找到任何发布版本，将从默认分支下载。")
        release_url = f"https://github.com/{author}/{repo}/archive/refs/heads/master.zip"
    else:
        release_url = releases[0]['zipball_url']

    download_file(release_url, target_path + ".zip")


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

    if not os.path.exists(os.path.join(plugin_path, "REPO")):
        raise Exception("插件更新信息文件 `REPO` 不存在，请手动升级，或者先卸载然后重新安装该插件。")
    
    repo_url = None
    with open(os.path.join(plugin_path, "REPO"), "r") as f:
        repo_url = f.read()

    download_from_repo_url(plugin_path, repo_url)
    try:
        remove_dir(plugin_path)
    except BaseException as e:
        logger.error(f"删除旧版本插件 {plugin_name} 文件夹失败: {str(e)}，使用覆盖安装。")
    unzip_file(plugin_path + ".zip", plugin_path)

    ok, err = plugin_reload(ctx)
    if not ok:
        raise Exception(err)

def unzip_file(zip_path: str, target_dir: str):
    '''
    解压缩文件, 并将压缩包内**第一个**文件夹内的文件移动到 target_dir
    '''
    os.makedirs(target_dir, exist_ok=True)
    update_dir = ""
    logger.info(f"解压文件: {zip_path}")
    with zipfile.ZipFile(zip_path, 'r') as z:
        update_dir = z.namelist()[0]
        z.extractall(target_dir)

    files = os.listdir(os.path.join(target_dir, update_dir))
    for f in files:
        logger.info(f"移动更新文件/目录: {f}")
        if os.path.isdir(os.path.join(target_dir, update_dir, f)):
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
        logger.warn(f"删除更新文件失败，可以手动删除 {zip_path} 和 {os.path.join(target_dir, update_dir)}")


def on_error(func, path, exc_info):
    '''
    a callback of the rmtree function.
    '''
    print(f"remove {path} failed.")
    import stat
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise