"""群设置管理路由

提供群聊特定的 Provider 和 Persona 设置管理 API。
"""

from quart import request

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.group_settings.manager import GroupSettingsManager

from .route import Response, Route, RouteContext


class GroupSettingsRoute(Route):
    """群设置管理路由"""

    def __init__(
        self,
        context: RouteContext,
        db_helper: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.db_helper = db_helper
        self.core_lifecycle = core_lifecycle
        self.group_settings_mgr = GroupSettingsManager()

        self.routes = {
            "/group-settings/list": ("GET", self.list_group_settings),
            "/group-settings/get": ("GET", self.get_group_setting),
            "/group-settings/set-provider": ("POST", self.set_group_provider),
            "/group-settings/set-persona": ("POST", self.set_group_persona),
            "/group-settings/clear": ("POST", self.clear_group_settings),
            "/group-settings/providers": ("GET", self.list_available_providers),
            "/group-settings/personas": ("GET", self.list_available_personas),
        }
        self.register_routes()

    async def list_group_settings(self):
        """获取所有群设置列表

        Query 参数:
            page: 页码，默认为 1
            page_size: 每页数量，默认为 20
            search: 搜索关键词，匹配 umo
        """
        try:
            page = request.args.get("page", 1, type=int)
            page_size = request.args.get("page_size", 20, type=int)
            search = request.args.get("search", "", type=str).strip()

            if page < 1:
                page = 1
            if page_size < 1:
                page_size = 20
            if page_size > 100:
                page_size = 100

            # 获取所有群设置
            all_settings = await self.group_settings_mgr.get_all_groups_with_settings()

            # 过滤和格式化
            settings_list = []
            for umo, settings in all_settings.items():
                # 搜索过滤
                if search and search.lower() not in umo.lower():
                    continue

                # 解析 umo 格式: 平台:消息类型:群ID
                parts = umo.split(":")
                platform = parts[0] if len(parts) >= 1 else "unknown"
                message_type = parts[1] if len(parts) >= 2 else "unknown"
                group_id = parts[2] if len(parts) >= 3 else umo

                settings_list.append({
                    "umo": umo,
                    "platform": platform,
                    "message_type": message_type,
                    "group_id": group_id,
                    "provider_id": settings.provider_id or "",
                    "persona_id": settings.persona_id or "",
                    "model": settings.model or "",
                    "set_by": settings.set_by or "",
                    "set_at": settings.set_at or "",
                })

            # 分页
            total = len(settings_list)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated = settings_list[start_idx:end_idx]

            return (
                Response()
                .ok({
                    "settings": paginated,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                })
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取群设置列表失败: {e!s}")
            return Response().error(f"获取群设置列表失败: {e!s}").__dict__

    async def get_group_setting(self):
        """获取指定群的设置

        Query 参数:
            umo: 群的 UMO 标识
        """
        try:
            umo = request.args.get("umo", "", type=str).strip()
            if not umo:
                return Response().error("缺少必要参数: umo").__dict__

            settings = await self.group_settings_mgr.get_settings(umo)

            # 解析 umo
            parts = umo.split(":")
            platform = parts[0] if len(parts) >= 1 else "unknown"
            message_type = parts[1] if len(parts) >= 2 else "unknown"
            group_id = parts[2] if len(parts) >= 3 else umo

            return (
                Response()
                .ok({
                    "umo": umo,
                    "platform": platform,
                    "message_type": message_type,
                    "group_id": group_id,
                    "provider_id": settings.provider_id or "",
                    "persona_id": settings.persona_id or "",
                    "model": settings.model or "",
                    "set_by": settings.set_by or "",
                    "set_at": settings.set_at or "",
                })
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取群设置失败: {e!s}")
            return Response().error(f"获取群设置失败: {e!s}").__dict__

    async def set_group_provider(self):
        """设置群的 Provider

        请求体:
        {
            "umo": "平台:消息类型:群ID",
            "provider_id": "provider_id"
        }
        """
        try:
            data = await request.get_json()
            umo = data.get("umo", "").strip()
            provider_id = data.get("provider_id", "").strip()

            if not umo:
                return Response().error("缺少必要参数: umo").__dict__
            if not provider_id:
                return Response().error("缺少必要参数: provider_id").__dict__

            # 验证 provider 是否存在
            provider_manager = self.core_lifecycle.provider_manager
            provider = provider_manager.get_provider_by_id(provider_id)
            if not provider:
                return Response().error(f"Provider '{provider_id}' 不存在").__dict__

            await self.group_settings_mgr.set_provider(
                umo=umo,
                provider_id=provider_id,
                set_by="webui",
            )

            return (
                Response()
                .ok({
                    "message": f"群 {umo} 的 Provider 已设置为 {provider_id}",
                    "umo": umo,
                    "provider_id": provider_id,
                })
                .__dict__
            )
        except Exception as e:
            logger.error(f"设置群 Provider 失败: {e!s}")
            return Response().error(f"设置群 Provider 失败: {e!s}").__dict__

    async def set_group_persona(self):
        """设置群的 Persona

        请求体:
        {
            "umo": "平台:消息类型:群ID",
            "persona_id": "persona_id"
        }
        """
        try:
            data = await request.get_json()
            umo = data.get("umo", "").strip()
            persona_id = data.get("persona_id", "").strip()

            if not umo:
                return Response().error("缺少必要参数: umo").__dict__
            if not persona_id:
                return Response().error("缺少必要参数: persona_id").__dict__

            # 验证 persona 是否存在
            persona_mgr = self.core_lifecycle.persona_mgr
            persona = persona_mgr.get_persona_v3_by_id(persona_id)
            if not persona:
                return Response().error(f"Persona '{persona_id}' 不存在").__dict__

            await self.group_settings_mgr.set_persona(
                umo=umo,
                persona_id=persona_id,
                set_by="webui",
            )

            return (
                Response()
                .ok({
                    "message": f"群 {umo} 的 Persona 已设置为 {persona_id}",
                    "umo": umo,
                    "persona_id": persona_id,
                })
                .__dict__
            )
        except Exception as e:
            logger.error(f"设置群 Persona 失败: {e!s}")
            return Response().error(f"设置群 Persona 失败: {e!s}").__dict__

    async def clear_group_settings(self):
        """清除群的设置

        请求体:
        {
            "umo": "平台:消息类型:群ID"  // 可选，不传则清除所有群设置
        }
        """
        try:
            data = await request.get_json()
            umo = data.get("umo", "").strip()

            if umo:
                # 清除指定群的设置
                await self.group_settings_mgr.clear_settings(umo)
                return (
                    Response()
                    .ok({
                        "message": f"群 {umo} 的设置已清除",
                        "umo": umo,
                    })
                    .__dict__
                )
            else:
                # 清除所有群设置
                all_settings = await self.group_settings_mgr.get_all_groups_with_settings()
                for group_umo in all_settings.keys():
                    await self.group_settings_mgr.clear_settings(group_umo)
                return (
                    Response()
                    .ok({
                        "message": "所有群设置已清除",
                    })
                    .__dict__
                )
        except Exception as e:
            logger.error(f"清除群设置失败: {e!s}")
            return Response().error(f"清除群设置失败: {e!s}").__dict__

    async def list_available_providers(self):
        """获取可用的 Provider 列表"""
        try:
            provider_manager = self.core_lifecycle.provider_manager

            providers = [
                {
                    "id": p.meta().id,
                    "name": p.meta().id,
                    "model": p.meta().model,
                    "type": "chat_completion",
                }
                for p in provider_manager.provider_insts
            ]

            return Response().ok({"providers": providers}).__dict__
        except Exception as e:
            logger.error(f"获取 Provider 列表失败: {e!s}")
            return Response().error(f"获取 Provider 列表失败: {e!s}").__dict__

    async def list_available_personas(self):
        """获取可用的 Persona 列表"""
        try:
            persona_mgr = self.core_lifecycle.persona_mgr

            personas = [
                {
                    "id": p["name"],
                    "name": p["name"],
                    "prompt": p.get("prompt", "")[:100] + "..." if len(p.get("prompt", "")) > 100 else p.get("prompt", ""),
                }
                for p in persona_mgr.personas_v3
            ]

            return Response().ok({"personas": personas}).__dict__
        except Exception as e:
            logger.error(f"获取 Persona 列表失败: {e!s}")
            return Response().error(f"获取 Persona 列表失败: {e!s}").__dict__
