"""Regression checks for privileged release workflow boundaries."""

from __future__ import annotations

import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "release.yml"
DOCKER_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "docker-image.yml"
DOCKERFILE = REPOSITORY_ROOT / "Dockerfile"


def _workflow_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_privileged_workflow_actions_are_commit_pinned() -> None:
    """Credential-bearing release jobs must not execute mutable action tags."""
    for path in (RELEASE_WORKFLOW, DOCKER_WORKFLOW):
        uses_values = re.findall(r"^\s*uses:\s*([^\s#]+)", _workflow_text(path), re.M)
        assert uses_values
        assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", value) for value in uses_values)


def test_dispatch_tag_is_not_interpolated_into_shell_source() -> None:
    """User-controlled workflow input must cross into Bash through env only."""
    for path in (RELEASE_WORKFLOW, DOCKER_WORKFLOW):
        text = _workflow_text(path)
        assert 'tag="${{ inputs.tag }}"' not in text
        assert 'version="${{ inputs.tag }}"' not in text
        assert "INPUT_TAG: ${{ inputs.tag }}" in text
        assert "Release tag must be a safe semantic version" in text

    release_text = _workflow_text(RELEASE_WORKFLOW)
    assert "required: true" in release_text
    assert "git describe --tags" not in release_text
    assert "inputs.ref" not in release_text


def test_versioned_release_assets_are_never_clobbered() -> None:
    """Rerunning a tag must fail before replacing version-addressed artifacts."""
    text = _workflow_text(RELEASE_WORKFLOW)
    assert "refuse_existing_object" in text
    assert "group: astrbot-release-${{" in text
    assert "cancel-in-progress: false" in text
    assert 'refuse_existing_object "astrbot-webui-${VERSION_TAG}.zip"' in text
    assert 'refuse_existing_object "astrbot-core-${VERSION_TAG}.zip"' in text
    assert "gh release delete-asset" not in text
    assert "--clobber" not in text
    assert "Refusing to overwrite immutable GitHub release asset" in text

    docker_text = _workflow_text(DOCKER_WORKFLOW)
    assert "group: astrbot-docker-release-${{" in docker_text
    assert "cancel-in-progress: false" in docker_text
    assert "Refuse to overwrite immutable nightly tag" in docker_text
    assert "manifests/${NIGHTLY_TAG}" in docker_text


def test_docker_dashboard_install_has_all_frozen_pnpm_inputs() -> None:
    """The dependency layer needs the workspace build-policy file before install."""
    text = _workflow_text(DOCKERFILE)
    copy_line = (
        "COPY dashboard/package.json dashboard/pnpm-lock.yaml "
        "dashboard/pnpm-workspace.yaml ./"
    )
    assert copy_line in text
    assert text.index(copy_line) < text.index("RUN pnpm install --frozen-lockfile")
