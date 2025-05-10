"""
AstrBot CLI入口
"""
import sys
import click
from astrbot import __version__
import dotenv
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from datetime import datetime
import time

# 创建Rich控制台
console = Console()

# 工具函数：创建进度条
def create_progress_bar(description: str = "Processing", total: int = 100) -> Progress:
    """创建一个美观的进度条"""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}[/bold blue]"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True
    )

# 工具函数：显示成功消息
def show_success(message: str) -> None:
    """显示成功消息"""
    console.print(f"[bold green]✓[/bold green] {message}")
    
# 工具函数：显示错误消息
def show_error(message: str) -> None:
    """显示错误消息"""
    console.print(f"[bold red]✗[/bold red] {message}")
    
# 工具函数：显示警告消息
def show_warning(message: str) -> None:
    """显示警告消息"""
    console.print(f"[bold yellow]![/bold yellow] {message}")

# 使用rich渲染的彩色Logo
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
    # 清晰的开始界面
    console.print(Panel.fit(
        Text(logo_tmpl, style="bold cyan"),
        title="[bold yellow]AstrBot CLI[/bold yellow]",
        border_style="blue",
        padding=(1, 2),
    ))
    
    # 添加版本信息和欢迎信息
    table = Table(show_header=False, box=None)
    table.add_column("key", style="green")
    table.add_column("value", style="yellow")
    
    table.add_row("Version", f"{__version__}")
    table.add_row("Date", f"{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    table.add_row("Status", "[bold green]Ready[/bold green]")
    
    console.print(Panel(
        table,
        title="[bold]Welcome to AstrBot CLI![/bold]",
        border_style="green",
        expand=False
    ))

@cli.command()
def star():
    """Star AstrBot on GitHub"""
    import webbrowser

    repo_url = "https://github.com/AstrBotDevs/AstrBot"
    console.print(Panel(f"[yellow]准备为[/yellow] [bold cyan]{repo_url}[/bold cyan] [yellow]点亮星标...[/yellow]", 
                       border_style="yellow"))
    
    # 方法1: 使用浏览器自动打开GitHub页面
    if click.confirm("是否直接在浏览器中打开项目页面进行Star?", default=True):
        webbrowser.open(repo_url)
        console.print("[bold green]✓[/bold green] 已打开浏览器，请在页面中点击[bold yellow]★ Star[/bold yellow]按钮。")
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
            help_text = command.get_help(ctx)
            console.print(Panel(
                help_text,
                title=f"[bold blue]Command: {command_name}[/bold blue]",
                border_style="green",
                expand=False
            ))
        else:
            console.print(Panel(
                f"[bold red]未找到命令: {command_name}[/bold red]\n\n运行 [bold yellow]astrbot --help[/bold yellow] 查看所有可用命令",
                title="[bold red]错误[/bold red]",
                border_style="red"
            ))
            sys.exit(1)
    else:
        # 显示通用帮助信息，创建一个美观的帮助面板
        help_table = Table(show_header=True, box=None, highlight=True, border_style="blue")
        help_table.add_column("命令", style="cyan", justify="left")
        help_table.add_column("描述", style="green")
        
        # 添加主要命令
        help_table.add_row("init", "初始化 AstrBot")
        help_table.add_row("run", "运行 AstrBot")
        help_table.add_row("plug", "管理 AstrBot 插件")
        help_table.add_row("star", "为 AstrBot 点亮 GitHub 星标")
        help_table.add_row("help", "显示帮助信息")
        
        console.print(Panel(
            help_table,
            title="[bold]AstrBot CLI 命令列表[/bold]",
            subtitle="使用 [italic yellow]astrbot help <命令名>[/italic yellow] 获取特定命令的详细信息",
            border_style="blue"
        ))

# endregion 基本命令

from astrbot.cli.commands import init, run, plug
cli.add_command(init)
cli.add_command(run)
cli.add_command(plug)


if __name__ == "__main__":
    cli()


