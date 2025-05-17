import json
import os
import uuid
import aiohttp
from typing import Dict, List, Union, AsyncIterator
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.api import logger
from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "minimax_tts_api", "MiniMax TTS API", provider_type=ProviderType.TEXT_TO_SPEECH
)
class ProviderMiniMaxTTSAPI(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key: str = provider_config.get("api_key", "")
        self.api_base: str = provider_config.get(
            "api_base", "https://api.minimax.chat/v1/t2a_v2"
        )
        self.group_id: str = provider_config.get("minimax-group-id", "")
        self.set_model(provider_config.get("model", ""))
        self.lang_boost: str = provider_config.get("minimax-langboost", "auto")
        self.is_timber_weight: bool = provider_config.get(
            "minimax-is-timber-weight", False
        )
        self.timber_weight: List[Dict[str, Union[str, int]]] = json.loads(
            provider_config.get(
                "minimax-timber-weight",
                '[{"voice_id": "Chinese (Mandarin)_Warm_Girl", "weight": 1}]',
            )
        )

        self.voice_setting: dict = {
            "speed": provider_config.get("minimax-voice-speed", 1.0),
            "vol": provider_config.get("minimax-voice-vol", 1.0),
            "pitch": provider_config.get("minimax-voice-pitch", 0),
            "voice_id": ""
            if self.is_timber_weight
            else provider_config.get("minimax-voice-id", ""),
            "emotion": provider_config.get("minimax-voice-emotion", "neutral"),
            "latex_read": provider_config.get("minimax-voice-latex", False),
            "english_normalization": provider_config.get(
                "minimax-voice-english-normalization", False
            ),
        }

        self.audio_setting: dict = {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
        }

        self.concat_base_url: str = f"{self.api_base}?GroupId={self.group_id}"
        self.headers = {
            "Authorization": f"Bearer {self.chosen_api_key}",
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
        }

    def _build_tts_stream_body(self, text: str):
        """构建流式请求体"""
        dict_body: Dict[str, object] = {
            "model": self.model_name,
            "text": text,
            "stream": True,
            "language_boost": self.lang_boost,
            "voice_setting": self.voice_setting,
            "audio_setting": self.audio_setting,
        }
        if self.is_timber_weight:
            dict_body["timber_weights"] = self.timber_weight

        return json.dumps(dict_body)

    async def _call_tts_stream(self, text: str) -> AsyncIterator[bytes]:
        """进行流式请求"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.concat_base_url,
                    headers=self.headers,
                    data=self._build_tts_stream_body(text),
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response:
                    response.raise_for_status()

                    buffer = b""
                    while True:
                        chunk = await response.content.read(8192)
                        if not chunk:
                            break

                        buffer += chunk

                        while b"\n\n" in buffer:
                            try:
                                message, buffer = buffer.split(b"\n\n", 1)
                                if message.startswith(b"data: "):
                                    try:
                                        data = json.loads(message[6:])
                                        if "extra_info" in data:
                                            continue
                                        audio = data.get("data", {}).get("audio")
                                        if audio is not None:
                                            yield audio
                                    except json.JSONDecodeError:
                                        logger.warning(
                                            "Failed to parse JSON data from SSE message"
                                        )
                                        continue
                            except ValueError:
                                buffer = buffer[-1024:]

        except aiohttp.ClientError as e:
            raise Exception(f"MiniMax TTS API请求失败: {str(e)}")

    async def _audio_play(self, audio_stream: AsyncIterator[str]) -> bytes:
        """解码数据流到 audio 比特流"""
        chunks = []
        async for chunk in audio_stream:
            if chunk.strip():
                chunks.append(bytes.fromhex(chunk.strip()))
        return b"".join(chunks)

    async def get_audio(self, text: str) -> str:
        temp_dir = os.path.join(get_astrbot_data_path(), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        path = os.path.join(temp_dir, f"minimax_tts_api_{uuid.uuid4()}.mp3")

        try:
            # 直接将异步生成器传递给 _audio_play 方法
            audio_stream = self._call_tts_stream(text)
            audio = await self._audio_play(audio_stream)

            # 结果保存至文件
            with open(path, "wb") as file:
                file.write(audio)

            return path

        except aiohttp.ClientError as e:
            raise e
