from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from astrbot.core import logger, sp
from astrbot.core.star.star_handler import star_handlers_registry


@dataclass(slots=True)
class PriorityApplyResult:
    persisted: bool
    applied_in_memory: bool


class PriorityCompatibility:
    """Compatibility layer for handler priority overrides (PR4716)."""

    @staticmethod
    async def get_priority_overrides() -> dict[str, int]:
        try:
            overrides = await sp.global_get("handler_priority_overrides", {})
            if isinstance(overrides, dict) and overrides:
                return {str(k): int(v) for k, v in overrides.items()}
        except Exception as e:
            logger.debug(f"Failed to read handler_priority_overrides from sp: {e!s}")

        overrides: dict[str, int] = {}
        for name, handler in star_handlers_registry.star_handlers_map.items():
            try:
                priority = int(handler.extras_configs.get("priority", 0) or 0)
            except Exception:
                priority = 0
            if priority != 0:
                overrides[name] = priority
        return overrides

    @staticmethod
    async def apply_priority_overrides(
        overrides: dict[str, int],
    ) -> PriorityApplyResult:
        normalized: dict[str, int] = {
            str(k): int(v) for k, v in (overrides or {}).items()
        }

        try:
            await sp.global_put("handler_priority_overrides", normalized)
            return PriorityApplyResult(persisted=True, applied_in_memory=False)
        except Exception as e:
            logger.debug(f"Failed to write handler_priority_overrides to sp: {e!s}")

        for name, priority in normalized.items():
            handler = star_handlers_registry.star_handlers_map.get(name)
            if handler is None:
                continue
            handler.extras_configs["priority"] = int(priority)

        # Best-effort compatibility: star_handlers_registry internals may change upstream.
        try:
            handlers = getattr(star_handlers_registry, "_handlers", None)
            if isinstance(handlers, list):
                handlers.sort(
                    key=lambda h: -int(h.extras_configs.get("priority", 0) or 0),
                )
        except Exception as e:
            logger.debug(
                f"Failed to sort handler registry after overrides (best effort): {e!s}"
            )

        return PriorityApplyResult(persisted=False, applied_in_memory=True)

    @staticmethod
    async def is_pr4716_available() -> bool:
        try:
            await sp.global_get("handler_priority_overrides", {})
        except Exception:
            return False

        try:
            _ = star_handlers_registry.star_handlers_map
        except Exception:
            return False

        return True


class ConflictDetectionCompatibility:
    """Compatibility layer for conflict detection (PR4451)."""

    @staticmethod
    async def check_conflicts(plugins: list[str]) -> dict[str, Any] | None:
        try:
            from astrbot.core.star.conflict_detection import (
                detect_conflicts,  # type: ignore
            )

            return await detect_conflicts(plugins)
        except ImportError:
            return None
        except Exception as e:
            logger.warning(f"Conflict detection failed: {e!s}")
            return None

    @staticmethod
    def is_conflict_detection_available() -> bool:
        try:
            from astrbot.core.star.conflict_detection import (
                detect_conflicts,  # type: ignore
            )

            _ = detect_conflicts
            return True
        except ImportError:
            return False
