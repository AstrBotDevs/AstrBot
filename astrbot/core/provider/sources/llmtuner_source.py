import os
from llmtuner.chat import ChatModel
from typing import List
from .. import Provider
from ..entities import LLMResponse
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
        default_persona=None,
    ) -> None:
        super().__init__(
            provider_config,
            provider_settings,
            persistant_history,
            db_helper,
            default_persona,
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
        if contexts is None:
            contexts = []
        system_prompt = ""
        new_record = {"role": "user", "content": prompt}
        query_context = [*contexts, new_record]

        # 提取出系统提示
        system_idxs = []
        for idx, context in enumerate(query_context):
            if context["role"] == "system":
                system_idxs.append(idx)

            if "_no_save" in context:
                del context["_no_save"]

        for idx in reversed(system_idxs):
            system_prompt += " " + query_context.pop(idx)["content"]

        conf = {
            "messages": query_context,
            "system": system_prompt,
        }
        if func_tool:
            tool_list = func_tool.get_func_desc_openai_style()
            if tool_list:
                conf["tools"] = tool_list

        responses = await self.model.achat(**conf)

        llm_response = LLMResponse("assistant", responses[-1].response_text)

        return llm_response

    async def text_chat_stream(
        self,
        prompt,
        session_id=None,
        image_urls=...,
        func_tool=None,
        contexts=...,
        system_prompt=None,
        tool_calls_result=None,
        **kwargs,
    ):
        # raise NotImplementedError("This method is not implemented yet.")
        # 调用 text_chat 模拟流式
        llm_response = await self.text_chat(
            prompt=prompt,
            session_id=session_id,
            image_urls=image_urls,
            func_tool=func_tool,
            contexts=contexts,
            system_prompt=system_prompt,
            tool_calls_result=tool_calls_result,
        )
        llm_response.is_chunk = True
        yield llm_response
        llm_response.is_chunk = False
        yield llm_response

    async def get_current_key(self):
        return "none"

    async def set_key(self, key):
        pass

    async def get_models(self):
        return [self.get_model()]
