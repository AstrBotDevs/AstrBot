"""
astrbot plugin tools
简称apt
        ————2025年5月5日anka道

我真是闲的才把这句加进来。
        ————2025年5月5日Raven注
"""

import datetime
import json
import re
from pathlib import Path

import click
import shutil
from ..utils import (
    get_git_repo,
    build_plug_list,
    manage_plugin,
    PluginStatus,
    check_astrbot_root,
)
from astrbot.core.utils.path_util import get_astrbot_root


@click.group()
def plug():
    """插件管理"""
    pass


def _get_cache_path(base_path: Path) -> Path:
    """获取缓存文件路径"""
    return base_path / "plugins_cache.json"


def _get_lock_path(base_path: Path) -> Path:
    """获取锁文件路径"""
    return base_path / "plugins_cache.lock"


def _acquire_lock(lock_path: Path) -> None:
    """尝试获取锁文件"""
    try:
        lock_path.touch(exist_ok=False)
    except FileExistsError:
        raise click.ClickException(
            f"无法获取锁文件 {lock_path}，如果确定没有其他实例正在运行，请删除该文件"
        )


def _release_lock(lock_path: Path) -> None:
    """释放锁文件"""
    try:
        lock_path.unlink(missing_ok=True)
    except FileNotFoundError:
        pass
    except Exception as e:
        click.echo(f"警告：无法删除锁文件 {lock_path}: {e!s}，请手动删除", err=True)


def _get_cached_plugins(base_path: Path, rebuild: bool = False) -> list:  # type: ignore
    """获取缓存的插件列表，需要时重新构建"""
    cache_path = _get_cache_path(base_path)
    lock_path = _get_lock_path(base_path)

    def _build_and_save_cache() -> list:
        """构建并保存插件缓存"""
        plugins = build_plug_list(base_path / "plugins")
        cache_data_a = {
            "timestamp": datetime.datetime.now().timestamp(),
            "plugins": plugins,
        }
        with cache_path.open("w", encoding="utf-8") as fa:
            json.dump(cache_data_a, fa, ensure_ascii=False, indent=2)
        return plugins

    _acquire_lock(lock_path)
    try:
        if rebuild or not cache_path.exists():
            return _build_and_save_cache()

        try:
            with cache_path.open("r", encoding="utf-8") as f:
                cache_data = json.load(f)
                formatted_time = datetime.datetime.fromtimestamp(
                    cache_data["timestamp"]
                ).strftime("%Y-%m-%d")
                click.echo(f"正在使用缓存的插件列表，构建日期: {formatted_time}")
                return cache_data["plugins"]
        except Exception as e:
            click.echo(f"读取缓存时出错: {e!s}。正在重新构建缓存...", err=True)
            return _build_and_save_cache()
    finally:
        _release_lock(lock_path)


def display_plugins(plugins, title=None, color=None):
    if title:
        click.echo(click.style(title, fg=color, bold=True))

    click.echo(f"{'名称':<20} {'版本':<10} {'状态':<10} {'作者':<15} {'描述':<30}")
    click.echo("-" * 85)

    for p in plugins:
        desc = p["desc"][:30] + ("..." if len(p["desc"]) > 30 else "")
        click.echo(
            f"{p['name']:<20} {p['version']:<10} {p['status']:<10} "
            f"{p['author']:<15} {desc:<30}"
        )


@plug.command()
@click.argument("name")
@click.option("--path", "-p", help="AstrBot 数据目录")
def new(name: str, path: str | None):
    """创建新插件"""
    if path:
        base_path = Path(path)
    else:
        base_path = get_astrbot_root()

    if not check_astrbot_root(base_path):
        raise click.ClickException(
            f"{base_path}不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init"
        )

    plug_path = base_path / "plugins" / name

    if plug_path.exists():
        raise click.ClickException(f"插件 {name} 已存在")

    author = click.prompt("请输入插件作者", type=str)
    desc = click.prompt("请输入插件描述", type=str)
    version = click.prompt("请输入插件版本", type=str)
    if not re.match(r"^\d+\.\d+(\.\d+)?$", version.lower().lstrip("v")):
        raise click.ClickException("版本号必须为 x.y 或 x.y.z 格式")
    repo = click.prompt("请输入插件仓库：", type=str)
    if not repo.startswith("http"):
        raise click.ClickException("仓库地址必须以 http 开头")

    click.echo("下载插件模板...")
    get_git_repo(
        "https://github.com/Soulter/helloworld",
        plug_path,
    )

    click.echo("重写插件信息...")
    # 重写 metadata.yaml
    with open(plug_path / "metadata.yaml", "w", encoding="utf-8") as f:
        f.write(
            f"name: {name}\n"
            f"desc: {desc}\n"
            f"version: {version}\n"
            f"author: {author}\n"
            f"repo: {repo}\n"
        )

    # 重写 README.md
    with open(plug_path / "README.md", "w", encoding="utf-8") as f:
        f.write(f"# {name}\n\n{desc}\n\n# 支持\n\n[帮助文档](https://astrbot.app)\n")

    # 重写 main.py
    with open(plug_path / "main.py", "r", encoding="utf-8") as f:
        content = f.read()

    new_content = content.replace(
        '@register("helloworld", "YourName", "一个简单的 Hello World 插件", "1.0.0")',
        f'@register("{name}", "{author}", "{desc}", "{version}")',
    )

    with open(plug_path / "main.py", "w", encoding="utf-8") as f:
        f.write(new_content)

    # 刷新缓存
    click.echo("刷新本地插件缓存...")
    _get_cached_plugins(base_path, rebuild=True)

    click.echo(f"插件 {name} 创建成功")


@plug.command()
@click.option("--all", "-a", is_flag=True, help="列出未安装的插件")
@click.option("--path", "-p", help="AstrBot 数据目录")
def list(online: bool, path: str | None):
    """列出插件"""
    if path:
        base_path = Path(path)
    else:
        base_path = get_astrbot_root()

    if not check_astrbot_root(base_path):
        raise click.ClickException(
            f"{base_path}不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init"
        )

    plugins = _get_cached_plugins(base_path)

    # 未发布的插件
    not_published_plugins = [
        p for p in plugins if p["status"] == PluginStatus.NOT_PUBLISHED
    ]
    if not_published_plugins:
        display_plugins(not_published_plugins, "未发布的插件", "red")

    # 需要更新的插件
    need_update_plugins = [
        p for p in plugins if p["status"] == PluginStatus.NEED_UPDATE
    ]
    if need_update_plugins:
        display_plugins(need_update_plugins, "需要更新的插件", "yellow")

    # 已安装的插件
    installed_plugins = [p for p in plugins if p["status"] == PluginStatus.INSTALLED]
    if installed_plugins:
        display_plugins(installed_plugins, "已安装的插件", "green")

    # 未安装的插件
    not_installed_plugins = [
        p for p in plugins if p["status"] == PluginStatus.NOT_INSTALLED
    ]
    if not_installed_plugins and online:
        display_plugins(not_installed_plugins, "未安装的插件", "blue")


@plug.command()
@click.argument("name")
@click.option("--proxy", help="代理服务器地址")
@click.option("--path", "-p", help="AstrBot 数据目录")
def install(name: str, proxy: str | None, path: str | None):
    """安装插件"""
    if path:
        base_path = Path(path)
    else:
        base_path = get_astrbot_root()

    if not check_astrbot_root(base_path):
        raise click.ClickException(
            f"{base_path}不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init"
        )

    plug_path = base_path / "plugins"

    plugins = _get_cached_plugins(base_path, rebuild=True)
    plugin = next(
        (
            p
            for p in plugins
            if p["name"] == name and p["status"] == PluginStatus.NOT_INSTALLED
        ),
        None,
    )

    if not plugin:
        raise click.ClickException(f"未找到可安装的插件 {name}")

    manage_plugin(plugin, plug_path, is_update=False, proxy=proxy)


@plug.command()
@click.argument("name")
@click.option("--path", "-p", help="AstrBot 数据目录")
def remove(name: str, path: str | None):
    """卸载插件"""
    if path:
        base_path = Path(path)
    else:
        base_path = get_astrbot_root()

    if not check_astrbot_root(base_path):
        raise click.ClickException(
            f"{base_path}不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init"
        )

    plugins = _get_cached_plugins(base_path)
    plugin = next((p for p in plugins if p["name"] == name), None)

    if not plugin or not plugin.get("local_path"):
        raise click.ClickException(f"插件 {name} 不存在")

    plugin_path = plugin["local_path"]

    click.confirm(f"确定要卸载插件 {name} 吗?", default=False, abort=True)

    try:
        shutil.rmtree(plugin_path)
        click.echo(f"插件 {name} 已卸载")
    except Exception as e:
        raise click.ClickException(f"卸载插件 {name} 失败: {e}")


@plug.command()
@click.option("--path", "-p", help="AstrBot 数据目录")
def update(path: str | None):
    """刷新插件列表缓存"""
    if path:
        base_path = Path(path)
    else:
        base_path = get_astrbot_root()

    if not check_astrbot_root(base_path):
        raise click.ClickException(
            f"{base_path} 不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init"
        )

    click.echo("正在更新插件缓存...")
    _get_cached_plugins(base_path, rebuild=True)
    click.echo("插件缓存更新完成")


@plug.command()
@click.argument("name", required=False)
@click.option("--proxy", help="代理服务器地址")
@click.option("--path", "-p", help="AstrBot 数据目录")
def upgrade(name: str, proxy: str | None, path: str | None):
    """更新插件"""
    if path:
        base_path = Path(path)
    else:
        base_path = get_astrbot_root()

    if not check_astrbot_root(base_path):
        raise click.ClickException(
            f"{base_path}不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init"
        )

    plug_path = base_path / "plugins"

    plugins = _get_cached_plugins(base_path)

    if name:
        plugin = next(
            (
                p
                for p in plugins
                if p["name"] == name and p["status"] == PluginStatus.NEED_UPDATE
            ),
            None,
        )

        if not plugin:
            raise click.ClickException(f"插件 {name} 不需要更新或无法更新")

        manage_plugin(plugin, plug_path, is_update=True, proxy=proxy)
    else:
        need_update_plugins = [
            p for p in plugins if p["status"] == PluginStatus.NEED_UPDATE
        ]

        if not need_update_plugins:
            click.echo("没有需要更新的插件")
            return

        click.echo(f"发现 {len(need_update_plugins)} 个插件需要更新")
        for plugin in need_update_plugins:
            plugin_name = plugin["name"]
            click.echo(f"正在更新插件 {plugin_name}...")
            manage_plugin(plugin, plug_path, is_update=True, proxy=proxy)


@plug.command()
@click.argument("query")
@click.option("--path", "-p", help="AstrBot 数据目录")
def search(query: str, path: str | None):
    """搜索插件"""
    if path:
        base_path = Path(path)
    else:
        base_path = get_astrbot_root()

    if not check_astrbot_root(base_path):
        raise click.ClickException(
            f"{base_path}不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init"
        )

    plugins = _get_cached_plugins(base_path)

    matched_plugins = [
        p
        for p in plugins
        if query.lower() in p["name"].lower()
        or query.lower() in p["desc"].lower()
        or query.lower() in p["author"].lower()
    ]

    if not matched_plugins:
        click.echo(f"未找到匹配 '{query}' 的插件")
        return

    display_plugins(matched_plugins, f"搜索结果: '{query}'", "cyan")
