from __future__ import annotations

import secrets
import string

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.platform import Platform
from astrbot.core.platform.sources.dingtalk.app_registration import (
    poll_dingtalk_app_registration_once,
    request_dingtalk_app_registration,
)
from astrbot.core.platform.sources.lark.app_registration import (
    poll_app_registration_once,
    request_app_registration,
)
from astrbot.core.platform.sources.lark.bot_info import request_lark_bot_info
from astrbot.core.platform.sources.qqofficial.login_registration import (
    poll_qqofficial_login_once,
    request_qqofficial_login_qr,
)
from astrbot.core.platform.sources.weixin_oc.login_registration import (
    poll_weixin_oc_login_once,
    request_weixin_oc_login_qr,
)


class PlatformServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


def random_platform_id_suffix() -> str:
    return "_" + "".join(secrets.choice(string.ascii_lowercase) for _ in range(4))


class PlatformService:
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle) -> None:
        self.platform_manager = core_lifecycle.platform_manager

    async def handle_webhook_callback(self, webhook_uuid: str, request_obj):
        platform_adapter = self.find_platform_by_uuid(webhook_uuid)

        if not platform_adapter:
            logger.warning(f"未找到 webhook_uuid 为 {webhook_uuid} 的平台")
            raise PlatformServiceError("未找到对应平台", 404)

        try:
            return await platform_adapter.webhook_callback(request_obj)
        except NotImplementedError as exc:
            logger.error(
                f"平台 {platform_adapter.meta().name} 未实现 webhook_callback 方法"
            )
            raise PlatformServiceError("平台未支持统一 Webhook 模式", 500) from exc
        except Exception as exc:
            logger.error(f"处理 webhook 回调时发生错误: {exc}", exc_info=True)
            raise PlatformServiceError("处理回调失败", 500) from exc

    def find_platform_by_uuid(self, webhook_uuid: str) -> Platform | None:
        for platform in self.platform_manager.platform_insts:
            if platform.config.get("webhook_uuid") == webhook_uuid:
                if platform.unified_webhook():
                    return platform
        return None

    def get_platform_stats(self):
        try:
            return self.platform_manager.get_all_stats()
        except Exception as exc:
            logger.error(f"获取平台统计信息失败: {exc}", exc_info=True)
            raise PlatformServiceError(f"获取统计信息失败: {exc}", 500) from exc

    async def handle_platform_registration(
        self,
        platform_type: str,
        payload: dict,
    ) -> dict:
        try:
            action = str(payload.get("action", "")).strip().lower()
            if not action:
                raise PlatformServiceError("Missing action", 400)

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
            if platform_type == "dingtalk":
                return await self._handle_dingtalk_registration(action, payload)
            if platform_type == "qq_official":
                return await self._handle_qqofficial_registration(
                    action,
                    payload,
                    platform_config,
                )

            raise PlatformServiceError(
                f"Unsupported platform registration: {platform_type}",
                404,
            )
        except PlatformServiceError:
            raise
        except Exception as exc:
            logger.error(f"处理平台一键创建请求失败: {exc}", exc_info=True)
            raise PlatformServiceError(str(exc), 500) from exc

    async def _handle_lark_registration(
        self,
        action: str,
        payload: dict,
        platform_config: dict,
    ) -> dict:
        domain = str(platform_config.get("domain") or "").strip()

        if action == "start":
            registration = await request_app_registration(domain)
            return {
                "status": "pending",
                "device_code": registration.device_code,
                "registration_code": registration.device_code,
                "user_code": registration.user_code,
                "verification_uri": registration.verification_uri,
                "verification_uri_complete": registration.verification_uri_complete,
                "expires_in": registration.expires_in,
                "interval": registration.interval,
            }

        if action == "poll":
            device_code = str(
                payload.get("device_code") or payload.get("registration_code") or ""
            ).strip()
            if not device_code:
                raise PlatformServiceError("Missing device_code", 400)
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
                except Exception as exc:
                    logger.error(f"获取飞书机器人信息失败: {exc}", exc_info=True)
            return result

        raise PlatformServiceError(f"Unsupported action: {action}", 400)

    async def _handle_dingtalk_registration(
        self,
        action: str,
        payload: dict,
    ) -> dict:
        if action == "start":
            registration = await request_dingtalk_app_registration()
            return {
                "status": "pending",
                "device_code": registration.device_code,
                "registration_code": registration.device_code,
                "user_code": registration.user_code,
                "verification_uri": registration.verification_uri,
                "verification_uri_complete": registration.verification_uri_complete,
                "expires_in": registration.expires_in,
                "interval": registration.interval,
            }

        if action == "poll":
            device_code = str(
                payload.get("device_code") or payload.get("registration_code") or ""
            ).strip()
            if not device_code:
                raise PlatformServiceError("Missing device_code", 400)
            result = await poll_dingtalk_app_registration_once(device_code)
            if result.get("status") == "created":
                result["platform_id_suffix"] = random_platform_id_suffix()
            return result

        raise PlatformServiceError(f"Unsupported action: {action}", 400)

    async def _handle_qqofficial_registration(
        self,
        action: str,
        payload: dict,
        platform_config: dict,
    ) -> dict:
        if action == "start":
            registration = await request_qqofficial_login_qr(platform_config)
            return {
                "status": "pending",
                "registration_code": registration.task_id,
                "task_id": registration.task_id,
                "bind_key": registration.bind_key,
                "qrcode": registration.qrcode,
                "qrcode_img_content": registration.qrcode,
                "interval": registration.interval,
            }

        if action == "poll":
            task_id = str(
                payload.get("task_id") or payload.get("registration_code") or ""
            ).strip()
            bind_key = str(payload.get("bind_key") or "").strip()
            if not task_id:
                raise PlatformServiceError("Missing task_id", 400)
            if not bind_key:
                raise PlatformServiceError("Missing bind_key", 400)
            return await poll_qqofficial_login_once(
                platform_config=platform_config,
                task_id=task_id,
                bind_key=bind_key,
            )

        raise PlatformServiceError(f"Unsupported action: {action}", 400)

    async def _handle_weixin_oc_registration(
        self,
        action: str,
        payload: dict,
        platform_config: dict,
    ) -> dict:
        if action == "start":
            registration = await request_weixin_oc_login_qr(platform_config)
            return {
                "status": "pending",
                "registration_code": registration.qrcode,
                "qrcode": registration.qrcode,
                "qrcode_img_content": registration.qrcode_img_content,
                "interval": registration.interval,
            }

        if action == "poll":
            qrcode = str(
                payload.get("qrcode") or payload.get("registration_code") or ""
            ).strip()
            if not qrcode:
                raise PlatformServiceError("Missing qrcode", 400)
            result = await poll_weixin_oc_login_once(
                platform_config=platform_config,
                qrcode=qrcode,
            )
            if result.get("status") == "created":
                result["platform_id_suffix"] = random_platform_id_suffix()
            return result

        raise PlatformServiceError(f"Unsupported action: {action}", 400)
