"""Human-readable quota results for the direct chat command."""

from datetime import datetime, timedelta, timezone

_BEIJING = timezone(timedelta(hours=8))
_STATUS = {
    "not_admin": "仅管理员可以查询 Codex 额度。",
    "group_not_allowed": "此群聊未加入 Codex 额度查询白名单。",
    "disabled": "额度查询已关闭。",
    "closed": "查询服务已关闭。",
    "provider_not_found": "配置的 OAuth 提供商不存在，请检查额度查询设置。",
    "not_oauth_provider": "请在额度查询设置中指定 Codex OAuth 提供商。",
    "authorization_changed": "查询账号配置已变更，请重新查询。",
    "unbound": "OAuth 凭据不完整。",
    "reauth_required": "当前 OAuth 凭据不可用，请检查授权或刷新状态。",
    "forbidden": "账号没有额度查询权限。",
    "rate_limited": "额度查询被限流，请稍后重试。",
    "unavailable": "额度查询暂时不可用。",
    "unparseable": "额度响应无法解析。",
    "unsupported_endpoint": "仅支持官方 Codex 额度接口。",
}


def _timestamp(value):
    try:
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return "未知"
        else:
            parsed = datetime.fromtimestamp(value, timezone.utc)
        return parsed.astimezone(_BEIJING).strftime("%Y-%m-%d %H:%M:%S") + " 北京时间"
    except (TypeError, ValueError, OverflowError, OSError):
        return "未知"


def _duration(seconds):
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return "未知周期"
    for size, unit in ((86400, "天"), (3600, "小时"), (60, "分钟")):
        if seconds % size == 0:
            return f"{seconds / size:g} {unit}"
    return f"{seconds:g} 秒"


def format_usage(data):
    status = data.get("status")
    if status != "success":
        return "Codex 额度：" + _STATUS.get(status, "查询暂时不可用。")
    lines = ["Codex 额度", "套餐：" + (data.get("plan_type") or "未知")]
    for window in data.get("windows", []):
        name = window.get("name") or window.get("limit_id") or "Codex"
        lines.append(f"{name} · {_duration(window.get('window_seconds'))}窗口")
        used = window.get("used_percent")
        remaining = window.get("remaining_percent")
        used_text = f"{used:g}%" if used is not None else "未知"
        remaining_text = f"{remaining:g}%" if remaining is not None else "未知"
        lines.append(f"已用 {used_text}，剩余 {remaining_text}")
        lines.append("重置时间：" + _timestamp(window.get("reset_at")))
    if not data.get("windows"):
        lines.append("上游未返回可用的额度窗口。")
    lines.append("采集时间：" + _timestamp(data.get("observed_at")))
    if data.get("cached"):
        lines.append("数据来自 60 秒内缓存。")
    return "\n".join(lines)
