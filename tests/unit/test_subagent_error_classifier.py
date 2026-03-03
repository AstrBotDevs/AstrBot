from __future__ import annotations

from astrbot.core.subagent.error_classifier import (
    DefaultErrorClassifier,
    build_error_classifier_from_config,
)
from astrbot.core.subagent.models import SubagentErrorClassifierConfig


def test_build_error_classifier_from_config_maps_allowlisted_types():
    classifier, diagnostics = build_error_classifier_from_config(
        SubagentErrorClassifierConfig(
            type="default",
            fatal_exceptions=["ValueError"],
            transient_exceptions=["TimeoutError"],
            default_class="retryable",
        )
    )
    assert diagnostics == []
    assert classifier.classify(ValueError("x")) == "fatal"
    assert classifier.classify(TimeoutError("x")) == "transient"
    assert classifier.classify(RuntimeError("x")) == "retryable"


def test_build_error_classifier_ignores_unknown_exception_name():
    _, diagnostics = build_error_classifier_from_config(
        SubagentErrorClassifierConfig(
            fatal_exceptions=["ValueError", "NotExistError"],
            transient_exceptions=["TimeoutError"],
            default_class="transient",
        )
    )
    assert any("NotExistError" in item for item in diagnostics)


def test_default_error_classifier_defaults_to_transient_for_unknown():
    classifier = DefaultErrorClassifier()
    assert classifier.classify(RuntimeError("unknown")) == "transient"
