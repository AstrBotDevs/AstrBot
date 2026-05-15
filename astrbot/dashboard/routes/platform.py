"""统一 Webhook 路由

提供统一的 webhook 回调入口，支持多个平台使用同一端口接收回调。
"""

from quart import request

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.platform import Platform
from astrbot.core.platform.sources.lark.app_registration import (
    poll_app_registration_once,
    request_app_registration,
)
from astrbot.core.platform.sources.lark.bot_info import request_lark_bot_info
from astrbot.core.platform.sources.weixin_oc.login_registration import (
    poll_weixin_oc_login_once,
    request_weixin_oc_login_qr,
)

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

        self.app.add_url_rule(
            "/api/platform/registration/<platform_type>",
            view_func=self.handle_platform_registration,
            methods=["POST"],
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
            logger.error(f"获取平台统计信息失败: {e}", exc_info=True)
            return Response().error(f"获取统计信息失败: {e}").__dict__, 500

    async def handle_platform_registration(self, platform_type: str):
        """Handle dashboard one-click platform registration actions."""
        try:
            payload = await request.get_json(silent=True) or {}
            action = str(payload.get("action", "")).strip().lower()
            if not action:
                return Response().error("Missing action").__dict__, 400

            platform_config = payload.get("platform_config")
            if not isinstance(platform_config, dict):
                platform_config = {}

            if platform_type == "lark":
                return await self._handle_lark_registration(
                    action,
                    payload,
                    platform_config,
                )
            if platform_type == "weixin_oc":
                return await self._handle_weixin_oc_registration(
                    action,
                    payload,
                    platform_config,
                )

            return Response().error(
                f"Unsupported platform registration: {platform_type}"
            ).__dict__, 404
        except Exception as e:
            logger.error(f"处理平台一键创建请求失败: {e}", exc_info=True)
            return Response().error(str(e)).__dict__, 500

    async def _handle_lark_registration(
        self,
        action: str,
        payload: dict,
        platform_config: dict,
    ):
        domain = str(platform_config.get("domain") or "").strip()

        if action == "start":
            registration = await request_app_registration(domain)
            return (
                Response()
                .ok(
                    {
                        "status": "pending",
                        "device_code": registration.device_code,
                        "registration_code": registration.device_code,
                        "user_code": registration.user_code,
                        "verification_uri": registration.verification_uri,
                        "verification_uri_complete": registration.verification_uri_complete,
                        "expires_in": registration.expires_in,
                        "interval": registration.interval,
                    }
                )
                .__dict__
            )

        if action == "poll":
            device_code = str(
                payload.get("device_code") or payload.get("registration_code") or ""
            ).strip()
            if not device_code:
                return Response().error("Missing device_code").__dict__, 400
            result = await poll_app_registration_once(
                domain=domain,
                device_code=device_code,
            )
            if result.get("status") == "created":
                try:
                    bot_info = await request_lark_bot_info(
                        domain=str(result.get("domain") or domain),
                        app_id=str(result.get("app_id") or ""),
                        app_secret=str(result.get("app_secret") or ""),
                    )
                    if bot_info.app_name:
                        result["bot_name"] = bot_info.app_name
                    if bot_info.open_id:
                        result["bot_open_id"] = bot_info.open_id
                except Exception as e:
                    logger.error(f"获取飞书机器人信息失败: {e}", exc_info=True)
            return Response().ok(result).__dict__

        return Response().error(f"Unsupported action: {action}").__dict__, 400

    async def _handle_weixin_oc_registration(
        self,
        action: str,
        payload: dict,
        platform_config: dict,
    ):
        if action == "start":
            registration = await request_weixin_oc_login_qr(platform_config)
            return (
                Response()
                .ok(
                    {
                        "status": "pending",
                        "registration_code": registration.qrcode,
                        "qrcode": registration.qrcode,
                        "qrcode_img_content": registration.qrcode_img_content,
                        "interval": registration.interval,
                    }
                )
                .__dict__
            )

        if action == "poll":
            qrcode = str(
                payload.get("qrcode") or payload.get("registration_code") or ""
            ).strip()
            if not qrcode:
                return Response().error("Missing qrcode").__dict__, 400
            result = await poll_weixin_oc_login_once(
                platform_config=platform_config,
                qrcode=qrcode,
            )
            return Response().ok(result).__dict__

        return Response().error(f"Unsupported action: {action}").__dict__, 400
