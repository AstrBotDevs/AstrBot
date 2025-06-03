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
    get_astrbot_root,
)


@click.group()
def plug():
    """插件管理"""
    pass


def _get_data_path() -> Path:
    base = get_astrbot_root()
    if not check_astrbot_root(base):
        raise click.ClickException(
            f"{base}不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init"
        )
    return (base / "data").resolve()


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
def new(name: str):
    """创建新插件"""
    base_path = _get_data_path()
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

    click.echo(f"插件 {name} 创建成功")


@plug.command()
@click.option("--all", "-a", is_flag=True, help="列出未安装的插件")
def list(all: bool):
    """列出插件"""
    base_path = _get_data_path()
    plugins = build_plug_list(base_path / "plugins")

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
    if not_installed_plugins and all:
        display_plugins(not_installed_plugins, "未安装的插件", "blue")

    if (
        not any([not_published_plugins, need_update_plugins, installed_plugins])
        and not all
    ):
        click.echo("未安装任何插件")


@plug.command()
@click.argument("name")
@click.option("--proxy", help="代理服务器地址")
def install(name: str, proxy: str | None):
    """安装插件"""
    base_path = _get_data_path()
    plug_path = base_path / "plugins"
    plugins = build_plug_list(base_path / "plugins")

    plugin = next(
        (
            p
            for p in plugins
            if p["name"] == name and p["status"] == PluginStatus.NOT_INSTALLED
        ),
        None,
    )

    if not plugin:
        raise click.ClickException(f"未找到可安装的插件 {name}，可能是不存在或已安装")

    manage_plugin(plugin, plug_path, is_update=False, proxy=proxy)


@plug.command()
@click.argument("name")
def remove(name: str):
    """卸载插件"""
    base_path = _get_data_path()
    plugins = build_plug_list(base_path / "plugins")
    plugin = next((p for p in plugins if p["name"] == name), None)

    if not plugin or not plugin.get("local_path"):
        raise click.ClickException(f"插件 {name} 不存在或未安装")

    plugin_path = plugin["local_path"]

    click.confirm(f"确定要卸载插件 {name} 吗?", default=False, abort=True)

    try:
        shutil.rmtree(plugin_path)
        click.echo(f"插件 {name} 已卸载")
    except Exception as e:
        raise click.ClickException(f"卸载插件 {name} 失败: {e}")


@plug.command()
@click.argument("name", required=False)
@click.option("--proxy", help="Github代理地址")
def update(name: str, proxy: str | None):
    """更新插件"""
    base_path = _get_data_path()
    plug_path = base_path / "plugins"
    plugins = build_plug_list(base_path / "plugins")

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
def search(query: str):
    """搜索插件"""
    base_path = _get_data_path()
    plugins = build_plug_list(base_path / "plugins")

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
