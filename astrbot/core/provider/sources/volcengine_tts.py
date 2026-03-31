import base64
import json
import traceback
import uuid
from typing import Any

import aiohttp
import anyio

from astrbot import logger
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.provider import TTSProvider
from astrbot.core.provider.register import register_provider_adapter
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path


@register_provider_adapter(
    "volcengine_tts",
    "火山引擎 TTS",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderVolcengineTTS(TTSProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        self.appid = provider_config.get("appid", "")
        self.cluster = provider_config.get("volcengine_cluster", "")
        self.voice_type = provider_config.get("volcengine_voice_type", "")
        self.speed_ratio = provider_config.get("volcengine_speed_ratio", 1.0)
        self.api_base = provider_config.get(
            "api_base",
            "https://openspeech.bytedance.com/api/v1/tts",
        )
        self.timeout = provider_config.get("timeout", 20)

    @staticmethod
    def _build_loggable_payload(payload: dict[str, object]) -> dict[str, object]:
        app_payload = payload.get("app")
        user_payload = payload.get("user")
        audio_payload = payload.get("audio")
        request_payload = payload.get("request")

        safe_app: dict[str, Any] = {}
        if isinstance(app_payload, dict):
            appid = app_payload.get("appid")
            if isinstance(appid, str) and appid:
                safe_app["appid"] = appid
            cluster = app_payload.get("cluster")
            if isinstance(cluster, str) and cluster:
                safe_app["cluster"] = cluster

        safe_user: dict[str, Any] = {}
        if isinstance(user_payload, dict):
            uid = user_payload.get("uid")
            if isinstance(uid, str) and uid:
                safe_user["uid"] = uid

        safe_audio: dict[str, Any] = (
            dict(audio_payload) if isinstance(audio_payload, dict) else {}
        )

        safe_request: dict[str, Any] = {}
        if isinstance(request_payload, dict):
            for key in (
                "reqid",
                "text_type",
                "operation",
                "with_frontend",
                "frontend_type",
            ):
                value = request_payload.get(key)
                if value is not None:
                    safe_request[key] = value
            text = request_payload.get("text")
            if isinstance(text, str):
                safe_request["text_length"] = len(text)

        return {
            "app": safe_app,
            "user": safe_user,
            "audio": safe_audio,
            "request": safe_request,
        }

    def _build_request_payload(self, text: str) -> dict:
        return {
            "app": {
                "appid": self.appid,
                "token": self.api_key,
                "cluster": self.cluster,
            },
            "user": {"uid": str(uuid.uuid4())},
            "audio": {
                "voice_type": self.voice_type,
                "encoding": "mp3",
                "speed_ratio": self.speed_ratio,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": text,
                "text_type": "plain",
                "operation": "query",
                "with_frontend": 1,
                "frontend_type": "unitTson",
            },
        }

    async def get_audio(self, text: str) -> str:
        """异步方法获取语音文件路径"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer; {self.api_key}",
        }

        payload = self._build_request_payload(text)
        loggable_payload = self._build_loggable_payload(payload)

        # Keep the request metadata useful for debugging without exposing secrets.
        logger.debug(f"请求 URL: {self.api_base}")
        logger.debug(
            f"请求体: {json.dumps(loggable_payload, ensure_ascii=False)[:100]}..."
        )

        try:
            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    self.api_base,
                    data=json.dumps(payload),
                    headers=headers,
                    timeout=self.timeout,
                ) as response,
            ):
                logger.debug(f"响应状态码: {response.status}")

                response_text = await response.text()
                logger.debug(f"响应内容: {response_text[:200]}...")

                if response.status == 200:
                    resp_data = json.loads(response_text)

                    if "data" in resp_data:
                        audio_data = base64.b64decode(resp_data["data"])

                        temp_dir = anyio.Path(get_astrbot_temp_path())
                        await temp_dir.mkdir(parents=True, exist_ok=True)
                        file_path = temp_dir / f"volcengine_tts_{uuid.uuid4()}.mp3"

                        async with await anyio.open_file(file_path, "wb") as audio_file:
                            await audio_file.write(audio_data)

                        return str(file_path)
                    error_msg = resp_data.get("message", "未知错误")
                    raise Exception(f"火山引擎 TTS API 返回错误: {error_msg}")
                raise Exception(
                    f"火山引擎 TTS API 请求失败: {response.status}, {response_text}",
                )

        except Exception as e:
            error_details = traceback.format_exc()
            logger.debug(f"火山引擎 TTS 异常详情: {error_details}")
            raise Exception(f"火山引擎 TTS 异常: {e!s}")
