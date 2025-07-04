import uuid
import time
import json
import re
import hashlib
import random
import asyncio
from pathlib import Path
from typing import Dict
from xml.sax.saxutils import escape

from httpx import AsyncClient, Timeout
from astrbot.core.config.default import VERSION

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter

TEMP_DIR = Path("data/temp/azure_tts")
TEMP_DIR.mkdir(parents=True, exist_ok=True)


class OTTSProvider:
    def __init__(self, config: Dict):
        self.skey = config["OTTS_SKEY"]
        self.api_url = config["OTTS_URL"]
        self.auth_time_url = config["OTTS_AUTH_TIME"]
        self.time_offset = 0
        self.last_sync_time = 0
        self.timeout = Timeout(10.0)
        self.retry_count = 3
        self.client = None

    async def __aenter__(self):
        self.client = AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def _sync_time(self):
        try:
            response = await self.client.get(self.auth_time_url)
            response.raise_for_status()
            server_time = int(response.json()["timestamp"])
            local_time = int(time.time())
            self.time_offset = server_time - local_time
            self.last_sync_time = local_time
        except Exception as e:
            if time.time() - self.last_sync_time > 3600:
                raise RuntimeError("时间同步失败") from e

    async def _generate_signature(self) -> str:
        await self._sync_time()
        timestamp = int(time.time()) + self.time_offset
        nonce = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=10))
        path = re.sub(r"^https?://[^/]+", "", self.api_url) or "/"
        return f"{timestamp}-{nonce}-0-{hashlib.md5(f'{path}-{timestamp}-{nonce}-0-{self.skey}'.encode()).hexdigest()}"

    async def get_audio(self, text: str, voice_params: Dict) -> str:
        file_path = TEMP_DIR / f"otts-{uuid.uuid4()}.wav"
        signature = await self._generate_signature()
        for attempt in range(self.retry_count):
            try:
                response = await self.client.post(
                    f"{self.api_url}?sign={signature}",
                    data={
                        "text": text,
                        "voice": voice_params["voice"],
                        "style": voice_params["style"],
                        "role": voice_params["role"],
                        "rate": voice_params["rate"],
                        "volume": voice_params["volume"],
                    },
                    headers={
                        "User-Agent": f"AstrBot/{VERSION}",
                        "UAK": "AstrBot/AzureTTS",
                    },
                )
                response.raise_for_status()
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with file_path.open("wb") as f:
                    async for chunk in response.aiter_bytes(4096):
                        f.write(chunk)
                return str(file_path.resolve())
            except Exception as e:
                if attempt == self.retry_count - 1:
                    raise RuntimeError(f"OTTS请求失败: {str(e)}") from e
                await asyncio.sleep(0.5 * (attempt + 1))


class AzureNativeProvider(TTSProvider):
    def __init__(self, provider_config: dict, provider_settings: dict):
        super().__init__(provider_config, provider_settings)
        self.subscription_key = provider_config.get(
            "azure_tts_subscription_key", ""
        ).strip()
        if not re.fullmatch(r"^[a-zA-Z0-9]{32}$", self.subscription_key):
            raise ValueError("无效的Azure订阅密钥")
        self.region = provider_config.get("azure_tts_region", "eastus").strip()
        self.endpoint = (
            f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1"
        )
        self.client = None
        self.token = None
        self.token_expire = 0
        self.voice_params = {
            "voice": provider_config.get("azure_tts_voice", "zh-CN-YunxiaNeural"),
            "style": provider_config.get("azure_tts_style", "cheerful"),
            "role": provider_config.get("azure_tts_role", "Boy"),
            "rate": provider_config.get("azure_tts_rate", "1"),
            "volume": provider_config.get("azure_tts_volume", "100"),
        }

    async def __aenter__(self):
        self.client = AsyncClient(
            headers={
                "User-Agent": f"AstrBot/{VERSION}",
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "riff-48khz-16bit-mono-pcm",
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def _refresh_token(self):
        token_url = (
            f"https://{self.region}.api.cognitive.microsoft.com/sts/v1.0/issuetoken"
        )
        response = await self.client.post(
            token_url, headers={"Ocp-Apim-Subscription-Key": self.subscription_key}
        )
        response.raise_for_status()
        self.token = response.text
        self.token_expire = time.time() + 540

    async def get_audio(self, text: str) -> str:
        if not self.token or time.time() > self.token_expire:
            await self._refresh_token()
        file_path = TEMP_DIR / f"azure-{uuid.uuid4()}.wav"
        ssml = f"""<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'
            xmlns:mstts='http://www.w3.org/2001/mstts' xml:lang='zh-CN'>
            <voice name='{escape(self.voice_params["voice"])}'>
                <mstts:express-as style='{escape(self.voice_params["style"])}'
                    role='{escape(self.voice_params["role"])}'>
                    <prosody rate='{escape(self.voice_params["rate"])}'
                        volume='{escape(self.voice_params["volume"])}'>
                        {escape(text)}
                    </prosody>
                </mstts:express-as>
            </voice>
        </speak>"""
        response = await self.client.post(
            self.endpoint,
            content=ssml,
            headers={
                "Authorization": f"Bearer {self.token}",
                "User-Agent": f"AstrBot/{VERSION}",
            },
        )
        response.raise_for_status()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("wb") as f:
            for chunk in response.iter_bytes(4096):
                f.write(chunk)
        return str(file_path.resolve())


@register_provider_adapter("azure_tts", "Azure TTS", ProviderType.TEXT_TO_SPEECH)
class AzureTTSProvider(TTSProvider):
    def __init__(self, provider_config: dict, provider_settings: dict):
        super().__init__(provider_config, provider_settings)
        key_value = provider_config.get("azure_tts_subscription_key", "")
        self.provider = self._parse_provider(key_value, provider_config)

    def _parse_provider(self, key_value: str, config: dict) -> TTSProvider:
        if key_value.lower().startswith("other["):
            try:
                match = re.match(r"other\[(.*)\]", key_value, re.DOTALL)
                if not match:
                    raise ValueError("无效的other[...]格式，应形如 other[{...}]")
                json_str = match.group(1).strip()
                otts_config = json.loads(json_str)
                required = {"OTTS_SKEY", "OTTS_URL", "OTTS_AUTH_TIME"}
                if missing := required - otts_config.keys():
                    raise ValueError(f"缺少OTTS参数: {', '.join(missing)}")
                return OTTSProvider(otts_config)
            except json.JSONDecodeError as e:
                error_msg = (
                    f"JSON解析失败，请检查格式（错误位置：行 {e.lineno} 列 {e.colno}）\n"
                    f"错误详情: {e.msg}\n"
                    f"错误上下文: {json_str[max(0, e.pos - 30) : e.pos + 30]}"
                )
                raise ValueError(error_msg) from e
            except KeyError as e:
                raise ValueError(f"配置错误: 缺少必要参数 {e}") from e
        if re.fullmatch(r"^[a-zA-Z0-9]{32}$", key_value):
            return AzureNativeProvider(config, self.provider_settings)
        raise ValueError("订阅密钥格式无效，应为32位字母数字或other[...]格式")

    async def get_audio(self, text: str) -> str:
        if isinstance(self.provider, OTTSProvider):
            async with self.provider as provider:
                return await provider.get_audio(
                    text,
                    {
                        "voice": self.provider_config.get("azure_tts_voice"),
                        "style": self.provider_config.get("azure_tts_style"),
                        "role": self.provider_config.get("azure_tts_role"),
                        "rate": self.provider_config.get("azure_tts_rate"),
                        "volume": self.provider_config.get("azure_tts_volume"),
                    },
                )
        else:
            async with self.provider as provider:
                return await provider.get_audio(text)
