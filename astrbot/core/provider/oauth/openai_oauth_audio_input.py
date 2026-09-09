"""Bounded audio materialization for OpenAI OAuth transcription."""

import asyncio
import base64
import binascii
import math
import mimetypes
import os
import re
import sys
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

_LIMITED_EXEC_SCRIPT = (
    "import os,resource,sys;"
    "file_limit=int(sys.argv[1]);memory_limit=int(sys.argv[2]);"
    "resource.setrlimit(resource.RLIMIT_FSIZE,(file_limit,file_limit));"
    "resource.setrlimit(resource.RLIMIT_AS,(memory_limit,memory_limit));"
    "os.execvp(sys.argv[3],sys.argv[3:])"
)


@dataclass(frozen=True)
class ResolvedOAuthAudio:
    path: Path
    mime_type: str
    format: str


class BoundedOAuthAudioResolver:
    """Resolve one audio reference without exceeding configured byte limits."""

    _CHUNK_SIZE = 64 * 1024

    def __init__(
        self,
        audio_ref: str,
        *,
        max_bytes: int,
        timeout: float,
        proxy: str | None = None,
    ) -> None:
        self.audio_ref = str(audio_ref or "").strip()
        self.max_bytes = int(max_bytes)
        self.timeout = float(timeout)
        self.proxy = proxy or None
        if not self.audio_ref:
            raise ValueError("OAuth 转录音频不能为空。")
        if self.max_bytes <= 0:
            raise ValueError("OAuth 转录文件大小上限必须大于 0。")

    @asynccontextmanager
    async def as_wav_path(self) -> AsyncIterator[ResolvedOAuthAudio]:
        """Yield a resolver-owned WAV path and always remove temporary files."""
        with tempfile.TemporaryDirectory(prefix="astrbot_oauth_audio_") as temp_name:
            temp_dir = Path(temp_name)
            source_path = temp_dir / self._source_filename()
            await self._materialize(source_path)
            await self._check_file_size(source_path, "输入")
            audio_format = await self._detect_format(source_path)
            if audio_format == "wav":
                if source_path.suffix.lower() == ".wav":
                    wav_path = source_path
                else:
                    wav_path = temp_dir / "normalized.wav"
                    source_path.replace(wav_path)
            elif audio_format == "silk":
                wav_path = temp_dir / "decoded.wav"
                await self._decode_silk(source_path, wav_path)
            elif audio_format in {"mp3", "ogg", "opus", "m4a", "aac", "amr", "flac"}:
                wav_path = temp_dir / "converted.wav"
                await self._convert_to_wav(source_path, wav_path)
            else:
                raise ValueError("OAuth 转录不支持或无法识别该音频格式。")
            await self._check_file_size(wav_path, "解码后音频")
            yield ResolvedOAuthAudio(wav_path, "audio/wav", "wav")

    def _source_filename(self) -> str:
        ref = self.audio_ref
        if ref.startswith("data:"):
            media_type = ref[5:].split(";", 1)[0].lower()
            suffix = mimetypes.guess_extension(media_type) or ".bin"
            return f"input{suffix}"
        if ref.startswith("base64://"):
            return "input.bin"
        parsed = urlparse(ref)
        if parsed.scheme in {"http", "https", "file"}:
            path = Path(unquote(parsed.path))
            name = path.name
            if not name:
                return "input.bin"
            safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
            if len(safe_name) > 128:
                suffix = Path(safe_name).suffix[:16]
                return f"input{suffix or '.bin'}"
            return safe_name
        if len(ref) > 240:
            return "input.bin"
        path = Path(ref)
        return path.name or "input.bin"

    async def _materialize(self, destination: Path) -> None:
        ref = self.audio_ref
        if ref.startswith(("http://", "https://")):
            await self._download(destination)
            return
        if ref.startswith("data:"):
            header, separator, payload = ref.partition(",")
            if not separator or ";base64" not in header.lower():
                raise ValueError("OAuth 转录仅支持 base64 data URI。")
            await self._decode_base64(payload, destination)
            return
        if ref.startswith("base64://"):
            await self._decode_base64(ref[9:], destination)
            return

        local_ref = ref
        if ref.startswith("file://"):
            parsed = urlparse(ref)
            local_ref = unquote(parsed.path)
            if os.name == "nt" and local_ref.startswith("/"):
                local_ref = local_ref[1:]
        source = Path(local_ref).expanduser()
        try:
            is_file = source.is_file()
        except OSError:
            is_file = False
        if is_file:
            await self._copy_local(source, destination)
            return
        await self._decode_base64(ref, destination)

    async def _copy_local(self, source: Path, destination: Path) -> None:
        size = source.stat().st_size
        if size > self.max_bytes:
            raise ValueError(f"OAuth 转录输入超过文件大小上限 {self.max_bytes} 字节。")
        copied = 0
        with source.open("rb") as reader, destination.open("wb") as writer:
            while chunk := reader.read(self._CHUNK_SIZE):
                copied += len(chunk)
                if copied > self.max_bytes:
                    raise ValueError(
                        f"OAuth 转录输入超过文件大小上限 {self.max_bytes} 字节。"
                    )
                writer.write(chunk)
                await asyncio.sleep(0)

    async def _download(self, destination: Path) -> None:
        async with httpx.AsyncClient(
            proxy=self.proxy,
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", self.audio_ref) as response:
                if not 200 <= response.status_code < 300:
                    raise ValueError(
                        f"OAuth 转录音频下载失败：HTTP {response.status_code}。"
                    ) from None
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        declared_size = int(content_length)
                    except ValueError:
                        declared_size = 0
                    if declared_size > self.max_bytes:
                        raise ValueError(
                            "OAuth 转录下载内容超过文件大小上限 "
                            f"{self.max_bytes} 字节。"
                        )
                downloaded = 0
                with destination.open("wb") as writer:
                    async for chunk in response.aiter_bytes(self._CHUNK_SIZE):
                        downloaded += len(chunk)
                        if downloaded > self.max_bytes:
                            raise ValueError(
                                "OAuth 转录下载内容超过文件大小上限 "
                                f"{self.max_bytes} 字节。"
                            )
                        writer.write(chunk)

    async def _decode_base64(self, payload: str, destination: Path) -> None:
        max_encoded = 4 * math.ceil(self.max_bytes / 3) + 8
        if len(payload) > max_encoded * 2:
            raise ValueError(
                f"OAuth 转录 base64 内容超过大小上限 {self.max_bytes} 字节。"
            )
        compact = "".join(payload.split())
        if len(compact) > max_encoded:
            raise ValueError(
                f"OAuth 转录 base64 内容超过大小上限 {self.max_bytes} 字节。"
            )
        try:
            padded = compact + "=" * (-len(compact) % 4)
            decoded = base64.b64decode(padded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("OAuth 转录音频引用无效。") from exc
        if len(decoded) > self.max_bytes:
            raise ValueError(
                f"OAuth 转录 base64 内容超过大小上限 {self.max_bytes} 字节。"
            )
        destination.write_bytes(decoded)

    async def _detect_format(self, path: Path) -> str:
        with path.open("rb") as source:
            header = source.read(32)
        if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
            return "wav"
        if header.startswith((b"#!SILK_V3", b"\x02#!SILK_V3")):
            return "silk"
        if header.startswith(b"ID3") or header[:2] in {
            b"\xff\xfb",
            b"\xff\xf3",
            b"\xff\xf2",
        }:
            return "mp3"
        if header.startswith(b"OggS"):
            return "ogg"
        if header.startswith(b"fLaC"):
            return "flac"
        if header.startswith((b"#!AMR\n", b"#!AMR-WB\n")):
            return "amr"
        if len(header) >= 8 and header[4:8] == b"ftyp":
            return "m4a"
        if len(header) >= 2 and header[0] == 0xFF and header[1] & 0xF6 == 0xF0:
            return "aac"
        suffix = path.suffix.lower().lstrip(".")
        return suffix if suffix in {"m4a", "aac", "amr", "opus"} else "unknown"

    async def _check_file_size(self, path: Path, label: str) -> None:
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError(f"OAuth 转录{label}为空。")
        if path.stat().st_size > self.max_bytes:
            raise ValueError(
                f"OAuth 转录{label}超过文件大小上限 {self.max_bytes} 字节。"
            )

    async def _convert_to_wav(self, source: Path, destination: Path) -> None:
        await self._run_converter(
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-fs",
            str(self.max_bytes),
            str(destination),
        )

    async def _decode_silk(self, source: Path, destination: Path) -> None:
        script = (
            "import io,sys,wave,pysilk\n"
            "src,dst,limit=sys.argv[1],sys.argv[2],int(sys.argv[3])\n"
            "class B(io.BytesIO):\n"
            " def write(self,b):\n"
            "  if self.tell()+len(b)>limit: raise ValueError('decoded audio too large')\n"
            "  return super().write(b)\n"
            "raw=open(src,'rb').read()\n"
            "raw=raw[1:] if raw.startswith(b'\\x02') else raw\n"
            "out=B(); pysilk.decode(io.BytesIO(raw),out,24000)\n"
            "with wave.open(dst,'wb') as w:\n"
            " w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); "
            "w.writeframes(out.getvalue())\n"
        )
        await self._run_converter(
            os.environ.get("PYTHON", os.sys.executable),
            "-c",
            script,
            str(source),
            str(destination),
            str(max(1, self.max_bytes - 44)),
        )

    async def _run_converter(self, *args: str) -> None:
        command = list(args)
        if os.name == "posix":
            file_limit = self.max_bytes + 64 * 1024
            memory_limit = max(512 * 1024 * 1024, self.max_bytes * 8)
            command = [
                sys.executable,
                "-c",
                _LIMITED_EXEC_SCRIPT,
                str(file_limit),
                str(memory_limit),
                *command,
            ]
        process_options = {
            "stdin": asyncio.subprocess.DEVNULL,
            "stdout": asyncio.subprocess.DEVNULL,
            "stderr": asyncio.subprocess.PIPE,
        }
        process = await asyncio.create_subprocess_exec(
            *command,
            **process_options,
        )
        try:
            _stdout, stderr = await process.communicate()
        except asyncio.CancelledError:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        if process.returncode != 0:
            detail = (stderr or b"").decode("utf-8", errors="replace").strip()
            if "too large" in detail.lower():
                raise ValueError(
                    f"OAuth 转录解码后音频超过文件大小上限 {self.max_bytes} 字节。"
                )
            raise ValueError("OAuth 转录音频解码或格式转换失败。")
