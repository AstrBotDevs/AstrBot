from model.command.manager import CommandManager
from type.message_event import AstrMessageEvent
from type.command import CommandResult
from type.types import Context
from SparkleLogging.utils.core import LogManager
from logging import Logger
from nakuru.entities.components import Image
from model.provider.openai_official import ProviderOpenAIOfficial, MODELS
from util.personality import personalities
from util.io import download_image_by_url

logger: Logger = LogManager.GetLogger(log_name='astrbot')


class OpenAIOfficialCommandHandler():
    def __init__(self, manager: CommandManager) -> None:
        self.manager = manager
        
        self.provider = None
        
        self.manager.register("reset", "重置会话", 10, self.reset)
        self.manager.register("his", "查看历史记录", 10, self.his)
        self.manager.register("status", "查看当前状态", 10, self.status)
        self.manager.register("switch", "切换账号", 10, self.switch)
        self.manager.register("unset", "清除个性化人格设置", 10, self.unset)
        self.manager.register("set", "设置个性化人格", 10, self.set)
        self.manager.register("draw", "调用 DallE 模型画图", 10, self.draw)
        self.manager.register("画", "调用 DallE 模型画图", 10, self.draw)
        
    def set_provider(self, provider):
        self.provider = provider
    
    async def reset(self, message: AstrMessageEvent, context: Context):
        tokens = self.manager.command_parser.parse(message.message_str)
        if tokens.len == 1:
            await self.provider.forget(message.session_id, keep_system_prompt=True)
            return CommandResult().message("重置成功")
        elif tokens.get(1) == 'p':
            await self.provider.forget(message.session_id)
        
    def his(self, message: AstrMessageEvent, context: Context):
        tokens = self.manager.command_parser.parse(message.message_str)
        size_per_page = 3
        page = 1
        if tokens.len == 2:
            try:
                page = int(tokens.get(1))
            except BaseException as e:
                return CommandResult().message("页码格式错误")
        contexts, total_num = self.provider.dump_contexts_page(message.session_id, size_per_page, page=page)
        t_pages = total_num // size_per_page + 1
        return CommandResult().message(f"历史记录如下：\n{contexts}\n第 {page} 页 | 共 {t_pages} 页\n*输入 /his 2 跳转到第 2 页")
    
    def status(self, message: AstrMessageEvent, context: Context):
        keys_data = self.provider.get_keys_data()
        ret = "OpenAI Key"
        for k in keys_data:
            status = "🟢" if keys_data[k] else "🔴"
            ret += "\n|- " + k[:8] + " " + status

        conf = self.provider.get_configs()
        ret += "\n当前模型: " + conf['model']
        if conf['model'] in MODELS:
            ret += "\n最大上下文窗口: " + str(MODELS[conf['model']]) + " tokens"

        if message.session_id in self.provider.session_memory and len(self.provider.session_memory[message.session_id]):
            ret += "\n你的会话上下文: " + str(self.provider.session_memory[message.session_id][-1]['usage_tokens']) + " tokens"

        return CommandResult().message(ret)
    
    async def switch(self, message: AstrMessageEvent, context: Context):
        '''
        切换账号
        '''
        tokens = self.manager.command_parser.parse(message.message_str)
        if tokens.len == 1:
            _, ret, _ = self.status()
            curr_ = self.provider.get_curr_key()
            if curr_ is None:
                ret += "当前您未选择账号。输入/switch <账号序号>切换账号。"
            else:
                ret += f"当前您选择的账号为：{curr_[-8:]}。输入/switch <账号序号>切换账号。"
            return CommandResult().message(ret)
        elif tokens.len == 2:
            try:
                key_stat = self.provider.get_keys_data()
                index = int(tokens.get(1))
                if index > len(key_stat) or index < 1:
                    return CommandResult().message("账号序号错误。")
                else:
                    try:
                        new_key = list(key_stat.keys())[index-1]
                        self.provider.set_key(new_key)
                    except BaseException as e:
                        return CommandResult().message("切换账号未知错误: "+str(e))
                    return CommandResult().message("切换账号成功。")    
            except BaseException as e:
                return CommandResult().message("切换账号错误。")
        else:
            return CommandResult().message("参数过多。")

    def unset(self, message: AstrMessageEvent, context: Context):
        self.provider.curr_personality = {}
        self.provider.forget(message.session_id)
        return CommandResult().message("已清除个性化设置。")
    
    
    def set(self, message: AstrMessageEvent, context: Context):
        l = message.message_str.split(" ")
        if len(l) == 1:
            return CommandResult().message("【人格文本由PlexPt开源项目awesome-chatgpt-prompts-zh提供】\n设置人格: \n/set 人格名。例如/set 编剧\n人格列表: /set list\n人格详细信息: /set view 人格名\n自定义人格: /set 人格文本\n重置会话(清除人格): /reset\n重置会话(保留人格): /reset p\n【当前人格】: " + str(self.provider.curr_personality))
        elif l[1] == "list":
            msg = "人格列表：\n"
            for key in personalities.keys():
                msg += f"  |-{key}\n"
            msg += '\n\n*输入/set view 人格名查看人格详细信息'
            return CommandResult().message(msg)
        elif l[1] == "view":
            if len(l) == 2:
                return CommandResult().message("请输入人格名")
            ps = l[2].strip()
            if ps in personalities:
                msg = f"人格{ps}的详细信息：\n"
                msg += f"{personalities[ps]}\n"
            else:
                msg = f"人格{ps}不存在"
            return CommandResult().message(msg)
        else:
            ps = l[1].strip()
            if ps in personalities:
                self.provider.curr_personality = {
                    'name': ps,
                    'prompt': personalities[ps]
                }
                self.provider.personality_set(ps, message.session_id)
                return CommandResult().message(f"人格已设置。 \n人格信息: {ps}")
            else:
                self.provider.curr_personality = {
                    'name': '自定义人格',
                    'prompt': ps
                }
                self.provider.personality_set(ps, message.session_id)
                return CommandResult().message(f"人格已设置。 \n人格信息: {ps}")

    async def draw(self, message: AstrMessageEvent, context: Context):
        message = message.message_str.removeprefix("画")
        img_url = await self.provider.image_generate(message)
        p = await download_image_by_url(url=img_url)
        with open(p, 'rb') as f:
            return CommandResult(
                message_chain=[Image.fromBytes(f.read())],
            )