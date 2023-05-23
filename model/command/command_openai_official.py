from model.command.command import Command
from model.provider.provider_openai_official import ProviderOpenAIOfficial
from cores.qqbot.personality import personalities
from model.platform.qq import QQ
from util import general_utils as gu


class CommandOpenAIOfficial(Command):
    def __init__(self, provider: ProviderOpenAIOfficial):
        self.provider = provider
        self.cached_plugins = {}
        
    def check_command(self, 
                      message: str, 
                      session_id: str, 
                      user_name: str, 
                      role: str, 
                      platform: str,
                      message_obj,
                      cached_plugins: dict,
                      qq_platform: QQ):
        self.platform = platform
        hit, res = super().check_command(message, role, platform, message_obj=message_obj, cached_plugins=cached_plugins, qq_platform=qq_platform)
        if hit:
            return True, res
        if self.command_start_with(message, "reset", "重置"):
            return True, self.reset(session_id)
        elif self.command_start_with(message, "his", "历史"):
            return True, self.his(message, session_id, user_name)
        elif self.command_start_with(message, "token"):
            return True, self.token(session_id)
        elif self.command_start_with(message, "gpt"):
            return True, self.gpt()
        elif self.command_start_with(message, "status"):
            return True, self.status()
        elif self.command_start_with(message, "count"):
            return True, self.count()
        elif self.command_start_with(message, "help", "帮助"):
            return True, self.help()
        elif self.command_start_with(message, "unset"):
            return True, self.unset(session_id)
        elif self.command_start_with(message, "set"):
            return True, self.set(message, session_id)
        elif self.command_start_with(message, "update"):
            return True, self.update(message, role)
        elif self.command_start_with(message, "画"):
            return True, self.draw(message)
        elif self.command_start_with(message, "keyword"):
            return True, self.keyword(message, role)
        elif self.command_start_with(message, "key"):
            return True, self.key(message, user_name)
        
        if self.command_start_with(message, "/"):
            return True, (False, "未知指令", "unknown_command")
        
        return False, None
    
    def help(self):
        commands = super().general_commands()
        commands['画'] = '画画'
        commands['key'] = '添加OpenAI key'
        commands['set'] = '人格设置面板'
        commands['gpt'] = '查看gpt配置信息'
        commands['status'] = '查看key使用状态'
        commands['token'] = '查看本轮会话token'
        return True, super().help_messager(commands, self.platform), "help"

    
    def reset(self, session_id: str):
        if self.provider is None:
            return False, "未启动OpenAI ChatGPT语言模型.", "reset"
        self.provider.forget(session_id)
        return True, "重置成功", "reset"
    
    def his(self, message: str, session_id: str, name: str):
        if self.provider is None:
            return False, "未启动OpenAI ChatGPT语言模型.", "his"
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
            return False, "未启动OpenAI ChatGPT语言模型.", "token"
        return True, f"会话的token数: {self.provider.get_user_usage_tokens(self.provider.session_dict[session_id])}\n系统最大缓存token数: {self.provider.max_tokens}", "token"

    def gpt(self):
        if self.provider is None:
            return False, "未启动OpenAI ChatGPT语言模型.", "gpt"
        return True, f"OpenAI GPT配置:\n {self.provider.chatGPT_configs}", "gpt"
    
    def status(self):
        if self.provider is None:
            return False, "未启动OpenAI ChatGPT语言模型.", "status"
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
            chatgpt_cfg_str += f"  |-{index}: {key_stat[key]['used']}/{max} {sponsor}赞助{tag}\n"
            index += 1
        return True, f"⭐使用情况({str(gg_count)}个已用):\n{chatgpt_cfg_str}⏰全频道已用{total}tokens", "status"

    def count(self):
        if self.provider is None:
            return False, "未启动OpenAI ChatGPT语言模型.", "reset"
        guild_count, guild_msg_count, guild_direct_msg_count, session_count = self.provider.get_stat()
        return True, f"当前会话数: {len(self.provider.session_dict)}\n共有频道数: {guild_count} \n共有消息数: {guild_msg_count}\n私信数: {guild_direct_msg_count}\n历史会话数: {session_count}", "count"

    def key(self, message: str, user_name: str):
        if self.provider is None:
            return False, "未启动OpenAI ChatGPT语言模型.", "reset"
        l = message.split(" ")
        if len(l) == 1:
            msg = "感谢您赞助key，key为官方API使用，请以以下格式赞助:\n/key xxxxx"
            return True, msg, "key"
        key = l[1]
        if self.provider.check_key(key):
            self.provider.append_key(key, user_name)
            return True, f"*★,°*:.☆(￣▽￣)/$:*.°★* 。\n该Key被验证为有效。感谢{user_name}赞助~"
        else:
            return True, "该Key被验证为无效。也许是输入错误了，或者重试。", "key"

    def unset(self, session_id: str):
        if self.provider is None:
            return False, "未启动OpenAI ChatGPT语言模型.", "unset"
        self.provider.now_personality = {}
        self.provider.forget(session_id)
        return True, "已清除人格并重置历史记录。", "unset"

    def set(self, message: str, session_id: str):
        if self.provider is None:
            return False, "未启动OpenAI ChatGPT语言模型.", "set"
        l = message.split(" ")
        if len(l) == 1:
            return True, f"【由Github项目QQChannelChatGPT支持】\n\n【人格文本由PlexPt开源项目awesome-chatgpt-pr \
        ompts-zh提供】\n\n这个是人格设置指令。\n设置人格: \n/set 人格名。例如/set 编剧\n人格列表: /set list\n人格详细信息: \
        /set view 人格名\n自定义人格: /set 人格文本\n清除人格: /unset\n【当前人格】: {str(self.provider.now_personality)}", "set"
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
                self.provider.now_personality = {
                    'name': ps,
                    'prompt': personalities[ps]
                }
                self.provider.session_dict[session_id] = []
                new_record = {
                    "user": {
                        "role": "system",
                        "content": personalities[ps],
                    },
                    'usage_tokens': 0,
                    'single-tokens': 0
                }
                self.provider.session_dict[session_id].append(new_record)
                return True, f"人格{ps}已设置.", "set"
            else:
                self.provider.now_personality = {
                    'name': '自定义人格',
                    'prompt': ps
                }
                new_record = {
                    "user": {
                        "role": "system",
                        "content": ps,
                    },
                    'usage_tokens': 0,
                    'single-tokens': 0
                }
                self.provider.session_dict[session_id] = []
                self.provider.session_dict[session_id].append(new_record)
                return True, f"自定义人格已设置。 \n人格信息: {ps}", "set"
            
    def draw(self, message):
        if self.provider is None:
            return False, "未启动OpenAI ChatGPT语言模型.", "draw"
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
        
    

    
    