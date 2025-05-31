import click

@click.command()
@click.option("--all", "-a", is_flag=True, help="列出未安装的插件")
def list(all: bool):
    """列出插件"""
    from ..utils import (
        get_astrbot_root,
        build_plug_list,
        display_plugins,
        PluginStatus
    )
    base_path = get_astrbot_root()
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
        click.echo(click.style("未安装任何插件", fg="yellow"))