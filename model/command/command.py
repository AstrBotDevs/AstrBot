import abc
import json
import git.exc
from git.repo import Repo
import os
import sys

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
    
    def keyword(self, message: str, role: str):
        if role != "admin":
            return True, "你没有权限使用该指令", "keyword"
        if len(message.split(" ")) != 3:
            return True, "【设置关键词/关键指令回复】示例：\nkeyword hi 你好\n当发送hi的时候会回复你好\nkeyword /hi 你好\n当发送/hi时会回复你好", "keyword"
        
        l = message.split(" ")
        try:
            if os.path.exists("keyword.json"):
                with open("keyword.json", "r", encoding="utf-8") as f:
                    keyword = json.load(f)
                    keyword[l[1]] = l[2]
            else:
                keyword = {l[1]: l[2]}
            with open("keyword.json", "w", encoding="utf-8") as f:
                json.dump(keyword, f, ensure_ascii=False, indent=4)
            return True, "设置成功: "+l[1]+" -> "+l[2], "keyword"
        except BaseException as e:
            return False, "设置失败: "+str(e), "keyword"
    
    def update(self, message: str, role: str):
        if role != "admin":
            return True, "你没有权限使用该指令", "keyword"
        l = message.split(" ")
        if len(l) == 1:
            # 得到本地版本号和最新版本号
            try:
                repo = Repo()
            except git.exc.InvalidGitRepositoryError:
                repo = Repo(path="QQChannelChatGPT")
            now_commit = repo.head.commit

            # 得到远程3条commit列表, 包含commit信息
            origin = repo.remotes.origin
            origin.fetch()
            commits = list(repo.iter_commits('master', max_count=3))
            commits_log = ''
            index = 1
            for commit in commits:
                if commit.message.endswith("\n"):
                    commits_log += f"[{index}] {commit.message}-----------\n"
                else:
                    commits_log += f"[{index}] {commit.message}\n-----------\n"
                index+=1
            remote_commit_hash = origin.refs.master.commit.hexsha[:6]

            return True, f"当前版本: {now_commit.hexsha[:6]}\n最新版本: {remote_commit_hash}\n\n3条commit(非最新):\n{str(commits_log)}\n使用update latest更新至最新版本\n", "update"
        else:
            if l[1] == "latest":
                pash_tag = ""
                try:
                    try:
                        repo = Repo()
                    except git.exc.InvalidGitRepositoryError:
                        repo = Repo(path="QQChannelChatGPT")
                        pash_tag = "QQChannelChatGPT"+os.sep
                    repo.remotes.origin.pull()

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
                    return True, "更新成功~是否重启？输入update reboot重启（重启指令不返回任何确认信息）。", "update"
                    
                except BaseException as e:
                    return False, "更新失败: "+str(e), "update"
            if l[1] == "reboot":
                py = sys.executable
                os.execl(py, py, *sys.argv)


    def reset(self):
        return False
    
    def set(self):
        return False
    
    def unset(self):
        return False
    
    def key(self):
        return False
    
    def help(self):
        return True, f"[Github项目名: QQChannelChatGPT，有问题请前往提交issue，欢迎Star此项目~]\n\n指令面板：\nstatus 查看机器人key状态\ncount 查看机器人统计信息\nreset 重置会话\nhis 查看历史记录\ntoken 查看会话token数\nhelp 查看帮助\nset 人格指令菜单\nkey 动态添加key", "help"
    
    def status(self):
        return False
    
    def token(self):
        return False
    
    def his(self):
        return False
    
    def draw(self):
        return False
    
    