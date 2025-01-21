import traceback
import base64
import json
import aiohttp
from astrbot.core.utils.io import download_image_by_url
from astrbot.core.db import BaseDatabase
from astrbot.api.provider import Provider, Personality
from astrbot import logger
from astrbot.core.provider.func_tool_manager import FuncCall
from typing import List
from ..register import register_provider_adapter
from astrbot.core.provider.entites import LLMResponse

class SimpleGoogleGenAIClient():
    def __init__(self, api_key: str, api_base: str):
        self.api_key = api_key
        if api_base.endswith("/"):
            self.api_base = api_base[:-1]
        else:
            self.api_base = api_base
        self.client = aiohttp.ClientSession(trust_env=True)
        
    async def models_list(self) -> List[str]:
        request_url = f"{self.api_base}/v1beta/models?key={self.api_key}"
        async with self.client.get(request_url, timeout=10) as resp:
            response = await resp.json()
            
            models = []
            for model in response["models"]:
                if 'generateContent' in model["supportedGenerationMethods"]:
                    models.append(model["name"].replace("models/", ""))
            return models

    async def generate_content(
        self, 
        contents: List[dict], 
        model: str="gemini-1.5-flash", 
        system_instruction: str="",
        tools: dict=None
    ):
        payload = {}
        if system_instruction:
            payload["system_instruction"] = {
                "parts": {"text": system_instruction}
            }
        if tools:
            payload["tools"] = [tools]
        payload["contents"] = contents
        logger.debug(f"payload: {payload}")
        request_url = f"{self.api_base}/v1beta/models/{model}:generateContent?key={self.api_key}"
        async with self.client.post(request_url, json=payload, timeout=10) as resp:
            response = await resp.json()
            return response


@register_provider_adapter("googlegenai_chat_completion", "Google Gemini Chat Completion 提供商适配器")
class ProviderGoogleGenAI(Provider):
    def __init__(
        self, 
        provider_config: dict, 
        provider_settings: dict,
        db_helper: BaseDatabase, 
        persistant_history = True,
        default_persona: Personality=None
    ) -> None:
        super().__init__(provider_config, provider_settings, persistant_history, db_helper, default_persona)
        self.chosen_api_key = None
        self.api_keys: List = provider_config.get("key", [])
        self.chosen_api_key = self.api_keys[0] if len(self.api_keys) > 0 else None
        
        self.client = SimpleGoogleGenAIClient(
            api_key=self.chosen_api_key,
            api_base=provider_config.get("api_base", None)
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
        return await self.client.models_list()
    
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
        tool = None
        if tools:
            tool = tools.get_func_desc_google_genai_style()
            if not tool:
                tool = None
        
        system_instruction = ""
        for message in payloads["messages"]:
            if message["role"] == "system":
                system_instruction = message["content"]
                break
        
        google_genai_conversation = []
        for message in payloads["messages"]:
            if message["role"] == "user":
                if isinstance(message["content"], str):
                    google_genai_conversation.append({
                        "role": "user",
                        "parts": [{"text": message["content"]}]
                    })
                elif isinstance(message["content"], list):
                    # images
                    parts = []
                    for part in message["content"]:
                        if part["type"] == "text":
                            parts.append({"text": part["text"]})
                        elif part["type"] == "image_url":
                            parts.append({"inline_data": {
                                "mime_type": "image/jpeg",
                                "data": part["image_url"]["url"].replace("data:image/jpeg;base64,", "") # base64
                            }})
                    google_genai_conversation.append({
                        "role": "user",
                        "parts": parts
                    })
                        
            elif message["role"] == "assistant":
                google_genai_conversation.append({
                    "role": "model",
                    "parts": [{"text": message["content"]}]
                })
                
        
        logger.debug(f"google_genai_conversation: {google_genai_conversation}")
        
        result = await self.client.generate_content(
            contents=google_genai_conversation,
            model=self.get_model(),
            system_instruction=system_instruction,
            tools=tool
        )
        logger.debug(f"result: {result}")
        
        candidates = result["candidates"][0]['content']['parts']
        llm_response = LLMResponse("assistant")
        for candidate in candidates:
            if 'text' in candidate:
                llm_response.completion_text += candidate['text']
            elif 'functionCall' in candidate:
                llm_response.role = "tool"
                llm_response.tools_call_args.append(candidate['functionCall']['args'])
                llm_response.tools_call_name.append(candidate['functionCall']['name'])
            
        return llm_response


    async def text_chat(
        self,
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
        else:
            context_query = [*contexts, new_record]
        if system_prompt:
            context_query.insert(0, {"role": "system", "content": system_prompt})
            
        for part in context_query:
            if '_no_save' in part:
                del part['_no_save']

        payloads = {
            "messages": context_query,
            **self.provider_config.get("model_config", {})
        }

        try:
            llm_response = await self._query(payloads, func_tool)
            await self.save_history(contexts, new_record, session_id, llm_response)
            return llm_response
        except Exception as e:
            if "maximum context length" in str(e):
                retry_cnt = 10
                while retry_cnt > 0:
                    logger.warning(f"请求失败：{e}。上下文长度超过限制。尝试弹出最早的记录然后重试。")
                    try:
                        self.pop_record(session_id)
                        llm_response = await self._query(payloads, func_tool)
                        break
                    except Exception as e:
                        if "maximum context length" in str(e):
                            retry_cnt -= 1
                        else:
                            raise e
            else:
                raise e
    
    async def save_history(self, contexts: List, new_record: dict, session_id: str, llm_response: LLMResponse):
        if llm_response.role == "assistant" and session_id:
            # 文本回复
            if not contexts:
                # 添加用户 record
                self.session_memory[session_id].append(new_record)
                # 添加 assistant record
                self.session_memory[session_id].append({
                    "role": "assistant",
                    "content": llm_response.completion_text
                })
            else:
                contexts_to_save = list(filter(lambda item: '_no_save' not in item, contexts))
                self.session_memory[session_id] = [*contexts_to_save, new_record, {
                    "role": "assistant",
                    "content": llm_response.completion_text
                }]
            self.db_helper.update_llm_history(session_id, json.dumps(self.session_memory[session_id]), self.provider_config['type'])
        
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