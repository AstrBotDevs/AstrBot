import uuid

from astrbot.core import astrbot_config, logger
from astrbot.core.config.default import WEBHOOK_SUPPORTED_PLATFORMS


def _get_callback_api_base() -> str:
    try:
        return astrbot_config.get("callback_api_base", "").rstrip("/")
    except Exception as e:
        logger.error(f"获取 callback_api_base 失败: {e!s}")
        return ""


def _get_dashboard_port() -> int:
    try:
        return astrbot_config.get("dashboard", {}).get("port", 6185)
    except Exception as e:
        logger.error(f"获取 dashboard 端口失败: {e!s}")
        return 6185


def log_webhook_info(platform_name: str, webhook_uuid: str):
    """打印美观的 webhook 信息日志

    Args:
        platform_name: 平台名称
        webhook_uuid: webhook 的 UUID
    """

    callback_base = _get_callback_api_base()

    if not callback_base:
        callback_base = "http(s)://<your-astrbot-domain>"

    if not callback_base.startswith("http"):
        callback_base = f"http(s)://{callback_base}"

    callback_base = callback_base.rstrip("/")
    webhook_url = f"{callback_base}/api/platform/webhook/{webhook_uuid}"

    display_log = (
        "\n====================\n"
        f"🔗 机器人平台 {platform_name} 已启用统一 Webhook 模式\n"
        f"📍 Webhook 回调地址: \n"
        f"   ➜  http://<your-ip>:{_get_dashboard_port()}/api/platform/webhook/{webhook_uuid}\n"
        f"   ➜  {webhook_url}\n"
        "====================\n"
    )
    logger.info(display_log)


def ensure_platform_webhook_config(platform_cfg: dict) -> bool:
    """为支持统一 webhook 的平台自动生成 webhook_uuid

    Args:
        platform_cfg (dict): 平台配置字典

    Returns:
        bool: 如果生成了 webhook_uuid 则返回 True，否则返回 False
    """
    pt = platform_cfg.get("type", "")
    if pt in WEBHOOK_SUPPORTED_PLATFORMS and not platform_cfg.get("webhook_uuid"):
        platform_cfg["webhook_uuid"] = uuid.uuid4().hex[:16]
        return True
    return False
