import click

@click.command()
@click.argument("query")
def search(query: str):
    """搜索插件"""
    from ..utils import get_astrbot_root, build_plug_list, display_plugins

    base_path = get_astrbot_root()
    plugins = build_plug_list(base_path / "plugins")

    matched_plugins = [
        p
        for p in plugins
        if query.lower() in p["name"].lower()
        or query.lower() in p["desc"].lower()
        or query.lower() in p["author"].lower()
    ]

    if not matched_plugins:
        click.echo(click.style(f"未找到匹配 '{query}' 的插件", fg="yellow"))
        return

    display_plugins(matched_plugins, f"搜索结果: '{query}'", "cyan")
