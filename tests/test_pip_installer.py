import asyncio
import threading
from unittest.mock import AsyncMock

import pytest

from astrbot.core.utils import core_constraints as core_constraints_module
from astrbot.core.utils import pip_installer as pip_installer_module
from astrbot.core.utils import requirements_utils
from astrbot.core.utils.pip_installer import PipInstaller


def _make_run_pip_mock(
    code: int = 0,
    output_lines: list[str] | None = None,
    conflict=None,
):
    del output_lines, conflict

    async def run_pip(*args, **kwargs):
        del args, kwargs
        return code

    return AsyncMock(side_effect=run_pip)


@pytest.mark.asyncio
async def test_install_targets_site_packages_for_desktop_client(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTRBOT_DESKTOP_CLIENT", "1")
    monkeypatch.delattr("sys.frozen", raising=False)

    site_packages_path = tmp_path / "site-packages"
    run_pip = _make_run_pip_mock()
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
    task = asyncio.create_task(
        installer._run_pip_in_process(["install", "demo-package"])
    )

    await asyncio.wait_for(first_line_seen.wait(), timeout=1)
    unblock_pip.set()
    result = await task

    assert result == 0
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

    assert result == 0
    assert logged_lines[-2:] == ["outerr", " line"]


@pytest.mark.asyncio
async def test_run_pip_in_process_preserves_blank_lines(monkeypatch):
    logged_lines = []

    def fake_pip_main(args):
        del args
        print("Collecting demo-package")
        print()
        print("Installing collected packages")
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

    assert result == 0
    assert logged_lines[-3:] == [
        "Collecting demo-package",
        "",
        "Installing collected packages",
    ]


@pytest.mark.asyncio
async def test_run_pip_in_process_preserves_trailing_blank_line_on_flush(monkeypatch):
    logged_lines = []

    def fake_pip_main(args):
        del args
        import sys

        sys.stdout.write("Collecting demo-package\n\n")
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

    assert result == 0
    assert logged_lines[-2:] == ["Collecting demo-package", ""]


@pytest.mark.asyncio
async def test_run_pip_in_process_normalizes_crlf_without_extra_blank_lines(
    monkeypatch,
):
    logged_lines = []

    def fake_pip_main(args):
        del args
        import sys

        sys.stdout.write("Collecting demo-package\r\n")
        sys.stdout.write("Installing collected packages\r\n")
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

    assert result == 0
    assert logged_lines[-2:] == [
        "Collecting demo-package",
        "Installing collected packages",
    ]


@pytest.mark.asyncio
async def test_run_pip_in_process_classifies_nonstandard_conflict_output(monkeypatch):
    def fake_pip_main(args):
        del args
        print(
            "Cannot install demo-package and astrbot-core because these package "
            "versions have conflicting dependencies."
        )
        print("The conflict is caused by:")
        print("    demo-package depends on shared-lib>=3.0")
        print("    AstrBot (constraint) depends on shared-lib==2.0")
        return 1

    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer._get_pip_main",
        lambda: fake_pip_main,
    )

    installer = PipInstaller("")
    with pytest.raises(pip_installer_module.DependencyConflictError) as exc_info:
        await installer._run_pip_in_process(["install", "demo-package"])

    assert exc_info.value.is_core_conflict is True
    assert "demo-package depends on shared-lib>=3.0" in str(exc_info.value)
    assert "AstrBot (constraint) depends on shared-lib==2.0" in str(exc_info.value)


def test_build_pip_args_rejects_package_name_and_requirements_path_together(tmp_path):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("demo-package\n", encoding="utf-8")

    installer = PipInstaller("")

    with pytest.raises(ValueError, match="package_name and requirements_path"):
        installer._build_pip_args("requests", str(requirements_path), None)


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

    missing = requirements_utils.find_missing_requirements(str(requirements_path))

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

    missing = requirements_utils.find_missing_requirements(str(requirements_path))

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

    missing = requirements_utils.find_missing_requirements(str(requirements_path))

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

    missing = requirements_utils.find_missing_requirements(str(requirements_path))

    assert missing == {"demo-package"}


def test_find_missing_requirements_returns_none_when_nested_file_missing(tmp_path):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("-r base.txt\n", encoding="utf-8")

    missing = requirements_utils.find_missing_requirements(str(requirements_path))

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

    missing = requirements_utils.find_missing_requirements(str(requirements_path))

    assert missing == {"demo-package"}


def test_find_missing_requirements_prefers_first_search_path_version(
    monkeypatch, tmp_path
):
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

    missing = requirements_utils.find_missing_requirements(str(requirements_path))

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

    missing = requirements_utils.find_missing_requirements(str(requirements_path))

    assert missing is None


def test_get_core_constraints_caches_fallback_resolution(monkeypatch):
    distribution_calls = []
    distributions_calls = []

    class FakeFallbackDistribution:
        metadata = {"Name": "AstrBot-App"}
        requires = ["shared-lib>=1.0"]

        def read_text(self, name):
            if name == "top_level.txt":
                return "astrbot\n"
            return ""

    fake_distribution = FakeFallbackDistribution()

    def mock_distribution(name):
        distribution_calls.append(name)
        if name == "AstrBot":
            raise pip_installer_module.importlib_metadata.PackageNotFoundError
        if name == "AstrBot-App":
            return fake_distribution
        raise pip_installer_module.importlib_metadata.PackageNotFoundError

    def mock_distributions(path=None):
        del path
        distributions_calls.append("scan")
        return [fake_distribution]

    monkeypatch.setattr(
        core_constraints_module.importlib_metadata,
        "distribution",
        mock_distribution,
    )
    monkeypatch.setattr(
        core_constraints_module.importlib_metadata,
        "distributions",
        mock_distributions,
    )
    monkeypatch.setattr(
        core_constraints_module,
        "_collect_installed_distribution_versions",
        lambda paths: {"shared-lib": "2.0"},
    )

    core_constraints_module._get_core_constraints.cache_clear()
    try:
        first = core_constraints_module._get_core_constraints(None)
        second = core_constraints_module._get_core_constraints(None)
    finally:
        core_constraints_module._get_core_constraints.cache_clear()

    assert first == ("shared-lib==2.0",)
    assert second == ("shared-lib==2.0",)
    assert distribution_calls == ["AstrBot", "AstrBot-App"]
    assert distributions_calls == ["scan"]


def test_get_core_constraints_skips_distributions_with_unreadable_top_level(
    monkeypatch,
):
    class BrokenDistribution:
        metadata = {"Name": "Broken-App"}
        requires = []

        def read_text(self, name):
            if name == "top_level.txt":
                raise OSError("cannot read top_level.txt")
            return ""

    class FakeFallbackDistribution:
        metadata = {"Name": "AstrBot-App"}
        requires = ["shared-lib>=1.0"]

        def read_text(self, name):
            if name == "top_level.txt":
                return "astrbot\n"
            return ""

    broken_distribution = BrokenDistribution()
    fake_distribution = FakeFallbackDistribution()

    def mock_distribution(name):
        if name == "AstrBot":
            raise pip_installer_module.importlib_metadata.PackageNotFoundError
        if name == "AstrBot-App":
            return fake_distribution
        raise pip_installer_module.importlib_metadata.PackageNotFoundError

    def mock_distributions(path=None):
        del path
        return [broken_distribution, fake_distribution]

    monkeypatch.setattr(
        core_constraints_module.importlib_metadata,
        "distribution",
        mock_distribution,
    )
    monkeypatch.setattr(
        core_constraints_module.importlib_metadata,
        "distributions",
        mock_distributions,
    )
    monkeypatch.setattr(
        core_constraints_module,
        "_collect_installed_distribution_versions",
        lambda paths: {"shared-lib": "2.0"},
    )

    core_constraints_module._get_core_constraints.cache_clear()
    try:
        constraints = core_constraints_module._get_core_constraints(None)
    finally:
        core_constraints_module._get_core_constraints.cache_clear()

    assert constraints == ("shared-lib==2.0",)


def test_core_constraints_file_propagates_inner_conflict_without_fake_warning(
    monkeypatch,
):
    warning_logs = []
    conflict = pip_installer_module.DependencyConflictError(
        "core conflict",
        [],
        is_core_conflict=True,
    )

    monkeypatch.setattr(
        core_constraints_module,
        "_get_core_constraints",
        lambda core_dist_name: ("aiohttp==3.13.3",),
    )
    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer.logger.warning",
        lambda line, *args: warning_logs.append(line % args if args else line),
    )

    with pytest.raises(
        pip_installer_module.DependencyConflictError,
        match="core conflict",
    ):
        with core_constraints_module._core_constraints_file(
            "AstrBot"
        ) as constraints_path:
            assert constraints_path is not None
            raise conflict

    assert warning_logs == []


def test_iter_requirement_lines_expands_nested_requirement_files(tmp_path):
    base_requirements = tmp_path / "base.txt"
    base_requirements.write_text("demo-package==1.0\n", encoding="utf-8")
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text(
        "# comment\n-r base.txt\n--extra-index-url https://example.com/simple\n",
        encoding="utf-8",
    )

    lines = list(requirements_utils._iter_requirement_lines(str(requirements_path)))

    assert lines == [
        "demo-package==1.0",
        "--extra-index-url https://example.com/simple",
    ]


def test_build_pip_args_extracts_requested_requirements():
    installer = PipInstaller("")

    args, requested = installer._build_pip_args(
        "--index-url https://example.com/simple demo-package",
        None,
        None,
    )

    assert args == [
        "install",
        "--index-url",
        "https://example.com/simple",
        "demo-package",
    ]
    assert requested == {"demo-package"}


def test_parse_package_install_input_collects_specs_and_requirement_names():
    parsed = requirements_utils.parse_package_install_input(
        "--index-url https://example.com/simple demo-package\nanother-package>=1.0\n"
    )

    assert parsed.specs == (
        "--index-url",
        "https://example.com/simple",
        "demo-package",
        "another-package>=1.0",
    )
    assert parsed.requirement_names == {"demo-package", "another-package"}


def test_build_pip_args_appends_default_index_when_not_overridden():
    installer = PipInstaller("")

    args, requested = installer._build_pip_args("demo-package", None, None)

    assert args == ["install", "demo-package", "-i", "https://pypi.org/simple"]
    assert requested == {"demo-package"}


@pytest.mark.asyncio
async def test_install_splits_space_separated_packages(monkeypatch):
    run_pip = _make_run_pip_mock()

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="demo-package another-package>=1.0")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:3] == ["install", "demo-package", "another-package>=1.0"]


@pytest.mark.asyncio
async def test_install_splits_three_space_separated_packages(monkeypatch):
    run_pip = _make_run_pip_mock()

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
    run_pip = _make_run_pip_mock()

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
    run_pip = _make_run_pip_mock()
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
    run_pip = _make_run_pip_mock()

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(
        package_name="demo-package another-package\nextra-package\n"
    )

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
    run_pip = _make_run_pip_mock()

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="demo-package ; python_version < '4'")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:2] == [
        "install",
        "demo-package ; python_version < '4'",
    ]


@pytest.mark.asyncio
async def test_install_keeps_single_requirement_with_compact_marker_intact(monkeypatch):
    run_pip = _make_run_pip_mock()

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name='demo-package; python_version < "4"')

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:2] == [
        "install",
        'demo-package; python_version < "4"',
    ]


@pytest.mark.asyncio
async def test_install_keeps_single_requirement_with_version_range_intact(monkeypatch):
    run_pip = _make_run_pip_mock()

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="demo-package >= 1.0, < 2.0")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:2] == [
        "install",
        "demo-package >= 1.0, < 2.0",
    ]


@pytest.mark.asyncio
async def test_install_tracks_only_real_requirement_names_for_spaced_single_requirement(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ASTRBOT_DESKTOP_CLIENT", "1")
    monkeypatch.delattr("sys.frozen", raising=False)

    site_packages_path = tmp_path / "site-packages"
    run_pip = _make_run_pip_mock()
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
    await installer.install(package_name="demo-package >= 1.0, < 2.0")

    assert ensure_preferred_calls == [(str(site_packages_path), {"demo-package"})]


def test_prefer_installed_dependencies_prefers_modules_for_requirements_in_desktop_runtime(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ASTRBOT_DESKTOP_CLIENT", "1")
    monkeypatch.delattr("sys.frozen", raising=False)

    site_packages_path = tmp_path / "site-packages"
    site_packages_path.mkdir()
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("demo-package>=1.0\n", encoding="utf-8")

    prepend_calls = []
    preferred_calls = []

    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer.get_astrbot_site_packages_path",
        lambda: str(site_packages_path),
    )
    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer._prepend_sys_path",
        lambda path: prepend_calls.append(path),
    )
    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer._ensure_plugin_dependencies_preferred",
        lambda path, requirements: preferred_calls.append((path, requirements)),
    )

    installer = PipInstaller("")
    installer.prefer_installed_dependencies(str(requirements_path))

    assert prepend_calls == [str(site_packages_path)]
    assert preferred_calls == [(str(site_packages_path), {"demo-package"})]


@pytest.mark.asyncio
async def test_install_multiline_input_strips_comments_and_splits_options(monkeypatch):
    run_pip = _make_run_pip_mock()

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
    run_pip = _make_run_pip_mock()

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="requests==2.31.0  # latest")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:2] == ["install", "requests==2.31.0"]


@pytest.mark.asyncio
async def test_install_splits_single_line_editable_option_input(monkeypatch):
    run_pip = _make_run_pip_mock()

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="-e .")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:3] == ["install", "-e", "."]


@pytest.mark.asyncio
async def test_install_splits_single_line_option_with_url(monkeypatch):
    run_pip = _make_run_pip_mock()

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
async def test_install_tracks_requirement_name_for_single_line_option_input(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ASTRBOT_DESKTOP_CLIENT", "1")
    monkeypatch.delattr("sys.frozen", raising=False)

    site_packages_path = tmp_path / "site-packages"
    run_pip = _make_run_pip_mock()
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
    await installer.install(
        package_name="--index-url https://example.com/simple demo-package"
    )

    assert ensure_preferred_calls == [(str(site_packages_path), {"demo-package"})]


@pytest.mark.asyncio
async def test_install_keeps_equals_form_index_override(monkeypatch):
    run_pip = _make_run_pip_mock()

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
    run_pip = _make_run_pip_mock()

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
    run_pip = _make_run_pip_mock()

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


def test_find_missing_requirements_returns_none_for_editable_local_path_reference(
    tmp_path,
):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("-e ../sharedlib\n", encoding="utf-8")

    missing = requirements_utils.find_missing_requirements(str(requirements_path))

    assert missing is None


@pytest.mark.parametrize(
    "requirement_line",
    [
        "-e sharedlib\n",
        "--editable=.\\sharedlib\n",
    ],
)
def test_find_missing_requirements_returns_none_for_editable_local_path_variants(
    tmp_path, requirement_line
):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text(requirement_line, encoding="utf-8")

    missing = requirements_utils.find_missing_requirements(str(requirements_path))

    assert missing is None


@pytest.mark.asyncio
async def test_install_strips_inline_comment_from_option_line(monkeypatch):
    run_pip = _make_run_pip_mock()

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(
        package_name=(
            "--extra-index-url https://example.com/simple  # mirror\ndemo-package\n"
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
    run_pip = _make_run_pip_mock()

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    raw_input = "demo-package !!! another-package"
    await installer.install(package_name=raw_input)

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:4] == ["install", "demo-package", "!!!", "another-package"]


@pytest.mark.asyncio
async def test_install_ignores_whitespace_only_package_string(monkeypatch):
    run_pip = _make_run_pip_mock()

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="   ")

    run_pip.assert_not_awaited()


@pytest.mark.asyncio
async def test_install_ignores_missing_package_and_requirements(monkeypatch):
    run_pip = _make_run_pip_mock()

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install()

    run_pip.assert_not_awaited()


@pytest.mark.asyncio
async def test_install_respects_index_override_in_pip_install_arg(monkeypatch):
    run_pip = _make_run_pip_mock()

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


@pytest.mark.asyncio
async def test_install_respects_no_index_with_find_links(monkeypatch):
    run_pip = _make_run_pip_mock()

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(
        package_name="--no-index --find-links /tmp/wheels demo-package"
    )

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert recorded_args[0:5] == [
        "install",
        "--no-index",
        "--find-links",
        "/tmp/wheels",
        "demo-package",
    ]
    assert "-i" not in recorded_args


def test_redact_pip_args_for_logging_redacts_inline_url_credentials():
    redacted_args = pip_installer_module._redact_pip_args_for_logging(
        [
            "install",
            "--index-url=https://user:secret@example.com/simple",
            "demo-package",
        ]
    )

    assert redacted_args == [
        "install",
        "--index-url=https://<redacted>@example.com/simple",
        "demo-package",
    ]


def test_redact_pip_args_for_logging_redacts_sensitive_option_value_pairs():
    redacted_args = pip_installer_module._redact_pip_args_for_logging(
        [
            "install",
            "--password",
            "super-secret",
            "--token",
            "opaque-token",
            "demo-package",
        ]
    )

    assert redacted_args == [
        "install",
        "--password",
        "****",
        "--token",
        "****",
        "demo-package",
    ]


def test_redact_pip_args_for_logging_redacts_inline_sensitive_values():
    redacted_args = pip_installer_module._redact_pip_args_for_logging(
        [
            "install",
            "--api-token=super-secret",
            "password=hunter2",
            "demo-package",
        ]
    )

    assert redacted_args == [
        "install",
        "--api-token=****",
        "password=****",
        "demo-package",
    ]


@pytest.mark.asyncio
async def test_install_logs_redacted_pip_argv_when_credentials_present(monkeypatch):
    run_pip = _make_run_pip_mock()
    logged_lines = []

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)
    monkeypatch.setattr(
        "astrbot.core.utils.pip_installer.logger.info",
        lambda line, *args: logged_lines.append(line % args if args else line),
    )

    installer = PipInstaller("")
    await installer.install(
        package_name="--index-url https://user:secret@example.com/simple demo-package"
    )

    argv_logs = [line for line in logged_lines if line.startswith("Pip 包管理器 argv:")]

    assert len(argv_logs) == 1
    assert "secret" not in argv_logs[0]
    assert "user:" not in argv_logs[0]
    assert "https://<redacted>@example.com/simple" in argv_logs[0]


@pytest.mark.asyncio
async def test_install_does_not_add_aliyun_trusted_host_for_default_index(monkeypatch):
    run_pip = _make_run_pip_mock()

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("")
    await installer.install(package_name="demo-package")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert "-i" in recorded_args
    assert "https://pypi.org/simple" in recorded_args
    assert "--trusted-host" not in recorded_args


@pytest.mark.asyncio
async def test_install_adds_aliyun_trusted_host_only_for_aliyun_index(monkeypatch):
    run_pip = _make_run_pip_mock()

    monkeypatch.setattr(PipInstaller, "_run_pip_in_process", run_pip)

    installer = PipInstaller("", pypi_index_url="https://mirrors.aliyun.com/simple")
    await installer.install(package_name="demo-package")

    run_pip.assert_awaited_once()
    recorded_args = run_pip.await_args_list[0].args[0]

    assert "-i" in recorded_args
    assert "https://mirrors.aliyun.com/simple" in recorded_args
    trusted_host_index = recorded_args.index("--trusted-host")
    assert recorded_args[trusted_host_index + 1] == "mirrors.aliyun.com"
