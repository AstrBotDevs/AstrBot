import asyncio
import os
from pathlib import Path
import sys
import click
try:
    from ..__about__ import __version__, __LOGO__
except ImportError:
    from astrbot.__about__ import __version__, __LOGO__
# 解释，这是cli包的入口文件，作为入口，不能使用相对导入 from .xxx import yyy 所以这个写一个try except


# utils
def _get_astrbot_root(path: str | None) -> Path:
    """获取astrbot根目录"""
    match path:
        case None:
            match ASTRBOT_ROOT := os.getenv("ASTRBOT_ROOT"):
                case None:
                    astrbot_root = Path.cwd() / "data"
                case _:
                    astrbot_root = Path(ASTRBOT_ROOT).resolve()
        case str():
            astrbot_root  = Path(path).resolve()

    dot_astrbot = astrbot_root / ".astrbot"
    if not dot_astrbot.exists():
        if click.confirm(
            f"请检查当前目录是否正确，回车以继续: {astrbot_root}",
            default=True,
            abort=True,
        ):
            dot_astrbot.touch()
            astrbot_root.mkdir(parents=True, exist_ok=True)
            click.echo(f"Created {dot_astrbot}")


    return astrbot_root


# 通过类型来验证先后，必须先获取Path对象才能对该目录进行检查
def _check_astrbot_root(astrbot_root: Path) -> None:
    """验证"""
    dot_astrbot = astrbot_root / ".astrbot"
    if not astrbot_root.exists():
        click.echo(f"AstrBot root directory does not exist: {astrbot_root}")
        click.echo("Please run 'astrbot init' to create the directory.")
        sys.exit(1)
    else:
        click.echo(f"AstrBot root directory exists: {astrbot_root}")
        if not dot_astrbot.exists():
            click.echo("如果你确认这是astrbot_root,你需要在当前目录下创建一个 .astrbot 文件标记该目录为 AstrBot 的数据目录。")
            if click.confirm(
                f"请检查当前目录是否正确，确认正确请回车: {astrbot_root}",
                default=True,
                abort=True,
            ):
                dot_astrbot.touch()
                click.echo(f"Created {dot_astrbot}")
        else:
            click.echo(f"Wellcome back! AstrBot root directory: {astrbot_root}")



async def _check_dashboard(astrbot_root: Path ) -> None:
    """检查是否安装了dashboard"""
    try:
        from ..core.utils.io import get_dashboard_version, download_dashboard
    except ImportError:
        from astrbot.core.utils.io import get_dashboard_version, download_dashboard

    try:
        # 添加 create=True 参数以确保在初始化时不会抛出异常
        dashboard_version = await get_dashboard_version()
        match dashboard_version:
            case None:
                click.echo("未安装管理面板")
            case str():
                if dashboard_version == f"v{__version__}":
                    click.echo("无需更新")
                else:
                    try:
                        version = dashboard_version.split("v")[1]
                        click.echo(f"管理面板版本: {version}")
                        # 确保使用 create=True 参数
                        await download_dashboard(path="data/dashboard.zip", extract_path=str(astrbot_root))
                    except Exception as e:
                        click.echo(f"下载管理面板失败: {e}")
                        return
    except FileNotFoundError:
        click.echo("初始化管理面板目录...")
        # 初始化模式下，下载到指定位置
        try:
            await download_dashboard(path=str(astrbot_root / "dashboard.zip"), extract_path=str(astrbot_root))
            click.echo("管理面板初始化完成")
        except Exception as e:
            click.echo(f"下载管理面板失败: {e}")
            return



@click.group(name="astrbot")
def cli() -> None:
    """AstrBot CLI"""
    click.echo(__LOGO__)
    click.echo("Welcome to AstrBot CLI!")
    click.echo(f"AstrBot version: {__version__}")
# 友情提醒，这个就不要加async, 待会这个click组会build进astrbot.exe 作为入口，这就是cli程序入口


# region init
@cli.command()
@click.option("--path", "-p", help="astrbot 数据目录")
def init(path: str | None) -> None:
    """Initialize AstrBot"""
    click.echo("Initializing AstrBot...")

    astrbot_root = _get_astrbot_root(path)

    _check_astrbot_root(astrbot_root)

    click.echo(f"AstrBot root directory: {astrbot_root}")

    if not astrbot_root.exists():
        # 创建目录
        astrbot_root.mkdir(parents=True, exist_ok=True)
        click.echo(f"Created directory: {astrbot_root}")
    else:
        click.echo(f"Directory already exists: {astrbot_root}")

    config_path: Path = astrbot_root / "config"
    plugins_path: Path = astrbot_root / "plugins"
    temp_path: Path = astrbot_root / "temp"
    config_path.mkdir(parents=True, exist_ok=True)
    plugins_path.mkdir(parents=True, exist_ok=True)
    temp_path.mkdir(parents=True, exist_ok=True)

    click.echo(f"Created directories: {config_path}, {plugins_path}, {temp_path}")

    # 检查是否安装了dashboard
    asyncio.run(_check_dashboard(astrbot_root))




# region run
@cli.command()
@click.option("--path","-p" , help="astrbot 数据目录")
def run(path: str | None = None) -> None:
    """Run AstrBot"""
    # 解析为绝对路径
    try:
        from ..core.log import LogBroker
        from ..core import db_helper
        from ..core.initial_loader import InitialLoader
    except ImportError:
        from astrbot.core.log import LogBroker
        from astrbot.core import db_helper
        from astrbot.core.initial_loader import InitialLoader

    astrbot_root = _get_astrbot_root(path)

    _check_astrbot_root(astrbot_root)

    asyncio.run(_check_dashboard(astrbot_root))

    log_broker = LogBroker()
    db = db_helper

    core_lifecycle = InitialLoader(db, log_broker)
    try:
        asyncio.run(core_lifecycle.start())
    except KeyboardInterrupt:
        click.echo("接收到退出信号，正在关闭AstrBot...")
    except Exception as e:
        click.echo(f"运行时出现错误: {e}")



# region Basic
@cli.command(name="version")
def version() -> None:
    """Show the version of AstrBot"""
    click.echo(f"AstrBot version: {__version__}")


@cli.command()
@click.argument("command_name", required=False, type=str)
def help(command_name: str | None) -> None:
    """Show help information for commands
    
    If COMMAND_NAME is provided, show detailed help for that command.
    Otherwise, show general help information.
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



if __name__ == "__main__":
    cli()
