import pytest

from astrbot.dashboard.services.update_service import UpdateService, UpdateServiceError


class _ControlledPipInstall:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[tuple, dict]] = []

    async def __call__(self, *args, **kwargs) -> None:
        self.calls.append((args, kwargs))
        if self.fail:
            raise RuntimeError("dependency install failed")


def _make_service(*, fail: bool = False, demo_mode: bool = False) -> UpdateService:
    return UpdateService(
        pip_install_func=_ControlledPipInstall(fail=fail),
        demo_mode=demo_mode,
        clear_site_data_headers={},
    )


@pytest.mark.asyncio
async def test_install_pip_package_succeeds() -> None:
    service = _make_service()
    result = await service.install_pip_package({"package": "demo", "mirror": None})
    assert result.message == "安装成功。"


@pytest.mark.asyncio
async def test_install_pip_package_requires_package() -> None:
    service = _make_service()
    with pytest.raises(UpdateServiceError, match="缺少参数 package"):
        await service.install_pip_package({})


@pytest.mark.asyncio
async def test_install_pip_package_rejects_demo_mode() -> None:
    service = _make_service(demo_mode=True)
    with pytest.raises(UpdateServiceError, match="demo mode"):
        await service.install_pip_package({"package": "demo"})


@pytest.mark.asyncio
async def test_install_pip_package_wraps_install_failure() -> None:
    service = _make_service(fail=True)
    with pytest.raises(UpdateServiceError, match="安装依赖失败"):
        await service.install_pip_package({"package": "demo"})


@pytest.mark.asyncio
async def test_update_service_shutdown_is_noop() -> None:
    service = _make_service()
    await service.shutdown()
