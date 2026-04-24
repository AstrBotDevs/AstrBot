import asyncio
import importlib
import uuid
from functools import partial
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_file
from astrbot.core.utils.tencent_record_helper import (
    convert_to_pcm_wav,
    tencent_silk_to_wav,
)

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "faster_whisper_stt_selfhost",
    "faster-whisper 模型部署",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderFasterWhisperSTTSelfHost(STTProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.set_model(provider_config["model"])
        self.device = str(
            provider_config.get("faster_whisper_device", "auto"),
        ).strip()
        self.model: Any = None

    async def initialize(self) -> None:
        loop = asyncio.get_running_loop()

        def _load_model() -> Any:
            faster_whisper = importlib.import_module("faster_whisper")
            whisper_model_cls = faster_whisper.WhisperModel
            return whisper_model_cls(
                self.model_name,
                device=self.device,
            )

        logger.info("下载或者加载 faster-whisper 模型中，这可能需要一些时间 ...")
        self.model = await loop.run_in_executor(None, _load_model)
        logger.info(
            "faster-whisper 模型加载完成。device=%s",
            self.device,
        )

    def _get_temp_dir(self) -> Path:
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir

    async def _detect_audio_format(self, file_path: Path) -> str | None:
        try:
            with file_path.open("rb") as file:
                file_header = file.read(8)
        except FileNotFoundError:
            return None

        if b"SILK" in file_header:
            return "silk"
        if b"#!AMR" in file_header:
            return "amr"
        return None

    async def _prepare_audio_input(self, audio_url: str) -> tuple[Path, list[Path]]:
        cleanup_paths: list[Path] = []
        source_path = Path(audio_url)
        is_remote = audio_url.startswith(("http://", "https://"))
        is_tencent = "multimedia.nt.qq.com.cn" in audio_url if is_remote else False

        if is_remote:
            parsed_url = urlparse(audio_url)
            suffix = Path(parsed_url.path).suffix or ".input"
            download_path = (
                self._get_temp_dir()
                / f"faster_whisper_selfhost_{uuid.uuid4().hex[:8]}{suffix}"
            )
            await download_file(audio_url, str(download_path))
            source_path = download_path
            cleanup_paths.append(download_path)

        if not source_path.exists():
            raise FileNotFoundError(f"文件不存在: {source_path}")

        if source_path.suffix.lower() in {".amr", ".silk"} or is_tencent:
            file_format = await self._detect_audio_format(source_path)
            if file_format in {"silk", "amr"}:
                converted_path = (
                    self._get_temp_dir()
                    / f"faster_whisper_selfhost_{uuid.uuid4().hex[:8]}.wav"
                )
                cleanup_paths.append(converted_path)

                if file_format == "silk":
                    logger.info("Converting silk file to wav ...")
                    await tencent_silk_to_wav(str(source_path), str(converted_path))
                else:
                    logger.info("Converting amr file to wav ...")
                    await convert_to_pcm_wav(str(source_path), str(converted_path))

                source_path = converted_path

        return source_path, cleanup_paths

    def _transcribe_audio(self, audio_path: Path) -> str:
        if self.model is None:
            raise RuntimeError("faster-whisper 模型未初始化")

        segments, info = self.model.transcribe(str(audio_path))
        segment_list = list(segments)
        text = "".join(segment.text for segment in segment_list).strip()
        logger.debug(
            "faster-whisper transcription completed. language=%s, text=%s",
            getattr(info, "language", None),
            text,
        )
        return cast(str, text)

    async def get_text(self, audio_url: str) -> str:
        loop = asyncio.get_running_loop()
        audio_path, cleanup_paths = await self._prepare_audio_input(audio_url)
        try:
            return await loop.run_in_executor(
                None,
                partial(self._transcribe_audio, audio_path),
            )
        finally:
            for path in cleanup_paths:
                try:
                    path.unlink(missing_ok=True)
                except Exception as exc:
                    logger.warning(
                        "Failed to remove temporary faster-whisper file %s: %s",
                        path,
                        exc,
                    )
