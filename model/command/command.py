import json
import inspect
import aiohttp
import asyncio
import json

import util.plugin_util as putil
import util.updator

from nakuru.entities.components import (
    Image
)
from util import general_utils as gu
from model.provider.provider import Provider
from util.cmd_config import CmdConfig as cc
from type.message import *
from type.types import GlobalObject
from type.command import *
from type.plugin import *
from type.register import *

from typing import List
from SparkleLogging.utils.core import LogManager
from logging import Logger

logger: Logger = LogManager.GetLogger(log_name='astrbot-core')

PLATFORM_QQCHAN = 'qqchan'
PLATFORM_GOCQ = 'gocq'

# 指令功能的基类，通用的（不区分语言模型）的指令就在这实现


class Command:
    def __init__(self, provider: Provider, global_object: GlobalObject = None):
        self.provider = provider
        self.global_object = global_object

    async def check_command(self,
                            message,
                            session_id: str,
                            role: str,
                            platform: RegisteredPlatform,
                            message_obj):
        self.platform = platform
        # 插件
        cached_plugins = self.global_object.cached_plugins
        # 将消息封装成 AstrMessageEvent 对象
        ame = AstrMessageEvent(
            message_str=message,
            message_obj=message_obj,
            platform=platform,
            role=role,
            context=self.global_object,
            session_id=session_id
        )
        # 从已启动的插件中查找是否有匹配的指令
        for plugin in cached_plugins:
            # 过滤掉平台类插件
            if plugin.metadata.plugin_type == PluginType.PLATFORM:
                continue
            try:
                if inspect.iscoroutinefunction(plugin.plugin_instance.run):
                    result = await plugin.plugin_instance.run(ame)
                else:
                    result = await asyncio.to_thread(plugin.plugin_instance.run, ame)
                if isinstance(result, CommandResult):
                    hit = result.hit
                    res = result._result_tuple()
                elif isinstance(result, tuple):
                    hit = result[0]
                    res = result[1]
                else:
                    raise TypeError("插件返回值格式错误。")
                if hit:
                    logger.debug("hit plugin: " + plugin.metadata.plugin_name)
                    return True, res
            except TypeError as e:
                # 参数不匹配，尝试使用旧的参数方案
                try:
                    if inspect.iscoroutinefunction(plugin.plugin_instance.run):
                        hit, res = await plugin.plugin_instance.run(message, role, platform, message_obj, self.global_object.platform_qq)
                    else:
                        hit, res = await asyncio.to_thread(plugin.plugin_instance.run, message, role, platform, message_obj, self.global_object.platform_qq)
                    if hit:
                        return True, res
                except BaseException as e:
                    logger.error(
                        f"{plugin.metadata.plugin_name} 插件异常，原因: {str(e)}\n如果你没有相关装插件的想法, 请直接忽略此报错, 不影响其他功能的运行。")
            except BaseException as e:
                logger.error(
                    f"{plugin.metadata.plugin_name} 插件异常，原因: {str(e)}\n如果你没有相关装插件的想法, 请直接忽略此报错, 不影响其他功能的运行。")

        if self.command_start_with(message, "nick"):
            return True, self.set_nick(message, platform, role)
        if self.command_start_with(message, "plugin"):
            return True, self.plugin_oper(message, role, cached_plugins, platform)
        if self.command_start_with(message, "myid") or self.command_start_with(message, "!myid"):
            return True, self.get_my_id(message_obj, platform)
        if self.command_start_with(message, "web"):  # 网页搜索
            return True, self.web_search(message)
        if self.command_start_with(message, "update"):
            return True, self.update(message, role)
        if not self.provider and self.command_start_with(message, "help"):
            return True, await self.help()

        return False, None

    def web_search(self, message):
        l = message.split(' ')
        if len(l) == 1:
            return True, f"网页搜索功能当前状态: {self.global_object.web_search}", "web"
        elif l[1] == 'on':
            self.global_object.web_search = True
            return True, "已开启网页搜索", "web"
        elif l[1] == 'off':
            self.global_object.web_search = False
            return True, "已关闭网页搜索", "web"

    def get_my_id(self, message_obj, platform):
        try:
            user_id = str(message_obj.user_id)
            return True, f"你在此平台上的ID：{user_id}", "plugin"
        except BaseException as e:
            return False, f"在{platform}上获取你的ID失败，原因: {str(e)}", "plugin"

    def get_new_conf(self, message, role):
        if role != "admin":
            return False, f"你的身份组{role}没有权限使用此指令。", "newconf"
        l = message.split(" ")
        if len(l) <= 1:
            obj = cc.get_all()
            p = gu.create_text_image("【cmd_config.json】", json.dumps(
                obj, indent=4, ensure_ascii=False))
            return True, [Image.fromFileSystem(p)], "newconf"

    '''
    插件指令
    '''

    def plugin_oper(self, message: str, role: str, cached_plugins: List[RegisteredPlugin], platform: str):
        l = message.split(" ")
        if len(l) < 2:
            p = gu.create_text_image(
                "【插件指令面板】", "安装插件: \nplugin i 插件Github地址\n卸载插件: \nplugin d 插件名 \n重载插件: \nplugin reload\n查看插件列表：\nplugin l\n更新插件: plugin u 插件名\n")
            return True, [Image.fromFileSystem(p)], "plugin"
        else:
            if l[1] == "i":
                if role != "admin":
                    return False, f"你的身份组{role}没有权限安装插件", "plugin"
                try:
                    putil.install_plugin(l[2], cached_plugins)
                    return True, "插件拉取并载入成功~", "plugin"
                except BaseException as e:
                    return False, f"拉取插件失败，原因: {str(e)}", "plugin"
            elif l[1] == "d":
                if role != "admin":
                    return False, f"你的身份组{role}没有权限删除插件", "plugin"
                try:
                    putil.uninstall_plugin(l[2], cached_plugins)
                    return True, "插件卸载成功~", "plugin"
                except BaseException as e:
                    return False, f"卸载插件失败，原因: {str(e)}", "plugin"
            elif l[1] == "u":
                try:
                    putil.update_plugin(l[2], cached_plugins)
                    return True, "\n更新插件成功!!", "plugin"
                except BaseException as e:
                    return False, f"更新插件失败，原因: {str(e)}。\n建议: 使用 plugin i 指令进行覆盖安装(插件数据可能会丢失)", "plugin"
            elif l[1] == "l":
                try:
                    plugin_list_info = ""
                    for plugin in cached_plugins:
                        plugin_list_info += f"{plugin.metadata.plugin_name}: \n名称: {plugin.metadata.plugin_name}\n简介: {plugin.metadata.plugin_desc}\n版本: {plugin.metadata.version}\n作者: {plugin.metadata.author}\n"
                    p = gu.create_text_image(
                        "【已激活插件列表】", plugin_list_info + "\n使用plugin v 插件名 查看插件帮助\n")
                    return True, [Image.fromFileSystem(p)], "plugin"
                except BaseException as e:
                    return False, f"获取插件列表失败，原因: {str(e)}", "plugin"
            elif l[1] == "v":
                try:
                    info = None
                    for i in cached_plugins:
                        if i.metadata.plugin_name == l[2]:
                            info = i.metadata
                            break
                    if info:
                        p = gu.create_text_image(
                            f"【插件信息】", f"名称: {info.plugin_name}\n类型: {info.plugin_type}\n{info.desc}\n版本: {info.version}\n作者: {info.author}")
                        return True, [Image.fromFileSystem(p)], "plugin"
                    else:
                        return False, "未找到该插件", "plugin"
                except BaseException as e:
                    return False, f"获取插件信息失败，原因: {str(e)}", "plugin"

    '''
    nick: 存储机器人的昵称
    '''

    def set_nick(self, message: str, platform: RegisteredPlatform, role: str = "member"):
        if role != "admin":
            return True, "你无权使用该指令 :P", "nick"
        if str(platform) == PLATFORM_GOCQ:
            l = message.split(" ")
            if len(l) == 1:
                return True, "【设置机器人昵称】示例：\n支持多昵称\nnick 昵称1 昵称2 昵称3", "nick"
            nick = l[1:]
            cc.put("nick_qq", nick)
            self.global_object.nick = tuple(nick)
            return True, f"设置成功！现在你可以叫我这些昵称来提问我啦~", "nick"
        elif str(platform) == PLATFORM_QQCHAN:
            nick = message.split(" ")[2]
            return False, "QQ频道平台不支持为机器人设置昵称。", "nick"

    def general_commands(self):
        return {
            "help": "帮助",
            "keyword": "设置关键词/关键指令回复",
            "update": "更新项目",
            "nick": "设置机器人昵称",
            "plugin": "插件安装、卸载和重载",
            "web on/off": "LLM 网页搜索能力",
        }

    async def help_messager(self, commands: dict, platform: str, cached_plugins: List[RegisteredPlugin] = None):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://soulter.top/channelbot/notice.json") as resp:
                    notice = (await resp.json())["notice"]
        except BaseException as e:
            notice = ""
        msg = "# Help Center\n## 指令列表\n"
        for key, value in commands.items():
            msg += f"`{key}` - {value}\n"
        # plugins
        if cached_plugins != None:
            plugin_list_info = ""
            for plugin in cached_plugins:
                plugin_list_info += f"`{plugin.metadata.plugin_name}` {plugin.metadata.desc}\n"
            if plugin_list_info.strip() != "":
                msg += "\n## 插件列表\n> 使用plugin v 插件名 查看插件帮助\n"
                msg += plugin_list_info
        msg += notice

        try:
            p = gu.create_markdown_image(msg)
            return [Image.fromFileSystem(p),]
        except BaseException as e:
            logger.error(str(e))
            return msg

    def command_start_with(self, message: str, *args):
        '''
        当消息以指定的指令开头时返回True
        '''
        for arg in args:
            if message.startswith(arg) or message.startswith('/'+arg):
                return True
        return False

    def update(self, message: str, role: str):
        if role != "admin":
            return True, "你没有权限使用该指令", "update"
        l = message.split(" ")
        if len(l) == 1:
            try:
                update_info = util.updator.check_update()
                update_info += "\nTips:\n输入「update latest」更新到最新版本\n输入「update <版本号如v3.1.3>」切换到指定版本\n输入「update r」重启机器人\n"
                return True, update_info, "update"
            except BaseException as e:
                return False, "检查更新失败: "+str(e), "update"
        else:
            if l[1] == "latest":
                try:
                    release_data = util.updator.request_release_info()
                    util.updator.update_project(release_data)
                    return True, "更新成功，重启生效。可输入「update r」重启", "update"
                except BaseException as e:
                    return False, "更新失败: "+str(e), "update"
            elif l[1] == "r":
                util.updator._reboot()
            else:
                if l[1].lower().startswith('v'):
                    try:
                        release_data = util.updator.request_release_info(
                            latest=False)
                        util.updator.update_project(
                            release_data, latest=False, version=l[1])
                        return True, "更新成功，重启生效。可输入「update r」重启", "update"
                    except BaseException as e:
                        return False, "更新失败: "+str(e), "update"
                else:
                    return False, "版本号格式错误", "update"

    def reset(self):
        return False

    def set(self):
        return False

    def unset(self):
        return False

    def key(self):
        return False

    async def help(self):
        ret = await self.help_messager(self.general_commands(), self.platform, self.global_object.cached_plugins)
        return True, ret, "help"

    def status(self):
        return False

    def token(self):
        return False

    def his(self):
        return False

    def draw(self):
        return False
