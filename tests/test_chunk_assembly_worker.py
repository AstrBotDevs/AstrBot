import asyncio
import threading
from pathlib import Path

import pytest

from astrbot.dashboard.services.chunked_upload_service import ChunkedUploadService


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_assembly_yields_and_serializes_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cancel: bool
) -> None:
    """Disk copying yields to the loop and holds ownership through cancellation."""
    service = ChunkedUploadService(tmp_path / "chunks", chunk_size=4)
    session = service.init_session(
        owner="alice",
        purpose="chat",
        filename="a.bin",
        original_filename="a.bin",
        total_size=4,
    )
    (session.chunk_dir / "0.part").write_bytes(b"data")
    session.received_chunks.add(0)
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    original = service._assemble_file

    def slow_merge(current, dest):
        loop.call_soon_threadsafe(entered.set)
        if not release.wait(3):
            raise RuntimeError("event loop did not advance during disk work")
        return original(current, dest)

    monkeypatch.setattr(service, "_assemble_file", slow_merge)
    destination = tmp_path / "merged.bin"
    assembly = asyncio.create_task(service.assemble(session.id, destination))
    abort = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        if cancel:
            assembly.cancel()
            await asyncio.sleep(0)
            assembly.cancel()
        abort = asyncio.create_task(service.abort(session.id))
        await asyncio.sleep(0)
        assert not abort.done()
        assert session.chunk_dir.exists()
        release.set()
        if cancel:
            with pytest.raises(asyncio.CancelledError):
                await assembly
            assert not destination.exists()
        else:
            assert await assembly == 4
            assert destination.read_bytes() == b"data"
        await abort
        assert not session.chunk_dir.exists()
    finally:
        release.set()
        await asyncio.gather(
            assembly, *([abort] if abort else []), return_exceptions=True
        )
