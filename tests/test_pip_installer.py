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


@pytest.mark.asyncio
async def test_install_splits_space_separated_packages(monkeypatch):
    run_pip = AsyncMock(return_value=0)

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="demo-package another-package>=1.0")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:3] == ["install", "demo-package", "another-package>=1.0"]


@pytest.mark.asyncio
async def test_install_splits_three_space_separated_packages(monkeypatch):
    run_pip = AsyncMock(return_value=0)

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(
        package_name="demo-package another-package extra-package>=1.0"
    )

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:4] == [
        "install",
        "demo-package",
        "another-package",
        "extra-package>=1.0",
    ]


@pytest.mark.asyncio
async def test_install_splits_three_bare_packages(monkeypatch):
    run_pip = AsyncMock(return_value=0)

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="demo-package another-package extra-package")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:4] == [
        "install",
        "demo-package",
        "another-package",
        "extra-package",
    ]


@pytest.mark.asyncio
async def test_install_tracks_multiline_packages_for_desktop_client(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ASTRBOT_DESKTOP_CLIENT", "1")
    monkeypatch.delattr("sys.frozen", raising=False)

    site_packages_path = tmp_path / "site-packages"
    run_pip = AsyncMock(return_value=0)
    ensure_preferred_calls = []

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)
    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer.get_astrbot_site_packages_path",
        lambda: str(site_packages_path),
    )
    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer._prepend_sys_path",
        lambda path: None,
    )
    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer._ensure_plugin_dependencies_preferred",
        lambda path, requirements: ensure_preferred_calls.append((path, requirements)),
    )

    installer = PipInstaller("")
    await installer.install(package_name="demo-package\nanother-package>=1.0\n")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:3] == ["install", "demo-package", "another-package>=1.0"]
    assert ensure_preferred_calls == [
        (str(site_packages_path), {"demo-package", "another-package"})
    ]


@pytest.mark.asyncio
async def test_install_keeps_single_requirement_with_marker_intact(monkeypatch):
    run_pip = AsyncMock(return_value=0)

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="demo-package ; python_version < '4'")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:2] == ["install", "demo-package ; python_version < '4'"]


@pytest.mark.asyncio
async def test_install_keeps_single_requirement_with_compact_marker_intact(monkeypatch):
    run_pip = AsyncMock(return_value=0)

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name='demo-package; python_version < "4"')

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:2] == ["install", 'demo-package; python_version < "4"']


@pytest.mark.asyncio
async def test_install_keeps_single_requirement_with_version_range_intact(monkeypatch):
    run_pip = AsyncMock(return_value=0)

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="demo-package >= 1.0, < 2.0")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:2] == ["install", "demo-package >= 1.0, < 2.0"]


@pytest.mark.asyncio
async def test_install_multiline_input_strips_comments_and_splits_options(monkeypatch):
    run_pip = AsyncMock(return_value=0)

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(
        package_name=(
            "demo-package==1.0  # pinned\n"
            "--extra-index-url https://example.com/simple\n"
            "another-package\n"
        )
    )

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:5] == [
        "install",
        "demo-package==1.0",
        "--extra-index-url",
        "https://example.com/simple",
        "another-package",
    ]


@pytest.mark.asyncio
async def test_install_splits_single_line_editable_option_input(monkeypatch):
    run_pip = AsyncMock(return_value=0)

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="-e .")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:3] == ["install", "-e", "."]


@pytest.mark.asyncio
async def test_install_splits_single_line_option_with_url(monkeypatch):
    run_pip = AsyncMock(return_value=0)

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(
        package_name="--index-url https://example.com/simple demo-package"
    )

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:4] == [
        "install",
        "--index-url",
        "https://example.com/simple",
        "demo-package",
    ]
    assert recorded_args.count("--index-url") == 1
    assert "-i" not in recorded_args


@pytest.mark.asyncio
async def test_install_keeps_equals_form_index_override(monkeypatch):
    run_pip = AsyncMock(return_value=0)

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(
        package_name="--index-url=https://example.com/simple demo-package"
    )

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:3] == [
        "install",
        "--index-url=https://example.com/simple",
        "demo-package",
    ]
    assert "-i" not in recorded_args


@pytest.mark.asyncio
async def test_install_falls_back_to_raw_input_for_invalid_token_string(monkeypatch):
    run_pip = AsyncMock(return_value=0)

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    raw_input = "demo-package !!! another-package"
    await installer.install(package_name=raw_input)

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:2] == ["install", raw_input]
