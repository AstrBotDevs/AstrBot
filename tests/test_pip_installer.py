from unittest.mock import AsyncMock

import pytest

from astrbot.core.utils.pip_installer import PipInstaller


@pytest.mark.asyncio
async def test_install_targets_site_packages_for_desktop_client(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTRBOT_DESKTOP_CLIENT", "1")
    monkeypatch.delattr("sys.frozen", raising=False)

    site_packages_path = tmp_path / "site-packages"
    run_pip = AsyncMock(return_value=0)
    prepend_sys_path_calls = []
    ensure_preferred_calls = []

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)
    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer.get_astrbot_site_packages_path",
        lambda: str(site_packages_path),
    )
    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer._prepend_sys_path",
        lambda path: prepend_sys_path_calls.append(path),
    )
    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer._ensure_plugin_dependencies_preferred",
        lambda path, requirements: ensure_preferred_calls.append((path, requirements)),
    )

    installer = PipInstaller("")
    await installer.install(package_name="demo-package")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert "--target" in recorded_args
    assert str(site_packages_path) in recorded_args
    assert prepend_sys_path_calls == [str(site_packages_path), str(site_packages_path)]
    assert ensure_preferred_calls == [(str(site_packages_path), {"demo-package"})]
