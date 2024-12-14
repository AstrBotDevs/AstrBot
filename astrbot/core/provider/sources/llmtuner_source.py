import json
import os
from llmtuner.chat import ChatModel
from typing import List
from .. import Provider
from astrbot.core.db import BaseDatabase
from astrbot import logger

from ..register import register_provider_adapter

@register_provider_adapter("llm_tuner", "LLMTuner 适配器, 用于装载使用 LlamaFactory 微调后的模型")
class LLMTunerModelLoader(Provider):
    def __init__(
        self, 
        provider_config: dict, 
        provider_settings: dict,
        db_helper: BaseDatabase, 
        persistant_history = True
    ) -> None:
        super().__init__(provider_config, provider_settings, persistant_history, db_helper)
        self.base_model_path = provider_config['base_model_path']
        self.adapter_model_path = provider_config['adapter_model_path']
        self.model = ChatModel({
            "model_name_or_path": self.base_model_path,
            "adapter_name_or_path": self.adapter_model_path,
            "template": provider_config['llmtuner_template'],
            "finetuning_type": provider_config['finetuning_type'],
            "quantization_bit": provider_config['quantization_bit'],
        })
        self.set_model(os.path.basename(self.base_model_path) + "_" + os.path.basename(self.adapter_model_path))
        
    async def assemble_context(self, text: str, image_urls: List[str] = None):
        '''
        组装上下文。
        '''
        return {"role": "user", "content": text}
        
    async def text_chat(self,
                        prompt: str,
                        session_id: str,
                        image_urls: List[str] = None,
                        tools = None,
                        contexts: List=None,
                        **kwargs) -> str:
        
        system_prompt = ""
        if not contexts:
            contexts = [*self.session_memory[session_id], {"role": "user", "content": prompt}]
            system_prompt = self.curr_personality["prompt"]
        else:
            # 提取出系统提示
            system_idxs = []
            for idx, context in enumerate(contexts):
                if context["role"] == "system":
                    system_idxs.append(idx)
            for idx in reversed(system_idxs):
                system_prompt += " " + contexts.pop(idx)["content"]
            
        logger.debug(f"请求上下文：{contexts}")
        logger.debug(f"请求 System Prompt：{system_prompt}")
        
        conf = {
            "messages": contexts,
            "system": system_prompt,
        }
        if tools:
            conf['tools'] = tools
            
        responses = await self.model.achat(**conf)
        logger.debug(f"返回上下文：{responses}")
        self.db_helper.update_llm_history(session_id, json.dumps(self.session_memory[session_id]), self.meta().type)
        self.session_memory[session_id].append({"role": "user", "content": prompt})
        self.session_memory[session_id].append({"role": "assistant", "content": responses[-1].response_text})
        return responses[-1].response_text

    async def forget(self, session_id):
        logger.info("llmtuner reset")
        self.session_memory[session_id] = []
        return True
    
    async def get_current_key(self):
        return "none"
    
    async def set_key(self, key):
        pass
    
    async def get_models(self):
        return [self.get_model()]
    

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