"""
AstrBot CLI入口
"""

import click
import sys
from astrbot.cli import __version__
from astrbot.cli.init import init
from astrbot.cli.run import run

logo_tmpl = r"""
     ___           _______.___________..______      .______     ______   .___________.
    /   \         /       |           ||   _  \     |   _  \   /  __  \  |           |
   /  ^  \       |   (----`---|  |----`|  |_)  |    |  |_)  | |  |  |  | `---|  |----`
  /  /_\  \       \   \       |  |     |      /     |   _  <  |  |  |  |     |  |
 /  _____  \  .----)   |      |  |     |  |\  \----.|  |_)  | |  `--'  |     |  |
/__/     \__\ |_______/       |__|     | _| `._____||______/   \______/      |__|
"""


@click.group(invoke_without_command=True, no_args_is_help=False)
@click.version_option(__version__, prog_name="AstrBot")
def cli() -> None:
    """The AstrBot CLI"""
    # Display colored logo and welcome message
    click.echo(click.style(logo_tmpl, fg="cyan"))
    click.echo(click.style("Welcome to AstrBot CLI!", fg="cyan", bold=True))
    click.echo(f"AstrBot CLI version: {click.style(__version__, fg='yellow')}")
    click.echo(click.style("=" * 30, fg="red"))
    click.echo(click.style("Available commands:", fg="white", bold=True))
    click.echo(f"  {click.style('Command Groups | 命令组:', fg='blue', bold=True)}")
    click.echo(f"    {click.style('conf', fg='blue')} - Configuration management | 配置管理")
    click.echo(f"    {click.style('plug', fg='blue')} - Plugin management | 插件管理")
    click.echo(f"  {click.style('Individual Commands | 可用的命令:', fg='green', bold=True)}")
    click.echo(f"    {click.style('init', fg='green')} - Initialize AstrBot | 初始化 AstrBot")
    click.echo(f"    {click.style('run', fg='green')} - Run AstrBot | 运行 AstrBot")
    click.echo(f"    {click.style('help', fg='green')} - Show help information | 显示帮助信息")
    click.echo(click.style("=" * 30, fg="red"))
    click.echo(f"Use {click.style('astrbot --help / help', fg='yellow')} for detailed help information.")

# 拓展帮助指令 当然直接使用 --help也是可以看帮助信息的
@cli.command()
@click.argument("command_name", required=False, type=str)
def help(command_name: str | None) -> None:
    """显示命令的帮助信息

    如果提供了 COMMAND_NAME，则显示该命令的详细帮助信息。
    否则，显示通用帮助信息。
    """
    ctx = click.get_current_context()
    if command_name:
        # 查找指定命令
        command = cli.get_command(ctx, command_name)
        if command:
            # 显示特定命令的帮助信息
            click.echo(click.style(f"Help for command '{command_name}':", fg="green", bold=True))
            click.echo(command.get_help(ctx))
        else:
            click.echo(click.style(f"Unknown command: {command_name}", fg="red", bold=True))
            sys.exit(1)
    else:
        # 显示通用帮助信息
        click.echo(click.style("AstrBot CLI Help", fg="cyan", bold=True))
        click.echo("=" * 20)
        click.echo(cli.get_help(ctx))

#region cli.command
cli.add_command(init)
cli.add_command(run)

#region cli.conf 子命令组
from astrbot.cli.conf import conf
cli.add_command(conf)


#region cli.plug 子命令组
from astrbot.cli.plug import plug
cli.add_command(plug)




if __name__ == "__main__":
    cli()
