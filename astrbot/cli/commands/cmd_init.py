import asyncio
import datetime
from pathlib import Path
import click

async def initialize_astrbot(astrbot_root : Path) -> None:
    """执行 AstrBot 初始化逻辑"""
    from ..utils import check_dashboard
    dot_astrbot = astrbot_root / ".astrbot"

    if not dot_astrbot.exists():
        click.echo(f"Current Directory: {astrbot_root}")
        click.echo(
            "如果你确认这是 Astrbot root directory, 你需要在当前目录下创建一个 .astrbot 文件标记该目录为 AstrBot 的根目录。"
        )

        if click.confirm(
            f"请检查当前目录是否正确，确认正确请回车: {astrbot_root}",
            default=True,
            abort=True,
        ):
            dot_astrbot.touch()
            # 标记astrbot根目录创建时版本
            import toml
            from astrbot.core.config.default import VERSION
            metadata : dict[str, str] = {
                "version": VERSION,
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "dashboard_version": "N/A",
            }
    
            with open(dot_astrbot, "w", encoding="utf-8") as f:
                toml.dump(metadata, f)

            click.echo(f"Created {dot_astrbot}")

    paths = {
        "config": astrbot_root / "config",
        "plugins": astrbot_root / "plugins",
        "temp": astrbot_root / "temp",
        "cache": astrbot_root / "cache",
    }

    for name, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        click.echo(f"{f'/{name} Created' if not path.exists() else 'Directory exists'}: {path}")

    await check_dashboard(astrbot_root)
    



@click.command()
def init() -> None:
    """初始化 AstrBot"""
    from ...core.utils.astrbot_path import get_astrbot_root
    from filelock import FileLock, Timeout
    click.echo("Initializing AstrBot...")
    astrbot_root = get_astrbot_root()
    lock_file = astrbot_root / "astrbot.lock"
    lock = FileLock(lock_file, timeout=5)

    try:
        with lock.acquire():
            asyncio.run(initialize_astrbot(astrbot_root))
    except Timeout:
        raise click.ClickException("无法获取锁文件，请检查是否有其他实例正在运行")

