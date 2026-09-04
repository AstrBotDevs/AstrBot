"""Approval state for workspace files that influence agent instructions."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

WORKSPACE_CONTROL_MANIFEST = ".astrbot_workspace_control.json"
EXTRA_PROMPT_PATH = "EXTRA_PROMPT.md"
WORKSPACE_SKILLS_PREFIX = "skills"
WORKSPACE_CONTROL_SCHEMA_VERSION = 1


def _relative_control_path(workspace_root: Path, target: Path) -> str | None:
    """Return a canonical control-plane path or ``None`` for ordinary files.

    Args:
        workspace_root: Root of the current UMO workspace.
        target: Candidate file or directory path.

    Returns:
        A POSIX relative path when the target controls prompts or skills.

    Raises:
        ValueError: If the candidate escapes the workspace.
    """
    root = workspace_root.resolve(strict=False)
    resolved = target.resolve(strict=False)
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("Workspace path escapes its root") from exc
    if relative == EXTRA_PROMPT_PATH or relative == WORKSPACE_CONTROL_MANIFEST:
        return relative
    if relative == WORKSPACE_SKILLS_PREFIX or relative.startswith(
        f"{WORKSPACE_SKILLS_PREFIX}/"
    ):
        return relative
    return None


def is_workspace_control_path(workspace_root: Path, target: Path) -> bool:
    """Return whether a target is a workspace prompt, skill, or manifest.

    Args:
        workspace_root: Root of the current UMO workspace.
        target: Candidate path.

    Returns:
        True when the path changes agent control-plane content.
    """
    try:
        return _relative_control_path(workspace_root, target) is not None
    except ValueError:
        return True


def compute_artifact_sha256(path: Path) -> str:
    """Calculate an artifact digest without loading it into memory.

    Args:
        path: Approved regular file.

    Returns:
        Lowercase SHA-256 hexadecimal digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def list_workspace_control_artifacts(workspace_root: Path) -> list[dict]:
    """List current control-plane files together with their approval state.

    Args:
        workspace_root: Root of the current UMO workspace.

    Returns:
        Stable, path-sorted descriptions of present and previously approved
        workspace control artifacts.
    """
    root = workspace_root.resolve(strict=False)
    manifest = _load_manifest(root)
    manifest_artifacts = manifest.get("artifacts", {})
    paths: set[str] = set()

    for candidate in (root / EXTRA_PROMPT_PATH,):
        if candidate.is_file() and not candidate.is_symlink():
            paths.add(EXTRA_PROMPT_PATH)

    skills_root = root / WORKSPACE_SKILLS_PREFIX
    if skills_root.is_dir() and not skills_root.is_symlink():
        for candidate in skills_root.rglob("*"):
            if not candidate.is_file() or candidate.is_symlink():
                continue
            try:
                relative = _relative_control_path(root, candidate)
            except ValueError:
                continue
            if relative:
                paths.add(relative)

    for relative in manifest_artifacts:
        if not isinstance(relative, str):
            continue
        try:
            candidate = (root / relative).resolve(strict=False)
            if _relative_control_path(root, candidate) == relative:
                paths.add(relative)
        except ValueError:
            continue

    result: list[dict] = []
    for relative in sorted(paths):
        raw_candidate = root / relative
        candidate = raw_candidate.resolve(strict=False)
        current_sha256 = (
            compute_artifact_sha256(candidate)
            if raw_candidate.is_file()
            and not raw_candidate.is_symlink()
            and candidate.is_file()
            else None
        )
        approval = manifest_artifacts.get(relative)
        approval = approval if isinstance(approval, dict) else {}
        approved_sha256 = approval.get("sha256")
        status = (
            "approved"
            if current_sha256 and current_sha256 == approved_sha256
            else "pending"
            if current_sha256
            else "missing"
        )
        result.append(
            {
                "path": relative,
                "sha256": current_sha256,
                "approved_sha256": approved_sha256,
                "approved_at": approval.get("approved_at"),
                "approved_by": approval.get("approved_by"),
                "status": status,
            }
        )
    return result


def _load_manifest(workspace_root: Path) -> dict:
    manifest_path = workspace_root / WORKSPACE_CONTROL_MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": WORKSPACE_CONTROL_SCHEMA_VERSION, "artifacts": {}}
    if not isinstance(manifest, dict) or not isinstance(
        manifest.get("artifacts"), dict
    ):
        return {"version": WORKSPACE_CONTROL_SCHEMA_VERSION, "artifacts": {}}
    return manifest


def is_workspace_control_artifact_approved(
    workspace_root: Path, relative_path: str
) -> bool:
    """Return whether an exact control artifact has an approval matching its hash.

    Args:
        workspace_root: Root of the current UMO workspace.
        relative_path: Canonical artifact path relative to the workspace.

    Returns:
        True only for a regular file with an exact approved digest.
    """
    raw_target = workspace_root / relative_path
    if raw_target.is_symlink():
        return False
    target = raw_target.resolve(strict=False)
    try:
        canonical = _relative_control_path(workspace_root, target)
    except ValueError:
        return False
    if canonical != relative_path or not target.is_file() or target.is_symlink():
        return False
    entry = _load_manifest(workspace_root).get("artifacts", {}).get(relative_path)
    return isinstance(entry, dict) and entry.get("sha256") == compute_artifact_sha256(
        target
    )


def approve_workspace_control_artifact(
    workspace_root: Path,
    relative_path: str,
    *,
    expected_sha256: str,
    approved_by: str,
) -> dict:
    """Approve a control artifact after checking its exact digest.

    Args:
        workspace_root: Root of the current UMO workspace.
        relative_path: Control file path relative to the workspace.
        expected_sha256: Digest displayed to the administrator.
        approved_by: Administrator sender identifier.

    Returns:
        Persisted approval metadata.

    Raises:
        ValueError: If the path is invalid or its digest changed.
    """
    raw_target = workspace_root / relative_path
    if raw_target.is_symlink():
        raise ValueError("Workspace control artifacts cannot be symbolic links")
    target = raw_target.resolve(strict=False)
    if (
        _relative_control_path(workspace_root, target) != relative_path
        or not target.is_file()
    ):
        raise ValueError("Only a workspace control file can be approved")
    actual = compute_artifact_sha256(target)
    if actual != expected_sha256.lower():
        raise ValueError("Artifact hash does not match the requested approval")
    manifest = _load_manifest(workspace_root)
    artifact = {
        "sha256": actual,
        "approved_at": datetime.now(UTC).isoformat(),
        "approved_by": approved_by,
    }
    manifest["version"] = WORKSPACE_CONTROL_SCHEMA_VERSION
    manifest.setdefault("artifacts", {})[relative_path] = artifact
    workspace_root.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".workspace-control-", dir=workspace_root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        Path(temporary).replace(workspace_root / WORKSPACE_CONTROL_MANIFEST)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return artifact


def revoke_workspace_control_artifact(workspace_root: Path, relative_path: str) -> bool:
    """Remove a previously stored artifact approval.

    Args:
        workspace_root: Root of the current UMO workspace.
        relative_path: Artifact path relative to the workspace.

    Returns:
        Whether an approval entry existed.
    """
    manifest = _load_manifest(workspace_root)
    removed = manifest.get("artifacts", {}).pop(relative_path, None) is not None
    if removed:
        fd, temporary = tempfile.mkstemp(
            prefix=".workspace-control-", dir=workspace_root
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(
                    manifest, stream, ensure_ascii=False, indent=2, sort_keys=True
                )
                stream.write("\n")
            os.chmod(temporary, 0o600)
            Path(temporary).replace(workspace_root / WORKSPACE_CONTROL_MANIFEST)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return removed
