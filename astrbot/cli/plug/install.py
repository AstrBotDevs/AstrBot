import click

@click.command()
@click.argument("name")
@click.option("--proxy", help="代理服务器地址")
def install(name: str, proxy: str | None):
    """安装插件"""
    from ..utils import get_astrbot_root, build_plug_list, manage_plugin, PluginStatus
    base_path = get_astrbot_root()
    plug_path = base_path / "data" / "plugins"
    plugins = build_plug_list(base_path / "data" / "plugins")

    # 首先尝试精确匹配
    exact_plugin = next(
        (
            p
            for p in plugins
            if p["name"] == name and p["status"] == PluginStatus.NOT_INSTALLED
        ),
        None,
    )

    if exact_plugin:
        manage_plugin(exact_plugin, plug_path, is_update=False, proxy=proxy)
        return

    # 如果精确匹配失败，进行模糊搜索
    available_plugins = [p for p in plugins if p["status"] == PluginStatus.NOT_INSTALLED]
    
    # 按优先级搜索：名称 > 描述 > 作者
    name_matches = []
    desc_matches = []
    author_matches = []
    
    name_lower = name.lower()
    for p in available_plugins:
        plugin_name_lower = p["name"].lower()
        plugin_desc_lower = p["desc"].lower()
        plugin_author_lower = p["author"].lower()
        
        # 优先级1: 名称匹配
        if name_lower in plugin_name_lower:
            name_matches.append(p)
        # 优先级2: 描述匹配（但名称不匹配）
        elif name_lower in plugin_desc_lower:
            desc_matches.append(p)
        # 优先级3: 作者匹配（但名称和描述都不匹配）
        elif name_lower in plugin_author_lower:
            author_matches.append(p)
    
    # 合并结果并限制为3个选项
    fuzzy_matches = (name_matches + desc_matches + author_matches)[:3]
    
    if not fuzzy_matches:
        raise click.ClickException(
            click.style(f"未找到匹配 '{name}' 的可安装插件", fg="red")
        )
    
    # 如果只有一个匹配项，直接安装
    if len(fuzzy_matches) == 1:
        click.echo(f"找到匹配的插件: {fuzzy_matches[0]['name']}")
        if click.confirm("是否安装此插件?"):
            manage_plugin(fuzzy_matches[0], plug_path, is_update=False, proxy=proxy)
        return
    
    # 多个匹配项，让用户选择
    click.echo(f"找到 {len(fuzzy_matches)} 个匹配 '{name}' 的插件:")
    click.echo()
    
    for i, plugin in enumerate(fuzzy_matches, 1):
        status_color = "green" if plugin["status"] == PluginStatus.NOT_INSTALLED else "yellow"
        click.echo(f"  {i}. {click.style(plugin['name'], fg='cyan')} ({plugin['version']}) - {plugin['author']}")
        click.echo(f"     {plugin['desc']}")
        click.echo(f"     Status: {click.style(plugin['status'].value, fg=status_color)}")
        click.echo()
    
    try:
        choice = click.prompt("请选择要安装的插件 (输入序号)", type=int)
        if 1 <= choice <= len(fuzzy_matches):
            selected_plugin = fuzzy_matches[choice - 1]
            manage_plugin(selected_plugin, plug_path, is_update=False, proxy=proxy)
        else:
            click.echo(click.style("无效的选择", fg="red"))
    except click.Abort:
        click.echo("安装已取消")
