import astrbot.core.message.components as Comp
import os
from typing import List
from .. import Provider
from ..entities import LLMResponse
from ..func_tool_manager import FuncCall
from ..register import register_provider_adapter
from astrbot.core.utils.dify_api_client import DifyAPIClient
from astrbot.core.utils.io import download_image_by_url, download_file
from astrbot.core import logger, sp
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


@register_provider_adapter("dify", "Dify APP 适配器。")
class ProviderDify(Provider):
    def __init__(
        self,
        provider_config,
        provider_settings,
        default_persona = None,
    ) -> None:
        super().__init__(
            provider_config,
            provider_settings,
            default_persona,
        )
        self.api_key = provider_config.get("dify_api_key", "")
        if not self.api_key:
            raise Exception("Dify API Key 不能为空。")
        api_base = provider_config.get("dify_api_base", "https://api.dify.ai/v1")
        self.api_type = provider_config.get("dify_api_type", "")
        if not self.api_type:
            raise Exception("Dify API 类型不能为空。")
        self.model_name = "dify"
        self.workflow_output_key = provider_config.get(
            "dify_workflow_output_key", "astrbot_wf_output"
        )
        self.dify_query_input_key = provider_config.get(
            "dify_query_input_key", "astrbot_text_query"
        )
        if not self.dify_query_input_key:
            self.dify_query_input_key = "astrbot_text_query"
        if not self.workflow_output_key:
            self.workflow_output_key = "astrbot_wf_output"
        self.variables: dict = provider_config.get("variables", {})
        self.timeout = provider_config.get("timeout", 120)
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)
        self.conversation_ids = {}
        """记录当前 session id 的对话 ID"""

        self.api_client = DifyAPIClient(self.api_key, api_base)

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
        if image_urls is None:
            image_urls = []
        result = ""
        session_id = session_id or kwargs.get("user") # 1734
        conversation_id = self.conversation_ids.get(session_id, "")

        files_payload = []
        for image_url in image_urls:
            image_path = (
                await download_image_by_url(image_url)
                if image_url.startswith("http")
                else image_url
            )
            file_response = await self.api_client.file_upload(
                image_path, user=session_id
            )
            logger.debug(f"Dify 上传图片响应：{file_response}")
            if "id" not in file_response:
                logger.warning(
                    f"上传图片后得到未知的 Dify 响应：{file_response}，图片将忽略。"
                )
                continue
            files_payload.append(
                {
                    "type": "image",
                    "transfer_method": "local_file",
                    "upload_file_id": file_response["id"],
                }
            )

        # 获得会话变量
        payload_vars = self.variables.copy()
        # 动态变量
        session_vars = sp.get("session_variables", {})
        session_var = session_vars.get(session_id, {})
        payload_vars.update(session_var)

        try:
            match self.api_type:
                case "chat" | "agent" | "chatflow":
                    if not prompt:
                        prompt = "请描述这张图片。"

                    async for chunk in self.api_client.chat_messages(
                        inputs={
                            **payload_vars,
                        },
                        query=prompt,
                        user=session_id,
                        conversation_id=conversation_id,
                        files=files_payload,
                        timeout=self.timeout,
                    ):
                        logger.debug(f"dify resp chunk: {chunk}")
                        if (
                            chunk["event"] == "message"
                            or chunk["event"] == "agent_message"
                        ):
                            result += chunk["answer"]
                            if not conversation_id:
                                self.conversation_ids[session_id] = chunk[
                                    "conversation_id"
                                ]
                                conversation_id = chunk["conversation_id"]
                        elif chunk["event"] == "message_end":
                            logger.debug("Dify message end")
                            break
                        elif chunk["event"] == "error":
                            logger.error(f"Dify 出现错误：{chunk}")
                            raise Exception(
                                f"Dify 出现错误 status: {chunk['status']} message: {chunk['message']}"
                            )

                case "workflow":
                    async for chunk in self.api_client.workflow_run(
                        inputs={
                            self.dify_query_input_key: prompt,
                            "astrbot_session_id": session_id,
                            **payload_vars,
                        },
                        user=session_id,
                        files=files_payload,
                        timeout=self.timeout,
                    ):
                        match chunk["event"]:
                            case "workflow_started":
                                logger.info(
                                    f"Dify 工作流(ID: {chunk['workflow_run_id']})开始运行。"
                                )
                            case "node_finished":
                                logger.debug(
                                    f"Dify 工作流节点(ID: {chunk['data']['node_id']} Title: {chunk['data'].get('title', '')})运行结束。"
                                )
                            case "workflow_finished":
                                logger.info(
                                    f"Dify 工作流(ID: {chunk['workflow_run_id']})运行结束"
                                )
                                logger.debug(f"Dify 工作流结果：{chunk}")
                                if chunk["data"]["error"]:
                                    logger.error(
                                        f"Dify 工作流出现错误：{chunk['data']['error']}"
                                    )
                                    raise Exception(
                                        f"Dify 工作流出现错误：{chunk['data']['error']}"
                                    )
                                if (
                                    self.workflow_output_key
                                    not in chunk["data"]["outputs"]
                                ):
                                    raise Exception(
                                        f"Dify 工作流的输出不包含指定的键名：{self.workflow_output_key}"
                                    )
                                result = chunk
                case _:
                    raise Exception(f"未知的 Dify API 类型：{self.api_type}")
        except Exception as e:
            logger.error(f"Dify 请求失败：{str(e)}")
            return LLMResponse(role="err", completion_text=f"Dify 请求失败：{str(e)}")

        if not result:
            logger.warning("Dify 请求结果为空，请查看 Debug 日志。")

        chain = await self.parse_dify_result(result)

        return LLMResponse(role="assistant", result_chain=chain)

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

    async def parse_dify_result(self, chunk: dict | str) -> MessageChain:
        if isinstance(chunk, str):
            # Chat
            return MessageChain(chain=[Comp.Plain(chunk)])

        async def parse_file(item: dict) -> Comp:
            match item["type"]:
                case "image":
                    return Comp.Image(file=item["url"], url=item["url"])
                case "audio":
                    # 仅支持 wav
                    temp_dir = os.path.join(get_astrbot_data_path(), "temp")
                    path = os.path.join(temp_dir, f"{item['filename']}.wav")
                    await download_file(item["url"], path)
                    return Comp.Image(file=item["url"], url=item["url"])
                case "video":
                    return Comp.Video(file=item["url"])
                case _:
                    return Comp.File(name=item["filename"], file=item["url"])

        output = chunk["data"]["outputs"][self.workflow_output_key]
        chains = []
        if isinstance(output, str):
            # 纯文本输出
            chains.append(Comp.Plain(output))
        elif isinstance(output, list):
            # 主要适配 Dify 的 HTTP 请求结点的多模态输出
            for item in output:
                # handle Array[File]
                if (
                    not isinstance(item, dict)
                    or item.get("dify_model_identity", "") != "__dify__file__"
                ):
                    chains.append(Comp.Plain(str(output)))
                    break
        else:
            chains.append(Comp.Plain(str(output)))

        # scan file
        files = chunk["data"].get("files", [])
        for item in files:
            comp = await parse_file(item)
            chains.append(comp)

        return MessageChain(chain=chains)

    async def forget(self, session_id):
        self.conversation_ids[session_id] = ""
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
