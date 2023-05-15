import datetime
import socket

FG_COLORS = {
    "black": "30",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "purple": "35",
    "cyan": "36",
    "white": "37",
    "default": "39",
}

BG_COLORS = {
    "black": "40",
    "red": "41",
    "green": "42",
    "yellow": "43",
    "blue": "44",
    "purple": "45",
    "cyan": "46",
    "white": "47",
    "default": "49",
}

LEVEL_INFO = "INFO"
LEVEL_WARNING = "WARNING"
LEVEL_ERROR = "ERROR"
LEVEL_CRITICAL = "CRITICAL"

level_colors = {
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "purple",
}

def log(
        msg: str,
        level: str = "INFO",
        tag: str = "System",
        fg: str = None,
        bg: str = None,
        max_len: int = 100):
    """
    日志记录函数
    """
    if len(msg) > max_len:
        msg = msg[:max_len] + "..."
    now = datetime.datetime.now().strftime("%m-%d %H:%M:%S")
    pre = f"[{now}] [{level}] [{tag}]: {msg}"
    if level == "INFO":
        if fg is None:
            fg = FG_COLORS["green"]
        if bg is None:
            bg = BG_COLORS["default"]
    elif level == "WARNING":
        if fg is None:
            fg = FG_COLORS["yellow"]
        if bg is None:
            bg = BG_COLORS["default"]
    elif level == "ERROR":
        if fg is None:
            fg = FG_COLORS["red"]
        if bg is None:
            bg = BG_COLORS["default"]
    elif level == "CRITICAL":
        if fg is None:
            fg = FG_COLORS["purple"]
        if bg is None:
            bg = BG_COLORS["default"]
    
    print(f"\033[{fg};{bg}m{pre}\033[0m")


def port_checker(port: int, host: str = "localhost"):
    sk = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    sk.settimeout(1)
    try:
        sk.connect((host, port))
        sk.close()
        return True
    except Exception:
        sk.close()
        return False
