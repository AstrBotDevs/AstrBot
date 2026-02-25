import asyncio
import contextlib
import importlib
import importlib.metadata as importlib_metadata
import importlib.util
import io
import logging
import os
import re
import sys
import threading
from collections import deque

from astrbot.core.utils.astrbot_path import get_astrbot_site_packages_path
from astrbot.core.utils.runtime_env import is_packaged_desktop_runtime

logger = logging.getLogger("astrbot")

_DISTLIB_FINDER_PATCH_ATTEMPTED = False
_SITE_PACKAGES_IMPORT_LOCK = threading.RLock()


def _canonicalize_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).strip("-").lower()


def _get_pip_main():
    try:
        from pip._internal.cli.main import main as pip_main
    except ImportError:
        try:
            from pip import main as pip_main
        except ImportError as exc:
            raise ImportError(
                "pip module is unavailable "
                f"(sys.executable={sys.executable}, "
                f"frozen={getattr(sys, 'frozen', False)}, "
                f"ASTRBOT_DESKTOP_CLIENT={os.environ.get('ASTRBOT_DESKTOP_CLIENT')})"
            ) from exc

    return pip_main


def _run_pip_main_with_output(pip_main, args: list[str]) -> tuple[int, str]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        result_code = pip_main(args)
    return result_code, stream.getvalue()


def _cleanup_added_root_handlers(original_handlers: list[logging.Handler]) -> None:
    root_logger = logging.getLogger()
    original_handler_ids = {id(handler) for handler in original_handlers}

    for handler in list(root_logger.handlers):
        if id(handler) not in original_handler_ids:
            root_logger.removeHandler(handler)
            with contextlib.suppress(Exception):
                handler.close()


def _prepend_sys_path(path: str) -> None:
    normalized_target = os.path.realpath(path)
    sys.path[:] = [
        item for item in sys.path if os.path.realpath(item) != normalized_target
    ]
    sys.path.insert(0, normalized_target)


def _module_exists_in_site_packages(module_name: str, site_packages_path: str) -> bool:
    base_path = os.path.join(site_packages_path, *module_name.split("."))
    package_init = os.path.join(base_path, "__init__.py")
    module_file = f"{base_path}.py"
    return os.path.isfile(package_init) or os.path.isfile(module_file)


def _is_module_loaded_from_site_packages(
    module_name: str,
    site_packages_path: str,
) -> bool:
    module = sys.modules.get(module_name)
    if module is None:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            return False

    module_file = getattr(module, "__file__", None)
    if not module_file:
        return False

    module_path = os.path.realpath(module_file)
    site_packages_real = os.path.realpath(site_packages_path)
    try:
        return (
            os.path.commonpath([module_path, site_packages_real]) == site_packages_real
        )
    except ValueError:
        return False


def _extract_requirement_name(raw_requirement: str) -> str | None:
    line = raw_requirement.split("#", 1)[0].strip()
    if not line:
        return None
    if line.startswith(("-r", "--requirement", "-c", "--constraint")):
        return None
    if line.startswith("-"):
        return None

    egg_match = re.search(r"#egg=([A-Za-z0-9_.-]+)", raw_requirement)
    if egg_match:
        return _canonicalize_distribution_name(egg_match.group(1))

    candidate = re.split(r"[<>=!~;\s\[]", line, maxsplit=1)[0].strip()
    if not candidate:
        return None
    return _canonicalize_distribution_name(candidate)


def _extract_requirement_names(requirements_path: str) -> set[str]:
    names: set[str] = set()
    try:
        with open(requirements_path, encoding="utf-8") as requirements_file:
            for line in requirements_file:
                requirement_name = _extract_requirement_name(line)
                if requirement_name:
                    names.add(requirement_name)
    except Exception as exc:
        logger.warning("读取依赖文件失败，跳过冲突检测: %s", exc)
    return names


def _extract_top_level_modules(
    distribution: importlib_metadata.Distribution,
) -> set[str]:
    try:
        text = distribution.read_text("top_level.txt") or ""
    except Exception:
        return set()

    modules: set[str] = set()
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        modules.add(candidate)
    return modules


def _collect_candidate_modules(
    requirement_names: set[str],
    site_packages_path: str,
) -> set[str]:
    by_name: dict[str, list[importlib_metadata.Distribution]] = {}
    try:
        for distribution in importlib_metadata.distributions(path=[site_packages_path]):
            distribution_name = distribution.metadata.get("Name")
            if not distribution_name:
                continue
            canonical_name = _canonicalize_distribution_name(distribution_name)
            by_name.setdefault(canonical_name, []).append(distribution)
    except Exception as exc:
        logger.warning("读取 site-packages 元数据失败，使用回退模块名: %s", exc)

    expanded_requirement_names: set[str] = set()
    pending = deque(requirement_names)
    while pending:
        requirement_name = pending.popleft()
        if requirement_name in expanded_requirement_names:
            continue
        expanded_requirement_names.add(requirement_name)

        for distribution in by_name.get(requirement_name, []):
            for dependency_line in distribution.requires or []:
                dependency_name = _extract_requirement_name(dependency_line)
                if not dependency_name:
                    continue
                if dependency_name in expanded_requirement_names:
                    continue
                pending.append(dependency_name)

    candidates: set[str] = set()
    for requirement_name in expanded_requirement_names:
        matched_distributions = by_name.get(requirement_name, [])
        modules_for_requirement: set[str] = set()
        for distribution in matched_distributions:
            modules_for_requirement.update(_extract_top_level_modules(distribution))

        if modules_for_requirement:
            candidates.update(modules_for_requirement)
            continue

        fallback_module_name = requirement_name.replace("-", "_")
        if fallback_module_name:
            candidates.add(fallback_module_name)

    return candidates


def _ensure_preferred_modules(
    module_names: set[str],
    site_packages_path: str,
) -> None:
    unresolved_prefer_reasons = _prefer_modules_from_site_packages(
        module_names, site_packages_path
    )

    unresolved_modules: list[str] = []
    for module_name in sorted(module_names):
        if not _module_exists_in_site_packages(module_name, site_packages_path):
            continue
        if _is_module_loaded_from_site_packages(module_name, site_packages_path):
            continue

        failure_reason = unresolved_prefer_reasons.get(module_name)
        if failure_reason:
            unresolved_modules.append(f"{module_name} -> {failure_reason}")
            continue

        loaded_module = sys.modules.get(module_name)
        loaded_from = getattr(loaded_module, "__file__", "unknown")
        unresolved_modules.append(f"{module_name} -> {loaded_from}")

    if unresolved_modules:
        conflict_message = (
            "检测到插件依赖与当前运行时发生冲突，无法安全加载该插件。"
            f"冲突模块: {', '.join(unresolved_modules)}"
        )
        raise RuntimeError(conflict_message)


def _prefer_module_from_site_packages(
    module_name: str, site_packages_path: str
) -> bool:
    with _SITE_PACKAGES_IMPORT_LOCK:
        base_path = os.path.join(site_packages_path, *module_name.split("."))
        package_init = os.path.join(base_path, "__init__.py")
        module_file = f"{base_path}.py"

        module_location = None
        submodule_search_locations = None

        if os.path.isfile(package_init):
            module_location = package_init
            submodule_search_locations = [os.path.dirname(package_init)]
        elif os.path.isfile(module_file):
            module_location = module_file
        else:
            return False

        spec = importlib.util.spec_from_file_location(
            module_name,
            module_location,
            submodule_search_locations=submodule_search_locations,
        )
        if spec is None or spec.loader is None:
            return False

        matched_keys = [
            key
            for key in list(sys.modules.keys())
            if key == module_name or key.startswith(f"{module_name}.")
        ]
        original_modules = {key: sys.modules[key] for key in matched_keys}

        try:
            for key in matched_keys:
                sys.modules.pop(key, None)

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            if "." in module_name:
                parent_name, child_name = module_name.rsplit(".", 1)
                parent_module = sys.modules.get(parent_name)
                if parent_module is not None:
                    setattr(parent_module, child_name, module)

            logger.info(
                "Loaded %s from plugin site-packages: %s",
                module_name,
                module_location,
            )
            return True
        except Exception:
            failed_keys = [
                key
                for key in list(sys.modules.keys())
                if key == module_name or key.startswith(f"{module_name}.")
            ]
            for key in failed_keys:
                sys.modules.pop(key, None)
            sys.modules.update(original_modules)
            raise


def _extract_conflicting_module_name(exc: Exception) -> str | None:
    if isinstance(exc, ModuleNotFoundError):
        missing_name = getattr(exc, "name", None)
        if missing_name:
            return missing_name.split(".", 1)[0]

    message = str(exc)
    from_match = re.search(r"from '([A-Za-z0-9_.]+)'", message)
    if from_match:
        return from_match.group(1).split(".", 1)[0]

    no_module_match = re.search(r"No module named '([A-Za-z0-9_.]+)'", message)
    if no_module_match:
        return no_module_match.group(1).split(".", 1)[0]

    return None


def _prefer_module_with_dependency_recovery(
    module_name: str,
    site_packages_path: str,
    max_attempts: int = 3,
) -> bool:
    recovered_dependencies: set[str] = set()

    for _ in range(max_attempts):
        try:
            return _prefer_module_from_site_packages(module_name, site_packages_path)
        except Exception as exc:
            dependency_name = _extract_conflicting_module_name(exc)
            if (
                not dependency_name
                or dependency_name == module_name
                or dependency_name in recovered_dependencies
            ):
                raise

            recovered_dependencies.add(dependency_name)
            recovered = _prefer_module_from_site_packages(
                dependency_name,
                site_packages_path,
            )
            if not recovered:
                raise
            logger.info(
                "Recovered dependency %s while preferring %s from plugin site-packages.",
                dependency_name,
                module_name,
            )

    return False


def _prefer_modules_from_site_packages(
    module_names: set[str],
    site_packages_path: str,
) -> dict[str, str]:
    pending_modules = sorted(module_names)
    unresolved_reasons: dict[str, str] = {}
    max_rounds = max(2, min(6, len(pending_modules) + 1))

    for _ in range(max_rounds):
        if not pending_modules:
            break

        next_round_pending: list[str] = []
        round_progress = False

        for module_name in pending_modules:
            try:
                loaded = _prefer_module_with_dependency_recovery(
                    module_name,
                    site_packages_path,
                )
            except Exception as exc:
                unresolved_reasons[module_name] = str(exc)
                next_round_pending.append(module_name)
                continue

            unresolved_reasons.pop(module_name, None)
            if loaded:
                round_progress = True
            else:
                logger.debug(
                    "Module %s not found in plugin site-packages: %s",
                    module_name,
                    site_packages_path,
                )

        if not next_round_pending:
            pending_modules = []
            break

        if not round_progress and len(next_round_pending) == len(pending_modules):
            pending_modules = next_round_pending
            break

        pending_modules = next_round_pending

    final_unresolved = {
        module_name: unresolved_reasons.get(module_name, "unknown import error")
        for module_name in pending_modules
    }
    for module_name, reason in final_unresolved.items():
        logger.warning(
            "Failed to prefer module %s from plugin site-packages: %s",
            module_name,
            reason,
        )

    return final_unresolved


def _ensure_plugin_dependencies_preferred(
    target_site_packages: str,
    requested_requirements: set[str],
) -> None:
    if not requested_requirements:
        return

    candidate_modules = _collect_candidate_modules(
        requested_requirements,
        target_site_packages,
    )
    if not candidate_modules:
        return

    _ensure_preferred_modules(candidate_modules, target_site_packages)


def _get_loader_for_package(package: object) -> object | None:
    loader = getattr(package, "__loader__", None)
    if loader is not None:
        return loader

    spec = getattr(package, "__spec__", None)
    if spec is None:
        return None
    return getattr(spec, "loader", None)


def _try_register_distlib_finder(
    distlib_resources: object,
    finder_registry: dict[type, object],
    register_finder,
    resource_finder: object,
    loader: object,
    package_name: str,
) -> bool:
    loader_type = type(loader)
    if loader_type in finder_registry:
        return False

    try:
        register_finder(loader, resource_finder)
    except Exception as exc:
        logger.warning(
            "Failed to patch pip distlib finder for loader %s (%s): %s",
            loader_type.__name__,
            package_name,
            exc,
        )
        return False

    updated_registry = getattr(distlib_resources, "_finder_registry", finder_registry)
    if isinstance(updated_registry, dict) and loader_type not in updated_registry:
        logger.warning(
            "Distlib finder patch did not take effect for loader %s (%s).",
            loader_type.__name__,
            package_name,
        )
        return False

    logger.info(
        "Patched pip distlib finder for frozen loader: %s (%s)",
        loader_type.__name__,
        package_name,
    )
    return True


def _patch_distlib_finder_for_frozen_runtime() -> None:
    global _DISTLIB_FINDER_PATCH_ATTEMPTED

    if not getattr(sys, "frozen", False):
        return
    if _DISTLIB_FINDER_PATCH_ATTEMPTED:
        return

    _DISTLIB_FINDER_PATCH_ATTEMPTED = True

    try:
        from pip._vendor.distlib import resources as distlib_resources
    except Exception:
        return

    finder_registry = getattr(distlib_resources, "_finder_registry", None)
    register_finder = getattr(distlib_resources, "register_finder", None)
    resource_finder = getattr(distlib_resources, "ResourceFinder", None)

    if not isinstance(finder_registry, dict):
        logger.warning(
            "Skip patching distlib finder because _finder_registry is unavailable."
        )
        return
    if not callable(register_finder) or resource_finder is None:
        logger.warning(
            "Skip patching distlib finder because register API is unavailable."
        )
        return

    for package_name in ("pip._vendor.distlib", "pip._vendor"):
        try:
            package = importlib.import_module(package_name)
        except Exception:
            continue

        loader = _get_loader_for_package(package)
        if loader is None:
            continue

        if _try_register_distlib_finder(
            distlib_resources,
            finder_registry,
            register_finder,
            resource_finder,
            loader,
            package_name,
        ):
            finder_registry = getattr(
                distlib_resources, "_finder_registry", finder_registry
            )


class PipInstaller:
    def __init__(self, pip_install_arg: str, pypi_index_url: str | None = None) -> None:
        self.pip_install_arg = pip_install_arg
        self.pypi_index_url = pypi_index_url

    async def install(
        self,
        package_name: str | None = None,
        requirements_path: str | None = None,
        mirror: str | None = None,
    ) -> None:
        args = ["install"]
        requested_requirements: set[str] = set()
        if package_name:
            args.append(package_name)
            requirement_name = _extract_requirement_name(package_name)
            if requirement_name:
                requested_requirements.add(requirement_name)
        elif requirements_path:
            args.extend(["-r", requirements_path])
            requested_requirements = _extract_requirement_names(requirements_path)

        index_url = mirror or self.pypi_index_url or "https://pypi.org/simple"
        args.extend(["--trusted-host", "mirrors.aliyun.com", "-i", index_url])

        target_site_packages = None
        if is_packaged_desktop_runtime():
            target_site_packages = get_astrbot_site_packages_path()
            os.makedirs(target_site_packages, exist_ok=True)
            _prepend_sys_path(target_site_packages)
            args.extend(["--target", target_site_packages])
            args.extend(["--upgrade", "--force-reinstall"])

        if self.pip_install_arg:
            args.extend(self.pip_install_arg.split())

        logger.info(f"Pip 包管理器: pip {' '.join(args)}")
        result_code = await self._run_pip_in_process(args)

        if result_code != 0:
            raise Exception(f"安装失败，错误码：{result_code}")

        if target_site_packages:
            _prepend_sys_path(target_site_packages)
            _ensure_plugin_dependencies_preferred(
                target_site_packages,
                requested_requirements,
            )
        importlib.invalidate_caches()

    def prefer_installed_dependencies(self, requirements_path: str) -> None:
        """优先使用已安装在插件 site-packages 中的依赖，不执行安装。"""
        if not is_packaged_desktop_runtime():
            return

        target_site_packages = get_astrbot_site_packages_path()
        if not os.path.isdir(target_site_packages):
            return

        requested_requirements = _extract_requirement_names(requirements_path)
        if not requested_requirements:
            return

        _prepend_sys_path(target_site_packages)
        _ensure_plugin_dependencies_preferred(
            target_site_packages,
            requested_requirements,
        )
        importlib.invalidate_caches()

    async def _run_pip_in_process(self, args: list[str]) -> int:
        pip_main = _get_pip_main()
        _patch_distlib_finder_for_frozen_runtime()

        original_handlers = list(logging.getLogger().handlers)
        result_code, output = await asyncio.to_thread(
            _run_pip_main_with_output, pip_main, args
        )
        for line in output.splitlines():
            line = line.strip()
            if line:
                logger.info(line)

        _cleanup_added_root_handlers(original_handlers)
        return result_code
