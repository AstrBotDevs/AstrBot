"""Localized Core replies, selected by the session's configuration profile."""

from collections.abc import Mapping
from typing import Any

CORE_MESSAGES = {
    "zh-CN": {
        "tool_call": "🔨 调用工具: {name}",
        "tool_call_pending": "🔨 调用工具...",
        "tool_result": "📎 返回结果: {result}",
        "llm_response_error": "LLM 响应错误: {detail}",
        "unknown_error": "未知错误",
        "reasoning": "🤔 思考: {content}\n\n────\n",
        "permission_denied": "您(ID: {sender_id})的权限不足以使用此指令。通过 /sid 获取 ID 并请管理员添加。",
        "plugin_filter_error": "插件 {plugin}: {detail}",
        "plugin_handler_error": ":(\n\n在调用插件 {plugin} 的处理函数 {handler} 时出现异常：{detail}",
        "greedy_param_not_last": "参数 '{name}' (GreedyStr) 必须是最后一个参数。",
        "missing_required_param": "必要参数缺失。该指令完整参数: {params}",
        "invalid_boolean_param": "参数 {name} 必须是布尔值（true/false, yes/no, 1/0）。",
        "invalid_param_type": "参数 {name} 类型错误。完整参数: {params}",
        "command_no_params": "无参数指令",
        "command_group_help": "参数不足。{group} 指令组下有如下指令，请参考：\n{tree}",
        "tool_approval_task_title": "定时任务「{name}」请求批准",
        "tool_approval_task_title_unnamed": "定时任务请求批准",
        "tool_approval_task_notice": "批准后，任务到点会自动执行，审批名单内的工具不再逐项询问。\n",
        "tool_approval_tool_title": "工具 {tool} 请求执行",
        "tool_approval_how_to": "点击按钮或回复 {code} 批准，发送其他内容则取消（{timeout} 秒内有效）",
        "tool_approval_args": "参数：",
        "tool_approval_args_cut": "\n……（参数共 {total} 字符，后面 {hidden} 字符未显示；看不到全部内容时请拒绝）",
        "tool_approval_allow": "允许",
        "tool_approval_allow_conversation": "本对话不再询问",
        "tool_approval_deny": "拒绝",
    },
    "en-US": {
        "tool_call": "🔨 Calling tool: {name}",
        "tool_call_pending": "🔨 Calling tool...",
        "tool_result": "📎 Result: {result}",
        "llm_response_error": "LLM response error: {detail}",
        "unknown_error": "Unknown error",
        "reasoning": "🤔 Thinking: {content}\n\n────\n",
        "permission_denied": "You (ID: {sender_id}) do not have permission to use this command. Use /sid to get your ID and ask an administrator to grant access.",
        "plugin_filter_error": "Plugin {plugin}: {detail}",
        "plugin_handler_error": ":(\n\nAn error occurred in handler {handler} of plugin {plugin}: {detail}",
        "greedy_param_not_last": "Parameter '{name}' (GreedyStr) must be the last parameter.",
        "missing_required_param": "Missing required parameter. Full command parameters: {params}",
        "invalid_boolean_param": "Parameter {name} must be a boolean (true/false, yes/no, 1/0).",
        "invalid_param_type": "Invalid type for parameter {name}. Full parameters: {params}",
        "command_no_params": "No parameters",
        "command_group_help": "Missing parameters. Available commands in group {group}:\n{tree}",
        "tool_approval_task_title": 'Scheduled task "{name}" needs approval',
        "tool_approval_task_title_unnamed": "Scheduled task needs approval",
        "tool_approval_task_notice": "If approved, the task runs on schedule and approval-listed tools are not asked about again.\n",
        "tool_approval_tool_title": "Tool {tool} wants to run",
        "tool_approval_how_to": "Click a button or reply {code} to approve; anything else cancels (valid for {timeout} s)",
        "tool_approval_args": "Arguments: ",
        "tool_approval_args_cut": "\n... ({hidden} of {total} characters not shown; deny if you cannot see everything you are approving)",
        "tool_approval_allow": "Allow",
        "tool_approval_allow_conversation": "Don't ask again in this conversation",
        "tool_approval_deny": "Deny",
    },
}


def get_config_locale(config: Mapping[str, Any]) -> str:
    """Read the bot reply language from an effective configuration.

    Args:
        config: Default or UMO-resolved configuration profile.

    Returns:
        A supported locale, defaulting to Chinese for missing or invalid values.
    """
    locale = config.get("platform_settings", {}).get("locale", "zh-CN")
    return locale if isinstance(locale, str) and locale in CORE_MESSAGES else "zh-CN"


def translate(key: str, locale: str = "zh-CN", **params: Any) -> str:
    """Format a built-in reply in the requested language.

    Args:
        key: Core message key.
        locale: Bot reply locale; unsupported locales fall back to Chinese.
        **params: Values interpolated into the translated message.

    Returns:
        The formatted reply.

    Raises:
        KeyError: The message key or a required interpolation parameter is missing.
    """
    return CORE_MESSAGES.get(locale, CORE_MESSAGES["zh-CN"])[key].format(**params)
