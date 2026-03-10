import asyncio
import threading
from unittest.mock import AsyncMock

import pytest

from astrbot.core.utils import pip_installer as pip_installer_module
from astrbot.core.utils.pip_installer import PipInstaller


@pytest.mark.asyncio
async def test_install_targets_site_packages_for_desktop_client(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTRBOT_DESKTOP_CLIENT", "1")
    monkeypatch.delattr("sys.frozen", raising=False)

    site_packages_path = tmp_path / "site-packages"
    run_pip = AsyncMock(return_value=(0, []))
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
async def test_run_pip_in_process_streams_output_lines(monkeypatch):
    logged_lines = []
    first_line_seen = asyncio.Event()
    unblock_pip = threading.Event()

    def fake_pip_main(args):
        del args
        print("Collecting demo-package")
        unblock_pip.wait(timeout=1)
        print("Downloading demo-package.whl")
        return 0

    loop = asyncio.get_running_loop()

    def record_log(line, *args):
        message = line % args if args else line
        logged_lines.append(message)
        if message == "Collecting demo-package":
            loop.call_soon_threadsafe(first_line_seen.set)

    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer._get_pip_main",
        lambda: fake_pip_main,
    )
    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer.logger.info",
        record_log,
    )

    installer = PipInstaller("")
    task = asyncio.create_task(installer._run_pip_in_process(["install", "demo-package"]))

    await asyncio.wait_for(first_line_seen.wait(), timeout=1)
    unblock_pip.set()
    result = await task

    assert result == (0, ["Collecting demo-package", "Downloading demo-package.whl"])
    assert logged_lines[-2:] == [
        "Collecting demo-package",
        "Downloading demo-package.whl",
    ]


@pytest.mark.asyncio
async def test_run_pip_in_process_preserves_shared_stream_order(monkeypatch):
    logged_lines = []

    def fake_pip_main(args):
        del args
        import sys

        sys.stdout.write("out")
        sys.stderr.write("err\n")
        sys.stdout.write(" line\n")
        return 0

    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer._get_pip_main",
        lambda: fake_pip_main,
    )
    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer.logger.info",
        lambda line, *args: logged_lines.append(line % args if args else line),
    )

    installer = PipInstaller("")
    result = await installer._run_pip_in_process(["install", "demo-package"])

    assert result == (0, ["outerr", " line"])
    assert logged_lines[-2:] == ["outerr", " line"]



def _make_fake_distribution(name: str, version: str):
    class FakeDistribution:
        metadata = {"Name": name}

        def __init__(self, version: str):
            self.version = version

    return FakeDistribution(version)


def test_find_missing_requirements_honors_version_specifiers(monkeypatch, tmp_path):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("demo-package>=2.0\n", encoding="utf-8")

    monkeypatch.setattr(
        pip_installer_module.importlib_metadata,
        "distributions",
        lambda path: [_make_fake_distribution("demo-package", "1.0")],
    )

    missing = pip_installer_module._find_missing_requirements(str(requirements_path))

    assert missing == {"demo-package"}


def test_find_missing_requirements_skips_unmatched_markers(monkeypatch, tmp_path):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text(
        'demo-package; sys_platform == "win32"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        pip_installer_module.importlib_metadata,
        "distributions",
        lambda path: [],
    )

    missing = pip_installer_module._find_missing_requirements(str(requirements_path))

    assert missing == set()


def test_find_missing_requirements_follows_nested_requirement_files(
    monkeypatch, tmp_path
):
    base_requirements = tmp_path / "base.txt"
    base_requirements.write_text("demo-package==1.0\n", encoding="utf-8")
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("-r base.txt\n", encoding="utf-8")

    monkeypatch.setattr(
        pip_installer_module.importlib_metadata,
        "distributions",
        lambda path: [],
    )

    missing = pip_installer_module._find_missing_requirements(str(requirements_path))

    assert missing == {"demo-package"}


def test_find_missing_requirements_follows_equals_form_nested_requirements(
    monkeypatch, tmp_path
):
    base_requirements = tmp_path / "base.txt"
    base_requirements.write_text("demo-package==1.0\n", encoding="utf-8")
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("--requirement=base.txt\n", encoding="utf-8")

    monkeypatch.setattr(
        pip_installer_module.importlib_metadata,
        "distributions",
        lambda path: [],
    )

    missing = pip_installer_module._find_missing_requirements(str(requirements_path))

    assert missing == {"demo-package"}


def test_find_missing_requirements_returns_none_when_nested_file_missing(tmp_path):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("-r base.txt\n", encoding="utf-8")

    missing = pip_installer_module._find_missing_requirements(str(requirements_path))

    assert missing is None


def test_find_missing_requirements_extracts_editable_vcs_requirement(
    monkeypatch, tmp_path
):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text(
        "-e git+https://example.com/demo.git#egg=demo-package\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        pip_installer_module.importlib_metadata,
        "distributions",
        lambda path: [],
    )

    missing = pip_installer_module._find_missing_requirements(str(requirements_path))

    assert missing == {"demo-package"}


def test_find_missing_requirements_prefers_first_search_path_version(monkeypatch, tmp_path):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("demo-package>=2.0\n", encoding="utf-8")

    monkeypatch.setattr(
        pip_installer_module.importlib_metadata,
        "distributions",
        lambda path: [
            _make_fake_distribution("demo-package", "1.0"),
            _make_fake_distribution("demo-package", "3.0"),
        ],
    )

    missing = pip_installer_module._find_missing_requirements(str(requirements_path))

    assert missing == {"demo-package"}


def test_find_missing_requirements_returns_none_when_distribution_scan_fails(
    monkeypatch, tmp_path
):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("demo-package>=2.0\n", encoding="utf-8")

    def failing_distributions(path):
        del path
        yield _make_fake_distribution("demo-package", "3.0")
        raise RuntimeError("scan failed")

    monkeypatch.setattr(
        pip_installer_module.importlib_metadata,
        "distributions",
        failing_distributions,
    )

    missing = pip_installer_module._find_missing_requirements(str(requirements_path))

    assert missing is None


@pytest.mark.asyncio
async def test_install_splits_space_separated_packages(monkeypatch):
    run_pip = AsyncMock(return_value=(0, []))

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="demo-package another-package>=1.0")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:3] == ["install", "demo-package", "another-package>=1.0"]


@pytest.mark.asyncio
async def test_install_splits_three_space_separated_packages(monkeypatch):
    run_pip = AsyncMock(return_value=(0, []))

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
    run_pip = AsyncMock(return_value=(0, []))

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
    run_pip = AsyncMock(return_value=(0, []))
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
async def test_install_splits_space_separated_packages_within_multiline_input(
    monkeypatch,
):
    run_pip = AsyncMock(return_value=(0, []))

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="demo-package another-package\nextra-package\n")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:4] == [
        "install",
        "demo-package",
        "another-package",
        "extra-package",
    ]


@pytest.mark.asyncio
async def test_install_keeps_single_requirement_with_marker_intact(monkeypatch):
    run_pip = AsyncMock(return_value=(0, []))

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="demo-package ; python_version < '4'")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert "install" in recorded_args
    assert "demo-package" in recorded_args
    assert ";" in recorded_args
    assert "python_version" in recorded_args


@pytest.mark.asyncio
async def test_install_keeps_single_requirement_with_compact_marker_intact(monkeypatch):
    run_pip = AsyncMock(return_value=(0, []))

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name='demo-package; python_version < "4"')

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert "install" in recorded_args
    assert "demo-package;" in recorded_args
    assert "python_version" in recorded_args


@pytest.mark.asyncio
async def test_install_keeps_single_requirement_with_version_range_intact(monkeypatch):
    run_pip = AsyncMock(return_value=(0, []))

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="demo-package >= 1.0, < 2.0")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert "install" in recorded_args
    assert "demo-package" in recorded_args
    assert ">=" in recorded_args
    assert "1.0," in recorded_args


@pytest.mark.asyncio
async def test_install_multiline_input_strips_comments_and_splits_options(monkeypatch):
    run_pip = AsyncMock(return_value=(0, []))

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
async def test_install_single_line_input_strips_inline_comment(monkeypatch):
    run_pip = AsyncMock(return_value=(0, []))

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="requests==2.31.0  # latest")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:2] == ["install", "requests==2.31.0"]


@pytest.mark.asyncio
async def test_install_splits_single_line_editable_option_input(monkeypatch):
    run_pip = AsyncMock(return_value=(0, []))

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="-e .")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:3] == ["install", "-e", "."]


@pytest.mark.asyncio
async def test_install_splits_single_line_option_with_url(monkeypatch):
    run_pip = AsyncMock(return_value=(0, []))

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
    run_pip = AsyncMock(return_value=(0, []))

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
async def test_install_keeps_short_form_index_override(monkeypatch):
    run_pip = AsyncMock(return_value=(0, []))

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="-ihttps://example.com/simple demo-package")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:3] == [
        "install",
        "-ihttps://example.com/simple",
        "demo-package",
    ]
    assert "-i" not in recorded_args


@pytest.mark.asyncio
async def test_install_preserves_url_fragment_in_option_input(monkeypatch):
    run_pip = AsyncMock(return_value=(0, []))

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(
        package_name="--index-url https://example.com/simple#frag demo-package"
    )

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:4] == [
        "install",
        "--index-url",
        "https://example.com/simple#frag",
        "demo-package",
    ]
    assert "-i" not in recorded_args


@pytest.mark.asyncio
async def test_install_strips_inline_comment_from_option_line(monkeypatch):
    run_pip = AsyncMock(return_value=(0, []))

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(
        package_name=(
            "--extra-index-url https://example.com/simple  # mirror\n"
            "demo-package\n"
        )
    )

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:4] == [
        "install",
        "--extra-index-url",
        "https://example.com/simple",
        "demo-package",
    ]


@pytest.mark.asyncio
async def test_install_falls_back_to_raw_input_for_invalid_token_string(monkeypatch):
    run_pip = AsyncMock(return_value=(0, []))

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    raw_input = "demo-package !!! another-package"
    await installer.install(package_name=raw_input)

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:4] == ["install", "demo-package", "!!!", "another-package"]


@pytest.mark.asyncio
async def test_install_ignores_whitespace_only_package_string(monkeypatch):
    run_pip = AsyncMock(return_value=(0, []))

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="   ")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    # Verify core install args are present; allow for extra args like -c constraints
    assert "install" in recorded_args
    # Verify --trusted-host and its value are present as a sequence
    idx = recorded_args.index("--trusted-host")
    assert recorded_args[idx + 1] == "mirrors.aliyun.com"
    assert "-i" in recorded_args
    assert "https://pypi.org/simple" in recorded_args


@pytest.mark.asyncio
async def test_install_respects_index_override_in_pip_install_arg(monkeypatch):
    run_pip = AsyncMock(return_value=(0, []))

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("--index-url https://example.com/simple")
    await installer.install(package_name="demo-package")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert "install" in recorded_args
    assert "demo-package" in recorded_args
    assert "--index-url" in recorded_args
    assert "https://example.com/simple" in recorded_args
    # Verify that default index overrides are NOT present
    assert "mirrors.aliyun.com" not in recorded_args
    assert "https://pypi.org/simple" not in recorded_args
