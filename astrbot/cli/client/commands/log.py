"""log 命令 - 获取 AstrBot 日志"""

import os
import re

import click

from ..connection import get_data_path, get_logs


@click.command(help="获取 AstrBot 日志")
@click.option(
    "--lines", default=100, type=int, help="返回的日志行数（默认 100，最大 1000）"
)
@click.option(
    "--level", default="", help="按级别过滤 (DEBUG/INFO/WARNING/ERROR/CRITICAL)"
)
@click.option("--pattern", default="", help="按模式过滤（子串匹配）")
@click.option("--regex", is_flag=True, help="使用正则表达式匹配 pattern")
@click.option(
    "--socket",
    "use_socket",
    is_flag=True,
    help="通过 Socket 连接 AstrBot 获取日志（需要 AstrBot 运行）",
)
@click.option(
    "-t", "--timeout", default=30.0, type=float, help="超时时间（仅 Socket 模式）"
)
def log(
    lines: int,
    level: str,
    pattern: str,
    regex: bool,
    use_socket: bool,
    timeout: float,
) -> None:
    """获取 AstrBot 日志

    \b
    示例:
      astr log                        # 直接读取日志文件（默认）
      astr log --lines 50             # 获取最近 50 行
      astr log --level ERROR          # 只显示 ERROR 级别
      astr log --pattern "plugin"      # 匹配包含 "plugin" 的日志
      astr log --pattern "ERRO|WARN" --regex  # 使用正则表达式
      astr log --socket               # 通过 Socket 连接 AstrBot 获取
    """
    if use_socket:
        response = get_logs(None, timeout, lines, level, pattern, regex)
        if response.get("status") == "success":
            formatted = response.get("response", "")
            click.echo(formatted)
        else:
            error = response.get("error", "Unknown error")
            click.echo(f"Error: {error}", err=True)
            raise SystemExit(1)
    else:
        _read_log_from_file(lines, level, pattern, regex)


def _read_log_from_file(lines: int, level: str, pattern: str, use_regex: bool) -> None:
    """直接从日志文件读取

    Args:
        lines: 返回的日志行数
        level: 日志级别过滤
        pattern: 模式过滤
        use_regex: 是否使用正则表达式
    """
    LEVEL_MAP = {
        "DEBUG": "DEBUG",
        "INFO": "INFO",
        "WARNING": "WARN",
        "WARN": "WARN",
        "ERROR": "ERRO",
        "CRITICAL": "CRIT",
    }

    level_filter = LEVEL_MAP.get(level.upper(), level.upper())

    log_path = os.path.join(get_data_path(), "logs", "astrbot.log")

    if not os.path.exists(log_path):
        click.echo(
            f"Error: 日志文件未找到: {log_path}",
            err=True,
        )
        click.echo(
            "提示: 请在配置中启用 log_file_enable 来记录日志到文件，或使用不带 --file 的方式连接 AstrBot",
            err=True,
        )
        raise SystemExit(1)

    try:
        with open(log_path, encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()

        logs = []
        for line in reversed(all_lines):
            if not line.strip():
                continue

            if level_filter:
                if not re.search(rf"\[{level_filter}\]", line):
                    continue

            if pattern:
                if use_regex:
                    try:
                        if not re.search(pattern, line):
                            continue
                    except re.error:
                        if pattern not in line:
                            continue
                else:
                    if pattern not in line:
                        continue

            logs.append(line.rstrip())

            if len(logs) >= lines:
                break

        logs.reverse()

        for log_line in logs:
            click.echo(log_line)

    except OSError as e:
        click.echo(f"Error: 读取日志文件失败: {e}", err=True)
        raise SystemExit(1)
