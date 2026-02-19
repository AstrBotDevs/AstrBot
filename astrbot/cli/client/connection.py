"""连接管理模块 - 路径/token/socket/发送

从 __main__.py 提取的连接相关功能，不导入 astrbot 框架。
"""

import json
import os
import socket
import sys
import uuid


def get_data_path() -> str:
    """获取数据目录路径

    优先级：
    1. 环境变量 ASTRBOT_ROOT
    2. 源码安装目录（通过 __file__ 获取）
    3. 当前工作目录
    """
    if root := os.environ.get("ASTRBOT_ROOT"):
        return os.path.join(root, "data")

    source_root = os.path.realpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")
    )
    data_dir = os.path.join(source_root, "data")

    if os.path.exists(data_dir):
        return data_dir

    return os.path.join(os.path.realpath(os.getcwd()), "data")


def get_temp_path() -> str:
    """获取临时目录路径,兼容容器和非容器环境"""
    if root := os.environ.get("ASTRBOT_ROOT"):
        return os.path.join(root, "data", "temp")

    source_root = os.path.realpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")
    )
    temp_dir = os.path.join(source_root, "data", "temp")
    if os.path.isdir(os.path.join(source_root, "data")):
        return temp_dir

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
    """
    connection_file = os.path.join(data_dir, ".cli_connection")
    try:
        with open(connection_file, encoding="utf-8") as f:
            return json.load(f)
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


def _receive_json_response(client_socket: socket.socket) -> dict:
    """从 socket 接收并解析 JSON 响应

    Args:
        client_socket: socket连接对象

    Returns:
        解析后的响应字典
    """
    response_data = b""
    while True:
        chunk = client_socket.recv(4096)
        if not chunk:
            break
        response_data += chunk
        try:
            return json.loads(response_data.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue

    return json.loads(response_data.decode("utf-8", errors="replace"))


def _get_connected_socket(
    socket_path: str | None = None, timeout: float = 30.0
) -> socket.socket:
    """获取已连接的 socket

    Args:
        socket_path: Unix socket路径(向后兼容)
        timeout: 超时时间（秒）

    Returns:
        已连接的 socket 对象

    Raises:
        ValueError, ConnectionError: 连接失败时
    """
    data_dir = get_data_path()
    connection_info = load_connection_info(data_dir)

    if connection_info is not None:
        return connect_to_server(connection_info, timeout)

    if socket_path is None:
        socket_path = os.path.join(get_temp_path(), "astrbot.sock")

    fallback_info = {"type": "unix", "path": socket_path}
    return connect_to_server(fallback_info, timeout)


def send_message(
    message: str, socket_path: str | None = None, timeout: float = 30.0
) -> dict:
    """发送消息到AstrBot并获取响应

    Args:
        message: 要发送的消息
        socket_path: Unix socket路径(仅用于向后兼容)
        timeout: 超时时间（秒）

    Returns:
        响应字典
    """
    auth_token = load_auth_token()

    request = {"message": message, "request_id": str(uuid.uuid4())}
    if auth_token:
        request["auth_token"] = auth_token

    try:
        client_socket = _get_connected_socket(socket_path, timeout)
    except (ValueError, ConnectionError) as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Connection error: {e}"}

    try:
        request_data = json.dumps(request, ensure_ascii=False).encode("utf-8")
        client_socket.sendall(request_data)
        return _receive_json_response(client_socket)
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
    auth_token = load_auth_token()

    request = {
        "action": "get_logs",
        "request_id": str(uuid.uuid4()),
        "lines": lines,
        "level": level,
        "pattern": pattern,
        "regex": use_regex,
    }
    if auth_token:
        request["auth_token"] = auth_token

    try:
        client_socket = _get_connected_socket(socket_path, timeout)
    except (ValueError, ConnectionError) as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Connection error: {e}"}

    try:
        request_data = json.dumps(request, ensure_ascii=False).encode("utf-8")
        client_socket.sendall(request_data)
        return _receive_json_response(client_socket)
    except TimeoutError:
        return {"status": "error", "error": "Request timeout"}
    except Exception as e:
        return {"status": "error", "error": f"Communication error: {e}"}
    finally:
        client_socket.close()


def _send_action_request(
    action: str,
    extra_fields: dict | None = None,
    socket_path: str | None = None,
    timeout: float = 30.0,
) -> dict:
    """发送 action 请求的通用方法"""
    auth_token = load_auth_token()

    request: dict = {"action": action, "request_id": str(uuid.uuid4())}
    if auth_token:
        request["auth_token"] = auth_token
    if extra_fields:
        request.update(extra_fields)

    try:
        client_socket = _get_connected_socket(socket_path, timeout)
    except (ValueError, ConnectionError) as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Connection error: {e}"}

    try:
        request_data = json.dumps(request, ensure_ascii=False).encode("utf-8")
        client_socket.sendall(request_data)
        return _receive_json_response(client_socket)
    except TimeoutError:
        return {"status": "error", "error": "Request timeout"}
    except Exception as e:
        return {"status": "error", "error": f"Communication error: {e}"}
    finally:
        client_socket.close()


def list_tools(socket_path: str | None = None, timeout: float = 30.0) -> dict:
    """列出所有注册的函数工具"""
    return _send_action_request("list_tools", socket_path=socket_path, timeout=timeout)


def call_tool(
    tool_name: str,
    tool_args: dict | None = None,
    socket_path: str | None = None,
    timeout: float = 60.0,
) -> dict:
    """调用指定的函数工具"""
    return _send_action_request(
        "call_tool",
        extra_fields={"tool_name": tool_name, "tool_args": tool_args or {}},
        socket_path=socket_path,
        timeout=timeout,
    )
