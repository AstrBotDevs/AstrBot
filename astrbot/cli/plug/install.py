import click

@click.command()
@click.argument("name")
@click.option("--proxy", help="代理服务器地址")
def install(name: str, proxy: str | None):
    """安装插件"""
    from ..utils import get_astrbot_root, build_plug_list, manage_plugin , PluginStatus
    base_path = get_astrbot_root()
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
        raise click.ClickException(click.style(f"未找到可安装的插件 {name}，可能是不存在或已安装", fg="red"))

    manage_plugin(plugin, plug_path, is_update=False, proxy=proxy)
