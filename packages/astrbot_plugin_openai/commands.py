from astrbot.api import Context, AstrMessageEvent, MessageEventResult, MessageChain
from . import PLUGIN_NAME
from astrbot.api import logger
from astrbot.api.message_components import Image, Plain
from astrbot.api import personalities
from astrbot.api import command_parser
from astrbot.api import Provider, Personality


class OpenAIAdapterCommand:
    def __init__(self, context: Context) -> None:
        self.provider: Provider = None
        self.context = context
        context.register_commands(PLUGIN_NAME, "reset", "重置会话", 10, self.reset)
        context.register_commands(PLUGIN_NAME, "his", "查看历史记录", 10, self.his)
        context.register_commands(PLUGIN_NAME, "status", "查看当前状态", 10, self.status)
        context.register_commands(PLUGIN_NAME, "switch", "切换账号", 10, self.switch)
        context.register_commands(PLUGIN_NAME, "persona", "设置个性化人格", 10, self.persona)
        context.register_commands(PLUGIN_NAME, "draw", "调用 DallE 模型画图", 10, self.draw)
        context.register_commands(PLUGIN_NAME, "model", "切换 LLM 模型", 10, self.model)
        context.register_commands(PLUGIN_NAME, "画", "调用 DallE 模型画图", 10, self.draw)
    
    def set_provider(self, provider: Provider):
        self.provider = provider
    
    async def reset(self, message: AstrMessageEvent):
        tokens = command_parser.parse(message.message_str)
        if tokens.len == 1:
            await self.provider.forget(message.session_id)
            message.set_result(MessageEventResult().message("重置成功"))
        elif tokens.get(1) == 'p':
            await self.provider.forget(message.session_id)
    
    async def model(self, message: AstrMessageEvent):
        tokens = command_parser.parse(message.message_str)
        if tokens.len == 1:
            ret = await self._print_models()
            message.set_result(MessageEventResult().message(ret).use_t2i(False))
            return
        model = tokens.get(1)
        if model.isdigit():
            try:
                models = await self.provider.get_models()
            except BaseException as e:
                logger.error(f"获取模型列表失败: {str(e)}。如果出现 404，可能与服务提供商未提供模型列表有关。")
                message.set_result(MessageEventResult().message("获取模型列表失败，无法使用编号切换模型。可以尝试直接输入模型名来切换，如 gpt-4o。"))
            models = list(models)
            if int(model) <= len(models) and int(model) >= 1:
                model = models[int(model)-1]
            self.provider.set_model(model.id)
            message.set_result(MessageEventResult().message(f"模型已设置为 {model.id}"))
        else:
            self.provider.set_model(model)
            message.set_result(MessageEventResult().message(f"模型已设置为 {model} (自定义)"))

    async def _print_models(self):
        models = []
        try:
            models = await self.provider.get_models()
        except BaseException as e:
            return "获取模型列表失败: " + str(e)
        i = 1
        ret = "下面列出了此服务提供商可用模型:"
        for model in models:
            ret += f"\n{i}. {model.id}"
            i += 1
        ret += "\nTips: 使用 /model 模型名/编号，即可实时更换模型。如目标模型不存在于上表，请输入模型名。"
        logger.debug(ret)
        return ret
        
    def his(self, message: AstrMessageEvent):
        tokens = command_parser.parse(message.message_str)
        size_per_page = 3
        page = 1
        if tokens.len == 2:
            try:
                page = int(tokens.get(1))
            except BaseException as e:
                message.set_result(MessageEventResult().message("页码格式错误"))
        contexts, total_num = self.provider.dump_contexts_page(message.session_id, size_per_page, page=page)
        t_pages = total_num // size_per_page + 1
        message.set_result(MessageEventResult().message(f"历史记录：\n\n{contexts}\n第 {page} 页 | 共 {t_pages} 页\n\n*输入 /his 2 跳转到第 2 页"))
    
    def status(self, message: AstrMessageEvent):
        keys_data = self.provider.get_all_keys()
        ret = "{} Key"
        for k in keys_data:
            ret += "\n|- " + k[:8]

        ret += "\n当前模型: " + self.provider.get_model()

        message.set_result(MessageEventResult().message(ret).use_t2i(False))
    
    async def switch(self, message: AstrMessageEvent):
        '''
        切换账号
        '''
        tokens = command_parser.parse(message.message_str)
        if tokens.len == 1:
            ret = ""
            curr_ = self.provider.get_curr_key()
            if curr_ is None:
                ret += "当前您未选择账号。输入/switch <账号序号>切换账号。使用 /status 查看账号列表。"
            else:
                ret += f"当前您选择的账号为：{curr_[:8]}。输入/switch <账号序号>切换账号。使用 /status 查看账号列表。"
            message.set_result(MessageEventResult().message(ret))
        elif tokens.len == 2:
            try:
                key_stat = self.provider.get_keys_data()
                index = int(tokens.get(1))
                if index > len(key_stat) or index < 1:
                    message.set_result(MessageEventResult().message("账号序号错误。"))
                else:
                    try:
                        new_key = list(key_stat.keys())[index-1]
                        self.provider.set_key(new_key)
                    except BaseException as e:
                        message.set_result(MessageEventResult().message("切换账号未知错误: "+str(e)))
                    message.set_result(MessageEventResult().message("切换账号成功。")    )
            except BaseException as e:
                message.set_result(MessageEventResult().message("切换账号错误。"))
        else:
            message.set_result(MessageEventResult().message("参数过多。"))

    
    def persona(self, message: AstrMessageEvent):
        l = message.message_str.split(" ")
        if len(l) == 1:
            message.set_result(
                MessageEventResult().message(f"""[Persona]

- 设置人格: `/persona 人格名`, 如 /persona 编剧
- 人格列表: `/persona list`
- 人格详细信息: `/persona view 人格名`
- 自定义人格: /persona 人格文本
- 重置 LLM 会话(清除人格): /reset
- 重置 LLM 会话(保留人格): /reset p

【当前人格】: {str(self.provider.curr_personality['prompt'])}
"""))
        elif l[1] == "list":
            msg = "人格列表：\n"
            for key in personalities.keys():
                msg += f"- {key}\n"
            msg += '\n\n*输入 `/persona view 人格名` 查看人格详细信息'
            message.set_result(MessageEventResult().message(msg))
        elif l[1] == "view":
            if len(l) == 2:
                message.set_result(MessageEventResult().message("请输入人格名"))
            ps = l[2].strip()
            if ps in personalities:
                msg = f"人格{ps}的详细信息：\n"
                msg += f"{personalities[ps]}\n"
            else:
                msg = f"人格{ps}不存在"
            message.set_result(MessageEventResult().message(msg))
        else:
            ps = "".join(l[1:]).strip()
            if ps in personalities:
                self.provider.curr_personality = Personality(name=ps, prompt=personalities[ps])
                message.set_result(MessageEventResult().message(f"人格已设置。 \n人格信息: {ps}"))
            else:
                self.provider.curr_personality = Personality(name="自定义人格", prompt=ps)
                message.set_result(MessageEventResult().message(f"人格已设置。 \n人格信息: {ps}"))

    async def draw(self, message: AstrMessageEvent):
        prompt = message.message_str.removeprefix("画")
        img_url = await self.provider.image_generate(prompt)
        message.set_result(MessageEventResult().url_image(img_url))