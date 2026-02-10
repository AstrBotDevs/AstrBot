import asyncio
import contextlib
import importlib
import importlib.util
import io
import logging
import os
import sys

from astrbot.core.utils.astrbot_path import get_astrbot_site_packages_path
from astrbot.core.utils.runtime_env import is_packaged_electron_runtime

logger = logging.getLogger("astrbot")

_DISTLIB_FINDER_PATCH_ATTEMPTED = False


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
                f"ASTRBOT_ELECTRON_CLIENT={os.environ.get('ASTRBOT_ELECTRON_CLIENT')})"
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


def _prefer_module_from_site_packages(
    module_name: str, site_packages_path: str
) -> bool:
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

    for key in list(sys.modules.keys()):
        if key == module_name or key.startswith(f"{module_name}."):
            sys.modules.pop(key, None)

    spec = importlib.util.spec_from_file_location(
        module_name,
        module_location,
        submodule_search_locations=submodule_search_locations,
    )
    if spec is None or spec.loader is None:
        return False

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    logger.info("Loaded %s from plugin site-packages: %s", module_name, module_location)
    return True


def _prefer_fastapi_related_modules(site_packages_path: str) -> None:
    for module_name in ("starlette", "starlette.status"):
        try:
            _prefer_module_from_site_packages(module_name, site_packages_path)
        except Exception as exc:
            logger.debug(
                "Failed to prefer module %s from plugin site-packages: %s",
                module_name,
                exc,
            )


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
        if package_name:
            args.append(package_name)
        elif requirements_path:
            args.extend(["-r", requirements_path])

        index_url = mirror or self.pypi_index_url or "https://pypi.org/simple"
        args.extend(["--trusted-host", "mirrors.aliyun.com", "-i", index_url])

        target_site_packages = None
        if is_packaged_electron_runtime():
            target_site_packages = get_astrbot_site_packages_path()
            os.makedirs(target_site_packages, exist_ok=True)
            _prepend_sys_path(target_site_packages)
            args.extend(["--target", target_site_packages])
            args.append("--upgrade")

        if self.pip_install_arg:
            args.extend(self.pip_install_arg.split())

        logger.info(f"Pip 包管理器: pip {' '.join(args)}")
        result_code = await self._run_pip_in_process(args)

        if result_code != 0:
            raise Exception(f"安装失败，错误码：{result_code}")

        if target_site_packages:
            _prepend_sys_path(target_site_packages)
            _prefer_fastapi_related_modules(target_site_packages)
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
