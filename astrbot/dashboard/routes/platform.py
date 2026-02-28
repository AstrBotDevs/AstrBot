"""统一 Webhook 路由

提供统一的 webhook 回调入口，支持多个平台使用同一端口接收回调。
"""
from astrbot.core.lang import t

from quart import request

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.platform import Platform

from .route import Response, Route, RouteContext


class PlatformRoute(Route):
    """统一 Webhook 路由"""

    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.platform_manager = core_lifecycle.platform_manager

        self._register_webhook_routes()

    def _register_webhook_routes(self) -> None:
        """注册 webhook 路由"""
        # 统一 webhook 入口，支持 GET 和 POST
        self.app.add_url_rule(
            "/api/platform/webhook/<webhook_uuid>",
            view_func=self.unified_webhook_callback,
            methods=["GET", "POST"],
        )

        # 平台统计信息接口
        self.app.add_url_rule(
            "/api/platform/stats",
            view_func=self.get_platform_stats,
            methods=["GET"],
        )

    async def unified_webhook_callback(self, webhook_uuid: str):
        """统一 webhook 回调入口

        Args:
            webhook_uuid: 平台配置中的 webhook_uuid

        Returns:
            根据平台适配器返回相应的响应
        """
        # 根据 webhook_uuid 查找对应的平台
        platform_adapter = self._find_platform_by_uuid(webhook_uuid)

        if not platform_adapter:
            logger.warning(t("msg-bcc64513", webhook_uuid=webhook_uuid))
            return Response().error(t("msg-1478800f")).__dict__, 404

        # 调用平台适配器的 webhook_callback 方法
        try:
            result = await platform_adapter.webhook_callback(request)
            return result
        except NotImplementedError:
            logger.error(
                t("msg-378cb077", res=platform_adapter.meta().name)
            )
            return Response().error(t("msg-2d797305")).__dict__, 500
        except Exception as e:
            logger.error(t("msg-83f8dedf", e=e), exc_info=True)
            return Response().error(t("msg-af91bc78")).__dict__, 500

    def _find_platform_by_uuid(self, webhook_uuid: str) -> Platform | None:
        """根据 webhook_uuid 查找对应的平台适配器

        Args:
            webhook_uuid: webhook UUID

        Returns:
            平台适配器实例，未找到则返回 None
        """
        for platform in self.platform_manager.platform_insts:
            if platform.config.get("webhook_uuid") == webhook_uuid:
                if platform.unified_webhook():
                    return platform
        return None

    async def get_platform_stats(self):
        """获取所有平台的统计信息

        Returns:
            包含平台统计信息的响应
        """
        try:
            stats = self.platform_manager.get_all_stats()
            return Response().ok(stats).__dict__
        except Exception as e:
            logger.error(t("msg-136a952f", e=e), exc_info=True)
            return Response().error(t("msg-60bb0722", e=e)).__dict__, 500
