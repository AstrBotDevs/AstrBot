import aiohttp
import astrbot.api.star as star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.config.default import VERSION
from astrbot.core.utils.io import get_dashboard_version


class HelpCommand:
    def __init__(self, context: star.Context):
        self.context = context

    async def _query_astrbot_notice(self):
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.get(
                    "https://astrbot.app/notice.json", timeout=2
                ) as resp:
                    return (await resp.json())["notice"]
        except BaseException:
            return ""

    async def help(self, event: AstrMessageEvent):
        """查看帮助"""
        notice = ""
        try:
            notice = await self._query_astrbot_notice()
        except BaseException:
            pass

        dashboard_version = await get_dashboard_version()

        msg = f"""AstrBot v{VERSION}(WebUI: {dashboard_version})
内置指令:
[System]
/plugin: 查看插件、插件帮助
/t2i: 开关文本转图片
/tts: 开关文本转语音
/sid: 获取会话 ID
/op: 管理员
/wl: 白名单
/dashboard_update: 更新管理面板(op)
/alter_cmd: 设置指令权限(op)

[大模型]
/llm: 开启/关闭 LLM
/provider: 大模型提供商
/model: 模型列表
/ls: 对话列表
/new: 创建新对话
/groupnew 群号: 为群聊创建新对话(op)
/switch 序号: 切换对话
/rename 新名字: 重命名当前对话
/del: 删除当前会话对话(op)
/reset: 重置 LLM 会话
/history: 当前对话的对话记录
/persona: 人格情景(op)
/key: API Key(op)
/websearch: 网页搜索
{notice}"""

        event.set_result(MessageEventResult().message(msg).use_t2i(False))
