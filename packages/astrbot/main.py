import aiohttp, base64, os, json, re, time
from typing import Dict
from astrbot.api import Context, AstrMessageEvent, MessageEventResult
from astrbot.api import logger, command_parser

class Main:
    def __init__(self, context: Context) -> None:
        self.context = context
        context.register_commands("astrbot", "help", "查看 AstrBot 帮助", 10, self.help)
        context.register_commands("astrbot", "plugin", "AstrBot 插件管理", 10, self.plugin)
        context.register_commands("astrbot", "t2i", "关闭/启动文本转图片", 10, self.t2i)
        context.register_commands("astrbot", "myid", "查看自己在该平台上的 ID", 10, self.myid)
        
        context.register_listener("astrbot", "keywords_ban_rate_limit", self.keywords_ban, "关键词屏蔽和发言频率监听器")
        # keywords
        with open(os.path.join(os.path.dirname(__file__), "unfit_words"), "r", encoding="utf-8") as f:
            self.keywords: list = json.loads(base64.b64decode(f.read()).decode("utf-8"))['keywords']
            internal_keywords_cfg = context.get_config().content_safety.internal_keywords
            if internal_keywords_cfg.enable:
                self.keywords.extend(internal_keywords_cfg.extra_keywords)
                
        # rate limit
        self.user_rate_limit: Dict[int, int] = {}
        rl_cfg = context.get_config().platform_settings.rate_limit
        self.rate_limit_time: int = rl_cfg.time
        self.rate_limit_count: int = rl_cfg.count
        self.user_frequency = {}
                
    async def keywords_ban(self, event: AstrMessageEvent):
        if not event.is_wake_up():
            return
        
        # keywords 检测
        for i in self.keywords:
            matches = re.match(i, event.get_message_str().strip(), re.I | re.M)
            if matches:
                event.set_result(MessageEventResult().message("你的消息中包含不适当的关键词，已被屏蔽。"))
                return
        
        # rate limit 检测
        ts = int(time.time())
        if event.session_id in self.user_frequency:
            if ts-self.user_frequency[event.session_id]['time'] > self.rate_limit_time:
                # reset
                self.user_frequency[event.session_id]['time'] = ts
                self.user_frequency[event.session_id]['count'] = 1
                return
            if self.user_frequency[event.session_id]['count'] >= self.rate_limit_count:
                event.set_result(MessageEventResult().message("你发送消息的频率过快，请稍后再试。"))
                return
            self.user_frequency[event.session_id]['count'] += 1
        else:
            t = {'time': ts, 'count': 1}
            self.user_frequency[event.session_id] = t
        

    async def help(self, event: AstrMessageEvent):
        notice = ""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://astrbot.soulter.top/notice.json") as resp:
                    notice = (await resp.json())["notice"]
        except BaseException as e:
            pass

        msg = "# AstrBot 帮助\n## 已注册的指令\n"
        for key, value in self.context.commands_handler.items():
            if value.plugin_metadata:
                msg += f"- `{key}` ({value.plugin_metadata.plugin_name}): {value.description}\n"
            else: msg += f"- `{key}`: {value.description}\n"

        msg += "\n> 提示：使用 /plugin 查看已加载的插件\n"
        msg += notice

        event.set_result(MessageEventResult().message(msg))
 
    async def plugin(self, event: AstrMessageEvent):
        plugin_list_info = "已加载的插件：\n"
        for plugin in self.context.registered_plugins:
            plugin_list_info += f"- `{plugin.metadata.plugin_name}` By {plugin.metadata.author}: {plugin.metadata.desc}\n"
        if plugin_list_info.strip() == "":
            plugin_list_info = "没有加载任何插件。"
        
        event.set_result(MessageEventResult().message(f"{plugin_list_info}"))
        
    async def t2i(self, event: AstrMessageEvent):
        config = self.context.get_config()
        if config.t2i:
            config.t2i = False
            config.save_config()
            event.set_result(MessageEventResult().message("已关闭文本转图片模式。"))
            return
        config.t2i = True
        config.save_config()
        event.set_result(MessageEventResult().message("已开启文本转图片模式。"))
        
    async def myid(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        event.set_result(MessageEventResult().message(f"你的 ID 是 {user_id}。此 ID 可用于设置 AstrBot 管理员。"))