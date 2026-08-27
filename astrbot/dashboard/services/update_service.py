import inspect
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from astrbot import logger
from astrbot.core.utils.error_redaction import redact_sensitive_text
from astrbot.core.utils.pip_installer import PipInstaller


async def call_pip_install(pip_installer: PipInstaller, *args, **kwargs):
    result = pip_installer.install(*args, **kwargs)
    if inspect.isawaitable(result):
        return await cast(Awaitable[Any], result)
    return result


@dataclass
class UpdateServiceResult:
    data: Any = None
    message: str | None = None
    status: str = "ok"
    headers: dict | None = None


class UpdateServiceError(Exception):
    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class UpdateService:
    def __init__(
        self,
        *,
        pip_install_func: Callable[..., Awaitable[Any]],
        demo_mode: bool,
        clear_site_data_headers: dict,
    ) -> None:
        self.pip_install = pip_install_func
        self.demo_mode = demo_mode
        self.clear_site_data_headers = clear_site_data_headers

    async def shutdown(self) -> None:
        return None

    async def install_pip_package(self, data: object) -> UpdateServiceResult:
        if self.demo_mode:
            raise UpdateServiceError(
                "You are not permitted to do this operation in demo mode"
            )

        payload = data if isinstance(data, dict) else {}
        package = payload.get("package", "")
        mirror = payload.get("mirror", None)
        if not package:
            raise UpdateServiceError("缺少参数 package 或不合法。")
        try:
            await self.pip_install(package, mirror=mirror)
            return UpdateServiceResult(message="安装成功。")
        except Exception as exc:
            logger.error(
                "/api/update_pip: %s",
                redact_sensitive_text(traceback.format_exc()),
            )
            raise UpdateServiceError("安装依赖失败。") from exc
