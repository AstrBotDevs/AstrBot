#!/usr/bin/env python3
"""
AstrBot CLI Client - 跨平台Socket客户端

支持Unix Socket和TCP Socket连接到CLIPlatformAdapter

用法:
    astr "你好"
    astr "/help"
    echo "你好" | astr
"""

# 抑制框架导入时的日志输出（必须在所有导入之前执行）
import logging

# 禁用所有 astrbot 相关日志
logging.getLogger("astrbot").setLevel(logging.CRITICAL + 1)
logging.getLogger("astrbot.core").setLevel(logging.CRITICAL + 1)
# 禁用根日志记录器的控制台输出
root = logging.getLogger()
root.setLevel(logging.CRITICAL + 1)
# 移除可能存在的控制台处理器
for handler in root.handlers[:]:
    if isinstance(handler, logging.StreamHandler):
        root.removeHandler(handler)

import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import socket  # noqa: E402
import sys  # noqa: E402
import uuid  # noqa: E402

import click  # noqa: E402

# 仅使用标准库导入，不导入astrbot框架
# Windows UTF-8 输出支持
if sys.platform == "win32":
    # 设置stdout/stderr为UTF-8编码
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def get_data_path() -> str:
    """获取数据目录路径

    优先级：
    1. 环境变量 ASTRBOT_ROOT
    2. 源码安装目录（通过 __file__ 获取）
    3. 当前工作目录
    """
    # 优先使用环境变量
    if root := os.environ.get("ASTRBOT_ROOT"):
        return os.path.join(root, "data")

    # 获取源码安装目录（__main__.py 在 astrbot/cli/client/）
    # 向上 3 级到达根目录
    source_root = os.path.realpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")
    )
    data_dir = os.path.join(source_root, "data")

    # 如果源码目录下存在 data 目录，使用它
    if os.path.exists(data_dir):
        return data_dir

    # 回退到当前工作目录
    return os.path.join(os.path.realpath(os.getcwd()), "data")


def get_temp_path() -> str:
    """获取临时目录路径,兼容容器和非容器环境"""
    # 优先使用环境变量
    if root := os.environ.get("ASTRBOT_ROOT"):
        return os.path.join(root, "data", "temp")
    # 通过源码目录定位
    source_root = os.path.realpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")
    )
    temp_dir = os.path.join(source_root, "data", "temp")
    if os.path.isdir(os.path.join(source_root, "data")):
        return temp_dir
    # 默认使用系统临时目录
    import tempfile

    return tempfile.gettempdir()


def load_auth_token() -> str:
    """从密钥文件加载认证token

    Returns:
        token字符串,如果文件不存在则返回空字符串
    """
    token_file = os.path.join(get_data_path(), ".cli_token")
    try:
        with open(token_file, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""
    except Exception:
        return ""


def load_connection_info(data_dir: str) -> dict | None:
    """加载连接信息

    从.cli_connection文件读取Socket连接信息

    Args:
        data_dir: 数据目录路径

    Returns:
        连接信息字典，如果文件不存在则返回None

    Example:
        Unix Socket: {"type": "unix", "path": "/tmp/astrbot.sock"}
        TCP Socket: {"type": "tcp", "host": "127.0.0.1", "port": 12345}
    """
    connection_file = os.path.join(data_dir, ".cli_connection")
    try:
        with open(connection_file, encoding="utf-8") as f:
            connection_info = json.load(f)
            return connection_info
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        print(
            f"[ERROR] Invalid JSON in connection file: {connection_file}",
            file=sys.stderr,
        )
        print(f"[ERROR] {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(
            f"[ERROR] Failed to load connection info: {e}",
            file=sys.stderr,
        )
        return None


def connect_to_server(connection_info: dict, timeout: float = 30.0) -> socket.socket:
    """连接到服务器

    根据连接信息类型选择Unix Socket或TCP Socket连接

    Args:
        connection_info: 连接信息字典
        timeout: 超时时间（秒）

    Returns:
        socket连接对象

    Raises:
        ValueError: 无效的连接类型
        ConnectionError: 连接失败
    """
    socket_type = connection_info.get("type")

    if socket_type == "unix":
        # Unix Socket连接
        socket_path = connection_info.get("path")
        if not socket_path:
            raise ValueError("Unix socket path is missing in connection info")

        try:
            client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client_socket.settimeout(timeout)
            client_socket.connect(socket_path)
            return client_socket
        except FileNotFoundError:
            raise ConnectionError(
                f"Socket file not found: {socket_path}. Is AstrBot running?"
            )
        except ConnectionRefusedError:
            raise ConnectionError(
                "Connection refused. Is AstrBot running in socket mode?"
            )
        except Exception as e:
            raise ConnectionError(f"Unix socket connection error: {e}")

    elif socket_type == "tcp":
        # TCP Socket连接
        host = connection_info.get("host")
        port = connection_info.get("port")
        if not host or not port:
            raise ValueError("TCP host or port is missing in connection info")

        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(timeout)
            client_socket.connect((host, port))
            return client_socket
        except ConnectionRefusedError:
            raise ConnectionError(
                f"Connection refused to {host}:{port}. Is AstrBot running?"
            )
        except TimeoutError:
            raise ConnectionError(f"Connection timeout to {host}:{port}")
        except Exception as e:
            raise ConnectionError(f"TCP socket connection error: {e}")

    else:
        raise ValueError(
            f"Invalid socket type: {socket_type}. Expected 'unix' or 'tcp'"
        )


def send_message(
    message: str, socket_path: str | None = None, timeout: float = 30.0
) -> dict:
    """发送消息到AstrBot并获取响应

    支持自动检测连接类型（Unix Socket或TCP Socket）

    Args:
        message: 要发送的消息
        socket_path: Unix socket路径(仅用于向后兼容，优先使用.cli_connection)
        timeout: 超时时间（秒）

    Returns:
        响应字典
    """
    data_dir = get_data_path()

    # 加载认证token
    auth_token = load_auth_token()

    # 创建请求
    request = {"message": message, "request_id": str(uuid.uuid4())}

    # 如果token存在,添加到请求中
    if auth_token:
        request["auth_token"] = auth_token

    # 尝试加载连接信息
    connection_info = load_connection_info(data_dir)

    # 连接到服务器
    try:
        if connection_info is not None:
            # 使用连接信息文件
            client_socket = connect_to_server(connection_info, timeout)
        else:
            # 向后兼容：使用默认Unix Socket路径
            if socket_path is None:
                socket_path = os.path.join(get_temp_path(), "astrbot.sock")

            fallback_info = {"type": "unix", "path": socket_path}
            client_socket = connect_to_server(fallback_info, timeout)

    except (ValueError, ConnectionError) as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Connection error: {e}"}

    try:
        # 发送请求
        request_data = json.dumps(request, ensure_ascii=False).encode("utf-8")
        client_socket.sendall(request_data)

        # 接收响应（循环接收所有数据，支持大响应如base64图片）
        response_data = b""
        while True:
            chunk = client_socket.recv(4096)
            if not chunk:
                break
            response_data += chunk
            # 尝试解析JSON，如果成功说明接收完整
            try:
                response = json.loads(response_data.decode("utf-8", errors="replace"))
                return response
            except json.JSONDecodeError:
                # JSON不完整，继续接收
                continue

        # 如果循环结束仍未成功解析，尝试最后一次
        response = json.loads(response_data.decode("utf-8", errors="replace"))
        return response

    except TimeoutError:
        return {"status": "error", "error": "Request timeout"}
    except Exception as e:
        return {"status": "error", "error": f"Communication error: {e}"}
    finally:
        client_socket.close()


def get_logs(
    socket_path: str | None = None,
    timeout: float = 30.0,
    lines: int = 100,
    level: str = "",
    pattern: str = "",
    use_regex: bool = False,
) -> dict:
    """获取AstrBot日志

    Args:
        socket_path: Socket路径
        timeout: 超时时间
        lines: 返回的日志行数
        level: 日志级别过滤
        pattern: 模式过滤
        use_regex: 是否使用正则表达式

    Returns:
        响应字典
    """
    data_dir = get_data_path()

    # 加载认证token
    auth_token = load_auth_token()

    # 创建请求
    request = {
        "action": "get_logs",
        "request_id": str(uuid.uuid4()),
        "lines": lines,
        "level": level,
        "pattern": pattern,
        "regex": use_regex,
    }

    # 添加token
    if auth_token:
        request["auth_token"] = auth_token

    # 加载连接信息
    connection_info = load_connection_info(data_dir)

    # 连接到服务器
    try:
        if connection_info is not None:
            client_socket = connect_to_server(connection_info, timeout)
        else:
            if socket_path is None:
                socket_path = os.path.join(get_temp_path(), "astrbot.sock")
            fallback_info = {"type": "unix", "path": socket_path}
            client_socket = connect_to_server(fallback_info, timeout)

    except (ValueError, ConnectionError) as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Connection error: {e}"}

    try:
        # 发送请求
        request_data = json.dumps(request, ensure_ascii=False).encode("utf-8")
        client_socket.sendall(request_data)

        # 接收响应
        response_data = b""
        while True:
            chunk = client_socket.recv(4096)
            if not chunk:
                break
            response_data += chunk
            try:
                response = json.loads(response_data.decode("utf-8", errors="replace"))
                return response
            except json.JSONDecodeError:
                continue

        response = json.loads(response_data.decode("utf-8", errors="replace"))
        return response

    except TimeoutError:
        return {"status": "error", "error": "Request timeout"}
    except Exception as e:
        return {"status": "error", "error": f"Communication error: {e}"}
    finally:
        client_socket.close()


def format_response(response: dict) -> str:
    """格式化响应输出

    处理：
    1. 分段回复（每行一句）
    2. 图片占位符

    Args:
        response: 响应字典

    Returns:
        格式化后的字符串
    """
    if response.get("status") != "success":
        return ""

    # 获取文本响应
    text = response.get("response", "")

    # 获取图片数量
    images = response.get("images", [])
    image_count = len(images)

    # 处理分段：按换行符分割，然后每行单独输出
    lines = text.split("\n")

    # 如果有图片，在末尾添加图片占位符
    if image_count > 0:
        if image_count == 1:
            lines.append("[图片]")
        else:
            lines.append(f"[{image_count}张图片]")

    # 用换行符连接所有行
    return "\n".join(lines)


def fix_git_bash_path(message: str) -> str:
    """修复 Git Bash 路径转换问题

    Git Bash (MSYS2) 会把 /plugin ls 转换为 C:/Program Files/Git/plugin ls
    检测并还原原始命令

    Args:
        message: 被转换后的消息

    Returns:
        修复后的消息
    """
    # 检测是否是 Git Bash 转换的路径
    # 模式: <drive>:/Program Files/Git/<command>
    pattern = r"[A-Z]:/(Program Files/Git|msys[0-9]+/[^/]+)/([^/]+)"
    match = re.match(pattern, message)

    if match:
        # 提取原始命令
        command = match.group(2)
        # 获取剩余部分
        rest = message[match.end() :].lstrip()
        if rest:
            return f"/{command} {rest}"
        return f"/{command}"

    return message


EPILOG = """使用示例:
  发送消息:
    astr 你好                       发送消息给 AstrBot
    astr send 你好                  同上（显式子命令）
    astr send /help                 查看内置命令帮助
    echo "你好" | astr              从标准输入读取

  获取日志:
    astr log                        获取最近 100 行日志（直接读取文件）
    astr --log                      同上（兼容旧用法）
    astr log --lines 50             获取最近 50 行
    astr log --level ERROR          只显示 ERROR 级别
    astr log --pattern "CLI"        只显示包含 "CLI" 的日志
    astr log --pattern "ERRO|WARN" --regex  使用正则表达式匹配
    astr log --socket               通过 Socket 连接 AstrBot 获取

  高级选项:
    astr -j "测试"                  输出原始 JSON 响应
    astr -t 60 "长时间任务"         设置超时时间为 60 秒

连接说明:
  自动从 data/.cli_connection 检测连接类型（Unix Socket 或 TCP）
  Token 自动从 data/.cli_token 读取
  需在 AstrBot 根目录下运行，或设置 ASTRBOT_ROOT 环境变量
"""


class RawEpilogGroup(click.Group):
    """保留 epilog 原始格式的 Group，同时支持默认子命令路由"""

    def format_epilog(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        if self.epilog:
            formatter.write("\n")
            for line in self.epilog.split("\n"):
                formatter.write(line + "\n")

    # send 子命令的 option 前缀，用于识别 astr -j "你好" 等旧用法
    _send_opts = {"-j", "--json", "-t", "--timeout", "-s", "--socket"}
    # --log 旧用法映射到 log 子命令
    _log_flag = {"--log"}

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if args:
            first = args[0]
            if first in self._log_flag:
                # astr --log ... → astr log ...
                args = ["log"] + args[1:]
            elif first not in self.commands:
                if not first.startswith("-") or first in self._send_opts:
                    # astr 你好 / astr -j "你好" → astr send ...
                    args = ["send"] + args
        return super().parse_args(ctx, args)


@click.group(
    cls=RawEpilogGroup,
    invoke_without_command=True,
    epilog=EPILOG,
)
@click.pass_context
def main(ctx: click.Context) -> None:
    """AstrBot CLI Client"""
    if ctx.invoked_subcommand is None:
        # 无子命令时，检查 stdin 是否有管道输入
        if not sys.stdin.isatty():
            message = sys.stdin.read().strip()
            if message:
                _do_send(message, None, 30.0, False)
                return
        click.echo(ctx.get_help())


@main.command(help="发送消息给 AstrBot")
@click.argument("message", nargs=-1)
@click.option("-s", "--socket", "socket_path", default=None, help="Unix socket 路径")
@click.option("-t", "--timeout", default=30.0, type=float, help="超时时间（秒）")
@click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON 响应")
def send(
    message: tuple[str, ...], socket_path: str | None, timeout: float, use_json: bool
) -> None:
    """发送消息给 AstrBot

    \b
    示例:
      astr send 你好
      astr send /help
      astr send plugin ls
      echo "你好" | astr send
    """
    if message:
        msg = " ".join(message)
        msg = fix_git_bash_path(msg)
    elif not sys.stdin.isatty():
        msg = sys.stdin.read().strip()
    else:
        click.echo("Error: 请提供消息内容", err=True)
        raise SystemExit(1)

    if not msg:
        click.echo("Error: 消息内容为空", err=True)
        raise SystemExit(1)

    _do_send(msg, socket_path, timeout, use_json)


def _do_send(msg: str, socket_path: str | None, timeout: float, use_json: bool) -> None:
    """执行消息发送并输出结果"""
    response = send_message(msg, socket_path, timeout)
    _output_response(response, use_json)


@main.command(help="获取 AstrBot 日志")
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
        # 通过 Socket 获取日志
        response = get_logs(None, timeout, lines, level, pattern, regex)
        # 输出响应（复用 _output_response，但不需要 use_json 参数）
        if response.get("status") == "success":
            formatted = response.get("response", "")
            click.echo(formatted)
        else:
            error = response.get("error", "Unknown error")
            click.echo(f"Error: {error}", err=True)
            raise SystemExit(1)
    else:
        # 直接读取日志文件（默认）
        _read_log_from_file(lines, level, pattern, regex)


def _output_response(response: dict, use_json: bool) -> None:
    """统一输出响应"""
    if use_json:
        click.echo(json.dumps(response, ensure_ascii=False, indent=2))
    else:
        if response.get("status") == "success":
            formatted = format_response(response)
            click.echo(formatted)
        else:
            error = response.get("error", "Unknown error")
            click.echo(f"Error: {error}", err=True)
            raise SystemExit(1)


def _read_log_from_file(lines: int, level: str, pattern: str, use_regex: bool) -> None:
    """直接从日志文件读取

    Args:
        lines: 返回的日志行数
        level: 日志级别过滤
        pattern: 模式过滤
        use_regex: 是否使用正则表达式
    """
    import re

    # 日志级别映射
    LEVEL_MAP = {
        "DEBUG": "DEBUG",
        "INFO": "INFO",
        "WARNING": "WARN",
        "WARN": "WARN",
        "ERROR": "ERRO",
        "CRITICAL": "CRIT",
    }

    # 映射级别
    level_filter = LEVEL_MAP.get(level.upper(), level.upper())

    # 日志文件路径
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

        # 从末尾开始筛选
        logs = []
        for line in reversed(all_lines):
            # 跳过空行
            if not line.strip():
                continue

            # 级别过滤
            if level_filter:
                if not re.search(rf"\[{level_filter}\]", line):
                    continue

            # 模式过滤
            if pattern:
                if use_regex:
                    try:
                        if not re.search(pattern, line):
                            continue
                    except re.error:
                        # 正则表达式错误，回退到子串匹配
                        if pattern not in line:
                            continue
                else:
                    if pattern not in line:
                        continue

            logs.append(line.rstrip())

            if len(logs) >= lines:
                break

        # 反转回来（使时间顺序正确）
        logs.reverse()

        # 输出
        for log_line in logs:
            click.echo(log_line)

    except OSError as e:
        click.echo(f"Error: 读取日志文件失败: {e}", err=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
