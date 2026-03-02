import os
import signal
import subprocess
import sys
import time

import click

from ..utils import check_astrbot_root, get_astrbot_root


def find_and_kill_astrbot_processes(astrbot_root: str) -> bool:
    """查找并终止正在运行的 AstrBot 进程

    Returns:
        bool: 是否成功终止了进程
    """
    killed = False
    current_pid = os.getpid()

    if sys.platform == "win32":
        # Windows: 使用 wmic 获取进程命令行，精确匹配 AstrBot 进程
        try:
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

                        if pid == current_pid:
                            continue

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
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            for line in result.stdout.split("\n"):
                if line.startswith("USER"):
                    continue

                if "python" in line.lower() and "astrbot" in line.lower():
                    parts = line.split(None, 10)
                    if len(parts) >= 2:
                        try:
                            pid = int(parts[1])

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


@click.option(
    "--wait-time",
    type=float,
    default=3.0,
    help="等待进程退出的时间（秒）",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="强制终止，删除锁文件",
)
@click.command()
def stop(wait_time: float, force: bool) -> None:
    """停止 AstrBot 进程"""
    try:
        os.environ["ASTRBOT_CLI"] = "1"
        astrbot_root = get_astrbot_root()

        if not check_astrbot_root(astrbot_root):
            raise click.ClickException(
                f"{astrbot_root}不是有效的 AstrBot 根目录",
            )

        # 查找并终止进程
        killed = find_and_kill_astrbot_processes(astrbot_root)

        if killed:
            click.echo(f"等待 {wait_time} 秒以确保进程退出...")
            time.sleep(wait_time)

            # 删除锁文件
            if force:
                lock_file = astrbot_root / "astrbot.lock"
                try:
                    lock_file.unlink(missing_ok=True)
                    click.echo("已删除锁文件")
                except Exception as e:
                    click.echo(f"删除锁文件失败: {e}")

            click.echo("[OK] AstrBot 已停止")
        else:
            click.echo("未找到正在运行的 AstrBot 进程")

    except Exception as e:
        raise click.ClickException(f"停止时出现错误: {e}")
