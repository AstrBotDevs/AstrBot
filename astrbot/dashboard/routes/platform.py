"""统一 Webhook 路由

提供统一的 webhook 回调入口，支持多个平台使用同一端口接收回调。
"""

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
            logger.warning(f"未找到 webhook_uuid 为 {webhook_uuid} 的平台")
            return Response().error("未找到对应平台").__dict__, 404

        # 调用平台适配器的 webhook_callback 方法
        try:
            result = await platform_adapter.webhook_callback(request)
            return result
        except NotImplementedError:
            logger.error(
                f"平台 {platform_adapter.meta().name} 未实现 webhook_callback 方法"
            )
            return Response().error("平台未支持统一 Webhook 模式").__dict__, 500
        except Exception as e:
            logger.error(f"处理 webhook 回调时发生错误: {e}", exc_info=True)
            return Response().error("处理回调失败").__dict__, 500

    def _find_platform_by_uuid(self, webhook_uuid: str) -> Platform | None:
        """根据 webhook_uuid 查找对应的平台适配器

        Args:
            webhook_uuid: webhook UUID

        Returns:
            平台适配器实例，未找到则返回 None
        """
        for platform in self.platform_manager.platform_insts:
            config = platform.config
            uuid_val = config.get("webhook_uuid") if isinstance(config, dict) else getattr(config, "webhook_uuid", None)
            if uuid_val == webhook_uuid:
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
            logger.error(f"获取平台统计信息失败: {e}", exc_info=True)
            return Response().error(f"获取统计信息失败: {e}").__dict__, 500
