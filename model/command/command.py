import abc
import json
import git.exc
from git.repo import Repo
import os
import sys


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
    
    def update(self, message: str):
        l = message.split(" ")
        if len(l) == 1:
            # 得到本地版本号和最新版本号
            try:
                repo = Repo()
            except git.exc.InvalidGitRepositoryError:
                repo = Repo(path="QQChannelChatGPT")
            now_commit = repo.head.commit

            # 得到最新的5条commit列表, 包含commit信息
            origin = repo.remotes.origin
            origin.fetch()
            commits = list(repo.iter_commits('master', max_count=5))
            commits_log = ''
            index = 1
            for commit in commits:
                commits_log += f"[{index}] {commit.message}\n-----------\n"
                index+=1
            remote_commit_hash = origin.refs.master.commit.hexsha[:6]

            return True, f"当前版本: {now_commit.hexsha[:6]}\n最新版本: {remote_commit_hash}\n\n最新5条commit:\n{str(commits_log)}\n使用update latest更新至最新版本\n"
        else:
            if l[1] == "latest":
                try:
                    repo = Repo()
                    repo.remotes.origin.pull()
                    py = sys.executable
                    os.execl(py, py, *sys.argv)
                    return True, "更新成功"
                    
                except BaseException as e:
                    return False, "更新失败: "+str(e)

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
    
    