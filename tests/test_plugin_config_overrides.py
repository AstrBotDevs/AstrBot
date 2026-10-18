import json
from pathlib import Path
from types import SimpleNamespace

from astrbot.core.star import context as context_module
from astrbot.core.star.plugin_config_overrides import (
    load_plugin_config_overrides,
    overrides_path_for,
    resolve_plugin_config,
    resolve_plugin_config_overrides,
    save_plugin_config_overrides,
)


def test_overrides_path_for_is_a_sibling_of_the_plugin_config(tmp_path: Path):
    config_path = tmp_path / "demo_config.json"

    assert overrides_path_for(config_path) == tmp_path / "demo_config.overrides.json"


def test_load_missing_file_returns_empty_mapping(tmp_path: Path):
    assert load_plugin_config_overrides(tmp_path / "missing.json") == {}


def test_load_malformed_file_returns_empty_mapping(tmp_path: Path):
    path = tmp_path / "demo_config.overrides.json"
    path.write_text("{not json", encoding="utf-8")

    assert load_plugin_config_overrides(path) == {}


def test_load_deeply_nested_json_returns_empty_mapping(tmp_path: Path):
    # 超出 json 解码递归限制的覆盖文件不应阻止插件启动。
    path = tmp_path / "demo_config.overrides.json"
    depth = 2000
    path.write_text("[" * depth + "]" * depth, encoding="utf-8")

    assert load_plugin_config_overrides(path) == {}


def test_load_non_object_root_returns_empty_mapping(tmp_path: Path):
    path = tmp_path / "demo_config.overrides.json"
    path.write_text(json.dumps(["aiocqhttp:group:1"]), encoding="utf-8")

    assert load_plugin_config_overrides(path) == {}


def test_load_without_scopes_object_returns_empty_mapping(tmp_path: Path):
    path = tmp_path / "demo_config.overrides.json"
    path.write_text(json.dumps({"version": 1}), encoding="utf-8")

    assert load_plugin_config_overrides(path) == {}


def test_load_skips_invalid_scope_entries(tmp_path: Path):
    path = tmp_path / "demo_config.overrides.json"
    path.write_text(
        json.dumps(
            {
                "scopes": {
                    "aiocqhttp:group:1": {"enable": True},
                    "aiocqhttp:group:2": "not an object",
                }
            }
        ),
        encoding="utf-8",
    )

    assert load_plugin_config_overrides(path) == {"aiocqhttp:group:1": {"enable": True}}


def test_load_skips_scopes_with_invalid_umo_syntax(tmp_path: Path):
    path = tmp_path / "demo_config.overrides.json"
    path.write_text(
        json.dumps(
            {
                "scopes": {
                    "not-a-umo-pattern": {"enable": True},
                    "aiocqhttp:group:1": {"enable": False},
                }
            }
        ),
        encoding="utf-8",
    )

    assert load_plugin_config_overrides(path) == {"aiocqhttp:group:1": {"enable": False}}


def test_save_rejects_scopes_with_invalid_umo_syntax(tmp_path: Path):
    try:
        save_plugin_config_overrides(
            tmp_path / "demo_config.overrides.json", {"bad-key": {"enable": True}}
        )
    except ValueError as exc:
        assert "bad-key" in str(exc)
    else:  # pragma: no cover - the assertion below is the failure path
        raise AssertionError("expected ValueError")


def test_saved_overrides_round_trip(tmp_path: Path):
    path = tmp_path / "demo_config.overrides.json"
    scopes = {"aiocqhttp:group:1": {"nested": {"value": 1}}}

    save_plugin_config_overrides(path, scopes)

    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1
    assert load_plugin_config_overrides(path) == scopes


def test_resolve_matches_exact_scope_and_ignores_others():
    scopes = {
        "aiocqhttp:group:1": {"reply_style": "concise"},
        "aiocqhttp:group:2": {"reply_style": "verbose"},
    }

    assert resolve_plugin_config_overrides(scopes, "aiocqhttp:group:1") == {
        "reply_style": "concise"
    }
    assert resolve_plugin_config_overrides(scopes, "aiocqhttp:group:3") == {}


def test_resolve_supports_wildcards_and_empty_segments():
    scopes = {"aiocqhttp:group:*": {"enable_tts": False}}

    assert resolve_plugin_config_overrides(scopes, "aiocqhttp:group:123") == {
        "enable_tts": False
    }
    assert resolve_plugin_config_overrides(scopes, "aiocqhttp:private:123") == {}

    catch_all = {"::": {"language": "zh"}}
    assert resolve_plugin_config_overrides(catch_all, "lark:group:abc") == {
        "language": "zh"
    }


def test_first_matching_scope_wins():
    scopes = {
        "aiocqhttp:group:*": {"reply_style": "concise"},
        "aiocqhttp:group:1": {"reply_style": "verbose"},
    }

    assert resolve_plugin_config_overrides(scopes, "aiocqhttp:group:1") == {
        "reply_style": "concise"
    }


def test_global_config_is_returned_without_umo():
    scopes = {"aiocqhttp:group:1": {"enable": False}}
    base = {"enable": True, "nested": {"a": 1}}

    result = resolve_plugin_config(base, scopes, None)

    assert result == base
    # 必须返回快照而非原对象，否则调用方可以篡改插件的全局配置。
    assert result is not base
    result["nested"]["a"] = 99
    assert base["nested"]["a"] == 1


def test_merge_is_recursive_and_does_not_mutate_the_global_config():
    base = {"enable": True, "nested": {"a": 1, "b": 2}, "items": [1, 2]}
    scopes = {
        "aiocqhttp:group:1": {"nested": {"b": 3, "c": 4}, "items": [9]},
    }

    merged = resolve_plugin_config(base, scopes, "aiocqhttp:group:1")

    assert merged == {
        "enable": True,
        "nested": {"a": 1, "b": 3, "c": 4},
        "items": [9],
    }
    assert base == {"enable": True, "nested": {"a": 1, "b": 2}, "items": [1, 2]}
    assert merged is not base


def test_context_get_plugin_config_merges_the_matching_override(monkeypatch):
    metadata = SimpleNamespace(
        name="demo",
        config={"enable": True, "nested": {"a": 1}},
        config_overrides={"aiocqhttp:group:1": {"nested": {"a": 2}}},
    )
    monkeypatch.setattr(context_module, "star_registry", [metadata])

    assert context_module.Context.get_plugin_config(
        object(), "demo", "aiocqhttp:group:1"
    ) == {"enable": True, "nested": {"a": 2}}
    assert context_module.Context.get_plugin_config(
        object(), "demo", "aiocqhttp:group:2"
    ) == {"enable": True, "nested": {"a": 1}}
    assert metadata.config == {"enable": True, "nested": {"a": 1}}


def test_context_get_plugin_config_rejects_unknown_plugin(monkeypatch):
    monkeypatch.setattr(context_module, "star_registry", [])

    try:
        context_module.Context.get_plugin_config(object(), "missing")
    except ValueError as exc:
        assert "missing" in str(exc)
    else:  # pragma: no cover - the assertion below is the failure path
        raise AssertionError("expected ValueError")


def test_context_get_plugin_config_disambiguates_duplicate_names(monkeypatch):
    first = SimpleNamespace(
        name="demo",
        plugin_id="alice/demo",
        config={"owner": "alice"},
        config_overrides={},
    )
    second = SimpleNamespace(
        name="demo",
        plugin_id="bob/demo",
        config={"owner": "bob"},
        config_overrides={},
    )
    monkeypatch.setattr(context_module, "star_registry", [first, second])

    # 重名插件必须能通过插件 ID（author/name）取到各自的配置。
    assert context_module.Context.get_plugin_config(object(), "alice/demo") == {
        "owner": "alice"
    }
    assert context_module.Context.get_plugin_config(object(), "bob/demo") == {
        "owner": "bob"
    }

    # 仅给重名的插件名时必须报错，而不是静默返回第一个插件的配置。
    try:
        context_module.Context.get_plugin_config(object(), "demo")
    except ValueError as exc:
        assert "demo" in str(exc)
    else:  # pragma: no cover - the assertion below is the failure path
        raise AssertionError("expected ValueError")
