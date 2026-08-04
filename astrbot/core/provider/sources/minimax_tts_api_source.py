import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

import aiohttp

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.datetime_utils import generate_timestamp_id

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


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
        self.voice_design_prompt: str = str(
            provider_config.get("minimax-voice-design-prompt") or "",
        ).strip()
        self.voice_design_preview_text: str = str(
            provider_config.get("minimax-voice-design-preview-text") or "",
        ).strip()
        self.voice_design_voice_id: str = str(
            provider_config.get("minimax-voice-design-voice-id") or "",
        ).strip()
        self.voice_design_prompt_audio: str = str(
            provider_config.get("minimax-voice-design-prompt-audio") or "",
        ).strip()
        self.voice_design_api_base: str = str(
            provider_config.get("minimax-voice-design-api-base") or "",
        ).strip()
        self._voice_design_ready = False
        self._voice_design_lock = asyncio.Lock()
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

    def _voice_design_url(self, path: str) -> str:
        """Build a MiniMax voice-design endpoint URL."""
        if self.voice_design_api_base:
            api_base = self.voice_design_api_base
        else:
            api_base = self.api_base.rstrip("/")
            if not api_base.endswith("/v1"):
                api_base = api_base.rsplit("/", 1)[0]
        return f"{api_base.rstrip('/')}/{path.lstrip('/')}"

    async def _ensure_voice_design(self) -> None:
        """Design the configured voice before the first synthesis request."""
        if not self.voice_design_prompt:
            return
        if self._voice_design_ready:
            return

        async with self._voice_design_lock:
            if self._voice_design_ready:
                return
            if self.is_timber_weight:
                raise ValueError(
                    "MiniMax voice design cannot be combined with mixed voices.",
                )
            if not self.voice_design_preview_text:
                raise ValueError(
                    "MiniMax voice design requires 'minimax-voice-design-preview-text'.",
                )

            if self.voice_design_prompt_audio:
                audio_path = Path(self.voice_design_prompt_audio).expanduser()
                if not audio_path.is_file():
                    raise FileNotFoundError(
                        f"MiniMax voice-design prompt audio file does not exist: {audio_path}",
                    )

                content_type = {
                    ".m4a": "audio/mp4",
                    ".mp3": "audio/mpeg",
                    ".wav": "audio/wav",
                }.get(audio_path.suffix.lower())
                if content_type is None:
                    raise ValueError(
                        "MiniMax voice design supports only .mp3, .m4a, and .wav prompt audio files.",
                    )

                try:
                    async with aiohttp.ClientSession() as session:
                        form = aiohttp.FormData()
                        with audio_path.open("rb") as audio_file:
                            form.add_field(
                                "file",
                                audio_file,
                                filename=audio_path.name,
                                content_type=content_type,
                            )
                            form.add_field("purpose", "prompt_audio")
                            async with session.post(
                                self._voice_design_url("files/upload"),
                                headers={
                                    "Authorization": self.headers["Authorization"]
                                },
                                data=form,
                                timeout=aiohttp.ClientTimeout(total=60),
                            ) as response:
                                if response.status >= 400:
                                    error_text = (await response.text())[:1024]
                                    raise RuntimeError(
                                        "MiniMax voice-design prompt audio upload failed: "
                                        f"HTTP {response.status}: {error_text}",
                                    )
                                upload_data = await response.json(content_type=None)

                        upload_base_resp = upload_data.get("base_resp", {})
                        upload_status_code = upload_base_resp.get("status_code")
                        if upload_status_code not in (None, 0, "0"):
                            status_msg = upload_base_resp.get(
                                "status_msg",
                                "unknown error",
                            )
                            raise RuntimeError(
                                f"MiniMax voice-design prompt audio upload failed: {status_msg}",
                            )

                        file_data = upload_data.get("file") or {}
                        nested_data = upload_data.get("data") or {}
                        file_id = (
                            upload_data.get("file_id")
                            or file_data.get("file_id")
                            or nested_data.get("file_id")
                        )
                        if not file_id:
                            raise RuntimeError(
                                "MiniMax voice-design prompt audio upload returned no file_id.",
                            )
                except aiohttp.ClientError as exc:
                    raise RuntimeError(
                        f"MiniMax voice-design prompt audio upload request failed: {exc!s}",
                    ) from exc

            design_body: dict[str, object] = {
                "prompt": self.voice_design_prompt,
                "preview_text": self.voice_design_preview_text,
            }
            if self.voice_design_voice_id:
                design_body["voice_id"] = self.voice_design_voice_id

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self._voice_design_url("voice_design"),
                        headers=self.headers,
                        json=design_body,
                        timeout=aiohttp.ClientTimeout(total=60),
                    ) as response:
                        if response.status >= 400:
                            error_text = (await response.text())[:1024]
                            raise RuntimeError(
                                "MiniMax voice design failed: "
                                f"HTTP {response.status}: {error_text}",
                            )
                        design_data = await response.json(content_type=None)
            except aiohttp.ClientError as exc:
                raise RuntimeError(
                    f"MiniMax voice design request failed: {exc!s}",
                ) from exc

            base_resp = design_data.get("base_resp", {})
            status_code = base_resp.get("status_code")
            if status_code not in (None, 0, "0"):
                status_msg = base_resp.get("status_msg", "unknown error")
                raise RuntimeError(
                    f"MiniMax voice design failed: {status_msg}",
                )

            design_result = design_data.get("data") or {}
            voice_id = (
                design_data.get("voice_id")
                or design_result.get("voice_id")
                or self.voice_design_voice_id
            )
            if not voice_id:
                raise RuntimeError(
                    "MiniMax voice design returned no voice_id.",
                )
            self.voice_setting["voice_id"] = voice_id
            self._voice_design_ready = True

    async def design_voice(self) -> str:
        """Design the configured MiniMax voice and return its voice ID."""
        await self._ensure_voice_design()
        if not self.voice_design_prompt:
            raise ValueError(
                "MiniMax voice design requires 'minimax-voice-design-prompt'.",
            )
        return self.voice_setting["voice_id"]

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
        return b"".join(chunks)

    async def get_audio(self, text: str) -> str:
        await self._ensure_voice_design()
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
