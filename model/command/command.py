import abc
import json
import platform
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
    
    # 接受可变参数
    def command_start_with(self, message: str, *args):
        for arg in args:
            if message.startswith(arg) or message.startswith('/'+arg):
                return True
        return False
    
    def update(self, message: str):
        l = message.split(" ")
        if len(l) == 1:
            # 得到本地版本号和最新版本号
            try:
                repo = Repo()
            except git.exc.InvalidGitRepositoryError:
                repo = Repo(path="QQChannelChatGPT")
            now_commit = repo.head.commit

            # 得到最新的3条commit列表, 包含commit信息
            origin = repo.remotes.origin
            origin.fetch()
            commits = list(repo.iter_commits('master', max_count=3))
            commits_log = ''
            index = 1
            for commit in commits:
                commits_log += f"[{index}] {commit.message}\n-----------\n"
                index+=1
            remote_commit_hash = origin.refs.master.commit.hexsha[:6]

            return True, f"当前版本: {now_commit.hexsha[:6]}\n最新版本: {remote_commit_hash}\n\n最新3条commit:\n{str(commits_log)}\n使用update latest更新至最新版本\n"
        else:
            if l[1] == "latest":
                pash_tag = ""
                try:
                    try:
                        repo = Repo()
                    except git.exc.InvalidGitRepositoryError:
                        repo = Repo(path="QQChannelChatGPT")
                        pash_tag = "QQChannelChatGPT\\"
                    repo.remotes.origin.pull()

                    try:
                        os.system("pip install -r "+pash_tag+"requirements.txt")
                    except BaseException as e:
                        print(str(e))

                    py = sys.executable
                    os.execl(py, py, *sys.argv)


                    # 检查是否是windows环境
                    # if platform.system().lower() == "windows":
                    #     if os.path.exists("launcher.exe"):
                    #         os.system("start launcher.exe")
                    #     elif os.path.exists("QQChannelChatGPT\\main.py"):
                    #         os.system("start python QQChannelChatGPT\\main.py")
                    #     else:
                    #         return True, "更新成功，未发现启动项，因此需要手动重启程序。"
                    #     exit()
                    # else:
                    #     py = sys.executable
                    #     os.execl(py, py, *sys.argv)
                    
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
        return True, f"[Github项目名: QQChannelChatGPT，有问题请前往提交issue，欢迎Star此项目~]\n\n指令面板：\nstatus 查看机器人key状态\ncount 查看机器人统计信息\nreset 重置会话\nhis 查看历史记录\ntoken 查看会话token数\nhelp 查看帮助\nset 人格指令菜单\nkey 动态添加key"
    
    def status(self):
        return False
    
    def token(self):
        return False
    
    def his(self):
        return False
    
    def draw(self):
        return False
    
    