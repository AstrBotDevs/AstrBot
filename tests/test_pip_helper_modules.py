from pathlib import Path

import pytest

from astrbot.core.utils import core_constraints as core_constraints_module
from astrbot.core.utils import requirements_utils
from astrbot.core.utils.core_constraints import CoreConstraintsProvider


def test_requirements_utils_parse_package_install_input_collects_specs_and_names():
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


def test_core_constraints_provider_writes_constraints_file_from_fallback_distribution(
    monkeypatch,
):
    class FakeFallbackDistribution:
        metadata = {"Name": "AstrBot-App"}
        requires = ["shared-lib>=1.0"]

        def read_text(self, name):
            if name == "top_level.txt":
                return "astrbot\n"
            return ""

    fake_distribution = FakeFallbackDistribution()

    def mock_distribution(name):
        if name == "AstrBot":
            raise core_constraints_module.importlib_metadata.PackageNotFoundError
        if name == "AstrBot-App":
            return fake_distribution
        raise core_constraints_module.importlib_metadata.PackageNotFoundError

    def mock_distributions(path=None):
        del path
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
        "collect_installed_distribution_versions",
        lambda paths: {"shared-lib": "2.0"},
    )

    core_constraints_module._get_core_constraints.cache_clear()
    try:
        provider = CoreConstraintsProvider(None)
        with provider.constraints_file() as constraints_path:
            assert constraints_path is not None
            assert (
                Path(constraints_path).read_text(encoding="utf-8") == "shared-lib==2.0"
            )
    finally:
        core_constraints_module._get_core_constraints.cache_clear()


def test_resolve_core_dist_name_skips_distribution_without_name(monkeypatch):
    class NamelessDistribution:
        metadata = {}

        def read_text(self, name):
            if name == "top_level.txt":
                return "astrbot\n"
            return ""

    class NamedDistribution:
        metadata = {"Name": "AstrBot-App"}

        def read_text(self, name):
            if name == "top_level.txt":
                return "astrbot\n"
            return ""

    monkeypatch.setattr(
        core_constraints_module.importlib_metadata,
        "distribution",
        lambda name: (_ for _ in ()).throw(
            core_constraints_module.importlib_metadata.PackageNotFoundError
        ),
    )
    monkeypatch.setattr(
        core_constraints_module.importlib_metadata,
        "distributions",
        lambda: [NamelessDistribution(), NamedDistribution()],
    )

    assert core_constraints_module._resolve_core_dist_name(None) == "AstrBot-App"


def test_find_missing_requirements_returns_none_when_precheck_gate_fails(
    monkeypatch,
    tmp_path,
):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("demo-package\n", encoding="utf-8")

    monkeypatch.setattr(
        requirements_utils,
        "_load_requirement_lines_for_precheck",
        lambda path: (False, None),
    )

    missing = requirements_utils.find_missing_requirements(str(requirements_path))

    assert missing is None


def test_parse_package_install_input_tracks_only_named_direct_references():
    named = requirements_utils.parse_package_install_input(
        "git+https://example.com/demo.git#egg=demo-package"
    )
    unnamed = requirements_utils.parse_package_install_input(
        "git+https://example.com/demo.git"
    )

    assert named.requirement_names == {"demo-package"}
    assert unnamed.requirement_names == set()


def test_find_missing_requirements_or_raise_uses_requirements_exception(tmp_path):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("-e ../sharedlib\n", encoding="utf-8")

    with pytest.raises(requirements_utils.RequirementsPrecheckFailed):
        requirements_utils.find_missing_requirements_or_raise(str(requirements_path))


def test_find_missing_requirements_logs_path_and_reason_on_precheck_fallback(
    monkeypatch,
    tmp_path,
):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("git+https://example.com/demo.git\n", encoding="utf-8")
    warning_logs = []

    monkeypatch.setattr(
        "astrbot.core.utils.requirements_utils.logger.warning",
        lambda line, *args: warning_logs.append(line % args if args else line),
    )

    missing = requirements_utils.find_missing_requirements(str(requirements_path))

    assert missing is None
    assert any(str(requirements_path) in log for log in warning_logs)
    assert any("direct reference" in log for log in warning_logs)


def test_load_requirement_lines_for_precheck_uses_parse_requirement_line_result(
    monkeypatch,
    tmp_path,
):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("git+https://example.com/demo.git\n", encoding="utf-8")

    monkeypatch.setattr(
        requirements_utils,
        "_parse_requirement_line",
        lambda line: ("demo-package", None) if line.startswith("git+") else None,
    )

    can_precheck, requirement_lines = (
        requirements_utils._load_requirement_lines_for_precheck(str(requirements_path))
    )

    assert can_precheck is True
    assert requirement_lines == ["git+https://example.com/demo.git"]
