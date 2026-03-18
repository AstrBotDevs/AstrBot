import asyncio
import importlib.util
import time
from pathlib import Path

import pytest


def _load_file_token_service() -> type:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "astrbot"
        / "core"
        / "file_token_service.py"
    )
    spec = importlib.util.spec_from_file_location(
        "file_token_service_test_module", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FileTokenService


FileTokenService = _load_file_token_service()


@pytest.mark.asyncio
async def test_single_use_token_is_invalid_after_first_access(tmp_path: Path) -> None:
    file_path = tmp_path / "logo.png"
    file_path.write_text("demo", encoding="utf-8")

    service = FileTokenService(default_timeout=300)
    token = await service.register_file(str(file_path))

    served_path = await service.handle_file(token)
    assert served_path == str(file_path)
    assert await service.check_token_expired(token) is True

    with pytest.raises(KeyError):
        await service.handle_file(token)


@pytest.mark.asyncio
async def test_reusable_token_can_be_served_multiple_times(tmp_path: Path) -> None:
    file_path = tmp_path / "logo.png"
    file_path.write_text("demo", encoding="utf-8")

    service = FileTokenService(default_timeout=300)
    token = await service.register_file(str(file_path), single_use=False)

    first_path = await service.handle_file(token)
    second_path = await service.handle_file(token)

    assert first_path == str(file_path)
    assert second_path == str(file_path)
    assert await service.check_token_expired(token) is False


@pytest.mark.asyncio
async def test_reusable_token_expires_normally(tmp_path: Path) -> None:
    file_path = tmp_path / "logo.png"
    file_path.write_text("demo", encoding="utf-8")

    service = FileTokenService(default_timeout=300)
    token = await service.register_file(
        str(file_path),
        expire_seconds=0.01,
        single_use=False,
    )

    assert await service.check_token_expired(token) is False
    await service._cleanup_expired_tokens()
    assert await service.check_token_expired(token) is False

    start = time.monotonic()
    timeout = 1.0
    expired = await service.check_token_expired(token)
    while not expired and time.monotonic() - start < timeout:
        await asyncio.sleep(0.01)
        expired = await service.check_token_expired(token)

    assert expired is True

    with pytest.raises(KeyError):
        await service.handle_file(token)
