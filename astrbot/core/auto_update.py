"""AstrBot 自动更新模块

负责：
1. 定时检查新版本并通知管理员
2. 定时清理过期的更新前备份
3. 支持自动更新触发
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.core.config.default import VERSION
from astrbot.core.utils.astrbot_path import get_astrbot_backups_path

if TYPE_CHECKING:
    from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
    from astrbot.core.updator import AstrBotUpdator


class AutoUpdateManager:
    """自动更新管理器。

    在 AstrBot 启动时注册后台任务：
    - 定时检查新版本
    - 定时清理过期备份
    """

    def __init__(self, core_lifecycle: AstrBotCoreLifecycle) -> None:
        self.core_lifecycle = core_lifecycle
        self._check_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._last_check_time: float = 0.0
        self._new_version_available: str | None = None

    @property
    def config(self) -> dict:
        return self.core_lifecycle.astrbot_config.get("auto_update", {})

    @property
    def enabled(self) -> bool:
        return self.config.get("enabled", False)

    @property
    def check_interval(self) -> int:
        val = self.config.get("check_interval", 86400)
        try:
            val = int(val)
            return val if val > 0 else 86400
        except (TypeError, ValueError):
            return 86400

    @property
    def backup_retention_days(self) -> int:
        val = self.config.get("backup_retention_days", 14)
        try:
            val = int(val)
            return val if val >= 0 else 14
        except (TypeError, ValueError):
            return 14

    @property
    def notify_on_new_version(self) -> bool:
        return self.config.get("notify_on_new_version", True)

    async def start_background_tasks(self) -> None:
        """启动后台任务。"""
        # 版本检查任务
        if self._check_task is None or self._check_task.done():
            self._check_task = asyncio.create_task(self._version_check_loop())

        # 备份清理任务
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._backup_cleanup_loop())

        logger.info("AutoUpdateManager background tasks started.")

    async def stop_background_tasks(self) -> None:
        """停止后台任务。"""
        for task in (self._check_task, self._cleanup_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    # ---- 版本检查 ----

    async def _version_check_loop(self) -> None:
        """版本检查循环。按配置的间隔定时检查。"""
        # 首次启动先等 60 秒，让服务完全就绪
        await asyncio.sleep(60)

        while True:
            try:
                await self._do_version_check()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.warning(
                    "版本检查失败（不影响正常使用）。",
                    exc_info=True,
                )

            await asyncio.sleep(self.check_interval)

    async def _do_version_check(self) -> None:
        """执行一次版本检查。"""
        now = time.time()
        # 去重：5 分钟内不重复检查
        if now - self._last_check_time < 300:
            return
        self._last_check_time = now

        updator = getattr(self.core_lifecycle, "astrbot_updator", None)
        if not updator:
            return

        try:
            result = await updator.check_update(None, None, True)
        except Exception:
            return

        if result is not None:
            new_ver = result.version
            self._new_version_available = new_ver
            logger.info(f"发现新版本: {new_ver}（当前: {VERSION}）")

            if self.notify_on_new_version:
                await self._notify_admins_new_version(new_ver)

            # 如果开启了自动更新，触发更新
            if self.enabled:
                logger.info(f"自动更新已开启，将在 30 秒后开始更新到 {new_ver}...")
                await asyncio.sleep(30)
                await self._trigger_auto_update(new_ver)
        else:
            self._new_version_available = None

    async def _notify_admins_new_version(self, new_version: str) -> None:
        """通知管理员有新版本可用。

        通过已连接的平台向管理员发送消息。
        """
        platform_manager = getattr(self.core_lifecycle, "platform_manager", None)
        if not platform_manager:
            return

        admin_ids = self.core_lifecycle.astrbot_config.get("admins_id", [])
        message = (
            f"🔔 AstrBot 新版本可用\n"
            f"当前版本: {VERSION}\n"
            f"最新版本: {new_version}\n"
            f"请在 WebUI 中更新，或使用 /update now 指令。"
        )

        for platform in platform_manager.platform_insts.values():
            try:
                if hasattr(platform, "send_by_session"):
                    # 尝试向管理员发送通知
                    for admin_id in admin_ids:
                        try:
                            await platform.send_by_session(
                                session_id=admin_id,
                                message_chain=message,
                            )
                        except Exception:
                            pass  # 单个管理员通知失败不影响其他
            except Exception:
                pass

    async def _trigger_auto_update(self, target_version: str | None = None) -> None:
        """触发自动更新流程。

        创建备份 → 下载更新 → 应用更新 → 重启。
        如果更新过程中发生错误，自动回滚到备份。
        """
        from astrbot.core.backup.exporter import AstrBotExporter
        from astrbot.core.backup.importer import AstrBotImporter

        backup_path: str | None = None
        auto_backup = self.config.get("auto_backup_before_update", True)

        # 1. 更新前备份
        if auto_backup:
            try:
                logger.info("正在创建更新前备份...")
                kb_manager = getattr(self.core_lifecycle, "kb_manager", None)
                exporter = AstrBotExporter(
                    main_db=self.core_lifecycle.db,
                    kb_manager=kb_manager,
                )
                raw_backup_path = await exporter.export_all()
                # 重命名为含 "update_backup" 标记的文件名，以便清理逻辑正确识别
                backup_dir = os.path.dirname(raw_backup_path)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                backup_filename = (
                    f"astrbot_update_backup_v{VERSION}_{timestamp}.zip"
                )
                backup_path = os.path.join(backup_dir, backup_filename)
                os.rename(raw_backup_path, backup_path)
                logger.info(f"更新前备份已创建: {backup_path}")
            except Exception as backup_exc:
                logger.warning(f"创建备份失败（继续更新）: {backup_exc}")

        # 2. 下载并应用更新
        try:
            logger.info(f"自动更新触发，目标版本: {target_version or 'latest'}")
            updator: AstrBotUpdator = self.core_lifecycle.astrbot_updator
            await updator.update(
                reboot=True,
                latest=target_version is None,
                version=target_version,
            )
        except Exception as exc:
            logger.error(f"自动更新失败: {exc}", exc_info=True)

            # 3. 自动回滚
            if backup_path and os.path.exists(backup_path):
                try:
                    logger.info("正在从备份恢复...")
                    kb_manager = getattr(self.core_lifecycle, "kb_manager", None)
                    importer = AstrBotImporter(
                        main_db=self.core_lifecycle.db,
                        kb_manager=kb_manager,
                    )
                    result = await importer.import_all(
                        zip_path=backup_path,
                        mode="replace",
                    )
                    if result.success:
                        logger.info("已从备份恢复数据。")
                    else:
                        logger.error(f"从备份恢复失败: {'; '.join(result.errors)}")
                except Exception as rollback_exc:
                    logger.error(
                        f"自动回滚失败，请手动恢复备份: {backup_path}。"
                        f"错误: {rollback_exc}"
                    )
            raise

    # ---- 备份清理 ----

    async def _backup_cleanup_loop(self) -> None:
        """备份清理循环。每小时检查一次。"""
        await asyncio.sleep(120)  # 启动后等 2 分钟

        while True:
            try:
                await self._cleanup_old_backups()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.warning("备份清理失败。", exc_info=True)

            await asyncio.sleep(3600)  # 每小时

    async def _cleanup_old_backups(self) -> None:
        """清理超过保留期限的更新备份。"""
        backup_dir = get_astrbot_backups_path()
        if not os.path.isdir(backup_dir):
            return

        retention_seconds = self.backup_retention_days * 86400
        now = time.time()
        deleted_count = 0

        # 收集更新备份文件
        update_backups: list[tuple[str, float]] = []
        for filename in os.listdir(backup_dir):
            if not filename.endswith(".zip"):
                continue
            # 只清理更新前自动创建的备份
            if "update_backup" not in filename:
                continue
            file_path = os.path.join(backup_dir, filename)
            try:
                mtime = os.path.getmtime(file_path)
                update_backups.append((file_path, mtime))
            except OSError:
                pass

        if len(update_backups) <= 1:
            return  # 保留至少一个备份

        # 按时间排序（新的在前）
        update_backups.sort(key=lambda x: x[1], reverse=True)

        # 保留最近一个，其余过期的删除
        for file_path, mtime in update_backups[1:]:
            if now - mtime > retention_seconds:
                try:
                    os.remove(file_path)
                    deleted_count += 1
                    logger.info(f"已删除过期更新备份: {os.path.basename(file_path)}")
                except OSError as exc:
                    logger.warning(f"删除过期备份失败 {file_path}: {exc}")

        if deleted_count > 0:
            logger.info(f"备份清理完成，删除了 {deleted_count} 个过期备份。")

    # ---- 公共 API ----

    async def check_now(self) -> dict:
        """立即检查更新（供聊天指令调用）。

        Returns:
            dict: 包含 has_update, current_version, latest_version 等信息。
        """
        updator = getattr(self.core_lifecycle, "astrbot_updator", None)
        if not updator:
            return {
                "has_update": False,
                "current_version": VERSION,
                "error": "更新器不可用",
            }

        try:
            result = await updator.check_update(None, None, True)
        except Exception as exc:
            return {
                "has_update": False,
                "current_version": VERSION,
                "error": str(exc),
            }

        if result is not None:
            self._new_version_available = result.version
            return {
                "has_update": True,
                "current_version": VERSION,
                "latest_version": result.version,
                "published_at": result.published_at,
                "body": result.body,
            }

        return {
            "has_update": False,
            "current_version": VERSION,
            "latest_version": VERSION,
        }

    async def trigger_update(self, version: str | None = None) -> None:
        """触发更新流程。

        Args:
            version: 目标版本，None 表示最新版本。
        """
        await self._trigger_auto_update(version)

    def get_new_version_info(self) -> str | None:
        """获取已知的新版本号。"""
        return self._new_version_available
