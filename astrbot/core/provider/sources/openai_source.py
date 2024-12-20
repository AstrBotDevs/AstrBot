import traceback
import base64
import json

from openai import AsyncOpenAI, NOT_GIVEN
from openai.types.chat.chat_completion import ChatCompletion
from openai._exceptions import NotFoundError
from astrbot.core.utils.io import download_image_by_url

from astrbot.core.db import BaseDatabase
from astrbot.api.provider import Provider
from astrbot import logger
from astrbot.core.provider.tool import FuncCall
from typing import List
from ..register import register_provider_adapter
from astrbot.core.provider.llm_response import LLMResponse

@register_provider_adapter("openai_chat_completion", "OpenAI API Chat Completion 提供商适配器")
class ProviderOpenAIOfficial(Provider):
    def __init__(
        self, 
        provider_config: dict, 
        provider_settings: dict,
        db_helper: BaseDatabase, 
        persistant_history = True
    ) -> None:
        super().__init__(provider_config, provider_settings, persistant_history, db_helper)
        self.chosen_api_key = None
        self.api_keys: List = provider_config.get("key", [])
        self.chosen_api_key = self.api_keys[0] if len(self.api_keys) > 0 else None

        self.client = AsyncOpenAI(
            api_key=self.chosen_api_key,
            base_url=provider_config.get("api_base", None),
            timeout=provider_config.get("timeout", NOT_GIVEN),
        )
        self.set_model(provider_config['model_config']['model'])
    
    async def get_human_readable_context(self, session_id, page, page_size):
        if session_id not in self.session_memory:
            raise Exception("会话 ID 不存在")
        contexts = []
        temp_contexts = []
        for record in self.session_memory[session_id]:
            if record['role'] == "user":
                temp_contexts.append(f"User: {record['content']}")
            elif record['role'] == "assistant":
                temp_contexts.append(f"Assistant: {record['content']}")
                contexts.insert(0, temp_contexts)
                temp_contexts = []

        # 展平 contexts 列表
        contexts = [item for sublist in contexts for item in sublist]

        # 计算分页
        paged_contexts = contexts[(page-1)*page_size:page*page_size]
        total_pages = len(contexts) // page_size
        if len(contexts) % page_size != 0:
            total_pages += 1
        
        return paged_contexts, total_pages

    async def get_models(self):
        try:
            models_str = []
            models = await self.client.models.list()
            models = models.data
            for model in models:
                models_str.append(model.id)
            return models_str
        except NotFoundError as e:
            raise Exception(f"获取模型列表失败：{e}")
    
    async def pop_record(self, session_id: str, pop_system_prompt: bool = False):
        '''
        弹出第一条记录
        '''
        if session_id not in self.session_memory:
            raise Exception("会话 ID 不存在")

        if len(self.session_memory[session_id]) == 0:
            return None

        for i in range(len(self.session_memory[session_id])):
            # 检查是否是 system prompt
            if not pop_system_prompt and self.session_memory[session_id][i]['user']['role'] == "system":
                # 如果只有一个 system prompt，才不删掉
                f = False
                for j in range(i+1, len(self.session_memory[session_id])):
                    if self.session_memory[session_id][j]['user']['role'] == "system":
                        f = True
                        break
                if not f:
                    continue
            record = self.session_memory[session_id].pop(i)
            break

        return record
    
    async def _query(self, payloads: dict, tools: FuncCall) -> LLMResponse:
        if tools:
            payloads["tools"] = tools.get_func_desc_openai_style()
        
        completion = await self.client.chat.completions.create(
            **payloads,
            stream=False
        )
        
        assert isinstance(completion, ChatCompletion)
        logger.debug(f"completion: {completion.usage}")

        if len(completion.choices) == 0:
            raise Exception("API 返回的 completion 为空。")
        choice = completion.choices[0]
        
        if choice.message.content:
            # text completion
            completion_text = str(choice.message.content).strip()
            return LLMResponse("assistant", completion_text)
        elif choice.message.tool_calls:
            # tools call (function calling)
            args_ls = []
            func_name_ls = []
            for tool_call in choice.message.tool_calls:
                for tool in tools.func_list:
                    if tool.name == tool_call.function.name:
                        args = json.loads(tool_call.function.arguments)
                        args_ls.append(args)
                        func_name_ls.append(tool_call.function.name)
            return LLMResponse(role="tool", tools_call_args=args_ls, tools_call_name=func_name_ls)
        else:
            raise Exception("Internal Error")

    async def text_chat(self,
                        prompt: str,
                        session_id: str,
                        image_urls: List[str]=None,
                        func_tool: FuncCall=None,
                        contexts=None,
                        system_prompt=None,
                        **kwargs
                        ) -> LLMResponse: 
        new_record = await self.assemble_context(prompt, image_urls)
        context_query = []
        if not contexts:
            context_query = [*self.session_memory[session_id], new_record]
            if system_prompt:
                context_query.insert(0, {"role": "system", "content": system_prompt})
        else:
            context_query = contexts
            
        logger.debug(f"请求上下文：{context_query}, {self.get_model()}")
        
        payloads = {
            "messages": context_query,
            **self.provider_config.get("model_config", {})
        }
        
        try:
            llm_response = await self._query(payloads, func_tool)
        except Exception as e:
            if "maximum context length" in str(e):
                logger.warning(f"请求失败：{e}。上下文长度超过限制。尝试弹出最早的记录然后重试。")
                self.pop_record(session_id)
            logger.warning(traceback.format_exc())
        
        if llm_response.role == "assistant":
            # 文本回复
            if not contexts:
                # 添加用户 record
                self.session_memory[session_id].append(new_record)
                # 添加 assistant record
                self.session_memory[session_id].append({
                    "role": "assistant",
                    "content": llm_response.completion_text
                })
                self.db_helper.update_llm_history(session_id, json.dumps(self.session_memory[session_id]), self.provider_config['type'])
        
        return llm_response

    async def forget(self, session_id: str) -> bool:
        self.session_memory[session_id] = []
        return True

    def get_current_key(self) -> str:
        return self.client.api_key

    def get_keys(self) -> List[str]:
        return self.api_keys
    
    def set_key(self, key):
        self.client.api_key = key
        
    async def assemble_context(self, text: str, image_urls: List[str] = None):
        '''
        组装上下文。
        '''
        if image_urls:
            user_content = {"role": "user","content": [{"type": "text", "text": text}]}
            for image_url in image_urls:
                if image_url.startswith("http"):
                    image_path = await download_image_by_url(image_url)
                    image_data = await self.encode_image_bs64(image_path)
                else:
                    image_data = await self.encode_image_bs64(image_url)
                user_content["content"].append({"type": "image_url", "image_url": {"url": image_data}})
            return user_content
        else:
            return {"role": "user","content": text}

    async def encode_image_bs64(self, image_url: str) -> str:
        '''
        将图片转换为 base64
        '''
        if image_url.startswith("base64://"):
            return image_url.replace("base64://", "data:image/jpeg;base64,")
        with open(image_url, "rb") as f:
            image_bs64 = base64.b64encode(f.read()).decode('utf-8')
            return "data:image/jpeg;base64," + image_bs64
        return ''