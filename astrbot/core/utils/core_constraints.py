import contextlib
import functools
import importlib.metadata as importlib_metadata
import logging
import os
from collections.abc import Iterator

from packaging.requirements import Requirement

from astrbot.core.utils.requirements_utils import (
    canonicalize_distribution_name,
    collect_installed_distribution_versions,
    get_requirement_check_paths,
)

logger = logging.getLogger("astrbot")


def _resolve_core_dist_name(core_dist_name: str | None) -> str | None:
    if core_dist_name:
        try:
            importlib_metadata.distribution(core_dist_name)
            return core_dist_name
        except importlib_metadata.PackageNotFoundError:
            return None

    try:
        importlib_metadata.distribution("AstrBot")
        return "AstrBot"
    except importlib_metadata.PackageNotFoundError:
        pass

    if not __package__:
        return None

    top_pkg = __package__.split(".")[0]
    for dist in importlib_metadata.distributions():
        try:
            top_level = dist.read_text("top_level.txt") or ""
        except Exception:
            continue
        if top_pkg in top_level.splitlines():
            if "Name" in dist.metadata:
                return dist.metadata["Name"]

    return None


@functools.cache
def _get_core_constraints(core_dist_name: str | None) -> tuple[str, ...]:
    try:
        resolved_core_dist_name = _resolve_core_dist_name(core_dist_name)

        if not resolved_core_dist_name:
            return ()

        try:
            dist = importlib_metadata.distribution(resolved_core_dist_name)
        except importlib_metadata.PackageNotFoundError:
            return ()

        if not dist or not dist.requires:
            return ()

        installed = collect_installed_distribution_versions(
            get_requirement_check_paths()
        )
        if not installed:
            return ()

        constraints: list[str] = []
        for req_str in dist.requires:
            try:
                req = Requirement(req_str)
                if req.marker and not req.marker.evaluate():
                    continue
                name = canonicalize_distribution_name(req.name)
                if name in installed:
                    constraints.append(f"{name}=={installed[name]}")
            except Exception:
                continue
    except Exception as exc:
        logger.warning("获取核心依赖约束失败: %s", exc)
        return ()

    return tuple(constraints)


class CoreConstraintsProvider:
    def __init__(self, core_dist_name: str | None) -> None:
        self._core_dist_name = core_dist_name

    @contextlib.contextmanager
    def constraints_file(self) -> Iterator[str | None]:
        constraints = _get_core_constraints(self._core_dist_name)
        if not constraints:
            yield None
            return

        path: str | None = None
        try:
            import tempfile

            with tempfile.NamedTemporaryFile(
                mode="w", suffix="_constraints.txt", delete=False, encoding="utf-8"
            ) as f:
                f.write("\n".join(constraints))
                path = f.name
            logger.info("已启用核心依赖版本保护 (%d 个约束)", len(constraints))
        except Exception as exc:
            logger.warning("创建临时约束文件失败: %s", exc)
            yield None
            return

        try:
            yield path
        finally:
            if path and os.path.exists(path):
                with contextlib.suppress(Exception):
                    os.remove(path)
