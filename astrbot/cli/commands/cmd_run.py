import os
from pathlib import Path
import click
import asyncio
import time
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

# 创建Rich控制台
console = Console()


async def run_astrbot(astrbot_root: Path):
    """运行 AstrBot"""
    from ..utils import check_dashboard
    from astrbot.core import logger, LogManager, LogBroker, db_helper
    from astrbot.core.initial_loader import InitialLoader
    
    # 使用进度条显示启动过程
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]启动中...[/bold blue]"),
        BarColumn(),
        TextColumn("{task.description}"),
        console=console
    ) as progress:
        # 检查控制面板
        dashboard_task = progress.add_task("正在检查控制面板...", total=1)
        await check_dashboard(astrbot_root)
        progress.update(dashboard_task, advance=1, description="[green]控制面板就绪[/green]")
        time.sleep(0.3)  # 为了更好的视觉效果
        
        # 初始化日志系统
        log_task = progress.add_task("正在初始化日志系统...", total=1)
        log_broker = LogBroker()
        LogManager.set_queue_handler(logger, log_broker)
        progress.update(log_task, advance=1, description="[green]日志系统就绪[/green]")
        time.sleep(0.3)  # 为了更好的视觉效果
        
        # 准备数据库
        db_task = progress.add_task("正在准备数据库...", total=1)
        db = db_helper
        progress.update(db_task, advance=1, description="[green]数据库就绪[/green]")
        time.sleep(0.3)  # 为了更好的视觉效果
        
        # 初始化核心系统
        core_task = progress.add_task("正在初始化核心系统...", total=1)
        core_lifecycle = InitialLoader(db, log_broker)
        progress.update(core_task, advance=1, description="[green]核心系统就绪[/green]")
        time.sleep(0.5)  # 为了更好的视觉效果
    
    # 启动提示
    console.print(Panel(
        "[bold cyan]AstrBot 正在启动中...[/bold cyan]",
        border_style="blue",
        title="[bold]启动信息[/bold]"
    ))
    
    # 启动系统核心
    await core_lifecycle.start()


@click.option("--reload", "-r", is_flag=True, help="插件自动重载")
@click.option("--port", "-p", help="Astrbot Dashboard端口", required=False, type=str)
@click.command()
def run(reload: bool, port: str) -> None:
    """运行 AstrBot"""
    from ...core.utils.astrbot_path import get_astrbot_root , check_astrbot_root
    from filelock import FileLock, Timeout

    # 显示欢迎界面
    console.print(Panel.fit(
        "[bold cyan]欢迎使用 AstrBot[/bold cyan]\n\n"
        "[yellow]本程序将启动 AstrBot 核心服务和控制面板。[/yellow]\n"
        "[italic]您可以使用 Ctrl+C 随时终止程序。[/italic]",
        border_style="blue",
        padding=(1, 2),
    ))

    try:
        # 设置环境变量
        os.environ["ASTRBOT_CLI"] = "1"
        astrbot_root = get_astrbot_root()

        # 检查根目录
        if not check_astrbot_root(astrbot_root):
            console.print(Panel(
                f"[bold red]错误:[/bold red] [yellow]{astrbot_root}[/yellow] 不是有效的 AstrBot 根目录\n\n"
                "请先使用 [bold green]astrbot init[/bold green] 命令初始化 AstrBot。",
                title="[bold red]初始化错误[/bold red]",
                border_style="red"
            ))
            raise click.ClickException(
                f"{astrbot_root}不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init"
            )

        # 设置路径
        os.environ["ASTRBOT_ROOT"] = str(astrbot_root)
        
        # 配置表格
        config_table = Table(title="AstrBot 启动配置", show_header=True, header_style="bold magenta")
        config_table.add_column("配置项", style="cyan")
        config_table.add_column("值", style="green")
        config_table.add_row("AstrBot 根目录", str(astrbot_root))
        
        # 处理配置选项
        if port:
            os.environ["DASHBOARD_PORT"] = port
            config_table.add_row("控制面板端口", port)
        else:
            config_table.add_row("控制面板端口", "默认")

        if reload:
            os.environ["ASTRBOT_RELOAD"] = "1"
            config_table.add_row("插件自动重载", "[bold green]已启用[/bold green]")
        else:
            config_table.add_row("插件自动重载", "[yellow]已禁用[/yellow]")
            
        # 显示配置信息
        console.print(config_table)

        # 获取锁并启动
        lock_file = astrbot_root / "astrbot.lock"
        lock = FileLock(lock_file, timeout=5)
        
        with lock.acquire():
            console.print("[bold green]已获取锁文件，准备启动 AstrBot...[/bold green]")
            asyncio.run(run_astrbot(astrbot_root))
            
    except KeyboardInterrupt:
        console.print(Panel(
            "[bold yellow]AstrBot 已被用户终止[/bold yellow]",
            border_style="yellow",
            title="[bold]系统关闭[/bold]"
        ))
    except Timeout:
        console.print(Panel(
            "[bold red]启动失败![/bold red]\n\n"
            "无法获取锁文件，请检查是否有其他 AstrBot 实例正在运行。\n"
            "您可以尝试关闭所有已运行的 AstrBot 进程后重试。",
            title="[bold red]错误[/bold red]",
            border_style="red"
        ))
        raise click.ClickException("无法获取锁文件，请检查是否有其他实例正在运行")
