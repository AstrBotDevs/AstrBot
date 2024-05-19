from type.register import *
from typing import List

class GlobalObject:
    '''
    存放一些公用的数据，用于在不同模块(如core与command)之间传递
    '''
    version: str  # 机器人版本
    nick: tuple  # 用户定义的机器人的别名
    base_config: dict  # config.json 中导出的配置
    cached_plugins: List[RegisteredPlugin]  # 加载的插件
    platforms: List[RegisteredPlatform]
    llms: List[RegisteredLLM]

    web_search: bool  # 是否开启了网页搜索
    reply_prefix: str  # 回复前缀
    unique_session: bool  # 是否开启了独立会话
    cnt_total: int  # 总消息数
    default_personality: dict
    dashboard_data = None

    def __init__(self):
        self.nick = None  # gocq 的昵称
        self.base_config = None  # config.yaml
        self.cached_plugins = []  # 缓存的插件
        self.web_search = False  # 是否开启了网页搜索
        self.reply_prefix = None
        self.unique_session = False
        self.cnt_total = 0
        self.platforms = []
        self.llms = []
        self.default_personality = None
        self.dashboard_data = None
        self.stat = {}
