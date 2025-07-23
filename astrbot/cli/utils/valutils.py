import hashlib
import zoneinfo
import click

def validate_log_level(value: str) -> str:
    """验证日志级别"""
    value = value.upper()
    if value not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        raise click.ClickException(
            "日志级别必须是 DEBUG/INFO/WARNING/ERROR/CRITICAL 之一"
        )
    return value

def validate_dashboard_port(value: str) -> int:
    """验证 Dashboard 端口"""
    try:
        port = int(value)
        if port < 1 or port > 65535:
            raise click.ClickException("端口必须在 1-65535 范围内")
        return port
    except ValueError:
        raise click.ClickException("端口必须是数字")

def validate_dashboard_username(value: str) -> str:
    """验证 Dashboard 用户名"""
    if not value:
        raise click.ClickException("用户名不能为空")
    return value

def validate_dashboard_password(value: str) -> str:
    """验证 Dashboard 密码"""
    if not value:
        raise click.ClickException("密码不能为空")
    return hashlib.md5(value.encode()).hexdigest()

def validate_timezone(value: str) -> str:
    """验证时区"""
    try:
        zoneinfo.ZoneInfo(value)
    except Exception:
        raise click.ClickException(f"无效的时区: {value}，请使用有效的IANA时区名称")
    return value

def validate_callback_api_base(value: str) -> str:
    """验证回调接口基址"""
    if not value.startswith("http://") and not value.startswith("https://"):
        raise click.ClickException("回调接口基址必须以 http:// 或 https:// 开头")
    return value
