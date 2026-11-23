"""Bootstrap decisions restore globals and never evict imported modules."""

from unittest.mock import Mock, call

import pytest

from astrbot.core.pipeline import bootstrap


@pytest.fixture
def isolated_bootstrap(monkeypatch):
    monkeypatch.setattr(bootstrap, "_builtin_stages_registered", False)
    monkeypatch.setattr(bootstrap, "registered_stages", [])
    importer = Mock()
    monkeypatch.setattr(bootstrap, "import_module", importer)
    return importer


def test_registered_flag_short_circuits(isolated_bootstrap, monkeypatch):
    monkeypatch.setattr(bootstrap, "_builtin_stages_registered", True)
    bootstrap.ensure_builtin_stages_registered()
    isolated_bootstrap.assert_not_called()


def test_complete_registry_skips_imports_by_class_name(isolated_bootstrap):
    bootstrap.registered_stages.extend(
        type(name, (), {}) for name in bootstrap._EXPECTED_STAGE_NAMES
    )
    bootstrap.registered_stages.append(type("CustomStage", (), {}))
    bootstrap.ensure_builtin_stages_registered()
    isolated_bootstrap.assert_not_called()
    assert bootstrap._builtin_stages_registered is True


@pytest.mark.parametrize("partial", [False, True])
def test_missing_stages_import_in_pipeline_order_only_once(isolated_bootstrap, partial):
    if partial:
        bootstrap.registered_stages.append(type("ProcessStage", (), {}))
    bootstrap.ensure_builtin_stages_registered()
    bootstrap.ensure_builtin_stages_registered()
    assert isolated_bootstrap.call_args_list == [
        call(path) for path in bootstrap._BUILTIN_STAGE_MODULES
    ]
    assert bootstrap._builtin_stages_registered is True


def test_import_failure_does_not_mark_bootstrap_complete(isolated_bootstrap):
    isolated_bootstrap.side_effect = ImportError("stage dependency failed")
    with pytest.raises(ImportError, match="stage dependency failed"):
        bootstrap.ensure_builtin_stages_registered()
    assert bootstrap._builtin_stages_registered is False
    assert isolated_bootstrap.call_args_list == [
        call(bootstrap._BUILTIN_STAGE_MODULES[0])
    ]


def test_builtin_stage_contract_covers_each_expected_stage_once():
    expected = {
        "waking_check": "WakingCheckStage",
        "whitelist_check": "WhitelistCheckStage",
        "session_status_check": "SessionStatusCheckStage",
        "rate_limit_check": "RateLimitStage",
        "content_safety_check": "ContentSafetyCheckStage",
        "preprocess_stage": "PreProcessStage",
        "process_stage": "ProcessStage",
        "result_decorate": "ResultDecorateStage",
        "respond": "RespondStage",
    }
    assert bootstrap._BUILTIN_STAGE_MODULES == tuple(
        f"astrbot.core.pipeline.{part}.stage" for part in expected
    )
    assert bootstrap._EXPECTED_STAGE_NAMES == set(expected.values())
