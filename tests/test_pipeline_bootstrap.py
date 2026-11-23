"""Real stage imports register exactly one built-in class per stage."""

from importlib import import_module

from astrbot.core.pipeline import bootstrap
from astrbot.core.pipeline.stage import registered_stages


def test_real_builtin_bootstrap_is_idempotent(monkeypatch):
    monkeypatch.setattr(bootstrap, "_builtin_stages_registered", False)
    bootstrap.ensure_builtin_stages_registered()
    first = list(registered_stages)
    bootstrap.ensure_builtin_stages_registered()
    assert registered_stages == first
    names = [stage.__name__ for stage in first]
    assert bootstrap._EXPECTED_STAGE_NAMES.issubset(names)
    for name in bootstrap._EXPECTED_STAGE_NAMES:
        assert names.count(name) == 1
    for module_path in bootstrap._BUILTIN_STAGE_MODULES:
        module = import_module(module_path)
        owned_classes = [
            stage for stage in first if stage.__module__ == module.__name__
        ]
        assert len(owned_classes) == 1
        assert getattr(module, owned_classes[0].__name__) is owned_classes[0]
