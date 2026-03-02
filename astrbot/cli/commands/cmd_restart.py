import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import click
from filelock import FileLock, Timeout

from ..utils import check_astrbot_root, check_dashboard, get_astrbot_root


async def run_astrbot(astrbot_root: Path):
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

    # 构建命令，添加 --no-window 标志让新窗口在当前窗口运行
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
        # Windows: 使用 CREATE_NEW_CONSOLE 在新窗口启动，环境变量通过 env 直接传递
        CREATE_NEW_CONSOLE = 0x00000010
        subprocess.Popen(
            cmd,
            env=env,
            cwd=str(astrbot_root),
            creationflags=CREATE_NEW_CONSOLE,
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


def find_and_kill_astrbot_processes(astrbot_root: Path) -> bool:
    """查找并终止正在运行的 AstrBot 进程

    Returns:
        bool: 是否成功终止了进程
    """
    killed = False
    current_pid = os.getpid()

    if sys.platform == "win32":
        # Windows: 使用 wmic 获取进程命令行，精确匹配 AstrBot 进程
        import subprocess

        try:
            # 使用 wmic 获取所有 python.exe 进程的命令行
            result = subprocess.run(
                [
                    "wmic",
                    "process",
                    "where",
                    "name='python.exe'",
                    "get",
                    "processid,commandline",
                    "/format:csv",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            # 解析输出并终止相关进程
            for line in result.stdout.split("\n"):
                if not line.strip() or "CommandLine" in line:
                    continue

                parts = line.split(",")
                if len(parts) >= 3:
                    _, cmdline, pid_str = (
                        parts[0].strip('"'),
                        parts[1].strip('"'),
                        parts[2].strip('"'),
                    )

                    try:
                        pid = int(pid_str)

                        # 跳过当前进程
                        if pid == current_pid:
                            continue

                        # 只终止包含 astrbot 的进程
                        # 匹配: astrbot, astrbot.exe, astrbot run, -m astrbot 等
                        cmdline_lower = cmdline.lower()
                        if "astrbot" in cmdline_lower or "astrbot.exe" in cmdline_lower:
                            subprocess.run(
                                ["taskkill", "/F", "/T", "/PID", str(pid)],
                                capture_output=True,
                                timeout=5,
                            )
                            click.echo(f"已终止进程: {pid}")
                            killed = True
                    except (ValueError, subprocess.TimeoutExpired):
                        continue
        except (subprocess.CalledProcessError, FileNotFoundError, Exception) as e:
            click.echo(f"查找进程时出错: {e}")

    else:
        # Unix/Linux/macOS: 使用 ps 和 kill
        import subprocess

        try:
            # 使用 ps 获取完整命令行，精确匹配
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            for line in result.stdout.split("\n"):
                # 跳过标题行
                if line.startswith("USER"):
                    continue

                # 检查是否是 python 进程且包含 astrbot
                if "python" in line.lower() and "astrbot" in line.lower():
                    parts = line.split(None, 10)  # 最多分割10次，保留完整命令行
                    if len(parts) >= 2:
                        try:
                            pid = int(parts[1])

                            # 跳过当前进程
                            if pid == current_pid:
                                continue

                            os.kill(pid, signal.SIGTERM)
                            click.echo(f"已发送 SIGTERM 到进程: {pid}")
                            killed = True
                        except (ValueError, ProcessLookupError):
                            continue
        except Exception as e:
            click.echo(f"查找进程时出错: {e}")

    return killed


@click.option("--reload", "-r", is_flag=True, help="启用插件自动重载")
@click.option("--port", "-p", help="Dashboard 端口", required=False, type=str)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="强制重启，即使无法清理锁文件也尝试启动",
)
@click.option(
    "--wait-time",
    type=float,
    default=3.0,
    help="等待进程退出的时间（秒）",
)
@click.option(
    "--no-window",
    is_flag=True,
    help="在当前窗口重启（仅 Windows）",
)
@click.command()
def restart(
    reload: bool,
    port: str,
    force: bool,
    wait_time: float,
    no_window: bool,
) -> None:
    """重启 AstrBot（Windows 默认新窗口，Linux/macOS 当前窗口）"""
    try:
        os.environ["ASTRBOT_CLI"] = "1"
        astrbot_root = get_astrbot_root()

        if not check_astrbot_root(astrbot_root):
            raise click.ClickException(
                f"{astrbot_root}不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init",
            )

        os.environ["ASTRBOT_ROOT"] = str(astrbot_root)
        sys.path.insert(0, str(astrbot_root))

        if port:
            os.environ["DASHBOARD_PORT"] = port

        if reload:
            os.environ["ASTRBOT_RELOAD"] = "1"

        lock_file = astrbot_root / "astrbot.lock"

        # 尝试获取锁，如果成功说明没有实例在运行
        lock = FileLock(lock_file, timeout=1)

        try:
            lock.acquire()
            lock.release()
        except Timeout:
            # 锁文件存在，有实例在运行
            click.echo("检测到正在运行的实例，正在停止...")

            # 1. 先尝试通过查找并终止进程
            killed = find_and_kill_astrbot_processes(astrbot_root)

            if killed:
                click.echo(f"等待 {wait_time} 秒以确保进程退出...")
                time.sleep(wait_time)

            # 2. 尝试删除锁文件（可能需要重试）
            max_retries = 5
            for i in range(max_retries):
                try:
                    lock_file.unlink(missing_ok=True)
                    break
                except PermissionError:
                    if i < max_retries - 1:
                        time.sleep(1)
                    else:
                        # 最后一次尝试：使用 FileLock 强制获取
                        try:
                            force_lock = FileLock(lock_file, timeout=1)
                            force_lock.acquire(force=True)
                            force_lock.release()
                            lock_file.unlink(missing_ok=True)
                        except Exception:
                            pass

        # 重新启动
        # Windows: 默认在新窗口启动（除非指定 --no-window）
        # Linux/macOS: 始终在当前窗口运行
        if sys.platform == "win32" and not no_window:
            launch_in_new_window(astrbot_root, reload, port)
            click.echo("[OK] AstrBot 已在新窗口中重启")
            return

        # 在当前窗口运行（Linux/macOS 默认，Windows 指定 --no-window）
        lock = FileLock(lock_file, timeout=5)
        with lock:
            asyncio.run(run_astrbot(astrbot_root))

    except KeyboardInterrupt:
        click.echo("\nAstrBot 已关闭...")
    except Timeout:
        raise click.ClickException(
            "无法获取锁文件，请使用 --force 参数强制重启",
        )
    except Exception as e:
        raise click.ClickException(f"运行时出现错误: {e}")
