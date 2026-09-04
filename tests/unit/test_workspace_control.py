import hashlib

import pytest

from astrbot.core.workspace_control import (
    approve_workspace_control_artifact,
    is_workspace_control_artifact_approved,
    is_workspace_control_path,
    list_workspace_control_artifacts,
    revoke_workspace_control_artifact,
)


def test_approval_requires_exact_current_digest(tmp_path):
    artifact = tmp_path / "EXTRA_PROMPT.md"
    artifact.write_text("trusted", encoding="utf-8")
    digest = hashlib.sha256(b"trusted").hexdigest()

    approval = approve_workspace_control_artifact(
        tmp_path,
        "EXTRA_PROMPT.md",
        expected_sha256=digest,
        approved_by="admin-1",
    )

    assert approval["sha256"] == digest
    assert is_workspace_control_artifact_approved(tmp_path, "EXTRA_PROMPT.md")

    artifact.write_text("changed", encoding="utf-8")
    assert not is_workspace_control_artifact_approved(tmp_path, "EXTRA_PROMPT.md")


def test_control_paths_include_prompt_skills_and_manifest(tmp_path):
    assert is_workspace_control_path(tmp_path, tmp_path / "EXTRA_PROMPT.md")
    assert is_workspace_control_path(
        tmp_path, tmp_path / "skills" / "demo" / "SKILL.md"
    )
    assert is_workspace_control_path(
        tmp_path, tmp_path / ".astrbot_workspace_control.json"
    )
    assert not is_workspace_control_path(tmp_path, tmp_path / "notes.txt")


def test_approval_rejects_symbolic_link_artifacts(tmp_path):
    """Do not approve control files through a symbolic link indirection."""
    target = tmp_path / "trusted.md"
    target.write_text("trusted", encoding="utf-8")
    link = tmp_path / "EXTRA_PROMPT.md"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="symbolic"):
        approve_workspace_control_artifact(
            tmp_path,
            "EXTRA_PROMPT.md",
            expected_sha256=hashlib.sha256(b"trusted").hexdigest(),
            approved_by="admin-1",
        )
    assert not is_workspace_control_artifact_approved(tmp_path, "EXTRA_PROMPT.md")


def test_approval_rejects_digest_mismatch_and_revoke(tmp_path):
    artifact = tmp_path / "skills" / "demo" / "SKILL.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# Demo", encoding="utf-8")

    with pytest.raises(ValueError, match="hash"):
        approve_workspace_control_artifact(
            tmp_path,
            "skills/demo/SKILL.md",
            expected_sha256="0" * 64,
            approved_by="admin-1",
        )

    digest = hashlib.sha256(b"# Demo").hexdigest()
    approve_workspace_control_artifact(
        tmp_path,
        "skills/demo/SKILL.md",
        expected_sha256=digest,
        approved_by="admin-1",
    )
    assert revoke_workspace_control_artifact(tmp_path, "skills/demo/SKILL.md")
    assert not is_workspace_control_artifact_approved(tmp_path, "skills/demo/SKILL.md")


def test_list_workspace_control_artifacts_includes_pending_and_missing(tmp_path):
    prompt = tmp_path / "EXTRA_PROMPT.md"
    prompt.write_text("pending", encoding="utf-8")
    skill = tmp_path / "skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Approved", encoding="utf-8")
    digest = hashlib.sha256(b"# Approved").hexdigest()
    approve_workspace_control_artifact(
        tmp_path,
        "skills/demo/SKILL.md",
        expected_sha256=digest,
        approved_by="admin-1",
    )
    skill.unlink()

    artifacts = list_workspace_control_artifacts(tmp_path)

    assert artifacts[0] == {
        "path": "EXTRA_PROMPT.md",
        "sha256": hashlib.sha256(b"pending").hexdigest(),
        "approved_sha256": None,
        "approved_at": None,
        "approved_by": None,
        "status": "pending",
    }
    assert artifacts[1]["path"] == "skills/demo/SKILL.md"
    assert artifacts[1]["sha256"] is None
    assert artifacts[1]["approved_sha256"] == digest
    assert artifacts[1]["approved_by"] == "admin-1"
    assert artifacts[1]["status"] == "missing"
