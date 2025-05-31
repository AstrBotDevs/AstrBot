import click

@click.group(invoke_without_command=True)
@click.pass_context
def plug(ctx):
    """插件管理子命令组"""
    if ctx.invoked_subcommand is None:
        click.echo(click.style("Plugin Management | 插件管理", fg="blue", bold=True))
        click.echo(click.style("=" * 30, fg="blue"))
        click.echo(f"Available {click.style('plug', fg='blue')} sub-commands | 可用的插件子命令:")
        click.echo(f"  {click.style('new', fg='magenta')}     Create a new plugin | 创建新插件")
        click.echo(f"  {click.style('search', fg='magenta')}  Search for plugins | 搜索插件")
        click.echo(f"  {click.style('list', fg='magenta')}    List installed plugins | 列出已安装的插件")
        click.echo(f"  {click.style('install', fg='magenta')} Install a plugin | 安装插件")
        click.echo(f"  {click.style('update', fg='magenta')}  Update plugins | 更新插件")
        click.echo(f"  {click.style('remove', fg='magenta')}  Remove a plugin | 删除插件")
        click.echo()

from astrbot.cli.plug.new import new
from astrbot.cli.plug.search import search
from astrbot.cli.plug.list import list_impl
from astrbot.cli.plug.install import install
from astrbot.cli.plug.update import update
from astrbot.cli.plug.remove import remove

plug.add_command(new)
plug.add_command(search)
plug.add_command(list_impl)
plug.add_command(install)
plug.add_command(update)
plug.add_command(remove)


if __name__ == "__main__":
    plug()
