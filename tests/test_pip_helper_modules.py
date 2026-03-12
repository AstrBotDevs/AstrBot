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


def test_build_missing_requirements_install_lines_keeps_only_missing_lines(tmp_path):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text(
        'aiohttp>=3.0\nboto3==1.2; python_version >= "3.0"\nbotocore\n',
        encoding="utf-8",
    )

    install_lines = requirements_utils.build_missing_requirements_install_lines(
        str(requirements_path), {"boto3", "botocore"}
    )

    assert install_lines == (
        'boto3==1.2; python_version >= "3.0"',
        "botocore",
    )


def test_build_missing_requirements_install_lines_returns_empty_tuple_when_all_satisfied(
    tmp_path,
):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("aiohttp>=3.0\nboto3\n", encoding="utf-8")

    install_lines = requirements_utils.build_missing_requirements_install_lines(
        str(requirements_path), set()
    )

    assert install_lines == ()


def test_build_missing_requirements_install_lines_returns_none_for_option_lines(
    tmp_path,
):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text(
        "--extra-index-url https://example.com/simple\nboto3\n",
        encoding="utf-8",
    )

    install_lines = requirements_utils.build_missing_requirements_install_lines(
        str(requirements_path), {"boto3"}
    )

    assert install_lines is None


def test_build_missing_requirements_install_lines_skips_inactive_marker_lines(
    tmp_path,
):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text(
        'boto3\nother-package; sys_platform == "win32"\n',
        encoding="utf-8",
    )

    install_lines = requirements_utils.build_missing_requirements_install_lines(
        str(requirements_path), {"boto3"}
    )

    assert install_lines == ("boto3",)


def test_plan_missing_requirements_install_returns_none_when_missing_names_cannot_map_to_lines(
    monkeypatch,
    tmp_path,
):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("boto3\n", encoding="utf-8")

    monkeypatch.setattr(
        requirements_utils,
        "find_missing_requirements",
        lambda path: {"botocore"},
    )

    plan = requirements_utils.plan_missing_requirements_install(str(requirements_path))

    assert plan is not None
    assert plan.missing_names == frozenset({"botocore"})
    assert plan.install_lines == ()
    assert plan.fallback_reason == "unmapped missing requirement names"


def test_build_missing_requirements_install_lines_logs_why_option_lines_fall_back(
    monkeypatch,
    tmp_path,
):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text(
        "--extra-index-url https://example.com/simple\nboto3\n",
        encoding="utf-8",
    )

    info_logs = []

    monkeypatch.setattr(
        "astrbot.core.utils.requirements_utils.logger.info",
        lambda line, *args: info_logs.append(line % args if args else line),
    )

    install_lines = requirements_utils.build_missing_requirements_install_lines(
        str(requirements_path), {"boto3"}
    )

    assert install_lines is None
    assert any(str(requirements_path) in log for log in info_logs)
    assert any("option/direct-reference" in log for log in info_logs)


def test_find_missing_requirements_logs_path_and_reason_on_precheck_fallback(
    monkeypatch,
    tmp_path,
):
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("git+https://example.com/demo.git\n", encoding="utf-8")

    info_logs = []

    monkeypatch.setattr(
        "astrbot.core.utils.requirements_utils.logger.info",
        lambda line, *args: info_logs.append(line % args if args else line),
    )

    missing = requirements_utils.find_missing_requirements(str(requirements_path))

    assert missing is None
    assert any(str(requirements_path) in log for log in info_logs)
    assert any("option/direct-reference" in log for log in info_logs)


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


def test_collect_installed_distribution_versions_skips_nameless_distribution(
    monkeypatch,
):
    class NamelessDistribution:
        metadata = {}
        version = "1.0"

    class NamedDistribution:
        metadata = {"Name": "demo-package"}
        version = "2.0"

    monkeypatch.setattr(
        requirements_utils.importlib_metadata,
        "distributions",
        lambda path: [NamelessDistribution(), NamedDistribution()],
    )

    installed = requirements_utils.collect_installed_distribution_versions(
        ["/tmp/test"]
    )

    assert installed == {"demo-package": "2.0"}


def test_get_core_constraints_logs_resolution_step_context(monkeypatch):
    warning_logs = []

    monkeypatch.setattr(
        core_constraints_module,
        "_resolve_core_dist_name",
        lambda core_dist_name: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        "astrbot.core.utils.core_constraints.logger.warning",
        lambda line, *args: warning_logs.append(line % args if args else line),
    )

    core_constraints_module._get_core_constraints.cache_clear()
    try:
        constraints = core_constraints_module._get_core_constraints(None)
    finally:
        core_constraints_module._get_core_constraints.cache_clear()

    assert constraints == ()
    assert any("解析核心分发名称失败" in log for log in warning_logs)


def test_iter_requirements_supports_direct_line_input():
    parsed = list(
        requirements_utils.iter_requirements(
            lines=["demo-package>=1.0", 'other-package; sys_platform == "win32"']
        )
    )

    assert parsed == [
        ("demo-package", requirements_utils.Requirement("demo-package>=1.0").specifier)
    ]


def test_parse_requirement_name_and_spec_preserves_direct_reference_rules():
    named = requirements_utils._parse_requirement_name_and_spec(
        "git+https://example.com/demo.git#egg=demo-package"
    )
    unnamed = requirements_utils._parse_requirement_name_and_spec(
        "git+https://example.com/demo.git"
    )

    assert named == ("demo-package", None)
    assert unnamed == (None, None)


def test_parse_requirement_name_and_spec_handles_plain_requirement_token():
    parsed = requirements_utils._parse_requirement_name_and_spec("demo-package>=1.0")

    assert parsed == (
        "demo-package",
        requirements_utils.Requirement("demo-package>=1.0").specifier,
    )
