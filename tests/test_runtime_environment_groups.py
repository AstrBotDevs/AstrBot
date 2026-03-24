from __future__ import annotations

import json
from pathlib import Path

import pytest

from astrbot_sdk.runtime.environment_groups import (
    EnvironmentGroup,
    EnvironmentPlanner,
    GROUP_STATE_FILE_NAME,
    GroupEnvironmentManager,
)
from astrbot_sdk.runtime.loader import PluginSpec


def _plugin_spec(
    tmp_path: Path,
    name: str,
    *,
    python_version: str = "3.12",
    requirements: list[str] | None = None,
) -> PluginSpec:
    plugin_dir = tmp_path / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = plugin_dir / "plugin.yaml"
    requirements_path = plugin_dir / "requirements.txt"
    manifest_path.write_text(f"name: {name}\n", encoding="utf-8")
    requirements_path.write_text(
        "\n".join(requirements or []) + ("\n" if requirements else ""),
        encoding="utf-8",
    )
    return PluginSpec(
        name=name,
        plugin_dir=plugin_dir,
        manifest_path=manifest_path,
        requirements_path=requirements_path,
        python_version=python_version,
        manifest_data={"name": name},
    )


def _group(
    repo_root: Path, plugin: PluginSpec, *, fingerprint: str = "fingerprint"
) -> EnvironmentGroup:
    venv_path = repo_root / ".astrbot" / "envs" / plugin.name
    lockfile_path = repo_root / ".astrbot" / "locks" / f"{plugin.name}.txt"
    metadata_path = repo_root / ".astrbot" / "groups" / f"{plugin.name}.json"
    source_path = repo_root / ".astrbot" / "groups" / f"{plugin.name}.in"
    python_path = venv_path / ("Scripts/python.exe")
    return EnvironmentGroup(
        id=plugin.name,
        python_version=plugin.python_version,
        plugins=[plugin],
        source_path=source_path,
        lockfile_path=lockfile_path,
        metadata_path=metadata_path,
        venv_path=venv_path,
        python_path=python_path,
        environment_fingerprint=fingerprint,
    )


def test_environment_planner_plan_groups_compatible_plugins_and_splits_conflicts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alpha = _plugin_spec(tmp_path, "alpha", requirements=["pkg==1.0", "shared==2.0"])
    beta = _plugin_spec(tmp_path, "beta", requirements=["pkg==1.0"])
    gamma = _plugin_spec(tmp_path, "gamma", requirements=["pkg==2.0"])
    planner = EnvironmentPlanner(tmp_path, uv_binary="uv")

    def fake_compile_lockfile(
        *, source_path: Path, output_path: Path, python_version: str
    ) -> None:
        content = source_path.read_text(encoding="utf-8")
        if "pkg==1.0" in content and "pkg==2.0" in content:
            raise RuntimeError("dependency conflict")
        output_path.write_text(f"# lock for {python_version}\n", encoding="utf-8")

    monkeypatch.setattr(planner, "_compile_lockfile", fake_compile_lockfile)

    plan = planner.plan([alpha, beta, gamma])

    assert len(plan.groups) == 2
    grouped_plugins = sorted(
        sorted(plugin.name for plugin in group.plugins) for group in plan.groups
    )
    assert grouped_plugins == [["alpha", "beta"], ["gamma"]]
    assert sorted(plugin.name for plugin in plan.plugins) == ["alpha", "beta", "gamma"]
    assert plan.skipped_plugins == {}
    assert plan.plugin_to_group["alpha"] is plan.plugin_to_group["beta"]
    assert plan.plugin_to_group["gamma"] is not plan.plugin_to_group["alpha"]


def test_environment_planner_cleanup_artifacts_removes_stale_entries(
    tmp_path: Path,
) -> None:
    plugin = _plugin_spec(tmp_path, "active")
    planner = EnvironmentPlanner(tmp_path, uv_binary="uv")
    active_group = _group(tmp_path, plugin)
    active_group.source_path.parent.mkdir(parents=True, exist_ok=True)
    active_group.lockfile_path.parent.mkdir(parents=True, exist_ok=True)
    active_group.venv_path.mkdir(parents=True, exist_ok=True)
    active_group.source_path.write_text("", encoding="utf-8")
    active_group.metadata_path.write_text("{}", encoding="utf-8")
    active_group.lockfile_path.write_text("", encoding="utf-8")

    stale_source = planner.group_dir / "stale.in"
    stale_metadata = planner.group_dir / "stale.json"
    stale_lockfile = planner.lock_dir / "stale.txt"
    stale_env = planner.env_dir / "stale"
    stale_source.parent.mkdir(parents=True, exist_ok=True)
    stale_lockfile.parent.mkdir(parents=True, exist_ok=True)
    stale_env.mkdir(parents=True, exist_ok=True)
    stale_source.write_text("", encoding="utf-8")
    stale_metadata.write_text("{}", encoding="utf-8")
    stale_lockfile.write_text("", encoding="utf-8")
    (stale_env / "pyvenv.cfg").write_text("version = 3.12\n", encoding="utf-8")

    planner.cleanup_artifacts([active_group])

    assert active_group.source_path.exists() is True
    assert active_group.metadata_path.exists() is True
    assert active_group.lockfile_path.exists() is True
    assert active_group.venv_path.exists() is True
    assert stale_source.exists() is False
    assert stale_metadata.exists() is False
    assert stale_lockfile.exists() is False
    assert stale_env.exists() is False


def test_group_environment_manager_prepare_rebuilds_when_runtime_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = _plugin_spec(tmp_path, "alpha")
    group = _group(tmp_path, plugin)
    group.lockfile_path.parent.mkdir(parents=True, exist_ok=True)
    group.lockfile_path.write_text("# lock\n", encoding="utf-8")
    manager = GroupEnvironmentManager(tmp_path, uv_binary="uv")
    calls: list[str] = []

    monkeypatch.setattr(
        manager,
        "_rebuild",
        lambda current_group: calls.append(f"rebuild:{current_group.id}"),
    )
    monkeypatch.setattr(
        manager,
        "_sync_existing",
        lambda current_group: calls.append(f"sync:{current_group.id}"),
    )

    python_path = manager.prepare(group)

    assert python_path == group.python_path
    assert calls == ["rebuild:alpha"]
    state = json.loads(
        (group.venv_path / GROUP_STATE_FILE_NAME).read_text(encoding="utf-8")
    )
    assert state["group_id"] == "alpha"
    assert state["environment_fingerprint"] == "fingerprint"


def test_group_environment_manager_prepare_syncs_existing_env_when_state_changed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = _plugin_spec(tmp_path, "alpha")
    group = _group(tmp_path, plugin, fingerprint="new-fingerprint")
    group.venv_path.mkdir(parents=True, exist_ok=True)
    group.lockfile_path.parent.mkdir(parents=True, exist_ok=True)
    group.lockfile_path.write_text("# lock\n", encoding="utf-8")
    group.python_path.parent.mkdir(parents=True, exist_ok=True)
    group.python_path.write_text("", encoding="utf-8")
    state_path = group.venv_path / GROUP_STATE_FILE_NAME
    state_path.write_text(
        json.dumps(
            {
                "group_id": group.id,
                "python_version": group.python_version,
                "environment_fingerprint": "old-fingerprint",
            }
        ),
        encoding="utf-8",
    )
    manager = GroupEnvironmentManager(tmp_path, uv_binary="uv")
    calls: list[str] = []

    monkeypatch.setattr(
        manager, "_matches_python_version", lambda venv_path, version: True
    )
    monkeypatch.setattr(
        manager,
        "_rebuild",
        lambda current_group: calls.append(f"rebuild:{current_group.id}"),
    )
    monkeypatch.setattr(
        manager,
        "_sync_existing",
        lambda current_group: calls.append(f"sync:{current_group.id}"),
    )

    python_path = manager.prepare(group)

    assert python_path == group.python_path
    assert calls == ["sync:alpha"]
    updated_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert updated_state["environment_fingerprint"] == "new-fingerprint"
