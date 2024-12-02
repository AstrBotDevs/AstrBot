import os
import asyncio
import traceback
import base64
import json

from openai import AsyncOpenAI
from openai.types.chat.chat_completion import ChatCompletion
from openai._exceptions import *
from astrbot.core.utils.io import download_image_by_url

from astrbot.core.db import BaseDatabase
from astrbot.api import Provider
from astrbot.core.config.astrbot_config import LLMConfig
from astrbot import logger
from typing import List, Dict
from dataclasses import asdict

class ProviderOpenAIOfficial(Provider):
    def __init__(self, llm_config: LLMConfig, db_helper: BaseDatabase, persistant_history = True) -> None:
        super().__init__(db_helper, llm_config.default_personality, persistant_history)
        self.api_keys = []
        self.chosen_api_key = None
        self.base_url = None
        self.llm_config = llm_config
        self.api_keys = llm_config.key
        if llm_config.api_base:
            self.base_url = llm_config.api_base
        self.chosen_api_key = self.api_keys[0]

        self.client = AsyncOpenAI(
            api_key=self.chosen_api_key,
            base_url=self.base_url
        )
        self.set_model(llm_config.model_config.model)
        
        # 各类模型的配置
        self.image_generator_model_configs = None
        self.embedding_model_configs = None
        if llm_config.image_generation_model_config and llm_config.image_generation_model_config.enable:
            self.image_generator_model_configs: Dict = asdict(
                llm_config.image_generation_model_config)
            self.image_generator_model_configs.pop("enable")
        if llm_config.embedding_model and llm_config.embedding_model.enable:
            self.embedding_model_configs: Dict = asdict(
                llm_config.embedding_model)
            self.embedding_model_configs.pop("enable")

    async def encode_image_bs64(self, image_url: str) -> str:
        '''
        将图片转换为 base64
        '''
        if image_url.startswith("http"):
            image_url = await download_image_by_url(image_url)

        with open(image_url, "rb") as f:
            image_bs64 = base64.b64encode(f.read()).decode('utf-8')
            return "data:image/jpeg;base64," + image_bs64
        return ''

    async def get_models(self):
        models = []
        try:
            models = await self.client.models.list()
        except NotFoundError as e:
            bu = str(self.client.base_url)
            self.client.base_url = bu + "/v1"
            models = await self.client.models.list()
        return models

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

    async def assemble_context(self, contexts: List, text: str, image_urls: List[str] = None):
        '''
        组装上下文。
        '''
        if image_urls:
            for image_url in image_urls:
                base_64_image = await self.encode_image_bs64(image_url)
                user_content = {"role": "user","content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": base_64_image}}
                ]}
                contexts.append(user_content)
        else:
            user_content = {"role": "user","content": text}
            contexts.append(user_content)
    
    async def text_chat(self,
                        prompt: str,
                        session_id: str,
                        image_urls=None,
                        tools=None,
                        contexts=None,
                        **kwargs
                        ) -> str:
        '''
        调用 LLM 进行文本对话。
        
        @param tools: LLM Function-calling 的工具函数
        @param contexts: 如果不为 None，则会原封不动地使用这个上下文进行对话。
        '''
        if os.environ.get("TEST_LLM", "off") != "on" and os.environ.get("TEST_MODE", "off") == "on":
            return "这是一个测试消息。"
            
        await self.assemble_context(self.session_memory[session_id], prompt, image_urls)
        if not contexts:
            contexts = [*self.session_memory[session_id]]
            if self.curr_personality["prompt"]:
                contexts.insert(0, {"role": "system", "content": self.curr_personality["prompt"]})
            
            
        logger.debug(f"请求上下文：{contexts}")
        conf = asdict(self.llm_config.model_config)
        if tools:
            conf['tools'] = tools

        # start request
        retry = 0
        while retry < 3:
            completion_coro = self.client.chat.completions.create(
                messages=contexts,
                stream=False,
                **conf
            )
            try:
                completion = await completion_coro
                break
            except Exception as e:
                retry += 1
                if retry >= 3:
                    logger.error(traceback.format_exc())
                    raise Exception(f"请求失败：{e}。重试次数已达到上限。")
                if "maximum context length" in str(e):
                    logger.warning(f"请求失败：{e}。上下文长度超过限制。尝试弹出最早的记录然后重试。")
                    self.pop_record(session_id)

                logger.warning(traceback.format_exc())
                logger.warning(f"请求失败：{e}。重试第 {retry} 次。")
                await asyncio.sleep(1)

        assert isinstance(completion, ChatCompletion)
        logger.debug(f"completion: {completion.usage}")

        if len(completion.choices) == 0:
            raise Exception("API 返回的 completion 为空。")
        choice = completion.choices[0]
        
        if choice.message.content:
            # 返回文本
            completion_text = str(choice.message.content).strip()
            self.session_memory[session_id].append({
                "role": "assistant",
                "content": completion_text
            })
            self.db_helper.update_llm_history(session_id, json.dumps(self.session_memory[session_id]))
            return completion_text
        elif choice.message.tool_calls and choice.message.tool_calls:
            # tools call (function calling)
            return choice.message.tool_calls[0].function
        else:
            raise Exception("Internal Error")

    async def image_generate(self, prompt: str, session_id: str = None, **kwargs) -> str:
        '''
        生成图片
        '''
        retry = 0
        if not self.image_generator_model_configs:
            return
        while retry < 3:
            try:
                images_response = await self.client.images.generate(
                    prompt=prompt,
                    **self.image_generator_model_configs
                )
                image_url = images_response.data[0].url
                return image_url
            except Exception as e:
                retry += 1
                if retry >= 3:
                    logger.error(traceback.format_exc())
                    raise Exception(f"图片生成请求失败：{e}。重试次数已达到上限。")
                logger.warning(f"图片生成请求失败：{e}。重试第 {retry} 次。")
                await asyncio.sleep(1)

    async def get_embedding(self, text) -> List[float]:
        '''
        获取文本的嵌入
        '''
        if not self.embedding_model_configs:
            return
        try:
            embedding = await self.client.embeddings.create(
                input=text,
                **self.embedding_model_configs
            )
            return embedding.data[0].embedding
        except Exception as e:
            logger.error(f"获取文本嵌入失败：{e}")

    async def forget(self, session_id: str) -> bool:
        self.session_memory[session_id] = []
        return True

    def dump_contexts_page(self, session_id: str, size=5, page=1,):
        '''
        获取缓存的会话
        '''
        contexts_str = ""
        if session_id in self.session_memory:
            for record in self.session_memory[session_id]:
                if record['role'] == "user":
                    text = record['content'][:100] + "..." if len(
                        record['content']) > 100 else record['content']
                    contexts_str += f"User: {text}\n\n"
                elif record['role'] == "assistant":
                    text = record['content'][:100] + "..." if len(
                        record['content']) > 100 else record['content']
                    contexts_str += f"Assistant: {text}\n\n"
        else:
            contexts_str = "会话 ID 不存在。"

        return contexts_str, len(self.session_memory[session_id])

    def get_curr_key(self):
        return self.chosen_api_key

    def get_all_keys(self):
        return self.api_keys