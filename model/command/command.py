import json
from util import general_utils as gu
has_git = True
try:
    import git.exc
    from git.repo import Repo
except BaseException as e:
    gu.log("你正运行在无Git环境下，暂时将无法使用插件、热更新功能。")
    has_git = False
import os
import sys
import requests
from model.provider.provider import Provider
import json
import util.plugin_util as putil
import shutil
import importlib
from util.cmd_config import CmdConfig as cc
from model.platform.qq import QQ
import stat
from nakuru.entities.components import (
    Plain,
    Image
)
from PIL import Image as PILImage
from cores.qqbot.global_object import GlobalObject, AstrMessageEvent
from pip._internal import main as pipmain

from .adapter.protocol_adapter import UnifiedBotCompatibleLayer
import asyncio

PLATFORM_QQCHAN = 'qqchan'
PLATFORM_GOCQ = 'gocq'

# 指令功能的基类，通用的（不区分语言模型）的指令就在这实现
class Command:
    def __init__(self, provider: Provider, global_object: GlobalObject = None, unified_bot_compatible_layer: UnifiedBotCompatibleLayer = None):
        self.provider = provider
        self.global_object = global_object
        self.unified_bot_compatible_layer = unified_bot_compatible_layer


    async def check_command(self, 
                      message, 
                      session_id: str,
                      role, 
                      platform, 
                      message_obj):
        # UBCL
        await self.unified_bot_compatible_layer.check_commands(message, message_obj)

        # 插件
        cached_plugins = self.global_object.cached_plugins
        ame = AstrMessageEvent(
            message_str=message,
            message_obj=message_obj,
            gocq_platform=self.global_object.platform_qq,
            qq_sdk_platform=self.global_object.platform_qqchan,
            platform=platform,
            role=role,
            global_object=self.global_object,
            session_id = session_id
        )
        for k, v in cached_plugins.items():
            try:
                hit, res = v["clsobj"].run(ame)
                if hit:
                    return True, res
            except TypeError as e:
                # 参数不匹配，尝试使用旧的参数方案
                try:
                    hit, res = v["clsobj"].run(message, role, platform, message_obj, self.global_object.platform_qq)
                    if hit:
                        return True, res
                except BaseException as e:
                    gu.log(f"{k}插件加载出现问题，原因: {str(e)}\n已安装插件: {cached_plugins.keys}\n如果你没有相关装插件的想法, 请直接忽略此报错, 不影响其他功能的运行。", level=gu.LEVEL_WARNING)
            except BaseException as e:
                gu.log(f"{k}插件加载出现问题，原因: {str(e)}\n已安装插件: {cached_plugins.keys}\n如果你没有相关装插件的想法, 请直接忽略此报错, 不影响其他功能的运行。", level=gu.LEVEL_WARNING)

        if self.command_start_with(message, "nick"):
            return True, self.set_nick(message, platform, role)
        if self.command_start_with(message, "plugin"):
            return True, self.plugin_oper(message, role, cached_plugins, platform)
        if self.command_start_with(message, "myid") or self.command_start_with(message, "!myid"):
            return True, self.get_my_id(message_obj)
        if self.command_start_with(message, "nconf") or self.command_start_with(message, "newconf"):
            return True, self.get_new_conf(message, role)
        if self.command_start_with(message, "web"): # 网页搜索
            return True, self.web_search(message)
        if self.command_start_with(message, "keyword"):
            return True, self.keyword(message_obj, role)
        
        return False, None
    
    def web_search(self, message):
        if message == "web on":
            self.global_object.web_search = True
            return True, "已开启网页搜索", "web"
        elif message == "web off":
            self.global_object.web_search = False
            return True, "已关闭网页搜索", "web"
        return True, f"网页搜索功能当前状态: {self.global_object.web_search}", "web"

    def get_my_id(self, message_obj):
        return True, f"你的ID：{str(message_obj.sender.tiny_id)}", "plugin"
            
    def get_new_conf(self, message, role):
        if role != "admin":
            return False, f"你的身份组{role}没有权限使用此指令。", "newconf"
        l = message.split(" ")
        if len(l) <= 1:
            obj = cc.get_all()
            p = gu.create_text_image("【cmd_config.json】", json.dumps(obj, indent=4, ensure_ascii=False))
            return True, [Image.fromFileSystem(p)], "newconf"
            
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

    def plugin_reload(self, cached_plugins: dict, target: str = None, all: bool = False):
        plugins = self.get_plugin_modules()
        fail_rec = ""
        if plugins is None:
            return False, "未找到任何插件模块"

        for plugin in plugins:
            try:
                p = plugin['module']
                root_dir_name = plugin['pname']
                if p not in cached_plugins or p == target or all:
                    module = __import__("addons.plugins." + root_dir_name + "." + p, fromlist=[p])
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
                    cached_plugins[info['name']] = {
                        "module": module,
                        "clsobj": obj,
                        "info": info,
                        "name": info['name'],
                        "root_dir_name": root_dir_name,
                    }
            except BaseException as e:
                fail_rec += f"加载{p}插件出现问题，原因 {str(e)}\n"
        if fail_rec == "":
            return True, None
        else:
            return False, fail_rec
    
    '''
    插件指令
    '''
    def plugin_oper(self, message: str, role: str, cached_plugins: dict, platform: str):
        if not has_git:
            return False, "你正在运行在无Git环境下，暂时将无法使用插件、热更新功能。", "plugin"
        l = message.split(" ")
        if len(l) < 2:
            p = gu.create_text_image("【插件指令面板】", "安装插件: \nplugin i 插件Github地址\n卸载插件: \nplugin d 插件名 \n重载插件: \nplugin reload\n查看插件列表：\nplugin l\n更新插件: plugin u 插件名\n")
            return True, [Image.fromFileSystem(p)], "plugin"
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
                    # 删除末尾的/
                    if l[2].endswith("/"):
                        l[2] = l[2][:-1]
                    # 得到url的最后一段
                    d = l[2].split("/")[-1]
                    # 转换非法字符：-
                    d = d.replace("-", "_")
                    # 创建文件夹
                    plugin_path = os.path.join(ppath, d)
                    if os.path.exists(plugin_path):
                        shutil.rmtree(plugin_path)
                    os.mkdir(plugin_path)
                    Repo.clone_from(l[2],to_path=plugin_path,branch='master')

                    # 读取插件的requirements.txt
                    if os.path.exists(os.path.join(plugin_path, "requirements.txt")):
                        mm = pipmain(['install', '-r', os.path.join(plugin_path, "requirements.txt")])
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
                if l[2] not in cached_plugins:
                    return False, "未找到该插件", "plugin"

                try:
                    root_dir_name = cached_plugins[l[2]]["root_dir_name"]
                    self.remove_dir(os.path.join(ppath, root_dir_name))
                    del cached_plugins[l[2]]
                    return True, "插件卸载成功~", "plugin"
                except BaseException as e:
                    return False, f"卸载插件失败，原因: {str(e)}", "plugin"
            elif l[1] == "u":
                if l[2] not in cached_plugins:
                    return False, "未找到该插件", "plugin"
                root_dir_name = cached_plugins[l[2]]["root_dir_name"]
                plugin_path = os.path.join(ppath, root_dir_name)
                try:
                    repo = Repo(path = plugin_path)
                    repo.remotes.origin.pull()
                    # 读取插件的requirements.txt
                    if os.path.exists(os.path.join(plugin_path, "requirements.txt")):
                        mm = pipmain(['install', '-r', os.path.join(plugin_path, "requirements.txt")])
                        if mm != 0:
                            return False, "插件依赖安装失败，需要您手动pip安装对应插件的依赖。", "plugin"

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
                    p = gu.create_text_image("【已激活插件列表】", plugin_list_info + "\n使用plugin v 插件名 查看插件帮助\n")
                    return True, [Image.fromFileSystem(p)], "plugin"
                except BaseException as e:
                    return False, f"获取插件列表失败，原因: {str(e)}", "plugin"
            elif l[1] == "v":
                try:
                    if l[2] in cached_plugins:
                        info = cached_plugins[l[2]]["info"]
                        p = gu.create_text_image(f"【插件信息】", f"名称: {info['name']}\n{info['desc']}\n版本: {info['version']}\n作者: {info['author']}\n\n帮助:\n{info['help']}")
                        return True, [Image.fromFileSystem(p)], "plugin"
                    else:
                        return False, "未找到该插件", "plugin"
                except BaseException as e:
                    return False, f"获取插件信息失败，原因: {str(e)}", "plugin"
            elif l[1] == "reload":
                if role != "admin":
                    return False, f"你的身份组{role}没有权限重载插件", "plugin"
                for plugin in cached_plugins:
                    try:
                        print(f"更新插件 {plugin} 依赖...")
                        plugin_path = os.path.join(ppath, cached_plugins[plugin]["root_dir_name"])
                        if os.path.exists(os.path.join(plugin_path, "requirements.txt")):
                            mm = pipmain(['install', '-r', os.path.join(plugin_path, "requirements.txt"), "--quiet"])
                            if mm != 0:
                                return False, "插件依赖安装失败，需要您手动pip安装对应插件的依赖。", "plugin"
                    except BaseException as e:
                        print(f"插件{plugin}依赖安装失败，原因: {str(e)}")
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
            cc.put("nick_qq", nick)
            self.global_object.nick = tuple(nick)
            return True, f"设置成功！现在你可以叫我这些昵称来提问我啦~", "nick"
        elif platform == PLATFORM_QQCHAN:
            nick = message.split(" ")[2]
            return False, "QQ频道平台不支持为机器人设置昵称。", "nick"

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
            "web on/off": "启动或关闭网页搜索能力",
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

        try:
            # p = gu.create_text_image("【Help Center】", msg)
            p = gu.create_markdown_image(msg)
            return [Image.fromFileSystem(p)]
        except BaseException as e:
            gu.log(str(e))
        finally:
            return msg
    
    # 接受可变参数
    def command_start_with(self, message: str, *args):
        for arg in args:
            if message.startswith(arg) or message.startswith('/'+arg):
                return True
        return False
    
    # keyword: 关键字
    def keyword(self, message_obj, role: str):
        if role != "admin":
            return True, "你没有权限使用该指令", "keyword"
        
        plain_text = ""
        image_url = ""

        for comp in message_obj.message:
            if isinstance(comp, Plain):
                plain_text += comp.text
            elif isinstance(comp, Image) and image_url == "":
                if comp.url is None:
                    image_url = comp.file
                else:
                    image_url = comp.url

        l = plain_text.split(" ")

        if len(l) < 3 and image_url == "":
            return True, """
【设置关键词回复】示例：
1. keyword hi 你好
当发送hi的时候会回复你好
2. keyword /hi 你好
当发送/hi时会回复你好
3. keyword d hi
删除hi关键词的回复
4. keyword hi <图片>
当发送hi时会回复图片
""", "keyword"
        
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
                        keyword[l[1]] = {
                            "plain_text": " ".join(l[2:]),
                            "image_url": image_url
                        }
            else:
                if del_mode:
                    return False, "该关键词不存在", "keyword"
                keyword = {
                    l[1]: {
                    "plain_text": " ".join(l[2:]),
                    "image_url": image_url
                    }
                }
            with open("keyword.json", "w", encoding="utf-8") as f:
                json.dump(keyword, f, ensure_ascii=False, indent=4)
                f.flush()
            if del_mode:
                return True, "删除成功: "+l[2], "keyword"
            if image_url == "":
                return True, "设置成功: "+l[1]+" "+" ".join(l[2:]), "keyword"
            else:
                return True, [Plain("设置成功: "+l[1]+" "+" ".join(l[2:])), Image.fromURL(image_url)], "keyword"
        except BaseException as e:
            return False, "设置失败: "+str(e), "keyword"
    
    def update(self, message: str, role: str):
        if not has_git:
            return False, "你正在运行在无Git环境下，暂时将无法使用插件、热更新功能。", "update"
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

                    try:
                        origin = repo.remotes.origin
                        origin.fetch()
                        commits = list(repo.iter_commits('master', max_count=1))
                        commit_log = commits[0].message
                    except BaseException as e:
                        commit_log = "无法获取commit信息"

                    tag = "update"
                    if len(l) == 3 and l[2] == "r":
                        tag = "update latest r"

                    return True, f"更新成功。新版本内容: \n{commit_log}\nps:重启后生效。输入update r重启（重启指令不返回任何确认信息）。", tag
                    
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
    
    