class GlobalObject():
    '''
    存放一些公用的数据，用于在不同模块(如core与command)之间传递
    '''
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