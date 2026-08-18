import asyncio
import hashlib
import json
import re
import secrets
import time
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

from httpx import AsyncClient, Timeout

from astrbot import logger
from astrbot.core.config.default import VERSION
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.error_redaction import safe_error

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter

TEMP_DIR = Path(get_astrbot_temp_path()) / "azure_tts"
AZURE_TTS_SUBSCRIPTION_KEY_PATTERN = r"^(?:[a-zA-Z0-9]{32}|[a-zA-Z0-9]{84})$"
_TTS_ERROR = "Azure TTS audio generation failed"


def _remove_incomplete_audio(file_path: Path) -> None:
    try:
        file_path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning(
            "Failed to remove incomplete Azure TTS audio: %s", safe_error("", exc)
        )


class OTTSProvider:
    def __init__(self, config: dict) -> None:
        self.skey = config["OTTS_SKEY"]
        self.api_url = config["OTTS_URL"]
        self.auth_time_url = config["OTTS_AUTH_TIME"]
        self.time_offset = 0
        self.last_sync_time = 0
        self.timeout = Timeout(10.0)
        self.retry_count = 3
        from astrbot.core.utils.proxy_route import resolve_proxy_route

        self._route = resolve_proxy_route(local_config=config)
        self.proxy = self._route.proxy_url or ""
        self._client: AsyncClient | None = None

    @property
    def client(self) -> AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "Client not initialized. Please use 'async with' context."
            )
        return self._client

    async def __aenter__(self):
        if self._client is not None:
            await self.__aexit__(None, None, None)
        self._client = AsyncClient(
            timeout=self.timeout, proxy=self.proxy if self.proxy else None
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            await client.aclose()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Azure OTTS client close failed: %s", safe_error("", exc))

    async def _sync_time(self) -> None:
        try:
            response = await self.client.get(self.auth_time_url)
            response.raise_for_status()
            server_time = int(response.json()["timestamp"])
            local_time = int(time.time())
            self.time_offset = server_time - local_time
            self.last_sync_time = local_time
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if time.time() - self.last_sync_time > 3600:
                logger.warning("Azure OTTS time sync failed: %s", safe_error("", exc))
                raise RuntimeError(_TTS_ERROR) from None

    async def _generate_signature(self) -> str:
        await self._sync_time()
        timestamp = int(time.time()) + self.time_offset
        nonce = "".join(
            secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(10)
        )
        path = re.sub(r"^https?://[^/]+", "", self.api_url) or "/"
        return (
            f"{timestamp}-{nonce}-0-"
            f"{hashlib.md5(f'{path}-{timestamp}-{nonce}-0-{self.skey}'.encode(), usedforsecurity=False).hexdigest()}"
        )

    async def get_audio(self, text: str, voice_params: dict) -> str:
        file_path = TEMP_DIR / f"otts-{uuid.uuid4()}.wav"
        completed = False
        try:
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
                    bytes_written = 0
                    with file_path.open("wb") as f:
                        async for chunk in response.aiter_bytes(4096):
                            if not isinstance(chunk, bytes):
                                raise ValueError(
                                    "Azure OTTS returned invalid audio data"
                                )
                            if not chunk:
                                continue
                            f.write(chunk)
                            bytes_written += len(chunk)
                    if not bytes_written:
                        raise RuntimeError("Azure OTTS returned empty audio")
                    completed = True
                    return str(file_path.resolve())
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    _remove_incomplete_audio(file_path)
                    if attempt == self.retry_count - 1:
                        raise
                    logger.warning(
                        "Azure OTTS attempt %d failed: %s",
                        attempt + 1,
                        safe_error("", exc),
                    )
                    await asyncio.sleep(0.5 * (attempt + 1))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Azure OTTS request failed: %s", safe_error("", exc))
            raise RuntimeError(_TTS_ERROR) from None
        finally:
            if not completed:
                _remove_incomplete_audio(file_path)

        raise RuntimeError(_TTS_ERROR)


class AzureNativeProvider(TTSProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.subscription_key = provider_config.get(
            "azure_tts_subscription_key",
            "",
        ).strip()
        if not re.fullmatch(AZURE_TTS_SUBSCRIPTION_KEY_PATTERN, self.subscription_key):
            raise ValueError("无效的Azure订阅密钥")
        self.region = provider_config.get("azure_tts_region", "eastus").strip()
        self.endpoint = (
            f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1"
        )
        self._client: AsyncClient | None = None
        self.token = None
        self.token_expire = 0
        self.voice_params = {
            "voice": provider_config.get("azure_tts_voice", "zh-CN-YunxiaNeural"),
            "style": provider_config.get("azure_tts_style", "cheerful"),
            "role": provider_config.get("azure_tts_role", "Boy"),
            "rate": provider_config.get("azure_tts_rate", "1"),
            "volume": provider_config.get("azure_tts_volume", "100"),
        }
        from astrbot.core.utils.proxy_route import resolve_proxy_route

        self._route = resolve_proxy_route(local_config=provider_config)
        self.proxy = self._route.proxy_url or ""

    @property
    def client(self) -> AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "Client not initialized. Please use 'async with' context."
            )
        return self._client

    async def __aenter__(self):
        if self._client is not None:
            await self.__aexit__(None, None, None)
        self._client = AsyncClient(
            headers={
                "User-Agent": f"AstrBot/{VERSION}",
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "riff-48khz-16bit-mono-pcm",
            },
            proxy=self.proxy if self.proxy else None,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            await client.aclose()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Azure native TTS client close failed: %s", safe_error("", exc)
            )

    async def _refresh_token(self) -> None:
        try:
            token_url = (
                f"https://{self.region}.api.cognitive.microsoft.com/sts/v1.0/issuetoken"
            )
            response = await self.client.post(
                token_url,
                headers={"Ocp-Apim-Subscription-Key": self.subscription_key},
            )
            response.raise_for_status()
            if not isinstance(response.text, str) or not response.text:
                raise ValueError("Azure native TTS returned an invalid token")
            self.token = response.text
            self.token_expire = time.time() + 540
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "Azure native TTS token refresh failed: %s", safe_error("", exc)
            )
            raise RuntimeError(_TTS_ERROR) from None

    async def get_audio(self, text: str) -> str:
        file_path = TEMP_DIR / f"azure-{uuid.uuid4()}.wav"
        completed = False
        try:
            if not self.token or time.time() > self.token_expire:
                await self._refresh_token()
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
            bytes_written = 0
            with file_path.open("wb") as f:
                for chunk in response.iter_bytes(4096):
                    if not isinstance(chunk, bytes):
                        raise ValueError("Azure native TTS returned invalid audio data")
                    if not chunk:
                        continue
                    f.write(chunk)
                    bytes_written += len(chunk)
            if not bytes_written:
                raise RuntimeError("Azure native TTS returned empty audio")
            completed = True
            return str(file_path.resolve())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Azure native TTS request failed: %s", safe_error("", exc))
            raise RuntimeError(_TTS_ERROR) from None
        finally:
            if not completed:
                _remove_incomplete_audio(file_path)


@register_provider_adapter("azure_tts", "Azure TTS", ProviderType.TEXT_TO_SPEECH)
class AzureTTSProvider(TTSProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        key_value = provider_config.get("azure_tts_subscription_key", "")
        self.provider = self._parse_provider(key_value, provider_config)

    def _parse_provider(
        self, key_value: str, config: dict
    ) -> OTTSProvider | AzureNativeProvider:
        if not isinstance(key_value, str):
            raise ValueError("订阅密钥格式无效，应为32位或84位字母数字或other[...]格式")
        if key_value.lower().startswith("other["):
            try:
                match = re.match(r"other\[(.*)\]", key_value, re.DOTALL)
                if not match:
                    raise ValueError("无效的other[...]格式，应形如 other[{...}]")
                json_str = match.group(1).strip()
                otts_config = json.loads(json_str)
                if not isinstance(otts_config, dict):
                    raise ValueError("OTTS配置必须是JSON对象")
                required = {"OTTS_SKEY", "OTTS_URL", "OTTS_AUTH_TIME"}
                if missing := required - otts_config.keys():
                    raise ValueError(f"缺少OTTS参数: {', '.join(sorted(missing))}")
                return OTTSProvider(otts_config)
            except json.JSONDecodeError as e:
                error_msg = (
                    f"JSON解析失败，请检查格式（错误位置：行 {e.lineno} 列 {e.colno}）"
                )
                raise ValueError(error_msg) from None
        if re.fullmatch(AZURE_TTS_SUBSCRIPTION_KEY_PATTERN, key_value):
            return AzureNativeProvider(config, self.provider_settings)
        raise ValueError("订阅密钥格式无效，应为32位或84位字母数字或other[...]格式")

    async def get_audio(self, text: str) -> str:
        try:
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
            async with self.provider as provider:
                return await provider.get_audio(text)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Azure TTS generation failed: %s", safe_error("", exc))
            raise RuntimeError(_TTS_ERROR) from None

    async def terminate(self) -> None:
        await self.provider.__aexit__(None, None, None)
