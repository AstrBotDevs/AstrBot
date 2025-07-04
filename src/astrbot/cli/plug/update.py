import click

@click.command()
@click.argument("name", required=False)
@click.option("--proxy", help="Github代理地址")
def update(name: str, proxy: str | None):
    """更新插件"""
    from ..utils import get_astrbot_root, build_plug_list, manage_plugin, PluginStatus
    base_path = get_astrbot_root()
    plug_path = base_path / "data" / "plugins"
    plugins = build_plug_list(base_path / "data" / "plugins")

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
            raise click.ClickException(click.style(f"插件 {name} 不需要更新或无法更新", fg="red"))

        manage_plugin(plugin, plug_path, is_update=True, proxy=proxy)
    else:
        need_update_plugins = [
            p for p in plugins if p["status"] == PluginStatus.NEED_UPDATE
        ]

        if not need_update_plugins:
            click.echo(click.style("没有需要更新的插件", fg="green"))
            return

        click.echo(click.style(f"发现 {len(need_update_plugins)} 个插件需要更新", fg="cyan", bold=True))
        for plugin in need_update_plugins:
            plugin_name = plugin["name"]
            click.echo(click.style(f"正在更新插件 {plugin_name}...", fg="yellow"))
            manage_plugin(plugin, plug_path, is_update=True, proxy=proxy)
