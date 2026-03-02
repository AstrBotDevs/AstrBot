from astrbot.core.lang import t
import re
import shutil
from pathlib import Path

import click

from ..utils import (
    PluginStatus,
    build_plug_list,
    check_astrbot_root,
    get_astrbot_root,
    get_git_repo,
    manage_plugin,
)


@click.group()
def plug() -> None:
    """插件管理"""


def _get_data_path() -> Path:
    base = get_astrbot_root()
    if not check_astrbot_root(base):
        raise click.ClickException(
            t("msg-cbd8802b", base=base),
        )
    return (base / "data").resolve()


def display_plugins(plugins, title=None, color=None) -> None:
    if title:
        click.echo(t("msg-78b9c276", res=click.style(title, fg=color, bold=True)))

    click.echo(t("msg-83664fcf", val='名称'))
    click.echo("-" * 85)

    for p in plugins:
        desc = p["desc"][:30] + ("..." if len(p["desc"]) > 30 else "")
        click.echo(
            t("msg-56f3f0bf", res=p['name'], res_2=p['version'], res_3=p['status'], res_4=p['author'], desc=desc),
        )


@plug.command()
@click.argument("name")
def new(name: str) -> None:
    """创建新插件"""
    base_path = _get_data_path()
    plug_path = base_path / "plugins" / name

    if plug_path.exists():
        raise click.ClickException(t("msg-1d802ff2", name=name))

    author = click.prompt("请输入插件作者", type=str)
    desc = click.prompt("请输入插件描述", type=str)
    version = click.prompt("请输入插件版本", type=str)
    if not re.match(r"^\d+\.\d+(\.\d+)?$", version.lower().lstrip("v")):
        raise click.ClickException(t("msg-a7be9d23"))
    repo = click.prompt("请输入插件仓库：", type=str)
    if not repo.startswith("http"):
        raise click.ClickException(t("msg-4d81299b"))

    click.echo(t("msg-93289755"))
    get_git_repo(
        "https://github.com/Soulter/helloworld",
        plug_path,
    )

    click.echo(t("msg-b21682dd"))
    # 重写 metadata.yaml
    with open(plug_path / "metadata.yaml", "w", encoding="utf-8") as f:
        f.write(
            f"name: {name}\n"
            f"desc: {desc}\n"
            f"version: {version}\n"
            f"author: {author}\n"
            f"repo: {repo}\n",
        )

    # 重写 README.md
    with open(plug_path / "README.md", "w", encoding="utf-8") as f:
        f.write(f"# {name}\n\n{desc}\n\n# 支持\n\n[帮助文档](https://astrbot.app)\n")

    # 重写 main.py
    with open(plug_path / "main.py", encoding="utf-8") as f:
        content = f.read()

    new_content = content.replace(
        '@register("helloworld", "YourName", "一个简单的 Hello World 插件", "1.0.0")',
        f'@register("{name}", "{author}", "{desc}", "{version}")',
    )

    with open(plug_path / "main.py", "w", encoding="utf-8") as f:
        f.write(new_content)

    click.echo(t("msg-bffc8bfa", name=name))


@plug.command()
@click.option("--all", "-a", is_flag=True, help="列出未安装的插件")
def list(all: bool) -> None:
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
        click.echo(t("msg-08eae1e3"))


@plug.command()
@click.argument("name")
@click.option("--proxy", help="代理服务器地址")
def install(name: str, proxy: str | None) -> None:
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
        raise click.ClickException(t("msg-1a021bf4", name=name))

    manage_plugin(plugin, plug_path, is_update=False, proxy=proxy)


@plug.command()
@click.argument("name")
def remove(name: str) -> None:
    """卸载插件"""
    base_path = _get_data_path()
    plugins = build_plug_list(base_path / "plugins")
    plugin = next((p for p in plugins if p["name"] == name), None)

    if not plugin or not plugin.get("local_path"):
        raise click.ClickException(t("msg-c120bafd", name=name))

    plugin_path = plugin["local_path"]

    click.confirm(f"确定要卸载插件 {name} 吗?", default=False, abort=True)

    try:
        shutil.rmtree(plugin_path)
        click.echo(t("msg-63da4867", name=name))
    except Exception as e:
        raise click.ClickException(t("msg-e4925708", name=name, e=e))


@plug.command()
@click.argument("name", required=False)
@click.option("--proxy", help="Github代理地址")
def update(name: str, proxy: str | None) -> None:
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
            raise click.ClickException(t("msg-f4d15a87", name=name))

        manage_plugin(plugin, plug_path, is_update=True, proxy=proxy)
    else:
        need_update_plugins = [
            p for p in plugins if p["status"] == PluginStatus.NEED_UPDATE
        ]

        if not need_update_plugins:
            click.echo(t("msg-94b035f7"))
            return

        click.echo(t("msg-0766d599", res=len(need_update_plugins)))
        for plugin in need_update_plugins:
            plugin_name = plugin["name"]
            click.echo(t("msg-bd5ab99c", plugin_name=plugin_name))
            manage_plugin(plugin, plug_path, is_update=True, proxy=proxy)


@plug.command()
@click.argument("query")
def search(query: str) -> None:
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
        click.echo(t("msg-e32912b8", query=query))
        return

    display_plugins(matched_plugins, f"搜索结果: '{query}'", "cyan")
