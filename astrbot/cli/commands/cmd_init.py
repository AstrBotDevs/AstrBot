import asyncio
import datetime
from pathlib import Path
import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
import time

# 创建Rich控制台
console = Console()

async def initialize_astrbot(astrbot_root : Path) -> None:
    """执行 AstrBot 初始化逻辑"""
    from ..utils import check_dashboard
    dot_astrbot = astrbot_root / ".astrbot"

    if not dot_astrbot.exists():
        console.print(Panel(f"[bold cyan]当前目录:[/bold cyan] [yellow]{astrbot_root}[/yellow]", 
                           border_style="blue"))
        console.print(
            "[italic]如果你确认这是 Astrbot root directory, 你需要在当前目录下创建一个 [bold].astrbot[/bold] 文件标记该目录为 AstrBot 的根目录。[/italic]"
        )

        if click.confirm(
            f"请检查当前目录是否正确，确认正确请回车: {astrbot_root}",
            default=True,
            abort=True,
        ):
            # 显示进度条动画
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]初始化中...[/bold blue]"),
                BarColumn(),
                TimeElapsedColumn(),
                console=console
            ) as progress:
                task = progress.add_task("初始化 AstrBot", total=100)
                
                # 创建基本结构
                progress.update(task, advance=20, description="创建配置文件...")
                dot_astrbot.touch()
                time.sleep(0.3)  # 为了更好的视觉效果
                
                # 写入元数据
                progress.update(task, advance=40, description="写入配置信息...")
                import toml
                from astrbot.core.config.default import VERSION
                metadata : dict[str, str] = {
                    "version": VERSION,
                    "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "dashboard_version": "N/A",
                }
                time.sleep(0.3)  # 为了更好的视觉效果
        
                with open(dot_astrbot, "w", encoding="utf-8") as f:
                    toml.dump(metadata, f)
                
                progress.update(task, advance=40, description="完成!")
                time.sleep(0.2)  # 为了更好的视觉效果

            console.print(f"[bold green]✓[/bold green] 已创建 [cyan]{dot_astrbot}[/cyan]")    # 创建目录结构
    paths = {
        "config": astrbot_root / "config",
        "plugins": astrbot_root / "plugins",
        "temp": astrbot_root / "temp",
        "cache": astrbot_root / "cache",
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]创建目录结构...[/bold blue]"),
        BarColumn(),
        TextColumn("{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("准备中...", total=len(paths))
        
        for name, path in paths.items():
            path.mkdir(parents=True, exist_ok=True)
            progress.update(task, advance=1, description=f"[green]处理 [bold]/{name}[/bold][/green]")
            time.sleep(0.2)  # 为了更好的视觉效果
            
        # 完成后的视觉提示
        progress.update(task, description="[bold green]目录结构创建完成![/bold green]")
        time.sleep(0.5)
    
    # 显示创建的目录
    console.print(Panel(
        "\n".join(f"[green]✓[/green] [blue]{name}:[/blue] {path}" for name, path in paths.items()),
        title="[bold]已创建以下目录结构[/bold]",
        border_style="green"
    ))

    # 检查控制面板
    console.print("[yellow]正在检查控制面板...[/yellow]")
    await check_dashboard(astrbot_root)
    



@click.command()
def init() -> None:
    """初始化 AstrBot"""
    from ...core.utils.astrbot_path import get_astrbot_root
    from filelock import FileLock, Timeout
    
    # 显示精美的初始化标题
    console.print(Panel.fit(
        "[bold cyan]AstrBot 初始化工具[/bold cyan]\n\n"
        "[yellow]本工具将帮助您初始化 AstrBot 环境，创建必要的目录结构和配置文件。[/yellow]",
        border_style="blue",
        padding=(1, 2),
    ))
    
    astrbot_root = get_astrbot_root()
    lock_file = astrbot_root / "astrbot.lock"
    lock = FileLock(lock_file, timeout=5)

    try:
        with lock.acquire():
            asyncio.run(initialize_astrbot(astrbot_root))
            
            # 完成时显示成功消息
            console.print(Panel(
                "[bold green]AstrBot 初始化成功![/bold green]\n\n"
                "您现在可以使用 [bold yellow]astrbot run[/bold yellow] 命令启动 AstrBot。",
                title="[bold]设置完成[/bold]",
                border_style="green"
            ))
    except Timeout:
        # 失败时显示错误消息
        console.print(Panel(
            "[bold red]初始化失败![/bold red]\n\n"
            "无法获取锁文件，请检查是否有其他 AstrBot 实例正在运行。\n"
            "您可以尝试关闭所有已运行的 AstrBot 进程后重试。",
            title="[bold]错误[/bold]",
            border_style="red"
        ))
        raise click.ClickException("无法获取锁文件，请检查是否有其他实例正在运行")

