import asyncio
import os
import subprocess
import sys
import traceback
from pathlib import Path

import click
from filelock import FileLock, Timeout

from ..utils import check_astrbot_root, check_dashboard, get_astrbot_root


async def run_astrbot(astrbot_root: Path) -> None:
    """运行 AstrBot"""
    from astrbot.core import LogBroker, LogManager, db_helper, logger
    from astrbot.core.initial_loader import InitialLoader

    await check_dashboard(astrbot_root / "data")

    log_broker = LogBroker()
    LogManager.set_queue_handler(logger, log_broker)
    db = db_helper

    core_lifecycle = InitialLoader(db, log_broker)

    await core_lifecycle.start()


def launch_in_new_window(
    astrbot_root: Path,
    reload: bool,
    port: str | None,
) -> None:
    """在新窗口启动 AstrBot（仅 Windows）"""
    python_exe = sys.executable

    # 构建命令，添加 --no-window 标志表示在当前窗口运行
    cmd = [python_exe, "-m", "astrbot.cli", "run", "--no-window"]

    if reload:
        cmd.append("-r")

    if port:
        cmd.extend(["-p", port])

    # 设置环境变量
    env = os.environ.copy()
    env["ASTRBOT_CLI"] = "1"
    env["ASTRBOT_ROOT"] = str(astrbot_root)

    if port:
        env["DASHBOARD_PORT"] = port

    if reload:
        env["ASTRBOT_RELOAD"] = "1"

    if sys.platform == "win32":
        # Windows: 使用 start 命令开新窗口
        cmd_str = " ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd)
        ps_script = f'Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd {astrbot_root}; {cmd_str}" -WindowStyle Normal'
        subprocess.Popen(
            ["powershell", "-Command", ps_script],
            env=env,
            shell=False,
        )
    elif sys.platform == "darwin":
        # macOS: 使用 osascript 打开新的 Terminal 窗口
        cmd_str = " ".join(cmd)
        script = f"""
        tell application "Terminal"
            do script "cd {astrbot_root} && {cmd_str}"
            activate
        end tell
        """
        subprocess.Popen(["osascript", "-e", script], env=env)
    else:
        # Linux: 使用 gnome-terminal 或 xterm
        cmd_str = " ".join(cmd)
        for term_cmd in ["gnome-terminal", "xterm", "konsole", "xfce4-terminal"]:
            try:
                if term_cmd == "gnome-terminal":
                    subprocess.Popen(
                        [
                            term_cmd,
                            "--",
                            "bash",
                            "-c",
                            f"cd {astrbot_root} && {cmd_str}; exec bash",
                        ],
                        env=env,
                    )
                else:
                    subprocess.Popen(
                        [
                            term_cmd,
                            "-e",
                            "bash",
                            "-c",
                            f"cd {astrbot_root} && {cmd_str}; exec bash",
                        ],
                        env=env,
                    )
                break
            except FileNotFoundError:
                continue
        else:
            raise click.ClickException(
                "无法找到终端模拟器，请手动安装 gnome-terminal 或 xterm"
            )


@click.option("--reload", "-r", is_flag=True, help="插件自动重载")
@click.option("--port", "-p", help="Astrbot Dashboard端口", required=False, type=str)
@click.option(
    "--window",
    "-w",
    is_flag=True,
    help="在新窗口中启动（仅 Windows）",
)
@click.option(
    "--no-window",
    is_flag=True,
    hidden=True,
    help="在当前窗口运行（内部使用）",
)
@click.command()
def run(reload: bool, port: str, window: bool, no_window: bool) -> None:
    """运行 AstrBot（Linux/macOS 默认当前窗口，Windows 可选 --window）"""
    os.environ["ASTRBOT_CLI"] = "1"
    astrbot_root = get_astrbot_root()

    if not check_astrbot_root(astrbot_root):
        raise click.ClickException(
            f"{astrbot_root}不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init",
        )

    # Windows: 如果指定了 --window 且不是 --no-window，在新窗口启动
    # Linux/macOS: 始终在当前窗口运行
    if sys.platform == "win32" and window and not no_window:
        launch_in_new_window(astrbot_root, reload, port)
        click.echo("[OK] AstrBot 已在新窗口中启动")
        return

    # 在当前窗口运行（Linux/macOS 默认，Windows 默认或指定 --no-window）
    try:
        os.environ["ASTRBOT_ROOT"] = str(astrbot_root)
        sys.path.insert(0, str(astrbot_root))

        if port:
            os.environ["DASHBOARD_PORT"] = port

        if reload:
            click.echo("启用插件自动重载")
            os.environ["ASTRBOT_RELOAD"] = "1"

        lock_file = astrbot_root / "astrbot.lock"
        lock = FileLock(lock_file, timeout=5)
        with lock.acquire():
            asyncio.run(run_astrbot(astrbot_root))
    except KeyboardInterrupt:
        click.echo("AstrBot 已关闭...")
    except Timeout:
        raise click.ClickException("无法获取锁文件，请检查是否有其他实例正在运行")
    except Exception as e:
        raise click.ClickException(f"运行时出现错误: {e}\n{traceback.format_exc()}")
