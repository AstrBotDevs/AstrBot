"""
AstrBot CLI入口
"""
import sys
import click
from astrbot import __version__
import dotenv

logo_tmpl = r"""
     ___           _______.___________..______      .______     ______   .___________.
    /   \         /       |           ||   _  \     |   _  \   /  __  \  |           |
   /  ^  \       |   (----`---|  |----`|  |_)  |    |  |_)  | |  |  |  | `---|  |----`
  /  /_\  \       \   \       |  |     |      /     |   _  <  |  |  |  |     |  |
 /  _____  \  .----)   |      |  |     |  |\  \----.|  |_)  | |  `--'  |     |  |
/__/     \__\ |_______/       |__|     | _| `._____||______/   \______/      |__|
"""

dotenv.load_dotenv()

@click.group()
@click.version_option(__version__, prog_name="AstrBot")
def cli() -> None:
    """
    AstrBot CLI \b\n
    @github: https://github.com/AstrBotDevs/AstrBot \b\n
    """
    click.echo(logo_tmpl)
    click.echo("Welcome to AstrBot CLI!")
    click.echo(f"AstrBot CLI version: {__version__}")

@cli.command()
def star():
    """Star AstrBot on GitHub"""
    import webbrowser

    repo_url = "https://github.com/AstrBotDevs/AstrBot"
    click.echo(f"准备为 {repo_url} 点亮星标...")
    
    # 方法1: 使用浏览器自动打开GitHub页面
    if click.confirm("是否直接在浏览器中打开项目页面进行Star?", default=True):
        webbrowser.open(repo_url)
        click.echo("已打开浏览器，请在页面中点击Star按钮。")
        return
    

    
# region 基本命令
@cli.command()
@click.argument("command_name", required=False, type=str)
def help(command_name: str | None) -> None:
    """Astrbot CLI helper
    usage: astrbot help [command_name]
    useful commands:
    init: Initialize the Astrbot \n
    run: Run the Astrbot \n 
    plug: Plug in a module to the Astrbot \n
    @github: https://github.com/AstrBotDevs/AstrBot
    """
    ctx = click.get_current_context()
    if command_name:
        # 查找指定命令
        command = cli.get_command(ctx, command_name)
        if command:
            # 显示特定命令的帮助信息
            click.echo(command.get_help(ctx))
        else:
            click.echo(f"Unknown command: {command_name}")
            sys.exit(1)
    else:
        # 显示通用帮助信息
        click.echo(cli.get_help(ctx))

# endregion 基本命令

from astrbot.cli.commands import init, run, plug
cli.add_command(init)
cli.add_command(run)
cli.add_command(plug)


if __name__ == "__main__":
    cli()


