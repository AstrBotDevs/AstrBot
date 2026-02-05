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

import argparse  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import socket  # noqa: E402
import sys  # noqa: E402
import uuid  # noqa: E402

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
    # 默认使用系统临时目录
    return "/tmp"


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
) -> dict:
    """获取AstrBot日志

    Args:
        socket_path: Socket路径
        timeout: 超时时间
        lines: 返回的日志行数
        level: 日志级别过滤
        pattern: 模式过滤

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
        rest = message[match.end():].lstrip()
        if rest:
            return f"/{command} {rest}"
        return f"/{command}"

    return message


def main() -> None:
    """主函数"""
    parser = argparse.ArgumentParser(
        description="AstrBot CLI Client - 与 CLI Platform 通信的客户端工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:

  发送消息:
    astr 你好                     # 发送消息给 AstrBot
    astr help                     # 查看内置命令帮助
    echo "你好" | astr             # 从标准输入读取

  获取日志:
    astr --log                     # 获取最近 100 行日志
    astr --log --lines 50          # 获取最近 50 行
    astr --log --level ERROR       # 只显示 ERROR 级别
    astr --log --pattern "CLI"     # 只显示包含 "CLI" 的日志
    astr --log --json              # 以 JSON 格式输出日志

  内置命令:
    astr help                      # 查看所有命令
    astr plugin ls                 # 列出已安装插件
    astr plugin on <name>          # 启用插件
    astr new                       # 创建新对话
    astr /自定义消息               # 带 / 的消息发给 LLM 处理

  高级选项:
    astr -j "测试"                 # 输出原始 JSON 响应
    astr -t 60 "长时间任务"        # 设置超时时间为 60 秒

连接说明:
  - 自动从 data/.cli_connection 文件检测连接类型（Unix Socket 或 TCP）
  - Token 自动从 data/.cli_token 文件读取
  - 必须在 AstrBot 根目录下运行，或设置 ASTRBOT_ROOT 环境变量

输出说明:
  - 默认模式下，图片以 [图片] 占位符显示，不返回实际图片内容
  - 分段回复会自动分行显示
  - 如需完整信息（包括图片 URL/base64），请使用 -j 参数输出 JSON
  - 如需查看详细日志，请使用 --log 参数
        """,
    )

    parser.add_argument(
        "message",
        nargs=argparse.REMAINDER,
        help="Message to send (if not provided, read from stdin)",
    )

    parser.add_argument(
        "-s",
        "--socket",
        default=None,
        help="Unix socket path (default: {temp_dir}/astrbot.sock)",
    )

    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=30.0,
        help="Timeout in seconds (default: 30.0)",
    )

    parser.add_argument(
        "-j", "--json", action="store_true", help="Output raw JSON response"
    )

    parser.add_argument(
        "--log",
        action="store_true",
        help="Get recent console logs (instead of sending a message)",
    )

    parser.add_argument(
        "--lines",
        type=int,
        default=100,
        help="Number of log lines to return (default: 100, max: 1000)",
    )

    parser.add_argument(
        "--level",
        default="",
        help="Filter logs by level (DEBUG/INFO/WARNING/ERROR/CRITICAL)",
    )

    parser.add_argument(
        "--pattern",
        default="",
        help="Filter logs by pattern (substring match)",
    )

    args = parser.parse_args()

    # 处理日志请求
    if args.log:
        response = get_logs(
            args.socket, args.timeout, args.lines, args.level, args.pattern
        )
    else:
        # 处理消息发送
        # 获取消息内容
        if args.message:
            # REMAINDER 模式下 args.message 是列表，用空格连接
            message = " ".join(args.message)
            # 修复 Git Bash 路径转换问题
            message = fix_git_bash_path(message)
        elif not sys.stdin.isatty():
            # 从stdin读取
            message = sys.stdin.read().strip()
        else:
            parser.print_help()
            sys.exit(1)

        if not message:
            print("Error: Empty message", file=sys.stderr)
            sys.exit(1)

        response = send_message(message, args.socket, args.timeout)

    # 输出响应
    if args.json:
        # 输出原始JSON
        print(json.dumps(response, ensure_ascii=False, indent=2))
    else:
        # 格式化输出
        if response.get("status") == "success":
            # 使用格式化函数处理响应
            formatted = format_response(response)
            print(formatted)
        else:
            error = response.get("error", "Unknown error")
            print(f"Error: {error}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
