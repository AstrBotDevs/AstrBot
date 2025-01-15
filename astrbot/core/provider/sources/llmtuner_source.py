import json
import os
from llmtuner.chat import ChatModel
from typing import List
from .. import Provider
from ..entites import LLMResponse
from ..func_tool_manager import FuncCall
from astrbot.core.db import BaseDatabase
from ..register import register_provider_adapter


@register_provider_adapter(
    "llm_tuner", "LLMTuner 适配器, 用于装载使用 LlamaFactory 微调后的模型"
)
class LLMTunerModelLoader(Provider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
        db_helper: BaseDatabase,
        persistant_history=True,
    ) -> None:
        super().__init__(
            provider_config, provider_settings, persistant_history, db_helper
        )
        if not os.path.exists(provider_config["base_model_path"]) or not os.path.exists(
            provider_config["adapter_model_path"]
        ):
            raise FileNotFoundError("模型文件路径不存在。")
        self.base_model_path = provider_config["base_model_path"]
        self.adapter_model_path = provider_config["adapter_model_path"]
        self.model = ChatModel(
            {
                "model_name_or_path": self.base_model_path,
                "adapter_name_or_path": self.adapter_model_path,
                "template": provider_config["llmtuner_template"],
                "finetuning_type": provider_config["finetuning_type"],
                "quantization_bit": provider_config["quantization_bit"],
            }
        )
        self.set_model(
            os.path.basename(self.base_model_path)
            + "_"
            + os.path.basename(self.adapter_model_path)
        )

    async def assemble_context(self, text: str, image_urls: List[str] = None):
        """
        组装上下文。
        """
        return {"role": "user", "content": text}

    async def text_chat(
        self,
        prompt: str,
        session_id: str = None,
        image_urls: List[str] = None,
        func_tool: FuncCall = None,
        contexts: List = None,
        system_prompt: str = None,
        **kwargs,
    ) -> LLMResponse:
        system_prompt = ""
        if not contexts:
            query_context = [
                *self.session_memory[session_id],
                {"role": "user", "content": prompt},
            ]
            system_prompt = self.curr_personality["prompt"]
        else:
            query_context = [*contexts, {"role": "user", "content": prompt}]

        # 提取出系统提示
        system_idxs = []
        for idx, context in enumerate(query_context):
            if context["role"] == "system":
                system_idxs.append(idx)
        for idx in reversed(system_idxs):
            system_prompt += " " + query_context.pop(idx)["content"]

        conf = {
            "messages": query_context,
            "system": system_prompt,
        }
        if func_tool:
            tool_list = func_tool.get_func_desc_openai_style()
            if tool_list:
                conf['tools'] = tool_list

        responses = await self.model.achat(**conf)

        if session_id:
            if not contexts:
                self.session_memory[session_id].append(
                    {"role": "user", "content": prompt}
                )
                self.session_memory[session_id].append(
                    {"role": "assistant", "content": responses[-1].response_text}
                )
            else:
                self.session_memory[session_id] = [
                    *contexts,
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": responses[-1].response_text},
                ]
            self.db_helper.update_llm_history(session_id, json.dumps(self.session_memory[session_id]), self.meta().type)
        return responses[-1].response_text

    async def forget(self, session_id):
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
            if record["role"] == "user":
                temp_contexts.append(f"User: {record['content']}")
            elif record["role"] == "assistant":
                temp_contexts.append(f"Assistant: {record['content']}")
                contexts.insert(0, temp_contexts)
                temp_contexts = []

        # 展平 contexts 列表
        contexts = [item for sublist in contexts for item in sublist]

        # 计算分页
        paged_contexts = contexts[(page - 1) * page_size : page * page_size]
        total_pages = len(contexts) // page_size
        if len(contexts) % page_size != 0:
            total_pages += 1

        return paged_contexts, total_pages
