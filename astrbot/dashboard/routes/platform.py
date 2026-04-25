"""统一 Webhook 路由

提供统一的 webhook 回调入口，支持多个平台使用同一端口接收回调。
"""

from quart import request

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.platform import Platform
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

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
            "/api/platform/wecom-kf/<platform_id>/accounts",
            view_func=self.get_wecom_kf_accounts,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/platform/wecom-kf/<platform_id>/accounts",
            view_func=self.add_wecom_kf_account,
            methods=["POST"],
        )
        self.app.add_url_rule(
            "/api/platform/wecom-kf/<platform_id>/accounts/<open_kfid>",
            view_func=self.update_wecom_kf_account,
            methods=["PUT"],
        )
        self.app.add_url_rule(
            "/api/platform/wecom-kf/<platform_id>/accounts/<open_kfid>",
            view_func=self.delete_wecom_kf_account,
            methods=["DELETE"],
        )
        self.app.add_url_rule(
            "/api/platform/wecom-kf/<platform_id>/avatar",
            view_func=self.upload_wecom_kf_avatar,
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

    def _find_wecom_kf_platform(self, platform_id: str) -> Platform | None:
        for platform in self.platform_manager.platform_insts:
            if platform.meta().id == platform_id and platform.meta().name == "wecom_kf":
                return platform
        return None

    async def get_wecom_kf_accounts(self, platform_id: str):
        platform = self._find_wecom_kf_platform(platform_id)
        if not platform or not hasattr(platform, "get_kf_accounts_payload"):
            return Response().error("未找到微信客服平台实例").__dict__, 404
        try:
            payload = await platform.get_kf_accounts_payload()
            return Response().ok(payload).__dict__
        except Exception as e:
            logger.error(f"获取微信客服账号列表失败: {e}", exc_info=True)
            return Response().error(f"获取微信客服账号列表失败: {e}").__dict__, 500

    async def add_wecom_kf_account(self, platform_id: str):
        platform = self._find_wecom_kf_platform(platform_id)
        if not platform or not hasattr(platform, "add_kf_account"):
            return Response().error("未找到微信客服平台实例").__dict__, 404

        body = await request.get_json(silent=True) or {}
        name = str(body.get("name", "")).strip()
        media_id = str(body.get("media_id", "")).strip()
        if not name:
            return Response().error("客服名称不能为空").__dict__, 400

        try:
            payload = await platform.add_kf_account(name, media_id)
            return Response().ok(payload, "微信客服账号已创建").__dict__
        except Exception as e:
            logger.error(f"创建微信客服账号失败: {e}", exc_info=True)
            return Response().error(f"创建微信客服账号失败: {e}").__dict__, 500

    async def update_wecom_kf_account(self, platform_id: str, open_kfid: str):
        platform = self._find_wecom_kf_platform(platform_id)
        if not platform or not hasattr(platform, "update_kf_account"):
            return Response().error("未找到微信客服平台实例").__dict__, 404

        body = await request.get_json(silent=True) or {}
        name = str(body.get("name", "")).strip()
        media_id = str(body.get("media_id", "")).strip()
        if not name and not media_id:
            return Response().error(
                "客服名称和头像 media_id 不能同时为空"
            ).__dict__, 400

        try:
            payload = await platform.update_kf_account(open_kfid, name, media_id)
            return Response().ok(payload, "微信客服账号已更新").__dict__
        except Exception as e:
            logger.error(f"更新微信客服账号失败: {e}", exc_info=True)
            return Response().error(f"更新微信客服账号失败: {e}").__dict__, 500

    async def delete_wecom_kf_account(self, platform_id: str, open_kfid: str):
        platform = self._find_wecom_kf_platform(platform_id)
        if not platform or not hasattr(platform, "delete_kf_account"):
            return Response().error("未找到微信客服平台实例").__dict__, 404

        try:
            payload = await platform.delete_kf_account(open_kfid)
            return Response().ok(payload, "微信客服账号已删除").__dict__
        except Exception as e:
            logger.error(f"删除微信客服账号失败: {e}", exc_info=True)
            return Response().error(f"删除微信客服账号失败: {e}").__dict__, 500

    async def upload_wecom_kf_avatar(self, platform_id: str):
        platform = self._find_wecom_kf_platform(platform_id)
        if not platform or not hasattr(platform, "upload_kf_avatar"):
            return Response().error("未找到微信客服平台实例").__dict__, 404

        files = await request.files
        file = files.get("file")
        if not file:
            return Response().error("未上传头像文件").__dict__, 400
        if file.mimetype and not file.mimetype.startswith("image/"):
            return Response().error("头像文件必须是图片").__dict__, 400

        from pathlib import Path

        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(file.filename or "").suffix or ".jpg"
        target = temp_dir / f"wecom_kf_avatar_{platform_id}{suffix}"

        try:
            await file.save(target)
            payload = await platform.upload_kf_avatar(target)
            media_id = str(payload.get("media_id", "")).strip()
            if not media_id:
                return Response().error("微信客服头像上传未返回 media_id").__dict__, 500
            return Response().ok({"media_id": media_id, "raw": payload}).__dict__
        except Exception as e:
            logger.error(f"上传微信客服头像失败: {e}", exc_info=True)
            return Response().error(f"上传微信客服头像失败: {e}").__dict__, 500
        finally:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
