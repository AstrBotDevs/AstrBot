import json
import os
import uuid
from typing import Iterator

import requests

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

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

        self.voice_setting: dict = {
            "speed": provider_config.get("minimax-voice-speed", 1.0),
            "vol": provider_config.get("minimax-voice-vol", 1.0),
            "pitch": provider_config.get("minimax-voice-pitch", 0),
            "voice_id": provider_config.get("minimax-voice-id", ""),
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

        self.concat_base_url: str = self.api_base + "?GroupId=" + self.group_id
        self.headers = {
            "Authorization": f"Bearer {self.chosen_api_key}",
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
        }

    def _build_tts_stream_body(self, text: str):
        """构建流式请求体"""
        body = json.dumps(
            {
                "model": self.model_name,
                "text": text,
                "stream": True,
                "language_boost": self.lang_boost,
                "voice_setting": self.voice_setting,
                "audio_setting": self.audio_setting,
            }
        )
        return body

    def _call_tts_stream(self, text: str) -> Iterator[bytes]:
        """进行流式请求"""
        tts_body = self._build_tts_stream_body(text)
        try:
            response = requests.request(
                "POST",
                self.concat_base_url,
                stream=True,
                headers=self.headers,
                data=tts_body,
            )
            response.raise_for_status()
            for chunk in response.raw:
                if chunk:
                    if chunk[:5] == b"data:":
                        data = json.loads(chunk[5:])
                        if "data" in data and "extra_info" not in data:
                            if "audio" in data["data"]:
                                audio = data["data"]["audio"]
                                yield audio
        except requests.exceptions.RequestException as e:
            raise Exception(f"MiniMax TTS API请求失败: {str(e)}")

    def _audio_play(self, audio_stream: Iterator[bytes]) -> bytes:
        """解码数据流到audio比特流"""
        audio = b""
        for chunk in audio_stream:
            if chunk is not None and chunk != "\n":
                decoded_hex = bytes.fromhex(chunk)
                audio += decoded_hex

        return audio

    async def get_audio(self, text: str) -> str:
        temp_dir = os.path.join(get_astrbot_data_path(), "temp")
        path = os.path.join(temp_dir, f"minimax_tts_api_{uuid.uuid4()}.mp3")

        try:
            audio_chunk_iterator = self._call_tts_stream(text)
            audio = self._audio_play(audio_chunk_iterator)

            # 结果保存至文件
            with open(path, "wb") as file:
                file.write(audio)

            return path

        except requests.exceptions.RequestException as e:
            raise e
