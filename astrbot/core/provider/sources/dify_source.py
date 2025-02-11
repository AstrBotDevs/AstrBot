from typing import List
from .. import Provider, Personality
from ..entites import LLMResponse
from ..func_tool_manager import FuncCall
from astrbot.core.db import BaseDatabase
from ..register import register_provider_adapter
from astrbot.core.utils.dify_api_client import DifyAPIClient
from astrbot.core.utils.io import download_image_by_url
from astrbot.core import logger, sp

@register_provider_adapter("dify", "Dify APP 适配器。")
class ProviderDify(Provider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
        db_helper: BaseDatabase,
        persistant_history=False,
        default_persona: Personality=None
    ) -> None:
        super().__init__(
            provider_config, provider_settings, persistant_history, db_helper, default_persona
        )
        self.api_key = provider_config.get("dify_api_key", "")
        if not self.api_key:
            raise Exception("Dify API Key 不能为空。")
        api_base = provider_config.get("dify_api_base", "https://api.dify.ai/v1")
        self.api_client = DifyAPIClient(self.api_key, api_base)
        self.api_type = provider_config.get("dify_api_type", "")
        if not self.api_type:
            raise Exception("Dify API 类型不能为空。")
        self.model_name = "dify"
        self.workflow_output_key = provider_config.get("dify_workflow_output_key", "astrbot_wf_output")
        self.timeout = provider_config.get("timeout", 120)
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)
        self.conversation_ids = {}
        '''记录当前 session id 的对话 ID'''


    async def text_chat(
        self,
        prompt: str,
        session_id: str = None,
        image_urls: List[str] = [],
        func_tool: FuncCall = None,
        contexts: List = None,
        system_prompt: str = None,
        **kwargs,
    ) -> LLMResponse:
        result = ""
        conversation_id = self.conversation_ids.get(session_id, "")
        
        files_payload = []
        for image_url in image_urls:
            if image_url.startswith("http"):
                image_path = await download_image_by_url(image_url)
                file_response = await self.api_client.file_upload(image_path, user=session_id)
                if 'id' not in file_response:
                    logger.warning(f"上传图片后得到未知的 Dify 响应：{file_response}，图片将忽略。")
                    continue
                files_payload.append({
                    "type": "image",
                    "transfer_method": "local_file",
                    "upload_file_id": file_response['id'],
                })
            else:
                # TODO: 处理更多情况
                logger.warning(f"未知的图片链接：{image_url}，图片将忽略。")
        
        # 获得会话变量
        session_vars = sp.get("session_variables", {})
        session_var = session_vars.get(session_id, {})
        
        match self.api_type:
            case "chat" | "agent":
                async for chunk in self.api_client.chat_messages(
                    inputs={
                        **session_var
                    },
                    query=prompt,
                    user=session_id,
                    conversation_id=conversation_id,
                    files=files_payload,
                    timeout=self.timeout
                ):
                    logger.debug(f"dify resp chunk: {chunk}")
                    if chunk['event'] == "message" or \
                        chunk['event'] == "agent_message":
                        result += chunk['answer']
                        if not conversation_id:
                            self.conversation_ids[session_id] = chunk['conversation_id']
                            conversation_id = chunk['conversation_id']
            
            case "workflow":
                async for chunk in self.api_client.workflow_run(
                    inputs={
                        "astrbot_text_query": prompt,
                        "astrbot_session_id": session_id,
                        **session_var
                    },
                    user=session_id,
                    files=files_payload,
                    timeout=self.timeout
                ):
                    match chunk['event']:
                        case "workflow_started":
                            logger.info(f"Dify 工作流(ID: {chunk['workflow_run_id']})开始运行。")
                        case "node_finished":
                            logger.debug(f"Dify 工作流节点(ID: {chunk['data']['node_id']} Title: {chunk['data'].get('title', '')})运行结束。")
                        case "workflow_finished":
                            logger.info(f"Dify 工作流(ID: {chunk['workflow_run_id']})运行结束。")
                            if chunk['data']['error']:
                                logger.error(f"Dify 工作流出现错误：{chunk['data']['error']}")
                                raise Exception(f"Dify 工作流出现错误：{chunk['data']['error']}")
                            if self.workflow_output_key not in chunk['data']['outputs']:
                                raise Exception(f"Dify 工作流的输出不包含指定的键名：{self.workflow_output_key}")
                            result = chunk['data']['outputs'][self.workflow_output_key]
            case _:
                raise Exception(f"未知的 Dify API 类型：{self.api_type}")
        return LLMResponse(role="assistant", completion_text=result)

    async def forget(self, session_id):
        self.conversation_ids.pop(session_id, None)
        return True

    async def get_current_key(self):
        return self.api_key

    async def set_key(self, key):
        raise Exception("Dify 适配器不支持设置 API Key。")

    async def get_models(self):
        return [self.get_model()]

    async def get_human_readable_context(self, session_id, page, page_size):
        raise Exception("暂不支持获得 Dify 的历史消息记录。")

    async def terminate(self):
        await self.api_client.close()