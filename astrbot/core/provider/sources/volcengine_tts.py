import uuid
import base64
import json
import os
import traceback
import asyncio
import aiohttp
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
        
        host = "openspeech.bytedance.com"
        self.api_base = provider_config.get("api_base", f"https://{host}/api/v1/tts")
        
        self.timeout = provider_config.get("timeout", 20)

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

    async def get_audio(self, text: str) -> str:
        """异步方法获取语音文件路径"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer;{self.api_key}"
        }
        
        payload = self._build_request_payload(text)
        
        # 打印请求信息以便调试
        print(f"请求 URL: {self.api_base}")
        print(f"请求头: {headers}")
        print(f"请求体: {json.dumps(payload, ensure_ascii=False)[:100]}...")
        
        try:
            # 使用 aiohttp 进行异步请求
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_base,
                    data=json.dumps(payload),  # 使用 data 而不是 json 参数
                    headers=headers,
                    timeout=self.timeout
                ) as response:
                    print(f"响应状态码: {response.status}")
                    
                    # 获取响应内容
                    response_text = await response.text()
                    print(f"响应内容: {response_text[:200]}...")
                    
                    if response.status == 200:
                        resp_data = json.loads(response_text)
                        
                        if "data" in resp_data:
                            audio_data = base64.b64decode(resp_data["data"])
                            
                            # 确保目录存在
                            os.makedirs("data/temp", exist_ok=True)
                            
                            file_path = f"data/temp/volcengine_tts_{uuid.uuid4()}.mp3"
                            
                            # 使用线程运行I/O操作，避免阻塞
                            loop = asyncio.get_running_loop()
                            await loop.run_in_executor(
                                None, 
                                lambda: open(file_path, "wb").write(audio_data)
                            )
                            
                            return file_path
                        else:
                            error_msg = resp_data.get("message", "未知错误")
                            raise Exception(f"火山引擎 TTS API 返回错误: {error_msg}")
                    else:
                        raise Exception(f"火山引擎 TTS API 请求失败: {response.status}, {response_text}")
        
        except Exception as e:
            # 添加更详细的异常捕获
            error_details = traceback.format_exc()
            print(f"火山引擎 TTS 异常详情: {error_details}")
            raise Exception(f"火山引擎 TTS 异常: {str(e)}")