import json
import logging
import os
import re
from functools import lru_cache
from typing import Any

from astrbot.core.utils.runtime_env import is_packaged_desktop_runtime

logger = logging.getLogger("astrbot")

DESKTOP_CORE_LOCK_PATH_ENV = "ASTRBOT_DESKTOP_CORE_LOCK_PATH"


def _canonicalize_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).strip("-").lower()


def _safe_requirement_pin(name: str, version: str) -> str | None:
    if not name or not version:
        return None
    if any(char.isspace() for char in name) or any(char.isspace() for char in version):
        return None
    return f"{name}=={version}"


def _fallback_module_name(name: str) -> str:
    return _canonicalize_distribution_name(name).replace("-", "_")


def _iter_distribution_records(data: Any):
    if not isinstance(data, dict):
        return
    distributions = data.get("distributions", [])
    if not isinstance(distributions, list):
        return
    for record in distributions:
        if isinstance(record, dict):
            yield record


@lru_cache(maxsize=8)
def _load_lock_data(lock_path: str) -> dict[str, Any] | None:
    try:
        with open(lock_path, encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        logger.warning("桌面端核心依赖锁不存在: %s", lock_path)
        return None
    except Exception as exc:
        logger.warning("读取桌面端核心依赖锁失败: %s", exc)
        return None

    if not isinstance(data, dict):
        logger.warning("桌面端核心依赖锁格式无效: %s", lock_path)
        return None
    return data


def _resolve_lock_data() -> dict[str, Any] | None:
    if not is_packaged_desktop_runtime():
        return None

    lock_path = os.environ.get(DESKTOP_CORE_LOCK_PATH_ENV, "").strip()
    if not lock_path:
        return None
    return _load_lock_data(lock_path)


def get_desktop_core_lock_constraints() -> tuple[str, ...]:
    data = _resolve_lock_data()
    if not data:
        return ()

    constraints: dict[str, str] = {}
    for record in _iter_distribution_records(data):
        name = record.get("name")
        version = record.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            continue

        pin = _safe_requirement_pin(name, version)
        if not pin:
            continue
        constraints.setdefault(_canonicalize_distribution_name(name), pin)

    return tuple(constraints[key] for key in sorted(constraints))


def get_desktop_core_lock_modules() -> frozenset[str]:
    data = _resolve_lock_data()
    if not data:
        return frozenset()

    modules: set[str] = set()
    for record in _iter_distribution_records(data):
        name = record.get("name")
        top_level_modules = record.get("top_level_modules", [])
        if isinstance(top_level_modules, list):
            for module_name in top_level_modules:
                if isinstance(module_name, str) and module_name:
                    modules.add(module_name.split(".", 1)[0])
        if isinstance(name, str):
            fallback = _fallback_module_name(name)
            if fallback:
                modules.add(fallback)

    return frozenset(modules)
