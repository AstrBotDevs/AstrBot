import json
import git.exc
from git.repo import Repo
import os
import sys
import requests
from model.provider.provider import Provider
import json
import util.plugin_util as putil
import shutil
import importlib
from util import general_utils as gu
from util.cmd_config import CmdConfig as cc
from model.platform.qq import QQ
import stat
from nakuru.entities.components import (
    Plain,
    Image
)
from PIL import Image as PILImage

PLATFORM_QQCHAN = 'qqchan'
PLATFORM_GOCQ = 'gocq'

# 指令功能的基类，通用的（不区分语言模型）的指令就在这实现
class Command:
    def __init__(self, provider: Provider):
        self.provider = Provider

    def get_plugin_modules(self):
        plugins = []
        try:
            if os.path.exists("addons/plugins"):
                plugins = putil.get_modules("addons/plugins")
                return plugins
            elif os.path.exists("QQChannelChatGPT/addons/plugins"):
                plugins = putil.get_modules("QQChannelChatGPT/addons/plugins")
                return plugins
            else:
                return None
        except BaseException as e:
            raise e

    def check_command(self, message, role, platform, message_obj, cached_plugins: dict, qq_platform: QQ):
        # 插件

        for k, v in cached_plugins.items():
            try:
                hit, res = v["clsobj"].run(message, role, platform, message_obj, qq_platform)
                if hit:
                    return True, res
            except BaseException as e:
                gu.log(f"{k}插件加载出现问题，原因: {str(e)}\n已安装插件: {cached_plugins.keys}\n如果你没有相关装插件的想法, 请直接忽略此报错, 不影响其他功能的运行。", level=gu.LEVEL_WARNING)

        if self.command_start_with(message, "nick"):
            return True, self.set_nick(message, platform, role)
        
        if self.command_start_with(message, "plugin"):
            return True, self.plugin_oper(message, role, cached_plugins, platform)
        
        if self.command_start_with(message, "myid"):
            return True, self.get_my_id(message_obj, platform)
        if self.command_start_with(message, "nconf") or self.command_start_with(message, "newconf"):
            return True, self.get_new_conf(message, role, platform)
        
        return False, None
    
    def get_my_id(self, message_obj, platform):
        if platform == "gocq":
            if message_obj.type == "GuildMessage":
                return True, f"你的频道id是{str(message_obj.sender.tiny_id)}", "plugin"
            else:
                return True, f"你的QQ是{str(message_obj.sender.user_id)}", "plugin"
            
    def get_new_conf(self, message, role, platform):
        if role != "admin":
            return False, f"你的身份组{role}没有权限使用此指令。", "newconf"
        if platform == gu.PLATFORM_GOCQ:
            l = message.split(" ")
            if len(l) <= 1:
                obj = cc.get_all()
                p = gu.create_text_image("【cmd_config.json】", json.dumps(obj, indent=4, ensure_ascii=False))
                return True, [Image.fromFileSystem(p)], "newconf"
        return False, f"Not support or not implemented.", "newconf"
            

    
    def plugin_reload(self, cached_plugins: dict, target: str = None, all: bool = False):
        plugins = self.get_plugin_modules()
        fail_rec = ""
        if plugins != None:
            for p in plugins:
                try:
                    if p not in cached_plugins or p == target or all:
                        module = __import__("addons.plugins." + p + "." + p, fromlist=[p])
                        if p in cached_plugins:
                            module = importlib.reload(module)
                        cls = putil.get_classes(p, module)
                        obj = getattr(module, cls[0])()
                        try:
                            info = obj.info()
                            if 'name' not in info or 'desc' not in info or 'version' not in info or 'author' not in info:
                                fail_rec += f"载入插件{p}失败，原因: 插件信息不完整\n"
                                continue
                            if isinstance(info, dict) == False:
                                fail_rec += f"载入插件{p}失败，原因: 插件信息格式不正确\n"
                                continue
                        except BaseException as e:
                            fail_rec += f"调用插件{p} info失败, 原因: {str(e)}\n"
                            continue
                        cached_plugins[p] = {
                            "module": module,
                            "clsobj": obj,
                            "info": info
                        }  
                except BaseException as e:
                    raise e
                    fail_rec += f"加载{p}插件出现问题，原因{str(e)}\n"
            if fail_rec == "":
                return True, None
            else:
                return False, fail_rec
        else:
            return False, "未找到任何插件模块"
    
    '''
    插件指令
    '''
    def plugin_oper(self, message: str, role: str, cached_plugins: dict, platform: str):
        l = message.split(" ")
        if len(l) < 2:
            if platform == gu.PLATFORM_GOCQ:
                p = gu.create_text_image("【插件指令面板】", "安装插件: \nplugin i 插件Github地址\n卸载插件: \nplugin i 插件名 \n重载插件: \nplugin reload\n查看插件列表：\nplugin l\n更新插件: plugin u 插件名\n")
                return True, [Image.fromFileSystem(p)], "plugin"
            return True, "\n=====插件指令面板=====\n安装插件: \nplugin i 插件Github地址\n卸载插件: \nplugin i 插件名 \n重载插件: \nplugin reload\n查看插件列表：\nplugin l\n更新插件: plugin u 插件名\n===============", "plugin"
        else:
            ppath = ""
            if os.path.exists("addons/plugins"):
                ppath = "addons/plugins"
            elif os.path.exists("QQChannelChatGPT/addons/plugins"):
                ppath = "QQChannelChatGPT/addons/plugins"
            else:
                return False, "未找到插件目录", "plugin"
            if l[1] == "i":
                if role != "admin":
                    return False, f"你的身份组{role}没有权限安装插件", "plugin"
                try:
                    # 得到url的最后一段
                    d = l[2].split("/")[-1]
                    # 创建文件夹
                    plugin_path = os.path.join(ppath, d)
                    if os.path.exists(plugin_path):
                        shutil.rmtree(plugin_path)
                    os.mkdir(plugin_path)
                    Repo.clone_from(l[2],to_path=plugin_path,branch='master')

                    # 读取插件的requirements.txt
                    if os.path.exists(os.path.join(plugin_path, "requirements.txt")):
                        with open(os.path.join(plugin_path, "requirements.txt"), "r", encoding="utf-8") as f:
                            for line in f.readlines():
                                mm = os.system(f"pip3 install {line.strip()}")
                                if mm != 0:
                                    return False, "插件依赖安装失败，需要您手动pip安装对应插件的依赖。", "plugin"
                    # 加载没缓存的插件
                    ok, err = self.plugin_reload(cached_plugins, target=d)
                    if ok:
                        return True, "插件拉取并载入成功~", "plugin"
                    else:
                        # if os.path.exists(plugin_path):
                        #     shutil.rmtree(plugin_path)
                        return False, f"插件拉取载入失败。\n跟踪: \n{err}", "plugin"
                except BaseException as e:
                    return False, f"拉取插件失败，原因: {str(e)}", "plugin"
            elif l[1] == "d":
                if role != "admin":
                    return False, f"你的身份组{role}没有权限删除插件", "plugin"
                try:
                    # 删除文件夹
                    # shutil.rmtree(os.path.join(ppath, l[2]))
                    self.remove_dir(os.path.join(ppath, l[2]))
                    if l[2] in cached_plugins:
                        del cached_plugins[l[2]]
                    return True, "插件卸载成功~", "plugin"
                except BaseException as e:
                    return False, f"卸载插件失败，原因: {str(e)}", "plugin"
            elif l[1] == "u":
                plugin_path = os.path.join(ppath, l[2])
                try:
                    repo = Repo(path = plugin_path)
                    repo.remotes.origin.pull()
                    ok, err = self.plugin_reload(cached_plugins, target=l[2])
                    if ok:
                        return True, "\n更新插件成功!!", "plugin"
                    else:
                        return False, "更新插件成功，但是重载插件失败。\n问题跟踪: \n"+err, "plugin"
                except BaseException as e:
                    return False, "更新插件失败, 请使用plugin i指令覆盖安装", "plugin"

            elif l[1] == "l":
                try:
                    plugin_list_info = "\n".join([f"{k}: \n名称: {v['info']['name']}\n简介: {v['info']['desc']}\n版本: {v['info']['version']}\n作者: {v['info']['author']}\n" for k, v in cached_plugins.items()])
                    if platform == gu.PLATFORM_GOCQ:
                        p = gu.create_text_image("【已激活插件列表】", plugin_list_info + "\n使用plugin v 插件名 查看插件帮助\n")
                        return True, [Image.fromFileSystem(p)], "plugin"
                    return True, "\n=====已激活插件列表=====\n" + plugin_list_info + "\n使用plugin v 插件名 查看插件帮助\n=================", "plugin"
                except BaseException as e:
                    return False, f"获取插件列表失败，原因: {str(e)}", "plugin"
            elif l[1] == "v":
                try:
                    if l[2] in cached_plugins:
                        info = cached_plugins[l[2]]["info"]
                        if platform == gu.PLATFORM_GOCQ:
                            p = gu.create_text_image(f"【插件信息】", f"名称: {info['name']}\n{info['desc']}\n版本: {info['version']}\n作者: {info['author']}\n\n帮助:\n{info['help']}")
                            return True, [Image.fromFileSystem(p)], "plugin"
                        res = f"\n=====插件信息=====\n名称: {info['name']}\n{info['desc']}\n版本: {info['version']}作者: {info['author']}\n\n帮助:\n{info['help']}"
                        return True, res, "plugin"
                    else:
                        return False, "未找到该插件", "plugin"
                except BaseException as e:
                    return False, f"获取插件信息失败，原因: {str(e)}", "plugin"
            elif l[1] == "reload":
                if role != "admin":
                    return False, f"你的身份组{role}没有权限重载插件", "plugin"
                try:
                    ok, err = self.plugin_reload(cached_plugins, all = True)
                    if ok:
                        return True, "\n重载插件成功~", "plugin"
                    else:
                        # if os.path.exists(plugin_path):
                        #     shutil.rmtree(plugin_path)
                        return False, f"插件重载失败。\n跟踪: \n{err}", "plugin"
                except BaseException as e:
                    return False, f"插件重载失败，原因: {str(e)}", "plugin"
                
            elif l[1] == "dev":
                if role != "admin":
                    return False, f"你的身份组{role}没有权限开发者模式", "plugin"
                return True, "cached_plugins: \n" + str(cached_plugins), "plugin"
    

    def remove_dir(self, file_path):        
        while 1:
            if not os.path.exists(file_path):
                break
            try:
                shutil.rmtree(file_path)
            except PermissionError as e:
                err_file_path = str(e).split("\'", 2)[1]
                if os.path.exists(err_file_path):
                    os.chmod(err_file_path, stat.S_IWUSR)


    '''
    nick: 存储机器人的昵称
    '''
    def set_nick(self, message: str, platform: str, role: str = "member"):
        if role != "admin":
            return True, "你无权使用该指令 :P", "nick"
        if platform == PLATFORM_GOCQ:
            l = message.split(" ")
            if len(l) == 1:
                return True, "【设置机器人昵称】示例：\n支持多昵称\nnick 昵称1 昵称2 昵称3", "nick"
            nick = l[1:]
            self.general_command_storer("nick_qq", nick)
            return True, f"设置成功！现在你可以叫我这些昵称来提问我啦~", "nick"
        elif platform == PLATFORM_QQCHAN:
            nick = message.split(" ")[2]
            return False, "QQ频道平台不支持为机器人设置昵称。", "nick"
    
    """
    存储指令结果到cmd_config.json
    """
    def general_command_storer(self, key, value):
        if not os.path.exists("cmd_config.json"):
            config = {}
        else:
            with open("cmd_config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
        config[key] = value
        with open("cmd_config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
            f.flush()

    
    def general_commands(self):
        return {
            "help": "帮助",
            "keyword": "设置关键词/关键指令回复",
            "update": "更新面板",
            "update latest": "更新到最新版本",
            "update r": "重启机器人",
            "reset": "重置会话",
            "nick": "设置机器人昵称",
            "plugin": "插件安装、卸载和重载",
            "/bing": "切换到bing模型",
            "/gpt": "切换到OpenAI ChatGPT API",
            "/revgpt": "切换到网页版ChatGPT",
        }
    
    def help_messager(self, commands: dict, platform: str, cached_plugins: dict = None):
        try:
            resp = requests.get("https://soulter.top/channelbot/notice.json").text
            notice = json.loads(resp)["notice"]
        except BaseException as e:
            notice = ""
        msg = "# Help Center\n## 指令列表\n"
        # msg = "Github项目名QQChannelChatGPT, 有问题提交issue, 欢迎Star\n【指令列表】\n"
        for key, value in commands.items():
            msg += f"`{key}` - {value}\n"
        # plugins
        if cached_plugins != None:
            plugin_list_info = "\n".join([f"`{k}` {v['info']['name']}\n{v['info']['desc']}\n" for k, v in cached_plugins.items()])
            if plugin_list_info.strip() != "":
                msg += "\n## 插件列表\n> 使用plugin v 插件名 查看插件帮助\n"
                msg += plugin_list_info
        msg += notice

        if platform == gu.PLATFORM_GOCQ:
            try:
                # p = gu.create_text_image("【Help Center】", msg)
                p = gu.create_markdown_image(msg)
                return [Image.fromFileSystem(p)]
            except BaseException as e:
                gu.log(str(e))
                return msg
        return msg
    
    # 接受可变参数
    def command_start_with(self, message: str, *args):
        for arg in args:
            if message.startswith(arg) or message.startswith('/'+arg):
                return True
        return False
    
    # keyword: 关键字
    def keyword(self, message: str, role: str):
        if role != "admin":
            return True, "你没有权限使用该指令", "keyword"

        l = message.split(" ")

        if len(l) < 3:
            return True, "【设置关键词回复】示例：\nkeyword hi 你好\n当发送hi的时候会回复你好\nkeyword /hi 你好\n当发送/hi时会回复你好\n删除关键词: keyword d hi\n删除hi关键词的回复", "keyword"
        
        del_mode = False
        if l[1] == "d":
            del_mode = True    

        try:
            if os.path.exists("keyword.json"):
                with open("keyword.json", "r", encoding="utf-8") as f:
                    keyword = json.load(f)
                    if del_mode:
                        # 删除关键词
                        if l[2] not in keyword:
                            return False, "该关键词不存在", "keyword"
                        else: del keyword[l[2]]
                    else:
                        keyword[l[1]] = l[2]
            else:
                if del_mode:
                    return False, "该关键词不存在", "keyword"
                keyword = {l[1]: l[2]}
            with open("keyword.json", "w", encoding="utf-8") as f:
                json.dump(keyword, f, ensure_ascii=False, indent=4)
                f.flush()
            if del_mode:
                return True, "删除成功: "+l[2], "keyword"
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

                    if len(l) == 3 and l[2] == "r":
                        py = sys.executable
                        os.execl(py, py, *sys.argv)

                    return True, "更新成功~是否重启？输入update r重启（重启指令不返回任何确认信息）。", "update"
                    
                except BaseException as e:
                    return False, "更新失败: "+str(e), "update"
            if l[1] == "r":
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
        return False
    
    def status(self):
        return False
    
    def token(self):
        return False
    
    def his(self):
        return False
    
    def draw(self):
        return False
    
    