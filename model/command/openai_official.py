from model.command.command import Command
from model.provider.openai_official import ProviderOpenAIOfficial, MODELS
from util.personality import personalities
from util.general_utils import download_image_by_url
from type.types import GlobalObject
from type.command import CommandItem
from SparkleLogging.utils.core import LogManager
from logging import Logger
from openai._exceptions import NotFoundError
from nakuru.entities.components import Image

logger: Logger = LogManager.GetLogger(log_name='astrbot-core')

class CommandOpenAIOfficial(Command):
    def __init__(self, provider: ProviderOpenAIOfficial, global_object: GlobalObject):
        self.provider = provider
        self.global_object = global_object
        self.personality_str = ""
        self.commands = [
            CommandItem("reset", self.reset, "重置 LLM 会话。", "内置"),
            CommandItem("his", self.his, "查看与 LLM 的历史记录。", "内置"),
            CommandItem("status", self.status, "查看 GPT 配置信息和用量状态。", "内置"),
        ]
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

        logger.debug(f"基础指令hit: {hit}, res: {res}")

        # 这里是这个 LLM 的专属指令
        if hit:
            return True, res
        if self.command_start_with(message, "reset", "重置"):
            return True, await self.reset(session_id, message)
        elif self.command_start_with(message, "his", "历史"):
            return True, self.his(message, session_id)
        elif self.command_start_with(message, "status"):
            return True, self.status(session_id)
        elif self.command_start_with(message, "help", "帮助"):
            return True, await self.help()
        elif self.command_start_with(message, "unset"):
            return True, self.unset(session_id)
        elif self.command_start_with(message, "set"):
            return True, self.set(message, session_id)
        elif self.command_start_with(message, "update"):
            return True, self.update(message, role)
        elif self.command_start_with(message, "画", "draw"):
            return True, await self.draw(message)
        elif self.command_start_with(message, "switch"):
            return True, await self.switch(message)
        elif self.command_start_with(message, "models"):
            return True, await self.print_models()
        elif self.command_start_with(message, "model"):
            return True, await self.set_model(message)
        return False, None
    
    async def get_models(self):
        try:
            models = await self.provider.client.models.list()
        except NotFoundError as e:
            bu = str(self.provider.client.base_url)
            self.provider.client.base_url = bu + "/v1"
            models = await self.provider.client.models.list()
        finally:
            return filter(lambda x: x.id.startswith("gpt"), models.data)

    async def print_models(self):
        models = await self.get_models()
        i = 1
        ret = "OpenAI GPT 类可用模型"
        for model in models:
            ret += f"\n{i}. {model.id}"
            i += 1
        ret += "\nTips: 使用 /model 模型名/编号，即可实时更换模型。如目标模型不存在于上表，请输入模型名。"
        logger.debug(ret)
        return True, ret, "models"

    
    async def set_model(self, message: str):
        l = message.split(" ")
        if len(l) == 1:
            return True, "请输入 /model 模型名/编号", "model"
        model = str(l[1])
        if model.isdigit():
            models = await self.get_models()
            models = list(models)
            if int(model) <= len(models) and int(model) >= 1:
                model = models[int(model)-1]
            self.provider.set_model(model.id)
            return True, f"模型已设置为 {model.id}", "model"
        else:
            self.provider.set_model(model)
            return True, f"模型已设置为 {model} (自定义)", "model"

        
    async def help(self):
        commands = super().general_commands()
        commands['画'] = '调用 OpenAI DallE 模型生成图片'
        commands['/set'] = '人格设置面板'
        commands['/status'] = '查看 Api Key 状态和配置信息'
        commands['/token'] = '查看本轮会话 token'
        commands['/reset'] = '重置当前与 LLM 的会话，但保留人格（system prompt）'
        commands['/reset p'] = '重置当前与 LLM 的会话，并清除人格。'
        commands['/models'] = '获取当前可用的模型'
        commands['/model'] = '更换模型'
        
        return True, await super().help_messager(commands, self.platform, self.global_object.cached_plugins), "help"

    async def reset(self, session_id: str, message: str = "reset"):
        if self.provider is None:
            return False, "未启用 OpenAI 官方 API", "reset"
        l = message.split(" ")
        if len(l) == 1:
            await self.provider.forget(session_id, keep_system_prompt=True)
            return True, "重置成功", "reset"
        if len(l) == 2 and l[1] == "p":
            await self.provider.forget(session_id)

    def his(self, message: str, session_id: str):
        if self.provider is None:
            return False, "未启用 OpenAI 官方 API", "his"
        size_per_page = 3
        page = 1
        l = message.split(" ")
        if len(l) == 2:
            try:
                page = int(l[1])
            except BaseException as e:
                return True, "页码不合法", "his"
        contexts, total_num = self.provider.dump_contexts_page(session_id, size_per_page, page=page)
        t_pages = total_num // size_per_page + 1
        return True, f"历史记录如下：\n{contexts}\n第 {page} 页 | 共 {t_pages} 页\n*输入 /his 2 跳转到第 2 页", "his"

    def status(self, session_id: str):
        if self.provider is None:
            return False, "未启用 OpenAI 官方 API", "status"
        keys_data = self.provider.get_keys_data()
        ret = "OpenAI Key"
        for k in keys_data:
            status = "🟢" if keys_data[k] else "🔴"
            ret += "\n|- " + k[:8] + " " + status

        conf = self.provider.get_configs()
        ret += "\n当前模型：" + conf['model']
        if conf['model'] in MODELS:
            ret += "\n最大上下文窗口：" + str(MODELS[conf['model']]) + " tokens"

        if session_id in self.provider.session_memory and len(self.provider.session_memory[session_id]):
            ret += "\n你的会话上下文：" + str(self.provider.session_memory[session_id][-1]['usage_tokens']) + " tokens"

        return True, ret, "status"

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
                key_stat = self.provider.get_keys_data()
                index = int(l[1])
                if index > len(key_stat) or index < 1:
                    return True, "账号序号不合法。", "switch"
                else:
                    try:
                        new_key = list(key_stat.keys())[index-1]
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
                self.provider.personality_set(ps, session_id)
                return True, f"人格{ps}已设置。", "set"
            else:
                self.provider.curr_personality = {
                    'name': '自定义人格',
                    'prompt': ps
                }
                self.provider.personality_set(ps, session_id)
                return True, f"自定义人格已设置。 \n人格信息: {ps}", "set"

    async def draw(self, message: str):
        if self.provider is None:
            return False, "未启用 OpenAI 官方 API", "draw"
        message = message.removeprefix("/").removeprefix("画")
        img_url = await self.provider.image_generate(message)
        p = await download_image_by_url(url=img_url)
        with open(p, 'rb') as f:
            return True, [Image.fromBytes(f.read())], "draw"