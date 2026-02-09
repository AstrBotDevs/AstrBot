import asyncio
import contextlib
import importlib
import io
import logging
import os
import sys

from astrbot.core.utils.astrbot_path import get_astrbot_site_packages_path
from astrbot.core.utils.runtime_env import is_packaged_electron_runtime

logger = logging.getLogger("astrbot")


def _get_pip_main():
    try:
        from pip._internal.cli.main import main as pip_main
    except ImportError:
        try:
            from pip import main as pip_main
        except ImportError as exc:
            raise ImportError("pip module is unavailable") from exc

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
            args.extend(["--target", target_site_packages])

        if self.pip_install_arg:
            args.extend(self.pip_install_arg.split())

        logger.info(f"Pip 包管理器: pip {' '.join(args)}")
        result_code = await self._run_pip_in_process(args)

        if result_code != 0:
            raise Exception(f"安装失败，错误码：{result_code}")

        if target_site_packages and target_site_packages not in sys.path:
            sys.path.insert(0, target_site_packages)
        importlib.invalidate_caches()

    async def _run_pip_in_process(self, args: list[str]) -> int:
        try:
            pip_main = _get_pip_main()
        except ImportError as exc:
            raise Exception("pip 模块不可用，请检查当前运行环境是否包含 pip") from exc

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
