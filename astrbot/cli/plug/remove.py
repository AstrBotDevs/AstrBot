import click

@click.command()
@click.argument("name")
def remove(name: str):
    """卸载插件"""
    import shutil
    from ..utils import get_astrbot_root, build_plug_list
    base_path = get_astrbot_root()
    plugins = build_plug_list(base_path / "data" / "plugins")
    plugin = next((p for p in plugins if p["name"] == name), None)

    if not plugin or not plugin.get("local_path"):
        raise click.ClickException(click.style(f"插件 {name} 不存在或未安装", fg="red"))

    plugin_path = plugin["local_path"]

    click.confirm(f"确定要卸载插件 {name} 吗?", default=False, abort=True)

    try:
        shutil.rmtree(plugin_path)
        click.echo(click.style(f"✓ 插件 {name} 已成功卸载", fg="green", bold=True))
    except Exception as e:
        raise click.ClickException(click.style(f"卸载插件 {name} 失败: {e}", fg="red"))
