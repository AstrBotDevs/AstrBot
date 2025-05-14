import uuid
import base64
import json
import requests
from ..provider import TTSProvider
from ..entities import ProviderType
from ..register import register_provider_adapter

@register_provider_adapter(
    "volcengine_tts", "火山引擎 TTS", provider_type=ProviderType.TEXT_TO_SPEECH
)
class ProviderVolcengineTTS(TTSProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        self.appid = provider_config.get("appid", "")
        self.cluster = provider_config.get("cluster", "")
        self.voice_type = provider_config.get("voice_type", "xiaoyun")
        self.api_base = provider_config.get("api_base", "https://openspeech.bytedance.com/api/v1/tts")
        self.timeout = provider_config.get("timeout", "20")

    def _build_request_payload(self, text: str) -> dict:
        return {
            "app": {
                "appid": self.appid,
                "token": self.api_key,
                "cluster": self.cluster
            },
            "user": {
                "uid": str(uuid.uuid4())
            },
            "audio": {
                "voice_type": self.voice_type,
                "encoding": "mp3",
                "speed_ratio": 1.0,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": text,
                "text_type": "plain",
                "operation": "query",
                "with_frontend": 1,
                "frontend_type": "unitTson"
            }
        }

    def get_audio(self, text: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = self._build_request_payload(text)
        response = requests.post(self.api_base, json=payload, headers=headers, timeout=self.timeout)

        if response.status_code == 200:
            resp_data = response.json()
            if "data" in resp_data:
                audio_data = base64.b64decode(resp_data["data"])
                file_path = f"data/temp/volcengine_tts_{uuid.uuid4()}.mp3"
                with open(file_path, "wb") as audio_file:
                    audio_file.write(audio_data)
                return file_path
            else:
                raise Exception(f"火山引擎 TTS API 返回错误: {resp_data}")
        else:
            raise Exception(f"火山引擎 TTS API 请求失败: {response.status_code}, {response.text}")