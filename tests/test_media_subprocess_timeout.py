"""Timeouts for the ffmpeg/ffprobe helper processes.

A hung ffmpeg used to block the caller forever (and keep its half-written output
file), which burned the platform request budget instead of failing fast. These
tests use a fake subprocess with an injectable timeout so nothing waits for the
real 120 s limit.
"""

import asyncio
from pathlib import Path

import pytest

from astrbot.core.utils import media_utils

SHORT_TIMEOUT = 0.01


class FakeProcess:
    """Minimal stand-in for ``asyncio.subprocess.Process``.

    Args:
        returncode: Exit code the process reports once it exits.
        stdout: Data returned from ``communicate()``.
        stderr: Error output returned from ``communicate()``.
        hang_calls: Number of leading ``communicate()`` calls that block until
            they are cancelled, simulating a hung ffmpeg.
        exit_on_hang: Whether the process is considered exited (with
            ``returncode``) when the hanging read is cancelled.
    """

    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: bytes = b"",
        stderr: bytes = b"",
        hang_calls: int = 0,
        exit_on_hang: bool = False,
    ) -> None:
        # ``None`` models a process that is still running, like the real
        # ``asyncio.subprocess.Process``.
        self.returncode: int | None = None
        self._final_returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.hang_calls = hang_calls
        self.exit_on_hang = exit_on_hang
        self.calls = 0
        self.communicating = False
        self.killed = False
        self.waited = False

    async def communicate(self) -> tuple[bytes, bytes]:
        self.calls += 1
        if self.calls <= self.hang_calls:
            self.communicating = True
            # Much longer than the injected timeout, so a missing timeout would
            # make the test appear to hang instead of failing fast.
            try:
                await asyncio.sleep(30)
            finally:
                if self.exit_on_hang:
                    self.returncode = self._final_returncode
        self.returncode = self._final_returncode
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.killed = True
        if self.returncode is None:
            self.returncode = -9

    async def wait(self) -> int:
        self.waited = True
        if self.returncode is None:
            self.returncode = -9
        return self.returncode


def _install_fake_process(
    monkeypatch,
    fake: FakeProcess,
    *,
    partial_output=None,
    timeout: float = SHORT_TIMEOUT,
):
    """Patch ``create_subprocess_exec`` and optionally write a partial file."""

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        if partial_output is not None:
            Path(partial_output).write_bytes(b"half-written")
        return fake

    monkeypatch.setattr(media_utils, "FFMPEG_TIMEOUT_SECONDS", timeout)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)


async def _run_until_started(fake: FakeProcess) -> None:
    """Give the coroutine a chance to spawn the process and start reading."""
    for _ in range(200):
        if fake.communicating:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("fake process never started communicating")


@pytest.mark.asyncio
async def test_convert_audio_format_kills_timed_out_ffmpeg(tmp_path, monkeypatch):
    output_path = tmp_path / "converted.wav"
    fake = FakeProcess(hang_calls=1)
    _install_fake_process(monkeypatch, fake, partial_output=output_path)

    with pytest.raises(Exception, match="timed out after"):
        await media_utils.convert_audio_format(
            str(tmp_path / "source.mp3"),
            output_format="wav",
            output_path=str(output_path),
        )

    assert fake.killed is True
    assert fake.waited is True
    assert not output_path.exists()


@pytest.mark.asyncio
async def test_convert_video_format_kills_timed_out_ffmpeg(tmp_path, monkeypatch):
    output_path = tmp_path / "converted.webm"
    fake = FakeProcess(hang_calls=1)
    _install_fake_process(monkeypatch, fake, partial_output=output_path)

    with pytest.raises(Exception, match="timed out after"):
        await media_utils.convert_video_format(
            str(tmp_path / "source.mp4"),
            output_format="webm",
            output_path=str(output_path),
        )

    assert fake.killed is True
    assert fake.waited is True
    assert not output_path.exists()


@pytest.mark.asyncio
async def test_extract_video_cover_kills_timed_out_ffmpeg(tmp_path, monkeypatch):
    output_path = tmp_path / "cover.jpg"
    fake = FakeProcess(hang_calls=1)
    _install_fake_process(monkeypatch, fake, partial_output=output_path)

    with pytest.raises(Exception, match="timed out after"):
        await media_utils.extract_video_cover(
            str(tmp_path / "source.mp4"), output_path=str(output_path)
        )

    assert fake.killed is True
    assert fake.waited is True
    assert not output_path.exists()


@pytest.mark.asyncio
async def test_get_media_duration_returns_none_on_timeout(tmp_path, monkeypatch):
    fake = FakeProcess(hang_calls=1)
    _install_fake_process(monkeypatch, fake)

    duration = await media_utils.get_media_duration(str(tmp_path / "source.mp4"))

    assert duration is None
    assert fake.killed is True
    assert fake.waited is True


@pytest.mark.asyncio
async def test_convert_audio_format_cleans_up_when_caller_is_cancelled(
    tmp_path, monkeypatch
):
    output_path = tmp_path / "converted.wav"
    fake = FakeProcess(hang_calls=1)
    _install_fake_process(monkeypatch, fake, partial_output=output_path, timeout=30)

    task = asyncio.create_task(
        media_utils.convert_audio_format(
            str(tmp_path / "source.mp3"),
            output_format="wav",
            output_path=str(output_path),
        )
    )
    await _run_until_started(fake)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert fake.killed is True
    assert fake.waited is True
    assert not output_path.exists()


@pytest.mark.asyncio
async def test_extract_video_cover_cleans_up_when_caller_is_cancelled(
    tmp_path, monkeypatch
):
    output_path = tmp_path / "cover.jpg"
    fake = FakeProcess(hang_calls=1)
    _install_fake_process(monkeypatch, fake, partial_output=output_path, timeout=30)

    task = asyncio.create_task(
        media_utils.extract_video_cover(
            str(tmp_path / "source.mp4"), output_path=str(output_path)
        )
    )
    await _run_until_started(fake)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert fake.killed is True
    assert fake.waited is True
    assert not output_path.exists()


@pytest.mark.asyncio
async def test_timeout_keeps_result_when_process_already_exited(
    tmp_path, monkeypatch
):
    """A process that exits as the deadline expires is not a timeout."""
    fake = FakeProcess(returncode=0, stdout=b"12.5\n", hang_calls=1, exit_on_hang=True)
    _install_fake_process(monkeypatch, fake)

    duration = await media_utils.get_media_duration(str(tmp_path / "source.mp4"))

    assert duration == 12500
    assert fake.killed is False
    assert fake.communicating is True


@pytest.mark.asyncio
async def test_timeout_preserves_preexisting_output(tmp_path, monkeypatch):
    output_path = tmp_path / "converted.wav"
    output_path.write_bytes(b"previous-run")
    fake = FakeProcess(hang_calls=1)
    _install_fake_process(monkeypatch, fake)

    with pytest.raises(Exception, match="timed out after"):
        await media_utils.convert_audio_format(
            str(tmp_path / "source.mp3"),
            output_format="wav",
            output_path=str(output_path),
        )

    assert fake.killed is True
    assert output_path.read_bytes() == b"previous-run"


@pytest.mark.asyncio
async def test_convert_audio_format_reports_success_without_killing(
    tmp_path, monkeypatch
):
    output_path = tmp_path / "converted.wav"
    fake = FakeProcess(returncode=0)
    _install_fake_process(monkeypatch, fake, partial_output=output_path)

    result = await media_utils.convert_audio_format(
        str(tmp_path / "source.mp3"),
        output_format="wav",
        output_path=str(output_path),
    )

    assert result == str(output_path)
    assert fake.killed is False
    assert fake.waited is False


@pytest.mark.asyncio
async def test_convert_audio_format_keeps_failure_cleanup(tmp_path, monkeypatch):
    output_path = tmp_path / "converted.wav"
    fake = FakeProcess(returncode=1, stderr=b"boom")
    _install_fake_process(monkeypatch, fake, partial_output=output_path)

    with pytest.raises(Exception, match="ffmpeg conversion failed: boom"):
        await media_utils.convert_audio_format(
            str(tmp_path / "source.mp3"),
            output_format="wav",
            output_path=str(output_path),
        )

    assert fake.killed is False
    assert not output_path.exists()


def test_timeout_constant_is_bounded_by_platform_api_timeouts():
    # The media limit must be long enough for real transcodes but below the
    # platform API timeout (OneBot calls are usually bounded at 180 s or more),
    # otherwise it would never fire before the platform gives up.
    timeout = media_utils.FFMPEG_TIMEOUT_SECONDS
    assert 1 < timeout < 180
