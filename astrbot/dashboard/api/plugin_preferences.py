from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import PluginPinnedExtensionsRequest
from astrbot.dashboard.services.plugin_preference_service import (
    PluginPreferenceService,
)

from .auth import AuthContext, require_scope

router = APIRouter(tags=["Plugin Preferences"])


async def require_plugin_scope(request: Request) -> AuthContext:
    """校验当前请求具有 plugin scope 权限。"""
    return await require_scope(request, "plugin")


def get_plugin_preference_service(request: Request) -> PluginPreferenceService:
    """从应用状态获取插件偏好服务。"""
    return request.app.state.services.plugin_preferences


@router.get("/plugins/preferences/pinned")
async def get_pinned_extensions(
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginPreferenceService = Depends(get_plugin_preference_service),
):
    """获取 Dashboard 全局置顶插件列表。"""
    try:
        pinned, preference_exists = await service.get_pinned_extensions()
    except Exception as exc:
        raise ApiError("加载插件置顶偏好失败", status_code=500) from exc
    return ok(
        {
            "pinned_extensions": pinned,
            "preference_exists": preference_exists,
        }
    )


@router.put("/plugins/preferences/pinned")
async def set_pinned_extensions(
    payload: PluginPinnedExtensionsRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginPreferenceService = Depends(get_plugin_preference_service),
):
    """更新 Dashboard 全局置顶插件列表。"""
    try:
        pinned = await service.set_pinned_extensions(payload.pinned_extensions)
    except Exception as exc:
        raise ApiError("保存插件置顶偏好失败", status_code=500) from exc
    return ok({"pinned_extensions": pinned, "preference_exists": True})
