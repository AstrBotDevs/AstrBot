from model.command.command import Command
from model.provider.provider_rev_chatgpt import ProviderRevChatGPT
from model.platform.qq import QQ
from cores.qqbot.personality import personalities

class CommandRevChatGPT(Command):
    def __init__(self, provider: ProviderRevChatGPT, global_object: dict):
        self.provider = provider
        self.cached_plugins = {}
        self.global_object = global_object
        super().__init__(provider, global_object)

    def check_command(self, 
                      message: str, 
                      session_id: str,
                      loop,
                      role: str, 
                      platform: str,
                      message_obj,
                      cached_plugins: dict,
                      qq_platform: QQ):
        self.platform = platform
        hit, res = super().check_command(
            message,
            session_id,
            loop,
            role,
            platform,
            message_obj,
            cached_plugins,
            qq_platform
        )
        
        if hit:
            return True, res
        if self.command_start_with(message, "help", "帮助"):
            return True, self.help(cached_plugins)
        elif self.command_start_with(message, "reset"):
            return True, self.reset(session_id)
        elif self.command_start_with(message, "update"):
            return True, self.update(message, role)
        elif self.command_start_with(message, "set"):
            return True, self.set(message, session_id)
        elif self.command_start_with(message, "switch"):
            return True, self.switch(message, session_id)
        if self.command_start_with(message, "/"):
            return True, (False, "未知指令", "unknown_command")
        return False, None

    def reset(self, session_id):
        self.provider.forget(session_id)
        return True, "重置完毕。", "reset"
    
    def set(self, message: str, session_id: str):
        l = message.split(" ")
        if len(l) == 1:
            return True, f"设置人格: \n/set 人格名。例如/set 编剧\n人格列表: /set list\n人格详细信息: \
        /set view 人格名\n清除人格: /reset", "set"
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
                msg = f"人格【{ps}】详细信息：\n"
                msg += f"{personalities[ps]}\n"
            else:
                msg = f"人格【{ps}】不存在。"
            return True, msg, "set"
        else:
            ps = l[1].strip()
            if ps in personalities:
                self.reset(session_id)
                self.provider.text_chat(personalities[ps], session_id)
                return True, f"人格【{ps}】已设置。", "set"
            else:
                return True, f"人格【{ps}】不存在。", "set"

    def switch(self, message: str, session_id: str):
        '''
        切换账号
        '''
        l = message.split(" ")
        rev_chatgpt = self.provider.get_revchatgpt()
        if len(l) == 1:
            ret = "当前账号：\n"
            index = 0
            curr_ = None
            for revstat in rev_chatgpt:
                index += 1
                ret += f"[{index}]. {revstat['id']}\n"
                if session_id in revstat['user']:
                    curr_ = revstat['id']
            if curr_ is None:
                ret += "当前您未选择账号。输入/switch <账号序号>切换账号。"
            else:
                ret += f"当前您选择的账号为：{curr_}。输入/switch <账号序号>切换账号。"
            return True, ret, "switch"
        elif len(l) == 2:
            try:
                index = int(l[1])
                if index > len(self.provider.rev_chatgpt) or index < 1:
                    return True, "账号序号不合法。", "switch"
                else:
                    # pop
                    for revstat in self.provider.rev_chatgpt:
                        if session_id in revstat['user']:
                            revstat['user'].remove(session_id)
                    # append
                    self.provider.rev_chatgpt[index - 1]['user'].append(session_id)
                    return True, f"切换账号成功。当前账号为：{self.provider.rev_chatgpt[index - 1]['id']}", "switch"
            except BaseException:
                return True, "账号序号不合法。", "switch"
        else:
            return True, "参数过多。", "switch"

    def help(self, cached_plugins: dict):
        commands = super().general_commands()
        commands['set'] = '设置人格'
        return True, super().help_messager(commands, self.platform, cached_plugins), "help"
