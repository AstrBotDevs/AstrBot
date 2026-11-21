"""Tests verifying the vendored `astrbot-sdk` snapshot integrity check."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from types import ModuleType

import pytest


def _load_sync_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "sync_astrbot_sdk.py"
    )
    spec = importlib.util.spec_from_file_location("sync_astrbot_sdk", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vendor_snapshot_matches_manifest() -> None:
    """Repository vendor/astrbot-sdk snapshot must match UPSTREAM.json."""
    sync_mod = _load_sync_module()
    meta = sync_mod.check_vendor_snapshot()
    assert meta.get("commit")
    assert meta.get("tree_sha256")


def test_vendor_snapshot_detects_tampered_file(tmp_path: Path) -> None:
    """Any modification in vendor/astrbot-sdk must fail digest verification."""
    sync_mod = _load_sync_module()
    repo_vendor = Path(__file__).resolve().parents[2] / "vendor" / "astrbot-sdk"
    copied = tmp_path / "astrbot-sdk"
    shutil.copytree(repo_vendor, copied)

    init_file = copied / "src" / "astrbot_sdk" / "__init__.py"
    init_file.write_text(
        init_file.read_text(encoding="utf-8") + "\n# tampered\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="digest mismatch"):
        sync_mod.check_vendor_snapshot(copied)


def test_vendor_snapshot_rejects_compiled_extension(tmp_path: Path) -> None:
    """Vendor snapshot must forbid compiled native extensions (.so/.pyd/.dylib)."""
    sync_mod = _load_sync_module()
    repo_vendor = Path(__file__).resolve().parents[2] / "vendor" / "astrbot-sdk"
    copied = tmp_path / "astrbot-sdk"
    shutil.copytree(repo_vendor, copied)

    (copied / "src" / "astrbot_sdk" / "_native.so").write_bytes(b"\x7fELF")

    with pytest.raises(ValueError, match="forbidden build artifact"):
        sync_mod.check_vendor_snapshot(copied)
