import json
import os
import uuid
from collections.abc import AsyncIterator

import aiofiles
import aiohttp

from astrbot.api import logger
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.provider import TTSProvider
from astrbot.core.provider.register import register_provider_adapter
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path


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
            {"voice_id": "Chinese (Mandarin)_Warm_Girl", "weight": 1},
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
                aiohttp.ClientSession() as session,
                session.post(
                    self.concat_base_url,
                    headers=self.headers,
                    data=self._build_tts_stream_body(text),
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response,
            ):
                # MiniMax returns a JSON error body (not SSE) for cases like quota /
                # rate-limit exceeded, invalid voice_id / model, API key issues.
                # Some of those come with 4xx HTTP status, others with 200 + a
                # JSON error body. Check Content-Type *before* raise_for_status
                # so we surface the structured `base_resp.status_code /
                # status_msg` even on 4xx responses, instead of an opaque
                # aiohttp.ClientResponseError. MIME types are case-insensitive
                # (RFC 7231 §3.1.1.1) and may include parameters like
                # `application/json; charset=utf-8` — lower-case the value and
                # strip parameters before comparing.
                content_type = (
                    response.headers.get("Content-Type", "")
                    .lower()
                    .split(";", 1)[0]
                    .strip()
                )
                if content_type != "text/event-stream":
                    body = await response.text()
                    err_msg = body[:200] or "empty response body"
                    err_code = "unknown"
                    try:
                        err_data = json.loads(body)
                        # Guard against `base_resp: null`, missing key, or a JSON
                        # array root — all of which would have raised
                        # AttributeError on `.get(...)` before this change.
                        if isinstance(err_data, dict):
                            base_resp = err_data.get("base_resp")
                            if isinstance(base_resp, dict):
                                err_msg = base_resp.get("status_msg", err_msg)
                                err_code = base_resp.get("status_code", err_code)
                    except json.JSONDecodeError:
                        pass
                    raise RuntimeError(
                        f"MiniMax TTS API error (code={err_code}): {err_msg}"
                    )

                # Non-SSE error path is exhausted — only here do we treat a
                # non-2xx status as a transport-level error.
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
                                        "audio",
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
            raise Exception(f"MiniMax TTS API请求失败: {e!s}") from e

    async def _audio_play(self, audio_stream: AsyncIterator[str]) -> bytes:
        """解码数据流到 audio 比特流"""
        chunks = []
        async for chunk in audio_stream:
            if chunk.strip():
                chunks.append(bytes.fromhex(chunk.strip()))
        return b"".join(chunks)

    async def get_audio(self, text: str) -> str:
        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)
        path = os.path.join(temp_dir, f"minimax_tts_api_{uuid.uuid4()}.wav")

        try:
            # 直接将异步生成器传递给 _audio_play 方法
            audio_stream = self._call_tts_stream(text)
            audio = await self._audio_play(audio_stream)

            # 检查音频数据是否为空
            if not audio or len(audio) == 0:
                raise Exception(
                    "MiniMax TTS API returned empty audio data. "
                    "Please verify your configuration, especially the 'group_id' parameter. "
                    "You can find your group_id in Account Management -> Basic Information on the MiniMax platform.",
                )

            # 结果保存至文件
            async with aiofiles.open(path, "wb") as file:
                await file.write(audio)

            return path

        except aiohttp.ClientError as e:
            raise Exception(f"MiniMax TTS API request failed: {e!s}") from e
