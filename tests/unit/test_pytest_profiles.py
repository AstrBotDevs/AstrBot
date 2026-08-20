"""Regression tests for the repository pytest profile policy."""

import ast
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFTEST_PATH = PROJECT_ROOT / "tests" / "conftest.py"
PLATFORM_TEST_MODULES = (
    "tests/unit/platform/test_dingtalk_adapter.py",
    "tests/unit/platform/test_discord_adapter.py",
    "tests/unit/platform/test_lark_adapter.py",
    "tests/unit/platform/test_line_adapter.py",
    "tests/unit/platform/test_mattermost_adapter.py",
    "tests/unit/platform/test_platform_audio_media_resolver.py",
    "tests/unit/platform/test_platform_image_format_preservation.py",
    "tests/unit/platform/test_slack_adapter.py",
    "tests/unit/platform/test_telegram_adapter.py",
    "tests/unit/platform/test_wecom_adapter.py",
    "tests/unit/platform/test_wecom_ai_bot_adapter.py",
    "tests/unit/platform/test_weixin_oc_adapter.py",
    "tests/unit/platform/test_weixin_official_account_adapter.py",
    "tests/unit/test_aiocqhttp_adapter.py",
    "tests/unit/test_misskey_adapter.py",
    "tests/unit/platform/test_napcat_ws_lifecycle.py",
    "tests/unit/platform/test_napcat_inbound_parse.py",
    "tests/unit/platform/test_napcat_inbound_events.py",
    "tests/unit/platform/test_napcat_notices.py",
    "tests/unit/platform/test_napcat_outbound.py",
    "tests/unit/test_satori_adapter.py",
)


def _load_conftest_module():
    spec = spec_from_file_location("astrbot_test_profile_conftest", CONFTEST_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load test configuration from {CONFTEST_PATH}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeItem:
    def __init__(
        self, path: Path, markers: dict[str, tuple[object, ...]] | None = None
    ):
        self.path = path
        self.markers = {
            name: SimpleNamespace(args=args) for name, args in (markers or {}).items()
        }

    def add_marker(self, marker) -> None:
        mark = marker.mark
        self.markers[mark.name] = SimpleNamespace(args=mark.args)

    def get_closest_marker(self, name: str):
        return self.markers.get(name)


class _FakeHook:
    def __init__(self) -> None:
        self.deselected: list[_FakeItem] = []

    def pytest_deselected(self, *, items: list[_FakeItem]) -> None:
        self.deselected.extend(items)


class _FakeConfig:
    def __init__(self, profile: str | None) -> None:
        self.profile = profile
        self.hook = _FakeHook()

    def getoption(self, option: str) -> str | None:
        assert option == "--test-profile"
        return self.profile


def _item(path: str, *markers: str) -> _FakeItem:
    return _FakeItem(
        PROJECT_ROOT / path,
        dict.fromkeys(markers, ()),
    )


def test_blocking_profile_excludes_all_non_blocking_domains() -> None:
    conftest = _load_conftest_module()
    items = [
        _item("tests/unit/test_core.py"),
        _item("tests/unit/test_provider.py", "provider"),
        _item("tests/unit/test_platform.py", "platform"),
        _item("tests/unit/test_slow.py", "slow"),
        _item("tests/unit/test_live.py", "live"),
        _item("tests/test_api.py", "integration"),
        _item("tests/e2e/test_browser.py"),
    ]
    config = _FakeConfig("blocking")

    conftest.pytest_collection_modifyitems(None, config, items)

    assert [item.path.name for item in items] == [
        "test_core.py",
        "test_provider.py",
        "test_platform.py",
    ]
    assert {item.path.name for item in config.hook.deselected} == {
        "test_slow.py",
        "test_live.py",
        "test_api.py",
        "test_browser.py",
    }


def test_collection_assigns_unit_integration_and_blocking_markers() -> None:
    conftest = _load_conftest_module()
    unit_item = _item("tests/unit/test_core.py")
    agent_item = _item("tests/agent/test_context.py")
    docs_item = _item("docs/tests/test_docs.py")
    integration_item = _item("tests/integration/test_api.py")
    e2e_item = _item("tests/e2e/test_browser.py")
    config = _FakeConfig("all")
    items = [unit_item, agent_item, docs_item, integration_item, e2e_item]

    conftest.pytest_collection_modifyitems(None, config, items)

    for item in (unit_item, agent_item, docs_item):
        assert {"unit", "blocking"} <= item.markers.keys()
    for item in (integration_item, e2e_item):
        assert "integration" in item.markers
        assert "blocking" not in item.markers


def test_profile_validation_rejects_unknown_environment_value(monkeypatch) -> None:
    conftest = _load_conftest_module()
    monkeypatch.setenv("ASTRBOT_TEST_PROFILE", "not-a-profile")

    with pytest.raises(pytest.UsageError, match="Unknown test profile"):
        conftest.get_test_profile(_FakeConfig(None))


def test_command_line_profile_takes_precedence_over_environment(monkeypatch) -> None:
    conftest = _load_conftest_module()
    monkeypatch.setenv("ASTRBOT_TEST_PROFILE", "blocking")

    assert conftest.get_test_profile(_FakeConfig("all")) == "all"


def test_platform_adapter_suites_keep_platform_domain_tag() -> None:
    for relative_path in PLATFORM_TEST_MODULES:
        module = ast.parse((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))
        markers = [
            assignment.value
            for assignment in module.body
            if isinstance(assignment, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "pytestmark"
                for target in assignment.targets
            )
        ]

        assert any(
            isinstance(marker, ast.Attribute)
            and marker.attr == "platform"
            and isinstance(marker.value, ast.Attribute)
            and marker.value.attr == "mark"
            and isinstance(marker.value.value, ast.Name)
            and marker.value.value.id == "pytest"
            for marker in markers
        ), relative_path


def test_mocked_platform_and_provider_suites_stay_in_blocking() -> None:
    conftest = _load_conftest_module()
    items = [
        _item("tests/unit/platform/test_telegram_adapter.py", "platform"),
        _item("tests/unit/test_openai_embedding_contract.py", "provider"),
        _item("tests/unit/test_core.py"),
    ]
    config = _FakeConfig("blocking")

    conftest.pytest_collection_modifyitems(None, config, items)

    assert [item.path.name for item in items] == [
        "test_telegram_adapter.py",
        "test_openai_embedding_contract.py",
        "test_core.py",
    ]
    assert config.hook.deselected == []
