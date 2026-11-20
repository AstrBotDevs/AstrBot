"""Runtime translations owned by the built-in commands plugin."""

MESSAGES = {
    "zh-CN": {
        "no_commands": "没有已启用的内置指令。",
        "name_usage": "用法: /name <名称>\nUMO: {umo}\n自动名称: {auto_name}\n别名: {alias}",
        "empty": "（空）",
        "name_set": "UMO 名称已设置为: {alias}\nUMO: {umo}",
        "sid": "UMO: 「{umo}」\nUID: 「{uid}」\n*UMO 可用于设置白名单和配置文件路由，UID 可用于设置管理员列表。\n\n会话信息:\n机器人 ID: 「{platform}」\n消息类型: 「{message_type}」\n会话 ID: 「{session_id}」\n\n",
        "group_id": "\n\n群组 ID: 「{group_id}」。将此 ID 加入白名单可允许整个群组。",
        "dashboard_updating": "⏳ 正在更新管理面板...",
        "dashboard_updated": "✅ 管理面板更新成功。",
        "variable_set": "会话 {umo} 变量 {name} 存储成功。使用 /unset 移除。",
        "variable_missing": "没有那个变量名。格式 /unset 变量名。",
        "variable_unset": "会话 {umo} 变量 {name} 移除成功。",
        "reset": "✅ 当前对话上下文已清空。",
        "stopping": "✅ 已请求停止 {count} 个运行中的任务。",
        "no_tasks": "✅ 当前会话没有运行中的任务。",
        "new_conversation": "✅ 已切换到新对话: {cid}。",
        "no_conversation": "❌ 当前没有对话。请使用 /new 创建。",
        "no_stats": "📊 当前对话暂无统计数据。",
        "stats": "📊 对话 Token 用量（ID: {cid}...）\n总计: {total:,}\n输入（缓存）: {cached:,}\n输入（其他）: {other:,}\n输出: {output:,}\n",
        "provider_testing": "👀 正在测试提供商连通性...",
        "provider_llm": "## 对话模型提供商\n",
        "provider_tts": "\n## 语音合成提供商\n",
        "provider_stt": "\n## 语音识别提供商\n",
        "provider_switch_llm": "\n使用 /provider <序号> 切换对话模型提供商。",
        "provider_switch_tts": "\n使用 /provider tts <序号> 切换语音合成提供商。",
        "provider_switch_stt": "\n使用 /provider stt <序号> 切换语音识别提供商。",
        "provider_inherit": "已恢复使用配置文件中的模型。",
        "provider_index_required": "请输入序号。",
        "provider_index_invalid": "❌ 无效的提供商序号。",
        "provider_switched": "✅ 已成功切换到 {id}。",
        "provider_invalid": "❌ 无效的参数。",
        "command.help": "显示帮助信息",
        "command.sid": "获取会话 ID 及相关信息",
        "command.name": "设置当前 UMO 的显示名称",
        "command.reset": "清空当前对话的上下文",
        "command.stop": "停止 Agent 执行",
        "command.new_conv": "创建新对话",
        "command.stats": "显示当前对话的 Token 用量统计",
        "command.provider": "查看或切换模型提供商",
        "command.update_dashboard": "更新 AstrBot 管理面板",
        "command.set_variable": "设置会话变量",
        "command.unset_variable": "移除会话变量",
    },
    "en-US": {
        "no_commands": "No enabled built-in commands.",
        "name_usage": "Usage: /name <name>\nUMO: {umo}\nAuto name: {auto_name}\nAlias: {alias}",
        "empty": "(empty)",
        "name_set": "UMO name set to: {alias}\nUMO: {umo}",
        "sid": "UMO: 「{umo}」\nUID: 「{uid}」\n*Use UMO to set the whitelist and configuration profile routing; use UID to set the administrator list.\n\nYour session information:\nBot ID: 「{platform}」\nMessage Type: 「{message_type}」\nSession ID: 「{session_id}」\n\n",
        "group_id": "\n\nThe group's ID: 「{group_id}」. Set this ID to whitelist to allow the entire group.",
        "dashboard_updating": "⏳ Updating dashboard...",
        "dashboard_updated": "✅ Dashboard updated successfully.",
        "variable_set": "Variable {name} saved for session {umo}. Use /unset to remove it.",
        "variable_missing": "Variable not found. Usage: /unset <name>.",
        "variable_unset": "Variable {name} removed from session {umo}.",
        "reset": "✅ The current conversation context has been cleared.",
        "stopping": "✅ Requested to stop {count} running tasks.",
        "no_tasks": "✅ No running tasks in the current session.",
        "new_conversation": "✅ Switched to new conversation: {cid}.",
        "no_conversation": "❌ You are not in a conversation. Use /new to create one.",
        "no_stats": "📊 No stats available for this conversation yet.",
        "stats": "📊 Conversation Token usage (ID: {cid}...)\nTotal:          {total:,}\nInput (cached): {cached:,}\nInput (other):  {other:,}\nOutput:         {output:,}\n",
        "provider_testing": "👀 Testing provider reachability...",
        "provider_llm": "## LLM Providers\n",
        "provider_tts": "\n## TTS Providers\n",
        "provider_stt": "\n## STT Providers\n",
        "provider_switch_llm": "\nUse /provider <idx> to switch LLM providers.",
        "provider_switch_tts": "\nUse /provider tts <idx> to switch TTS providers.",
        "provider_switch_stt": "\nUse /provider stt <idx> to switch STT providers.",
        "provider_inherit": "Following profile models.",
        "provider_index_required": "Please enter the index.",
        "provider_index_invalid": "❌ Invalid provider index.",
        "provider_switched": "✅ Successfully switched to {id}.",
        "provider_invalid": "❌ Invalid parameter.",
        "command.help": "Show help message",
        "command.sid": "Get session ID and other related information",
        "command.name": "Set display name for current UMO",
        "command.reset": "Clear the context of the current conversation.",
        "command.stop": "Stop agent execution",
        "command.new_conv": "Create a new conversation.",
        "command.stats": "Show token usage statistics for the current conversation",
        "command.provider": "View or switch LLM Provider",
        "command.update_dashboard": "Update AstrBot WebUI",
        "command.set_variable": "Set session variable",
        "command.unset_variable": "Unset session variable",
    },
}


def translate(key: str, locale: str, **params: object) -> str:
    """Format a built-in command reply using the session's system language.

    Args:
        key: Message key owned by this plugin.
        locale: System language returned by Context.locale.
        **params: Values interpolated into the reply.

    Returns:
        The localized reply, falling back to Chinese for unsupported locales.

    Raises:
        KeyError: The message key or a required interpolation parameter is missing.
    """
    return MESSAGES.get(locale, MESSAGES["zh-CN"])[key].format(**params)
