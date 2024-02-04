from model.platform.qq_official import QQOfficial, NakuruGuildMember, NakuruGuildMessage
from model.platform.qq_gocq import QQGOCQ
from model.provider.provider import Provider
from addons.dashboard.server import DashBoardData
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
    base_config: dict # config.json
    cached_plugins: dict # 缓存的插件
    web_search: bool # 是否开启了网页搜索
    reply_prefix: str
    admin_qq: str
    admin_qqchan: str
    uniqueSession: bool
    cnt_total: int
    platform_qq: QQGOCQ
    platform_qqchan: QQOfficial
    default_personality: dict
    dashboard_data: DashBoardData
    stat: dict
    logger: None
    
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
        self.default_personality = None
        self.dashboard_data = None
        self.stat = {}


class AstrMessageEvent():
    message_str: str # 纯消息字符串
    message_obj: Union[GroupMessage, FriendMessage, GuildMessage, NakuruGuildMessage] # 消息对象
    gocq_platform: QQGOCQ
    qq_sdk_platform: QQOfficial
    platform: str # `gocq` 或 `qqchan`
    role: str # `admin` 或 `member`
    global_object: GlobalObject # 一些公用数据
    session_id: int # 会话id (可能是群id，也可能是某个user的id。取决于是否开启了 uniqueSession)

    def __init__(self, message_str: str, 
                 message_obj: Union[GroupMessage, FriendMessage, GuildMessage, NakuruGuildMessage], 
                 gocq_platform: QQGOCQ, 
                 qq_sdk_platform: QQOfficial, 
                 platform: str, 
                 role: str, 
                 global_object: GlobalObject,
                 llm_provider: Provider = None,
                 session_id: int = None):
        self.message_str = message_str
        self.message_obj = message_obj
        self.gocq_platform = gocq_platform
        self.qq_sdk_platform = qq_sdk_platform
        self.platform = platform
        self.role = role
        self.global_object = global_object
        self.llm_provider = llm_provider
        self.session_id = session_id
        
class CommandResult():
    '''
    用于在Command中返回多个值
    '''
    def __init__(self, hit: bool, success: bool, message_chain: list, command_name: str = "unknown_command") -> None:
        self.hit = hit
        self.success = success
        self.message_chain = message_chain
        self.command_name = command_name
        
    def _result_tuple(self):
        return (self.success, self.message_chain, self.command_name)