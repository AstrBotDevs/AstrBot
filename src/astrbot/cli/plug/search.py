import click

@click.command()
@click.argument("query")
def search(query: str):
    """搜索插件"""
    from ..utils import get_astrbot_root, build_plug_list, display_plugins

    base_path = get_astrbot_root()
    plugins = build_plug_list(base_path / "plugins")    # 按优先级分类搜索结果：名称 > 描述 > 作者
    name_matches = []
    desc_matches = []
    author_matches = []
    
    for p in plugins:
        name_lower = p["name"].lower()
        desc_lower = p["desc"].lower()
        author_lower = p["author"].lower()
        query_lower = query.lower()
        
        # 优先级1: 名称匹配
        if query_lower in name_lower:
            name_matches.append(p)
        # 优先级2: 描述匹配（但名称不匹配）
        elif query_lower in desc_lower:
            desc_matches.append(p)
        # 优先级3: 作者匹配（但名称和描述都不匹配）
        elif query_lower in author_lower:
            author_matches.append(p)
      # 按优先级合并结果，并逆序排列（最新的在前面）
    matched_plugins = (name_matches + desc_matches + author_matches)[::-1]

    if not matched_plugins:
        click.echo(click.style(f"未找到匹配 '{query}' 的插件", fg="yellow"))
        return

    display_plugins(matched_plugins, f"搜索结果: '{query}'", "cyan")
