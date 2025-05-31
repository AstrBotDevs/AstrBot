import click


@click.command()
@click.argument("name")
def new(name: str):
    """创建新插件"""
    from ..utils import get_astrbot_root, get_git_repo
    import re
    base_path = get_astrbot_root()
    plug_path = base_path / "plugins" / name

    if plug_path.exists():
        raise click.ClickException(click.style(f"插件 {name} 已存在", fg="red"))

    author = click.prompt("请输入插件作者", type=str)
    desc = click.prompt("请输入插件描述", type=str)
    version = click.prompt("请输入插件版本", type=str)
    if not re.match(r"^\d+\.\d+(\.\d+)?$", version.lower().lstrip("v")):
        raise click.ClickException(click.style("版本号必须为 x.y 或 x.y.z 格式", fg="red"))
    repo = click.prompt("请输入插件仓库：", type=str)
    if not repo.startswith("http"):
        raise click.ClickException(click.style("仓库地址必须以 http 开头", fg="red"))

    click.echo(click.style("正在下载插件模板...", fg="cyan"))
    get_git_repo(
        "https://github.com/Soulter/helloworld",
        plug_path,
    )

    click.echo(click.style("正在重写插件信息...", fg="yellow"))
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

    click.echo(click.style(f"✓ 插件 {name} 创建成功", fg="green", bold=True))
