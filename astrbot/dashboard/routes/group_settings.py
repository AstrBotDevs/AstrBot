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
            "/group-settings/clear-provider": ("POST", self.clear_group_provider),
            "/group-settings/clear-persona": ("POST", self.clear_group_persona),
            "/group-settings/clear": ("POST", self.clear_group_settings),
            "/group-settings/providers": ("GET", self.list_available_providers),
            "/group-settings/personas": ("GET", self.list_available_personas),
        }
        self.register_routes()

    def _parse_umo(self, umo: str) -> dict:
        """解析 UMO 字符串
        
        Args:
            umo: 统一消息来源标识，格式: platform:message_type:group_id
            
        Returns:
            dict: 包含 umo, platform, message_type, group_id 的字典
        """
        parts = umo.split(":")
        return {
            "umo": umo,
            "platform": parts[0] if len(parts) >= 1 else "unknown",
            "message_type": parts[1] if len(parts) >= 2 else "unknown",
            "group_id": parts[2] if len(parts) >= 3 else "",
        }

    def _serialize_settings(self, umo: str, settings) -> dict:
        """序列化设置为字典
        
        Args:
            umo: 统一消息来源标识
            settings: GroupSettings 对象
            
        Returns:
            dict: 包含完整设置信息的字典
        """
        base = self._parse_umo(umo)
        base.update({
            "provider_id": settings.provider_id or "",
            "persona_id": settings.persona_id or "",
            "model": settings.model or "",
            "set_by": settings.set_by or "",
            "set_at": settings.set_at or "",
        })
        return base

    def _validate_pagination(self, page: int, page_size: int) -> tuple:
        """验证分页参数
        
        Args:
            page: 页码
            page_size: 每页数量
            
        Returns:
            tuple: (is_valid, error_message, status_code)
        """
        if page < 1:
            return False, "page must be >= 1", 400
        if page_size < 1:
            return False, "page_size must be >= 1", 400
        if page_size > 100:
            return False, "page_size must be <= 100", 400
        return True, None, 200

    async def list_group_settings(self):
        """获取所有群设置列表

        Query 参数:
            page: 页码，默认为 1
            page_size: 每页数量，默认为 20
            search: 搜索关键词，匹配 umo, provider_id, persona_id
        """
        try:
            page = request.args.get("page", 1, type=int)
            page_size = request.args.get("page_size", 20, type=int)
            search = request.args.get("search", "", type=str).strip()

            # 验证分页参数
            is_valid, error_msg, status_code = self._validate_pagination(page, page_size)
            if not is_valid:
                return Response().error(error_msg).__dict__, status_code

            # 获取所有群设置
            all_settings = await self.group_settings_mgr.get_all_groups_with_settings()

            # 过滤和格式化
            settings_list = []
            for umo, settings in all_settings.items():
                # 搜索过滤 - 同时搜索 umo, provider_id, persona_id
                if search:
                    search_lower = search.lower()
                    umo_match = search_lower in umo.lower()
                    provider_match = settings.provider_id and search_lower in settings.provider_id.lower()
                    persona_match = settings.persona_id and search_lower in settings.persona_id.lower()
                    
                    if not (umo_match or provider_match or persona_match):
                        continue

                settings_list.append(self._serialize_settings(umo, settings))

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
                return Response().error("缺少必要参数: umo").__dict__, 400

            settings = await self.group_settings_mgr.get_settings(umo)

            return (
                Response()
                .ok(self._serialize_settings(umo, settings))
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
                return Response().error("缺少必要参数: umo").__dict__, 400
            if not provider_id:
                return Response().error("缺少必要参数: provider_id").__dict__, 400

            # 验证 provider 是否存在
            provider_manager = self.core_lifecycle.provider_manager
            provider = provider_manager.get_provider_by_id(provider_id)
            if not provider:
                return Response().error(f"Provider '{provider_id}' 不存在").__dict__, 404

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
                return Response().error("缺少必要参数: umo").__dict__, 400
            if not persona_id:
                return Response().error("缺少必要参数: persona_id").__dict__, 400

            # 验证 persona 是否存在
            persona_mgr = self.core_lifecycle.persona_mgr
            persona = persona_mgr.get_persona_v3_by_id(persona_id)
            if not persona:
                return Response().error(f"Persona '{persona_id}' 不存在").__dict__, 404

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

    async def clear_group_provider(self):
        """清除群的 Provider 设置

        请求体:
        {
            "umo": "平台:消息类型:群ID"
        }
        """
        try:
            data = await request.get_json()
            umo = data.get("umo", "").strip()

            if not umo:
                return Response().error("缺少必要参数: umo").__dict__, 400

            await self.group_settings_mgr.remove_provider_override(umo)

            return (
                Response()
                .ok({
                    "message": f"群 {umo} 的 Provider 设置已清除",
                    "umo": umo,
                })
                .__dict__
            )
        except Exception as e:
            logger.error(f"清除群 Provider 失败: {e!s}")
            return Response().error(f"清除群 Provider 失败: {e!s}").__dict__

    async def clear_group_persona(self):
        """清除群的 Persona 设置

        请求体:
        {
            "umo": "平台:消息类型:群ID"
        }
        """
        try:
            data = await request.get_json()
            umo = data.get("umo", "").strip()

            if not umo:
                return Response().error("缺少必要参数: umo").__dict__, 400

            await self.group_settings_mgr.remove_persona_override(umo)

            return (
                Response()
                .ok({
                    "message": f"群 {umo} 的 Persona 设置已清除",
                    "umo": umo,
                })
                .__dict__
            )
        except Exception as e:
            logger.error(f"清除群 Persona 失败: {e!s}")
            return Response().error(f"清除群 Persona 失败: {e!s}").__dict__

    async def clear_group_settings(self):
        """清除群的设置（需要显式确认才能清除全部）

        请求体:
        {
            "umo": "平台:消息类型:群ID",  // 清除指定群
            "confirm_clear_all": true     // 清除所有群设置时需要此标志
        }
        """
        try:
            data = await request.get_json()
            umo = data.get("umo", "").strip()
            confirm_clear_all = data.get("confirm_clear_all", False)

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
            elif confirm_clear_all:
                # 清除所有群设置 - 需要显式确认
                all_settings = await self.group_settings_mgr.get_all_groups_with_settings()
                count = 0
                for group_umo in list(all_settings.keys()):
                    await self.group_settings_mgr.clear_settings(group_umo)
                    count += 1
                return (
                    Response()
                    .ok({
                        "message": f"已清除 {count} 个群的设置",
                        "cleared_count": count,
                    })
                    .__dict__
                )
            else:
                return (
                    Response()
                    .error("请指定 umo 或设置 confirm_clear_all=true 以清除所有设置")
                    .__dict__, 400
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
