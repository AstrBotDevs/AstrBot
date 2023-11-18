from model.platform.qqchan import QQChan, NakuruGuildMember, NakuruGuildMessage
from model.platform.qq import QQ
from model.provider.provider import Provider
from nakuru import (
    CQHTTP,
    GroupMessage,
    GroupMemberIncrease,
    FriendMessage,
    GuildMessage,
    Notify
)
from typing import Union

class GlobalObject:
    '''
    存放一些公用的数据，用于在不同模块(如core与command)之间传递
    '''
    nick: str # gocq 的昵称
    base_config: dict # config.yaml
    cached_plugins: dict # 缓存的插件
    web_search: bool # 是否开启了网页搜索
    reply_prefix: str
    admin_qq: str
    admin_qqchan: str
    uniqueSession: bool
    cnt_total: int
    platform_qq: QQ
    platform_qqchan: QQ
    
    def __init__(self):
        self.nick = None # gocq 的昵称
        self.base_config = None # config.yaml
        self.cached_plugins = {} # 缓存的插件
        self.web_search = False # 是否开启了网页搜索
        self.reply_prefix = None
        self.admin_qq = "123456"
        self.admin_qqchan = "123456"
        self.uniqueSession = False
        self.cnt_total = 0
        self.platform_qq = None
        self.platform_qqchan = None

class AstrMessageEvent():
    message_str: str # 纯消息字符串
    message_obj: Union[GroupMessage, FriendMessage, GuildMessage, NakuruGuildMessage] # 消息对象
    gocq_platform: QQ
    qq_sdk_platform: QQChan
    platform: str # `gocq` 或 `qqchan`
    role: str # `admin` 或 `member`
    global_object: GlobalObject # 一些公用数据

    def __init__(self, message_str: str, 
                 message_obj: Union[GroupMessage, FriendMessage, GuildMessage, NakuruGuildMessage], 
                 gocq_platform: QQ, 
                 qq_sdk_platform: QQChan, 
                 platform: str, 
                 role: str, 
                 global_object: GlobalObject,
                 llm_provider: Provider = None):
        self.message_str = message_str
        self.message_obj = message_obj
        self.gocq_platform = gocq_platform
        self.qq_sdk_platform = qq_sdk_platform
        self.platform = platform
        self.role = role
        self.global_object = global_object
        self.llm_provider = llm_provider