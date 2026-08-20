import pytest

from astrbot.core.file_token_service import FileTokenService


class FakeEvent:
    def __init__(self, path: str):
        self.paths = {path}

    def has_temporary_local_file(self, path: str) -> bool:
        return path in self.paths

    def transfer_temporary_local_file(self, path: str) -> bool:
        if path not in self.paths:
            return False
        self.paths.remove(path)
        return True

    def cleanup(self) -> None:
        for path in list(self.paths):
            self.paths.remove(path)
            try:
                __import__("os").remove(path)
            except FileNotFoundError:
                pass


@pytest.mark.asyncio
async def test_owned_artifact_is_deleted_after_response_release(tmp_path):
    artifact = tmp_path / "audio.mp3"
    artifact.write_bytes(b"audio")
    event = FakeEvent(str(artifact))
    service = FileTokenService()

    token = await service.register_owned_file(str(artifact), event)
    assert event.paths == set()
    claimed_path, owned = await service.claim_file(token)
    assert (claimed_path, owned) == (str(artifact), True)
    assert artifact.exists()

    await service.release_token(token)

    assert not artifact.exists()


@pytest.mark.asyncio
async def test_expired_owned_token_deletes_unclaimed_artifact(tmp_path):
    artifact = tmp_path / "image.png"
    artifact.write_bytes(b"image")
    service = FileTokenService(default_timeout=-1)

    await service.register_owned_file(str(artifact), FakeEvent(str(artifact)))
    assert await service.check_token_expired("missing") is True
    assert not artifact.exists()


@pytest.mark.asyncio
async def test_regular_register_file_never_deletes_caller_file(tmp_path):
    source = tmp_path / "caller.txt"
    source.write_text("caller", encoding="utf-8")
    service = FileTokenService()

    token = await service.register_file(str(source))
    assert await service.handle_file(token) == str(source)
    assert source.exists()


@pytest.mark.asyncio
async def test_multiple_owned_tokens_reference_count_the_same_artifact(tmp_path):
    artifact = tmp_path / "shared.png"
    artifact.write_bytes(b"shared")
    service = FileTokenService()
    token_a = await service.register_owned_file(str(artifact), FakeEvent(str(artifact)))
    token_b = await service.register_owned_file(str(artifact), FakeEvent(str(artifact)))

    await service.claim_file(token_a)
    await service.release_token(token_a)
    assert artifact.exists()

    await service.claim_file(token_b)
    await service.release_token(token_b)
    assert not artifact.exists()


@pytest.mark.asyncio
async def test_owned_registration_failure_keeps_event_ownership(tmp_path):
    missing = tmp_path / "missing.wav"
    event = FakeEvent(str(missing))
    service = FileTokenService()

    with pytest.raises(FileNotFoundError):
        await service.register_owned_file(str(missing), event)

    assert event.paths == {str(missing)}


@pytest.mark.asyncio
async def test_event_cleanup_does_not_remove_transferred_artifact(tmp_path):
    artifact = tmp_path / "tts.wav"
    artifact.write_bytes(b"tts")
    event = FakeEvent(str(artifact))
    service = FileTokenService()
    await service.register_owned_file(str(artifact), event)

    event.cleanup()
    assert artifact.exists()
    await service.shutdown()
    assert not artifact.exists()


@pytest.mark.asyncio
async def test_shutdown_removes_claimed_and_unclaimed_owned_artifacts(tmp_path):
    claimed = tmp_path / "claimed.bin"
    unclaimed = tmp_path / "unclaimed.bin"
    claimed.write_bytes(b"claimed")
    unclaimed.write_bytes(b"unclaimed")
    service = FileTokenService()
    token = await service.register_owned_file(str(claimed), FakeEvent(str(claimed)))
    await service.claim_file(token)
    await service.register_owned_file(str(unclaimed), FakeEvent(str(unclaimed)))

    await service.shutdown()

    assert not claimed.exists()
    assert not unclaimed.exists()
