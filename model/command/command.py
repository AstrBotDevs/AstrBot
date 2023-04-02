import abc
import json

import requests
from model.provider.provider import Provider

class Command:
    def __init__(self, provider: Provider):
        self.provider = Provider

    @abc.abstractmethod
    def check_command(self, message):
        if message.startswith("help") or message.startswith("帮助"):
            return True, self.help()
        return False, None

    def reset(self):
        return False
    
    def set(self):
        return False
    
    def unset(self):
        return False
    
    def key(self):
        return False
    
    def help(self):
        # ol_version = 'Unknown'
        # try:
        #     res = requests.get("https://soulter.top/channelbot/update.json")
        #     res_obj = json.loads(res.text)
        #     ol_version = res_obj['version']
        # except BaseException:
        #     pass
        return True, f"[Github项目名: QQChannelChatGPT，有问题请前往提交issue，欢迎Star此项目~]\n\n指令面板：\nstatus 查看机器人key状态\ncount 查看机器人统计信息\nreset 重置会话\nhis 查看历史记录\ntoken 查看会话token数\nhelp 查看帮助\nset 人格指令菜单\nkey 动态添加key"
    
    
    def status(self):
        return False
    
    def token(self):
        return False
    
    def his(self):
        return False
    
    def draw(self):
        return False
    
    