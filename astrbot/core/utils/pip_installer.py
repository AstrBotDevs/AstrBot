import asyncio
import contextlib
import importlib
import importlib.metadata as importlib_metadata
import importlib.util
import io
import logging
import os
import re
import shlex
import sys
import threading
from collections import deque
from collections.abc import Iterator

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from astrbot.core.utils.astrbot_path import get_astrbot_site_packages_path
from astrbot.core.utils.runtime_env import is_packaged_desktop_runtime

logger = logging.getLogger("astrbot")

_DISTLIB_FINDER_PATCH_ATTEMPTED = False
_SITE_PACKAGES_IMPORT_LOCK = threading.RLock()


class DependencyConflictError(Exception):
    """Raised when pip encounters a dependency conflict."""

    def __init__(
        self, message: str, errors: list[str], *, is_core_conflict: bool
    ) -> None:
        super().__init__(message)
        self.errors = errors
        self.is_core_conflict = is_core_conflict


class RequirementsPrecheckFailed(Exception):
    """Raised when the pre-check of requirements fails."""

    pass


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


def _strip_inline_requirement_comment(raw_input: str) -> str:
    return re.split(r"[ \t]+#", raw_input, maxsplit=1)[0].strip()


def _prepend_sys_path(path: str) -> None:
    normalized_target = os.path.realpath(path)
    sys.path[:] = [
        item for item in sys.path if os.path.realpath(item) != normalized_target
    ]
    sys.path.insert(0, normalized_target)


def _cleanup_added_root_handlers(original_handlers: list[logging.Handler]) -> None:
    root_logger = logging.getLogger()
    original_handler_ids = {id(handler) for handler in original_handlers}

    for handler in list(root_logger.handlers):
        if id(handler) not in original_handler_ids:
            root_logger.removeHandler(handler)
            with contextlib.suppress(Exception):
                handler.close()


def _get_requirement_check_paths() -> list[str]:
    paths = list(sys.path)
    if is_packaged_desktop_runtime():
        target_site_packages = get_astrbot_site_packages_path()
        if os.path.isdir(target_site_packages):
            paths.insert(0, target_site_packages)
    return paths


def _specifier_contains_version(specifier: SpecifierSet, version: str) -> bool:
    try:
        parsed_version = Version(version)
    except InvalidVersion:
        return False
    return specifier.contains(parsed_version, prereleases=True)


def _iter_normalized_requirement_lines(raw_input: str) -> Iterator[str]:
    normalized = raw_input.strip()
    if not normalized:
        return

    for line in normalized.splitlines():
        stripped = _strip_inline_requirement_comment(line)
        if stripped:
            yield stripped


def _split_package_install_input(raw_input: str) -> list[str]:
    """
    Normalize the user-provided package string into a list of pip args.

    - Supports multiline input (one requirement / options per line).
    - Strips inline comments (`# ...`) and empty lines.
    - Preserves a single valid requirement string, even when it contains spaces.
    - Falls back to shlex splitting for command-style input and options.
    """
    specs: list[str] = []
    for line in _iter_normalized_requirement_lines(raw_input):
        specs.extend(_split_package_install_line(line))
    return specs


def _split_package_install_line(line: str) -> list[str]:
    try:
        Requirement(line)
    except InvalidRequirement:
        return shlex.split(line)
    return [line]


def _extract_requested_requirements_from_package_input(raw_input: str) -> set[str]:
    requirements: set[str] = set()
    for line in _iter_normalized_requirement_lines(raw_input):
        try:
            req = Requirement(line)
        except InvalidRequirement:
            tokens = _split_package_install_line(line)
            if not tokens:
                continue
            if tokens[0] in {"-e", "--editable"} or tokens[0].startswith("--editable="):
                requirement_name = _extract_requirement_name(line)
                if requirement_name:
                    requirements.add(requirement_name)
                continue
            if tokens[0].startswith("-"):
                continue
            for token in tokens:
                requirement_name = _extract_requirement_name(token)
                if requirement_name:
                    requirements.add(requirement_name)
        else:
            requirements.add(_canonicalize_distribution_name(req.name))
    return requirements


def _package_specs_override_index(package_specs: list[str]) -> bool:
    for index, spec in enumerate(package_specs):
        if spec in {"-i", "--index-url"}:
            if index + 1 < len(package_specs):
                return True
            continue
        if spec.startswith("--index-url="):
            return True
        if spec.startswith("-i") and spec != "-i":
            return True
    return False


def _extract_requirement_name(raw_requirement: str) -> str | None:
    line = raw_requirement.split("#", 1)[0].strip()
    if not line:
        return None
    if line.startswith(("-r", "--requirement", "-c", "--constraint")):
        return None

    egg_match = re.search(r"#egg=([A-Za-z0-9_.-]+)", raw_requirement)
    if egg_match:
        return _canonicalize_distribution_name(egg_match.group(1))

    if line.startswith("-"):
        return None

    candidate = re.split(r"[<>=!~;\s\[]", line, maxsplit=1)[0].strip()
    if not candidate:
        return None
    return _canonicalize_distribution_name(candidate)


def _iter_requirements(
    requirements_path: str,
    _visited: set[str] | None = None,
) -> Iterator[tuple[str, SpecifierSet | None]]:
    visited = _visited or set()
    resolved_path = os.path.realpath(requirements_path)
    if resolved_path in visited:
        logger.warning(
            "检测到循环依赖的 requirements 包含: %s，将跳过该文件", resolved_path
        )
        return
    visited.add(resolved_path)

    try:
        with open(resolved_path, encoding="utf-8") as f:
            for raw_line in f:
                for line in _iter_normalized_requirement_lines(raw_line):
                    tokens = shlex.split(line)
                    if not tokens:
                        continue

                    # Handle recursion
                    nested: str | None = None
                    if tokens[0] in {"-r", "--requirement"} and len(tokens) > 1:
                        nested = tokens[1]
                    elif tokens[0].startswith("--requirement="):
                        nested = tokens[0].split("=", 1)[1]

                    if nested:
                        if not os.path.isabs(nested):
                            nested = os.path.join(
                                os.path.dirname(resolved_path), nested
                            )
                        yield from _iter_requirements(nested, _visited=visited)
                        continue

                    if tokens[0] in {"-c", "--constraint"}:
                        continue

                    if tokens[0].startswith("-"):
                        name = _extract_requirement_name(line)
                        if name:
                            yield name, None
                        continue

                    try:
                        req = Requirement(line)
                        if req.marker and not req.marker.evaluate():
                            continue
                        yield (
                            _canonicalize_distribution_name(req.name),
                            req.specifier or None,
                        )
                    except InvalidRequirement:
                        name = _extract_requirement_name(line)
                        if name:
                            yield name, None
    except FileNotFoundError:
        # Rethrow to allow find_missing_requirements to return None
        raise


def _extract_requirement_names(requirements_path: str) -> set[str]:
    try:
        return {name for name, _ in _iter_requirements(requirements_path)}
    except Exception as exc:
        logger.warning("读取依赖文件失败，跳过冲突检测: %s", exc)
        return set()


def _collect_installed_distribution_versions(paths: list[str]) -> dict[str, str] | None:
    installed: dict[str, str] = {}
    try:
        for distribution in importlib_metadata.distributions(path=paths):
            distribution_name = (
                distribution.metadata["Name"]
                if "Name" in distribution.metadata
                else None
            )
            if not distribution_name:
                continue
            installed.setdefault(
                _canonicalize_distribution_name(distribution_name),
                distribution.version,
            )
    except Exception as exc:
        logger.warning("读取已安装依赖失败，跳过缺失依赖预检查: %s", exc)
        return None
    return installed


def _find_missing_requirements(requirements_path: str) -> set[str] | None:
    try:
        required = list(_iter_requirements(requirements_path))
    except Exception as exc:
        logger.warning("预检查缺失依赖失败，将回退到完整安装: %s", exc)
        return None

    if not required:
        return set()

    installed = _collect_installed_distribution_versions(_get_requirement_check_paths())
    if installed is None:
        return None

    missing: set[str] = set()
    for name, specifier in required:
        installed_version = installed.get(name)
        if not installed_version:
            missing.add(name)
            continue
        if specifier and not _specifier_contains_version(specifier, installed_version):
            missing.add(name)

    return missing


def find_missing_requirements(requirements_path: str) -> set[str] | None:
    return _find_missing_requirements(requirements_path)


def find_missing_requirements_or_raise(requirements_path: str) -> set[str]:
    missing = find_missing_requirements(requirements_path)
    if missing is None:
        raise RequirementsPrecheckFailed(f"预检查失败: {requirements_path}")
    return missing


def _get_core_constraints(core_dist_name: str | None) -> list[str]:
    """
    Get version constraints for core dependencies to prevent downgrades.
    """
    constraints: list[str] = []
    try:
        if core_dist_name is None:
            core_dist_name = "AstrBot"
            try:
                importlib_metadata.distribution("AstrBot")
            except importlib_metadata.PackageNotFoundError:
                try:
                    if __package__:
                        top_pkg = __package__.split(".")[0]
                        for dist in importlib_metadata.distributions():
                            if (
                                top_pkg
                                in (dist.read_text("top_level.txt") or "").splitlines()
                            ):
                                core_dist_name = dist.metadata["Name"]
                                break
                except Exception:
                    pass

        try:
            dist = importlib_metadata.distribution(core_dist_name)
        except importlib_metadata.PackageNotFoundError:
            return []

        if not dist or not dist.requires:
            return []

        installed = _collect_installed_distribution_versions(
            _get_requirement_check_paths()
        )
        if not installed:
            return []

        for req_str in dist.requires:
            try:
                req = Requirement(req_str)
                if req.marker and not req.marker.evaluate():
                    continue
                name = _canonicalize_distribution_name(req.name)
                if name in installed:
                    constraints.append(f"{name}=={installed[name]}")
            except Exception:
                continue
    except Exception as exc:
        logger.warning("获取核心依赖约束失败: %s", exc)
    return constraints


@contextlib.contextmanager
def _core_constraints_file(core_dist_name: str | None) -> Iterator[str | None]:
    constraints = _get_core_constraints(core_dist_name)
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
        yield path
    except Exception as exc:
        logger.warning("创建临时约束文件失败: %s", exc)
        yield None
    finally:
        if path and os.path.exists(path):
            with contextlib.suppress(Exception):
                os.remove(path)


class _StreamingLogWriter(io.TextIOBase):
    def __init__(self, log_func) -> None:
        self._log_func = log_func
        self._buffer = ""
        self.lines: list[str] = []

    def write(self, text: str) -> int:
        if not text:
            return 0

        self._buffer += text.replace("\r", "\n")
        while "\n" in self._buffer:
            raw_line, self._buffer = self._buffer.split("\n", 1)
            line = raw_line.rstrip("\r\n")
            self._log_func(line)
            self.lines.append(line)
        return len(text)

    def flush(self) -> None:
        line = self._buffer.rstrip("\r\n")
        if line:
            self._log_func(line)
            self.lines.append(line)
        self._buffer = ""


def _run_pip_main_streaming(pip_main, args: list[str]) -> tuple[int, list[str]]:
    stream = _StreamingLogWriter(logger.info)
    with (
        contextlib.redirect_stdout(stream),
        contextlib.redirect_stderr(stream),
    ):
        result_code = pip_main(args)
    stream.flush()
    return result_code, stream.lines


def _classify_pip_failure(lines: list[str]) -> DependencyConflictError | None:
    error_lines = [
        line
        for line in lines
        if line.startswith("ERROR:")
        or "The user requested" in line
        or "ResolutionImpossible" in line
    ]
    if not error_lines:
        return None

    is_conflict = any(
        "conflict" in line.lower() or "resolutionimpossible" in line.lower()
        for line in error_lines
    )
    if not is_conflict:
        return None

    is_core_conflict = any("(constraint)" in line for line in error_lines)
    constraints = [line.strip() for line in error_lines if "(constraint)" in line]
    requested = [
        line.strip()
        for line in error_lines
        if "The user requested" in line and "(constraint)" not in line
    ]

    detail = ""
    if constraints and requested:
        detail = (
            " 冲突详情: "
            f"{requested[0].removeprefix('The user requested ')} vs "
            f"{constraints[0].removeprefix('The user requested ')}。"
        )

    if is_core_conflict:
        message = (
            f"检测到核心依赖版本保护冲突。{detail}插件要求的依赖版本与 AstrBot 核心不兼容，"
            "为了系统稳定，已阻止该降级行为。请联系插件作者或调整 requirements.txt。"
        )
    else:
        message = f"检测到依赖冲突。{detail}"

    return DependencyConflictError(
        message, error_lines, is_core_conflict=is_core_conflict
    )


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
    def __init__(
        self,
        pip_install_arg: str,
        pypi_index_url: str | None = None,
        core_dist_name: str | None = "AstrBot",
    ) -> None:
        self.pip_install_arg = pip_install_arg
        self.pypi_index_url = pypi_index_url
        self.core_dist_name = core_dist_name

    def _build_pip_args(
        self,
        package_name: str | None,
        requirements_path: str | None,
        mirror: str | None,
    ) -> tuple[list[str], set[str]]:
        args: list[str] = []
        requested_requirements: set[str] = set()
        pip_install_args = (
            shlex.split(self.pip_install_arg) if self.pip_install_arg else []
        )
        normalized_requirements_path = (
            requirements_path.strip() if requirements_path else ""
        )

        if package_name:
            package_specs = _split_package_install_input(package_name)
            if package_specs:
                args = ["install", *package_specs]
                requested_requirements = (
                    _extract_requested_requirements_from_package_input(package_name)
                )
        elif normalized_requirements_path:
            args = ["install", "-r", normalized_requirements_path]
            requested_requirements = _extract_requirement_names(
                normalized_requirements_path
            )

        if not args:
            return [], requested_requirements

        if not _package_specs_override_index([*args[1:], *pip_install_args]):
            index_url = mirror or self.pypi_index_url or "https://pypi.org/simple"
            args.extend(["--trusted-host", "mirrors.aliyun.com", "-i", index_url])

        if pip_install_args:
            args.extend(pip_install_args)

        return args, requested_requirements

    async def install(
        self,
        package_name: str | None = None,
        requirements_path: str | None = None,
        mirror: str | None = None,
    ) -> None:
        args, requested_requirements = self._build_pip_args(
            package_name, requirements_path, mirror
        )
        if not args:
            logger.info("Pip 包管理器跳过安装：未提供有效的包名或 requirements 文件。")
            return

        target_site_packages = None
        if is_packaged_desktop_runtime():
            target_site_packages = get_astrbot_site_packages_path()
            os.makedirs(target_site_packages, exist_ok=True)
            _prepend_sys_path(target_site_packages)
            args.extend(
                [
                    "--target",
                    target_site_packages,
                    "--upgrade",
                    "--upgrade-strategy",
                    "only-if-needed",
                ]
            )

        with _core_constraints_file(self.core_dist_name) as constraints_file_path:
            if constraints_file_path:
                args.extend(["-c", constraints_file_path])

            logger.info("Pip 包管理器 argv: %s", ["pip", *args])
            result_code, lines = await self._run_pip_in_process(args)

            if result_code != 0:
                conflict = _classify_pip_failure(lines)
                if conflict:
                    raise conflict
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

    async def _run_pip_in_process(self, args: list[str]) -> tuple[int, list[str]]:
        pip_main = _get_pip_main()
        _patch_distlib_finder_for_frozen_runtime()

        original_handlers = list(logging.getLogger().handlers)
        result_code, error_lines = await asyncio.to_thread(
            _run_pip_main_streaming, pip_main, args
        )

        _cleanup_added_root_handlers(original_handlers)
        return result_code, error_lines
