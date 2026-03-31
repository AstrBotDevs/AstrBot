import asyncio
import json
import traceback
import uuid

import aiohttp

from astrbot import logger

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "volcengine_stt",
    "火山引擎 STT",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderVolcengineSTT(STTProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.access_key = provider_config.get("access_key", "")
        self.secret_key = provider_config.get("secret_key", "")
        self.appid = provider_config.get("appid", "")
        self.cluster = provider_config.get("volcengine_cluster", "volc.seedasr.auc")
        self.api_base_submit = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
        self.api_base_query = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
        self.timeout = provider_config.get("timeout", 30)

    def _get_submit_headers(self, request_id: str) -> dict:
        return {
            "Content-Type": "application/json",
            "X-Api-App-Key": self.appid,
            "X-Api-Access-Key": self.access_key,
            "X-Api-Secret-Key": self.secret_key,
            "X-Api-Resource-Id": self.cluster,
            "X-Api-Request-Id": request_id,
            "X-Api-Sequence": "-1",
        }

    def _get_query_headers(self, request_id: str) -> dict:
        return {
            "Content-Type": "application/json",
            "X-Api-App-Key": self.appid,
            "X-Api-Access-Key": self.access_key,
            "X-Api-Secret-Key": self.secret_key,
            "X-Api-Resource-Id": self.cluster,
            "X-Api-Request-Id": request_id,
            "X-Api-Sequence": "-1",
        }

    async def _submit_task(self, audio_url: str, request_id: str) -> dict:
        payload = {
            "app": {
                "appid": self.appid,
                "token": self.access_key,
            },
            "user": {"uid": str(uuid.uuid4())},
            "audio": {
                "format": "mp3",
                "url": audio_url,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
            },
        }

        headers = self._get_submit_headers(request_id)

        logger.debug(f"Volcengine STT 提交任务 headers: {headers}")
        logger.debug(f"Volcengine STT 提交任务 payload: {json.dumps(payload, ensure_ascii=False)}")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.api_base_submit,
                data=json.dumps(payload),
                headers=headers,
                timeout=self.timeout,
            ) as response:
                response_text = await response.text()
                logger.debug(f"Volcengine STT 提交响应: {response.status} - {response_text[:500]}")

                if response.status != 200:
                    raise Exception(f"Volcengine STT 提交任务失败: {response.status}, {response_text}")

                return {"status": response.status, "message": "OK"}

    async def _query_result(self, request_id: str) -> str:
        headers = self._get_query_headers(request_id)

        max_retries = 60
        retry_interval = 1

        for i in range(max_retries):
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_base_query,
                    data="{}",
                    headers=headers,
                    timeout=self.timeout,
                ) as response:
                    if response.status != 200:
                        response_text = await response.text()
                        raise Exception(f"Volcengine STT 查询失败: {response.status}, {response_text}")

                    resp_data = json.loads(await response.text())
                    logger.debug(f"Volcengine STT 查询响应: {json.dumps(resp_data, ensure_ascii=False)[:500]}")

                    status_code = int(response.headers.get("X-Api-Status-Code", "0"))

                    if status_code == 20000000:
                        if "result" in resp_data and "text" in resp_data["result"]:
                            return resp_data["result"]["text"]
                        return ""
                    elif status_code in (20000001, 20000002):
                        logger.debug(f"Volcengine STT 任务处理中 ({i+1}/{max_retries})，等待 {retry_interval}s...")
                        await asyncio.sleep(retry_interval)
                        continue
                    else:
                        message = response.headers.get("X-Api-Message", "未知错误")
                        raise Exception(f"Volcengine STT API 错误: {status_code} - {message}")

        raise Exception("Volcengine STT 任务超时")

    async def get_text(self, audio_url: str) -> str:
        request_id = str(uuid.uuid4())

        if not audio_url.startswith("http"):
            raise ValueError("Volcengine STT 仅支持 URL 格式的音频，请先上传到可访问的 URL")

        try:
            await self._submit_task(audio_url, request_id)
            text = await self._query_result(request_id)
            return text
        except Exception as e:
            error_details = traceback.format_exc()
            logger.error(f"Volcengine STT 异常: {e}")
            logger.debug(f"Volcengine STT 异常详情: {error_details}")
            raise
