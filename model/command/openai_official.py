from model.command.command import Command
from model.provider.openai_official import ProviderOpenAIOfficial
from cores.qqbot.personality import personalities
from cores.qqbot.types import GlobalObject

class CommandOpenAIOfficial(Command):
    def __init__(self, provider: ProviderOpenAIOfficial, global_object: GlobalObject):
        self.provider = provider
        self.global_object = global_object
        self.personality_str = ""
        super().__init__(provider, global_object)
        
    async def check_command(self, 
                      message: str, 
                      session_id: str, 
                      role: str, 
                      platform: str,
                      message_obj):
        self.platform = platform
        
        # 检查基础指令
        hit, res = await super().check_command(
            message,
            session_id,
            role,
            platform,
            message_obj
        )
        
        # 这里是这个 LLM 的专属指令
        if hit:
            return True, res
        if self.command_start_with(message, "reset", "重置"):
            return True, await self.reset(session_id, message)
        elif self.command_start_with(message, "his", "历史"):
            return True, self.his(message, session_id)
        elif self.command_start_with(message, "token"):
            return True, self.token(session_id)
        elif self.command_start_with(message, "gpt"):
            return True, self.gpt()
        elif self.command_start_with(message, "status"):
            return True, self.status()
        elif self.command_start_with(message, "help", "帮助"):
            return True, await self.help()
        elif self.command_start_with(message, "unset"):
            return True, self.unset(session_id)
        elif self.command_start_with(message, "set"):
            return True, self.set(message, session_id)
        elif self.command_start_with(message, "update"):
            return True, self.update(message, role)
        elif self.command_start_with(message, "画", "draw"):
            return True, self.draw(message)
        elif self.command_start_with(message, "key"):
            return True, self.key(message)
        elif self.command_start_with(message, "switch"):
            return True, await self.switch(message)
        
        return False, None
    
    async def help(self):
        commands = super().general_commands()
        commands['画'] = '画画'
        commands['key'] = '添加OpenAI key'
        commands['set'] = '人格设置面板'
        commands['gpt'] = '查看gpt配置信息'
        commands['status'] = '查看key使用状态'
        commands['token'] = '查看本轮会话token'
        return True, await super().help_messager(commands, self.platform, self.global_object.cached_plugins), "help"

        
    async def reset(self, session_id: str, message: str = "reset"):
        if self.provider is None:
            return False, "未启用 OpenAI 官方 API", "reset"
        l = message.split(" ")
        if len(l) == 1:
            await self.provider.forget(session_id)
            return True, "重置成功", "reset"
        if len(l) == 2 and l[1] == "p":
            self.provider.forget(session_id)
            if self.personality_str != "":
                self.set(self.personality_str, session_id) # 重新设置人格
            return True, "重置成功", "reset"
    
    def his(self, message: str, session_id: str):
        if self.provider is None:
            return False, "未启用 OpenAI 官方 API", "his"
        #分页，每页5条
        msg = ''
        size_per_page = 3
        page = 1
        if message[4:]:
            page = int(message[4:])
        # 检查是否有过历史记录
        if session_id not in self.provider.session_dict:
            msg = f"历史记录为空"
            return True, msg, "his"
        l = self.provider.session_dict[session_id]
        max_page = len(l)//size_per_page + 1 if len(l)%size_per_page != 0 else len(l)//size_per_page
        p = self.provider.get_prompts_by_cache_list(self.provider.session_dict[session_id], divide=True, paging=True, size=size_per_page, page=page)
        return True, f"历史记录如下：\n{p}\n第{page}页 | 共{max_page}页\n*输入/his 2跳转到第2页", "his"
    
    def token(self, session_id: str):
        if self.provider is None:
            return False, "未启用 OpenAI 官方 API", "token"
        return True, f"会话的token数: {self.provider.get_user_usage_tokens(self.provider.session_dict[session_id])}\n系统最大缓存token数: {self.provider.max_tokens}", "token"

    def gpt(self):
        if self.provider is None:
            return False, "未启用 OpenAI 官方 API", "gpt"
        return True, f"OpenAI GPT配置:\n {self.provider.chatGPT_configs}", "gpt"
    
    def status(self):
        if self.provider is None:
            return False, "未启用 OpenAI 官方 API", "status"
        chatgpt_cfg_str = ""
        key_stat = self.provider.get_key_stat()
        index = 1
        max = 9000000
        gg_count = 0
        total = 0
        tag = ''
        for key in key_stat.keys():
            sponsor = ''
            total += key_stat[key]['used']
            if key_stat[key]['exceed']:
                gg_count += 1
                continue
            if 'sponsor' in key_stat[key]:
                sponsor = key_stat[key]['sponsor']
            chatgpt_cfg_str += f"  |-{index}: {key[-8:]} {key_stat[key]['used']}/{max} {sponsor}{tag}\n"
            index += 1
        return True, f"⭐使用情况({str(gg_count)}个已用):\n{chatgpt_cfg_str}", "status"

    def key(self, message: str):
        if self.provider is None:
            return False, "未启用 OpenAI 官方 API", "reset"
        l = message.split(" ")
        if len(l) == 1:
            msg = "感谢您赞助key，key为官方API使用，请以以下格式赞助:\n/key xxxxx"
            return True, msg, "key"
        key = l[1]
        if self.provider.check_key(key):
            self.provider.append_key(key)
            return True, f"*★,°*:.☆(￣▽￣)/$:*.°★* 。\n该Key被验证为有效。感谢你的赞助~"
        else:
            return True, "该Key被验证为无效。也许是输入错误了，或者重试。", "key"

    async def switch(self, message: str):
        '''
        切换账号
        '''
        l = message.split(" ")
        if len(l) == 1:
            _, ret, _ = self.status()
            curr_ = self.provider.get_curr_key()
            if curr_ is None:
                ret += "当前您未选择账号。输入/switch <账号序号>切换账号。"
            else:
                ret += f"当前您选择的账号为：{curr_[-8:]}。输入/switch <账号序号>切换账号。"
            return True, ret, "switch"
        elif len(l) == 2:
            try:
                key_stat = self.provider.get_key_stat()
                index = int(l[1])
                if index > len(key_stat) or index < 1:
                    return True, "账号序号不合法。", "switch"
                else:
                    try:
                        new_key = list(key_stat.keys())[index-1]
                        ret = await self.provider.check_key(new_key)
                        self.provider.set_key(new_key)
                    except BaseException as e:
                        return True, "账号切换失败，原因: " + str(e), "switch"
                    return True, f"账号切换成功。", "switch"
            except BaseException as e:
                return True, "未知错误: "+str(e), "switch"
        else:
            return True, "参数过多。", "switch"

    def unset(self, session_id: str):
        if self.provider is None:
            return False, "未启用 OpenAI 官方 API", "unset"
        self.provider.curr_personality = {}
        self.provider.forget(session_id)
        return True, "已清除人格并重置历史记录。", "unset"

    def set(self, message: str, session_id: str):
        if self.provider is None:
            return False, "未启用 OpenAI 官方 API", "set"
        l = message.split(" ")
        if len(l) == 1:
            return True, f"【人格文本由PlexPt开源项目awesome-chatgpt-pr \
        ompts-zh提供】\n设置人格: \n/set 人格名。例如/set 编剧\n人格列表: /set list\n人格详细信息: \
        /set view 人格名\n自定义人格: /set 人格文本\n重置会话(清除人格): /reset\n重置会话(保留人格): /reset p\n【当前人格】: {str(self.provider.curr_personality)}", "set"
        elif l[1] == "list":
            msg = "人格列表：\n"
            for key in personalities.keys():
                msg += f"  |-{key}\n"
            msg += '\n\n*输入/set view 人格名查看人格详细信息'
            msg += '\n*不定时更新人格库，请及时更新本项目。'
            return True, msg, "set"
        elif l[1] == "view":
            if len(l) == 2:
                return True, "请输入/set view 人格名", "set"
            ps = l[2].strip()
            if ps in personalities:
                msg = f"人格{ps}的详细信息：\n"
                msg += f"{personalities[ps]}\n"
            else:
                msg = f"人格{ps}不存在"
            return True, msg, "set"
        else:
            ps = l[1].strip()
            if ps in personalities:
                self.provider.curr_personality = {
                    'name': ps,
                    'prompt': personalities[ps]
                }
                self.provider.session_dict[session_id] = []
                new_record = {
                    "user": {
                        "role": "user",
                        "content": personalities[ps],
                    },
                    "AI": {
                        "role": "assistant",
                        "content": "好的，接下来我会扮演这个角色。"
                    },
                    'type': "personality",
                    'usage_tokens': 0,
                    'single-tokens': 0
                }
                self.provider.session_dict[session_id].append(new_record)
                self.personality_str = message
                return True, f"人格{ps}已设置。", "set"
            else:
                self.provider.curr_personality = {
                    'name': '自定义人格',
                    'prompt': ps
                }
                new_record = {
                    "user": {
                        "role": "user",
                        "content": ps,
                    },
                    "AI": {
                        "role": "assistant",
                        "content": "好的，接下来我会扮演这个角色。"
                    },
                    'type': "personality",
                    'usage_tokens': 0,
                    'single-tokens': 0
                }
                self.provider.session_dict[session_id] = []
                self.provider.session_dict[session_id].append(new_record)
                self.personality_str = message
                return True, f"自定义人格已设置。 \n人格信息: {ps}", "set"
            
    def draw(self, message):
        if self.provider is None:
            return False, "未启用 OpenAI 官方 API", "draw"
        if message.startswith("/画"):
            message = message[2:]
        elif message.startswith("画"):
            message = message[1:]
        try:
            # 画图模式传回3个参数
            img_url = self.provider.image_chat(message)
            return True, img_url, "draw"
        except Exception as e:
            if 'exceeded' in str(e):
                return f"OpenAI API错误。原因：\n{str(e)} \n超额了。可自己搭建一个机器人(Github仓库：QQChannelChatGPT)"
            return False, f"图片生成失败: {e}", "draw"