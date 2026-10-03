import json
import os
import struct
from collections.abc import AsyncIterator

import aiohttp

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.datetime_utils import generate_timestamp_id

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


def _repair_wav_header(audio: bytes) -> bytes:
    """按实际数据长度重建流式 WAV 的 RIFF/data 头部。

    MiniMax 以 stream=True 返回经服务端 ffmpeg 转出的流式 WAV，总长度
    未知，RIFF 总长度与 data 块长度只能写 0xFFFFFFFF 占位。浏览器解码
    器可以容忍这种头部，但 Android WebView、系统播放器等严格解码器会
    直接判定文件非法。合成结束后按真实长度回填，若头部已一致则原样
    返回。
    """
    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        return audio
    pos, fmt, data_start, data_size = 12, b"", 0, 0
    while pos + 8 <= len(audio):
        cid = audio[pos : pos + 4]
        csize = struct.unpack_from("<I", audio, pos + 4)[0]
        chunk_start, remaining = pos + 8, max(0, len(audio) - (pos + 8))
        actual = min(csize, remaining)
        if cid == b"fmt ":
            fmt = audio[chunk_start : chunk_start + actual]
        elif cid == b"data":
            data_start, data_size = chunk_start, actual
            break
        if csize > remaining:
            break
        pos = chunk_start + csize + (csize % 2)
    if not fmt or not data_start or not data_size:
        return audio
    if (
        struct.unpack_from("<I", audio, 4)[0] == len(audio) - 8
        and struct.unpack_from("<I", audio, data_start - 4)[0] == data_size
    ):
        return audio
    payload = audio[data_start : data_start + data_size]
    return b"".join(
        (
            b"RIFF",
            struct.pack("<I", 4 + (8 + len(fmt)) + (8 + len(payload))),
            b"WAVE",
            b"fmt ",
            struct.pack("<I", len(fmt)),
            fmt,
            b"data",
            struct.pack("<I", len(payload)),
            payload,
        )
    )


@register_provider_adapter(
    "minimax_tts_api",
    "MiniMax TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
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
            "api_base",
            "https://api.minimax.chat/v1/t2a_v2",
        )
        self.group_id: str = provider_config.get("minimax-group-id", "")
        self.set_model(provider_config.get("model", ""))
        self.lang_boost: str = provider_config.get("minimax-langboost", "auto")
        self.is_timber_weight: bool = provider_config.get(
            "minimax-is-timber-weight",
            False,
        )
        default_timber_weight = [
            {"voice_id": "Chinese (Mandarin)_Warm_Girl", "weight": 1}
        ]
        raw_timber_weight = provider_config.get("minimax-timber-weight", "")
        if not raw_timber_weight:
            self.timber_weight = default_timber_weight
        else:
            try:
                self.timber_weight = json.loads(raw_timber_weight)
            except json.JSONDecodeError:
                logger.warning(
                    "MiniMax TTS 权重配置解析失败，将使用默认值。 raw_value: %s",
                    raw_timber_weight,
                )
                self.timber_weight = default_timber_weight

        self.voice_setting: dict = {
            "speed": provider_config.get("minimax-voice-speed", 1.0),
            "vol": provider_config.get("minimax-voice-vol", 1.0),
            "pitch": provider_config.get("minimax-voice-pitch", 0),
            "voice_id": ""
            if self.is_timber_weight
            else provider_config.get("minimax-voice-id", ""),
            "emotion": provider_config.get("minimax-voice-emotion", "auto"),
            "latex_read": provider_config.get("minimax-voice-latex", False),
            "english_normalization": provider_config.get(
                "minimax-voice-english-normalization",
                False,
            ),
        }

        if self.voice_setting["emotion"] == "auto":
            self.voice_setting.pop("emotion", None)

        self.audio_setting: dict = {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "wav",
        }

        self.concat_base_url: str = f"{self.api_base}?GroupId={self.group_id}"
        self.headers = {
            "Authorization": f"Bearer {self.chosen_api_key}",
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
        }

    def _build_tts_stream_body(self, text: str):
        """构建流式请求体"""
        dict_body: dict[str, object] = {
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

    async def _call_tts_stream(self, text: str) -> AsyncIterator[str]:
        """进行流式请求"""
        try:
            async with (
                aiohttp.ClientSession(headers=self.request_headers) as session,
                session.post(
                    self.concat_base_url,
                    headers=self.headers,
                    data=self._build_tts_stream_body(text),
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response,
            ):
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
                                    audio: str | None = data.get("data", {}).get(
                                        "audio"
                                    )
                                    if audio is not None:
                                        yield audio
                                except json.JSONDecodeError:
                                    logger.warning(
                                        "Failed to parse JSON data from SSE message",
                                    )
                                    continue
                        except ValueError:
                            buffer = buffer[-1024:]

        except aiohttp.ClientError as e:
            raise Exception(f"MiniMax TTS API请求失败: {e!s}")

    async def _audio_play(self, audio_stream: AsyncIterator[str]) -> bytes:
        """解码数据流到 audio 比特流"""
        chunks = []
        async for chunk in audio_stream:
            if chunk.strip():
                chunks.append(bytes.fromhex(chunk.strip()))
        return _repair_wav_header(b"".join(chunks))

    async def get_audio(self, text: str) -> str:
        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)
        path = os.path.join(temp_dir, f"minimax_tts_api_{generate_timestamp_id()}.wav")

        try:
            # 直接将异步生成器传递给 _audio_play 方法
            audio_stream = self._call_tts_stream(text)
            audio = await self._audio_play(audio_stream)

            # 检查音频数据是否为空
            if not audio or len(audio) == 0:
                raise Exception(
                    "MiniMax TTS API returned empty audio data. "
                    "Please verify your configuration, especially the 'group_id' parameter. "
                    "You can find your group_id in Account Management -> Basic Information on the MiniMax platform."
                )

            # 结果保存至文件
            with open(path, "wb") as file:
                file.write(audio)

            return path

        except aiohttp.ClientError as e:
            raise Exception(f"MiniMax TTS API request failed: {e!s}")
