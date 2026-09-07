"""内置指令的多语言文案表与翻译助手。

文案按 ``key -> {语言代码: 文本}`` 组织,支持 ``{var}`` 占位符。
语言解析复用 ``Context.get_lang``(会话级 sp -> 全局配置 -> 默认)。
"""

from __future__ import annotations

from astrbot.api.star import Context
from astrbot.core.utils.lang_utils import DEFAULT_LANG

# 内置指令固定回复文案表(四语言)
MSGS: dict[str, dict[str, str]] = {
    # conversation.py
    "reset.success": {
        "zh-CN": "✅ 会话已重置。",
        "en-US": "✅ Conversation reset successfully.",
        "ru-RU": "✅ Диалог сброшен.",
        "ja-JP": "✅ 会話をリセットしました。",
    },
    "reset.no_provider": {
        "zh-CN": "😕 未找到 LLM 服务,请先配置。",
        "en-US": "😕 Cannot find any LLM provider. Configure one first.",
        "ru-RU": "😕 Не найден LLM-провайдер. Настройте его.",
        "ja-JP": "😕 LLMプロバイダが見つかりません。先に設定してください。",
    },
    "reset.no_conv": {
        "zh-CN": "😕 当前不在会话中,请用 /new 创建。",
        "en-US": "😕 You are not in a conversation. Use /new to create one.",
        "ru-RU": "😕 Вы не в диалоге. Используйте /new.",
        "ja-JP": "😕 会話がありません。/new で作成してください。",
    },
    "reset.perm_denied": {
        "zh-CN": "❌ 在{scene}场景下需要管理员权限,您(ID {sender})不是管理员。",
        "en-US": "❌ Reset requires admin in {scene} scenario; ID {sender} is not admin.",
        "ru-RU": "❌ В сценарии {scene} требуется админ; ID {sender} не админ.",
        "ja-JP": "❌ {scene}では管理者権限が必要です(ID {sender} は管理者ではありません)。",
    },
    "stop.done": {
        "zh-CN": "✅ 已请求停止 {count} 个任务。",
        "en-US": "✅ Requested to stop {count} running tasks.",
        "ru-RU": "✅ Запрошена остановка {count} задач.",
        "ja-JP": "✅ {count} 件のタスクを停止しました。",
    },
    "stop.none": {
        "zh-CN": "✅ 当前会话没有运行中的任务。",
        "en-US": "✅ No running tasks in the current session.",
        "ru-RU": "✅ Нет выполняемых задач в текущей сессии.",
        "ja-JP": "✅ 実行中のタスクはありません。",
    },
    "new.success": {
        "zh-CN": "✅ 已切换到新会话: {cid}。",
        "en-US": "✅ Switched to new conversation: {cid}.",
        "ru-RU": "✅ Переключено на новый диалог: {cid}.",
        "ja-JP": "✅ 新しい会話に切り替えました: {cid}。",
    },
    "new.created": {
        "zh-CN": "✅ 已创建新对话。",
        "en-US": "✅ New conversation created.",
        "ru-RU": "✅ Новый диалог создан.",
        "ja-JP": "✅ 新しい会話を作成しました。",
    },
    "stats.none": {
        "zh-CN": "📊 当前会话暂无统计。",
        "en-US": "📊 No stats available for this conversation yet.",
        "ru-RU": "📊 Статистики пока нет.",
        "ja-JP": "📊 統計はまだありません。",
    },
    "stats.header": {
        "zh-CN": "📊 会话 Token 用量 (ID: {cid}...)\n总计:          {total:,}\n输入(缓存): {cached:,}\n输入(其他):  {other:,}\n输出:         {output:,}\n",
        "en-US": "📊 Conversation Token usage (ID: {cid}...)\nTotal:          {total:,}\nInput (cached): {cached:,}\nInput (other):  {other:,}\nOutput:         {output:,}\n",
        "ru-RU": "📊 Использование токенов (ID: {cid}...)\nВсего:          {total:,}\nВход (кэш):     {cached:,}\nВход (прочее):  {other:,}\nВыход:          {output:,}\n",
        "ja-JP": "📊 トークン使用量 (ID: {cid}...)\n合計:          {total:,}\n入力(キャッシュ): {cached:,}\n入力(その他):  {other:,}\n出力:         {output:,}\n",
    },
    # name.py
    "name.usage": {
        "zh-CN": "用法: /name <名称>\nUMO: {umo}\n自动名: {name}\n别名: {alias}",
        "en-US": "Usage: /name <name>\nUMO: {umo}\nAuto name: {name}\nAlias: {alias}",
        "ru-RU": "Использование: /name <имя>\nUMO: {umo}\nАвтоимя: {name}\nАлиас: {alias}",
        "ja-JP": "使い方: /name <名前>\nUMO: {umo}\n自動名: {name}\n別名: {alias}",
    },
    "name.set": {
        "zh-CN": "✅ UMO 名称已设置为: {alias}\nUMO: {umo}",
        "en-US": "✅ UMO name set to: {alias}\nUMO: {umo}",
        "ru-RU": "✅ Имя UMO задано: {alias}\nUMO: {umo}",
        "ja-JP": "✅ UMO 名を設定しました: {alias}\nUMO: {umo}",
    },
    # provider.py
    "provider.testing": {
        "zh-CN": "👀 正在检测提供商可用性…",
        "en-US": "👀 Testing provider reachability...",
        "ru-RU": "👀 Проверка доступности провайдера...",
        "ja-JP": "👀 プロバイダの到達性を確認中...",
    },
    "provider.switched": {
        "zh-CN": "✅ 已切换到 {id}。",
        "en-US": "✅ Successfully switched to {id}.",
        "ru-RU": "✅ Переключено на {id}.",
        "ja-JP": "✅ {id} に切り替えました。",
    },
    "provider.invalid_idx": {
        "zh-CN": "❌ 无效的提供商索引。",
        "en-US": "❌ Invalid provider index.",
        "ru-RU": "❌ Неверный индекс провайдера.",
        "ja-JP": "❌ 無効なプロバイダ番号です。",
    },
    "provider.invalid_param": {
        "zh-CN": "❌ 无效参数。",
        "en-US": "❌ Invalid parameter.",
        "ru-RU": "❌ Неверный параметр.",
        "ja-JP": "❌ 無効なパラメータです。",
    },
    "provider.enter_index": {
        "zh-CN": "请输入索引。",
        "en-US": "Please enter the index.",
        "ru-RU": "Пожалуйста, введите индекс.",
        "ja-JP": "番号を入力してください。",
    },
    "provider.switch_hint": {
        "zh-CN": "使用 /provider <索引> 切换 LLM 提供商。",
        "en-US": "Use /provider <idx> to switch LLM providers.",
        "ru-RU": "Используйте /provider <idx> для переключения LLM-провайдера.",
        "ja-JP": "/provider <番号> で LLMプロバイダを切り替えます。",
    },
    "provider.switch_hint_tts": {
        "zh-CN": "使用 /provider tts <索引> 切换 TTS 提供商。",
        "en-US": "Use /provider tts <idx> to switch TTS providers.",
        "ru-RU": "Используйте /provider tts <idx> для переключения TTS-провайдера.",
        "ja-JP": "/provider tts <番号> で TTSプロバイダを切り替えます。",
    },
    "provider.switch_hint_stt": {
        "zh-CN": "使用 /provider stt <索引> 切换 STT 提供商。",
        "en-US": "Use /provider stt <idx> to switch STT providers.",
        "ru-RU": "Используйте /provider stt <idx> для переключения STT-провайдера.",
        "ja-JP": "/provider stt <番号> で STTプロバイダを切り替えます。",
    },
    "provider.title_llm": {
        "zh-CN": "## LLM 提供商",
        "en-US": "## LLM Providers",
        "ru-RU": "## LLM-провайдеры",
        "ja-JP": "## LLMプロバイダ",
    },
    "provider.title_tts": {
        "zh-CN": "## TTS 提供商",
        "en-US": "## TTS Providers",
        "ru-RU": "## TTS-провайдеры",
        "ja-JP": "## TTSプロバイダ",
    },
    "provider.title_stt": {
        "zh-CN": "## STT 提供商",
        "en-US": "## STT Providers",
        "ru-RU": "## STT-провайдеры",
        "ja-JP": "## STTプロバイダ",
    },
    # setunset.py
    "set.success": {
        "zh-CN": "✅ 会话 {uid} 变量 {key} 已存储,使用 /unset 移除。",
        "en-US": "✅ Session {uid} variable {key} stored. Use /unset to remove.",
        "ru-RU": "✅ Переменная {key} сессии {uid} сохранена. /unset — удалить.",
        "ja-JP": "✅ セッション {uid} の変数 {key} を保存しました。/unset で削除できます。",
    },
    "set.missing": {
        "zh-CN": "❌ 没有该变量。格式:/unset 变量名。",
        "en-US": "❌ No such variable. Format: /unset <key>.",
        "ru-RU": "❌ Нет такой переменной. Формат: /unset <key>.",
        "ja-JP": "❌ その変数はありません。形式:/unset <キー>。",
    },
    "set.removed": {
        "zh-CN": "✅ 会话 {uid} 变量 {key} 已移除。",
        "en-US": "✅ Session {uid} variable {key} removed.",
        "ru-RU": "✅ Переменная {key} сессии {uid} удалена.",
        "ja-JP": "✅ セッション {uid} の変数 {key} を削除しました。",
    },
    # sid.py
    "sid.usage": {
        "zh-CN": "*UMO 用于设置白名单与路由,UID 用于设置管理员列表",
        "en-US": "*Use UMO to set whitelist and configure routing, use UID to set admin list",
        "ru-RU": "*UMO — для белого списка и маршрутизации, UID — для админов",
        "ja-JP": "*UMO は許可リスト/ルーティング、UID は管理者設定に使用",
    },
    # admin.py
    "dashboard.updating": {
        "zh-CN": "⏳ 正在更新面板…",
        "en-US": "⏳ Updating dashboard...",
        "ru-RU": "⏳ Обновление панели...",
        "ja-JP": "⏳ パネルを更新中...",
    },
    "dashboard.done": {
        "zh-CN": "✅ 面板更新成功。",
        "en-US": "✅ Dashboard updated successfully.",
        "ru-RU": "✅ Панель обновлена.",
        "ja-JP": "✅ パネルを更新しました。",
    },
    # lang.py
    "lang.current": {
        "zh-CN": "当前语言: {lang}(来源: {source})。",
        "en-US": "Current language: {lang} (source: {source}).",
        "ru-RU": "Текущий язык: {lang} (источник: {source}).",
        "ja-JP": "現在の言語: {lang}(ソース: {source})。",
    },
    "lang.global_invalid": {
        "zh-CN": "⚠️ 全局语言为 {value}(未识别),当前按默认 {lang} 生效。",
        "en-US": "⚠️ Global language is {value} (unrecognized); using default {lang}.",
        "ru-RU": "⚠️ Глобальный язык {value} не распознан; используется {lang}.",
        "ja-JP": "⚠️ グローバル言語 {value} は認識されません。デフォルト {lang} を使用します。",
    },
    "lang.set": {
        "zh-CN": "✅ 已设置本会话语言为 {lang}。",
        "en-US": "✅ Session language set to {lang}.",
        "ru-RU": "✅ Язык сессии установлен: {lang}.",
        "ja-JP": "✅ セッション言語を {lang} に設定しました。",
    },
    "lang.reset": {
        "zh-CN": "✅ 已移除会话级语言设置,回退到全局配置。",
        "en-US": "✅ Session language override removed; using global config.",
        "ru-RU": "✅ Локальная настройка языка удалена; используется глобальная.",
        "ja-JP": "✅ セッション言語の設定を解除し、グローバル設定に戻しました。",
    },
    "lang.invalid": {
        "zh-CN": "❌ 不支持的语言: {value}。可用: {langs}。",
        "en-US": "❌ Unsupported language: {value}. Available: {langs}.",
        "ru-RU": "❌ Неподдерживаемый язык: {value}. Доступно: {langs}.",
        "ja-JP": "❌ 未対応の言語です: {value}。利用可能: {langs}。",
    },
}

# 内置指令描述(用于 /help 列表;键与命令名一致,四语言)
CMD_DESCS: dict[str, dict[str, str]] = {
    "help": {
        "zh-CN": "查看帮助",
        "en-US": "Show help message",
        "ru-RU": "Показать справку",
        "ja-JP": "ヘルプを表示",
    },
    "lang": {
        "zh-CN": "查看或设置会话语言(仅管理员)",
        "en-US": "View or set session/global language (admin)",
        "ru-RU": "Просмотр и настройка языка сессии (админ)",
        "ja-JP": "セッション言語の表示・設定(管理者のみ)",
    },
    "name": {
        "zh-CN": "设置当前 UMO 的显示名称",
        "en-US": "Set display name for current UMO",
        "ru-RU": "Задать отображаемое имя текущего UMO",
        "ja-JP": "現在の UMO の表示名を設定",
    },
    "new": {
        "zh-CN": "创建新对话",
        "en-US": "Create new conversation",
        "ru-RU": "Создать новый диалог",
        "ja-JP": "新しい会話を作成",
    },
    "provider": {
        "zh-CN": "查看或切换 LLM 提供商",
        "en-US": "View or switch LLM Provider",
        "ru-RU": "Просмотр и переключение LLM-провайдера",
        "ja-JP": "LLMプロバイダの表示・切り替え",
    },
    "reset": {
        "zh-CN": "重置对话历史",
        "en-US": "Reset conversation history",
        "ru-RU": "Сбросить историю диалога",
        "ja-JP": "会話履歴をリセット",
    },
    "sid": {
        "zh-CN": "获取会话 ID 与相关信息",
        "en-US": "Get session ID and other related information",
        "ru-RU": "Получить ID сессии и другую информацию",
        "ja-JP": "セッション ID と関連情報を取得",
    },
    "stats": {
        "zh-CN": "查看当前会话的 token 用量统计",
        "en-US": "Show token usage statistics for the current conversation",
        "ru-RU": "Статистика расхода токенов текущего диалога",
        "ja-JP": "現在の会話のトークン使用量を表示",
    },
    "stop": {
        "zh-CN": "停止 Agent 执行",
        "en-US": "Stop agent execution",
        "ru-RU": "Остановить выполнение агента",
        "ja-JP": "エージェントの実行を停止",
    },
    "set": {
        "zh-CN": "设置会话变量",
        "en-US": "Set session variable",
        "ru-RU": "Задать переменную сессии",
        "ja-JP": "セッション変数を設定",
    },
    "unset": {
        "zh-CN": "移除会话变量",
        "en-US": "Unset session variable",
        "ru-RU": "Удалить переменную сессии",
        "ja-JP": "セッション変数を削除",
    },
    "dashboard_update": {
        "zh-CN": "更新 AstrBot WebUI",
        "en-US": "Update AstrBot WebUI",
        "ru-RU": "Обновить WebUI AstrBot",
        "ja-JP": "AstrBot WebUI を更新",
    },
}


async def t(context: Context, umo: str, key: str, **params) -> str:
    """按当前会话语言取内置指令文案。

    Args:
        context: 插件上下文(用于解析语言)。
        umo: unified_message_origin。
        key: 文案键(如 ``"reset.success"``)。
        **params: 占位符参数(如 ``cid=...``)。

    Returns:
        翻译后的文案;找不到时回退 ``zh-CN``,再回退键名本身。
    """
    lang = await context.get_lang(umo)
    entry = MSGS.get(key, {})
    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    return text.format(**params)


async def command_desc(context: Context, umo: str, cmd: str) -> str:
    """按当前会话语言取内置指令描述(用于 /help)。

    Args:
        context: 插件上下文(用于解析语言)。
        umo: unified_message_origin。
        cmd: 命令名(如 ``"reset"``)。

    Returns:
        翻译后的描述;找不到时回退 ``zh-CN``,再回退空串。
    """
    lang = await context.get_lang(umo)
    entry = CMD_DESCS.get(cmd, {})
    return entry.get(lang) or entry.get(DEFAULT_LANG) or ""
