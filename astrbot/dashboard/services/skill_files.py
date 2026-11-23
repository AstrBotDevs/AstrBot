"""Skill filesystem and credential helpers shared by HTTP entry points."""

from __future__ import annotations

import os
import re
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anyio

from astrbot.core import logger

if TYPE_CHECKING:
    from astrbot.core.config.astrbot_config import AstrBotConfig
    from astrbot.core.skills.skill_manager import SkillManager

_SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


_SKILL_FILE_MAX_BYTES = 512 * 1024


_EDITABLE_SKILL_FILE_SUFFIXES = {
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}


_EDITABLE_SKILL_FILENAMES = {"Dockerfile", "Makefile"}


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump())
    return value


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _next_available_temp_path(temp_dir: str, filename: str) -> str:
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    candidate = filename
    index = 1
    while os.path.exists(os.path.join(temp_dir, candidate)):
        candidate = f"{stem}_{index}{suffix}"
        index += 1
    return os.path.join(temp_dir, candidate)


def resolve_local_skill_dir(
    name: str, manager_factory: Callable[[], SkillManager]
) -> Path:
    skill_name = str(name or "").strip()
    if not skill_name:
        raise ValueError("Missing skill name")
    if not _SKILL_NAME_RE.match(skill_name):
        raise ValueError("Invalid skill name")

    skill_mgr = manager_factory()
    if skill_mgr.is_sandbox_only_skill(skill_name):
        raise PermissionError(
            "Sandbox preset skill cannot be opened from local skill files."
        )

    plugin_skill_dir = skill_mgr._get_plugin_skill_dir(skill_name)
    if plugin_skill_dir is not None:
        return plugin_skill_dir.resolve(strict=True)

    skills_root = Path(skill_mgr.skills_root).resolve(strict=True)
    skill_dir = (skills_root / skill_name).resolve(strict=True)
    if not skill_dir.is_relative_to(skills_root):
        raise PermissionError("Invalid skill path")
    if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").exists():
        raise FileNotFoundError("Local skill not found")
    return skill_dir


def resolve_skill_relative_path(
    skill_dir: Path,
    relative_path: str | None,
    *,
    expect_file: bool,
) -> Path:
    raw_path = str(relative_path or ".").strip() or "."
    normalized = Path(raw_path.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError("Invalid relative path")

    target = (skill_dir / normalized).resolve(strict=True)
    if not target.is_relative_to(skill_dir):
        raise PermissionError("Path escapes skill directory")
    if expect_file and not target.is_file():
        raise FileNotFoundError("Skill file not found")
    if not expect_file and not target.is_dir():
        raise FileNotFoundError("Skill directory not found")
    return target


def skill_relative_path(skill_dir: Path, target: Path) -> str:
    rel = target.relative_to(skill_dir).as_posix()
    return "" if rel == "." else rel


def is_editable_skill_file(path: Path) -> bool:
    return (
        path.name in _EDITABLE_SKILL_FILENAMES
        or path.suffix.lower() in _EDITABLE_SKILL_FILE_SUFFIXES
    )


def get_neo_client_config(
    config: AstrBotConfig, discover_credentials: Callable[[str], str | None]
) -> tuple[str, str]:
    provider_settings = config.get(
        "provider_settings",
        {},
    )
    sandbox = provider_settings.get("sandbox", {})
    endpoint = sandbox.get("shipyard_neo_endpoint", "")
    access_token = sandbox.get("shipyard_neo_access_token", "")

    if not access_token and endpoint:
        access_token = discover_credentials(endpoint)

    if not endpoint or not access_token:
        raise ValueError(
            "Shipyard Neo endpoint or access token not configured. "
            "Set them in Dashboard or ensure Bay's credentials.json is accessible."
        )
    return endpoint, access_token


async def install_skill_archives(
    file_list: list[Any],
    skill_mgr: SkillManager,
    temp_dir: str,
    *,
    next_temp_path: Callable[[str, str], str],
    sync_skills: Callable[[], Awaitable[None]],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Install each archive and retain per-file outcomes and cleanup."""
    succeeded = []
    failed = []
    skipped = []
    os.makedirs(temp_dir, exist_ok=True)

    for file in file_list:
        filename = os.path.basename(file.filename or "unknown.zip")
        temp_path = None

        try:
            if not filename.lower().endswith(".zip"):
                failed.append(
                    {
                        "filename": filename,
                        "error": "Only .zip files are supported",
                    }
                )
                continue

            temp_path = next_temp_path(temp_dir, filename)
            await file.save(temp_path)

            try:
                skill_name = skill_mgr.install_skill_from_zip(
                    temp_path,
                    overwrite=False,
                    skill_name_hint=Path(filename).stem,
                )
            except TypeError:
                try:
                    skill_name = skill_mgr.install_skill_from_zip(
                        temp_path,
                        overwrite=False,
                    )
                except FileExistsError:
                    skipped.append(
                        {
                            "filename": filename,
                            "name": Path(filename).stem,
                            "error": "Skill already exists.",
                        }
                    )
                    skill_name = None
            except FileExistsError:
                skipped.append(
                    {
                        "filename": filename,
                        "name": Path(filename).stem,
                        "error": "Skill already exists.",
                    }
                )
                skill_name = None

            if skill_name is None:
                continue
            succeeded.append({"filename": filename, "name": skill_name})

        except Exception as exc:
            failed.append({"filename": filename, "error": str(exc)})
        finally:
            if temp_path and await anyio.Path(temp_path).exists():
                try:
                    await anyio.Path(temp_path).unlink()
                except Exception:
                    pass

    if succeeded:
        try:
            await sync_skills()
        except Exception:
            logger.warning("Failed to sync uploaded skills to active sandboxes.")
    return succeeded, failed, skipped


def iter_skill_files(skill_dir: Path, target_dir: Path) -> Iterator[Path]:
    """Yield sorted file entries that remain within the selected skill."""
    for entry in sorted(
        target_dir.iterdir(),
        key=lambda item: (not item.is_dir(), item.name.lower()),
    ):
        try:
            resolved = entry.resolve(strict=True)
        except OSError:
            continue
        if not resolved.is_relative_to(skill_dir):
            continue
        if not resolved.is_dir() and not resolved.is_file():
            continue
        yield resolved
