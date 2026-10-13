import asyncio
import traceback
from asyncio import Queue
from dataclasses import dataclass

from astrbot.core import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.star_handler import EventType, star_handlers_registry, star_map
from astrbot.core.utils.webhook_utils import ensure_platform_webhook_config

from .platform import Platform, PlatformStatus
from .register import platform_cls_map
from .sources.webchat.webchat_adapter import WebChatAdapter


@dataclass
class PlatformTasks:
    run: asyncio.Task
    wrapper: asyncio.Task


class PlatformManager:
    def __init__(self, config: AstrBotConfig, event_queue: Queue) -> None:
        self.platform_insts: list[Platform] = []
        """Loaded Platform instances."""

        self._inst_map: dict[str, dict] = {}
        self._platform_tasks: dict[str, PlatformTasks] = {}

        self.astrbot_config = config
        self.platforms_config = config["platform"]
        self.settings = config["platform_settings"]
        """The default configuration is used here for maximum compatibility.

        The unique_session setting requires special handling. All references to
        unique_session in the project must use the default configuration.
        """
        self.event_queue = event_queue

    def _is_valid_platform_id(self, platform_id: str | None) -> bool:
        if not platform_id:
            return False
        return ":" not in platform_id and "!" not in platform_id

    def _sanitize_platform_id(self, platform_id: str | None) -> tuple[str | None, bool]:
        if not platform_id:
            return platform_id, False
        sanitized = platform_id.replace(":", "_").replace("!", "_")
        return sanitized, sanitized != platform_id

    def _start_platform_task(self, task_name: str, inst: Platform) -> None:
        run_task = asyncio.create_task(inst.run(), name=task_name)
        wrapper_task = asyncio.create_task(
            self._task_wrapper(run_task, platform=inst),
            name=f"{task_name}_wrapper",
        )
        self._platform_tasks[inst.client_self_id] = PlatformTasks(
            run=run_task,
            wrapper=wrapper_task,
        )

    async def _stop_platform_task(self, client_id: str) -> None:
        tasks = self._platform_tasks.pop(client_id, None)
        if not tasks:
            return
        for task in (tasks.run, tasks.wrapper):
            if not task.done():
                task.cancel()
        await asyncio.gather(tasks.run, tasks.wrapper, return_exceptions=True)

    async def _terminate_inst_and_tasks(self, inst: Platform) -> None:
        client_id = inst.client_self_id
        try:
            if getattr(inst, "terminate", None):
                try:
                    await inst.terminate()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(
                        "Failed to terminate platform adapter: client_id=%s, error=%s",
                        client_id,
                        e,
                    )
                    logger.error(traceback.format_exc())
        finally:
            await self._stop_platform_task(client_id)

    async def initialize(self) -> None:
        """初始化所有平台适配器"""
        for platform in self.platforms_config:
            try:
                if ensure_platform_webhook_config(platform):
                    self.astrbot_config.save_config()
                await self.load_platform(platform)
            except Exception as e:
                logger.error(f"Failed to initialize platform adapter {platform}: {e}")

        # 网页聊天
        webchat_inst = WebChatAdapter({}, self.settings, self.event_queue)
        self.platform_insts.append(webchat_inst)
        self._start_platform_task("webchat", webchat_inst)

    async def load_platform(self, platform_config: dict) -> None:
        """实例化一个平台"""
        # 动态导入
        try:
            if not platform_config["enable"]:
                return
            platform_id = platform_config.get("id")
            if not self._is_valid_platform_id(platform_id):
                sanitized_id, changed = self._sanitize_platform_id(platform_id)
                if sanitized_id and changed:
                    logger.warning(
                        "Platform ID %r contains invalid ':' or '!' characters and "
                        "was changed to %r.",
                        platform_id,
                        sanitized_id,
                    )
                    platform_config["id"] = sanitized_id
                    self.astrbot_config.save_config()
                else:
                    logger.error(
                        f"Platform ID {platform_id!r} cannot be empty; skipping "
                        "the platform adapter.",
                    )
                    return

            logger.info(
                "Loading IM platform adapter %s(%s) ...",
                platform_config["type"],
                platform_config["id"],
            )
            match platform_config["type"]:
                case "aiocqhttp":
                    from .sources.aiocqhttp.aiocqhttp_platform_adapter import (
                        AiocqhttpAdapter,  # noqa: F401
                    )
                case "qq_official":
                    from .sources.qqofficial.qqofficial_platform_adapter import (
                        QQOfficialPlatformAdapter,  # noqa: F401
                    )
                case "qq_official_webhook":
                    from .sources.qqofficial_webhook.qo_webhook_adapter import (
                        QQOfficialWebhookPlatformAdapter,  # noqa: F401
                    )
                case "lark":
                    from .sources.lark.lark_adapter import (
                        LarkPlatformAdapter,  # noqa: F401
                    )
                case "dingtalk":
                    from .sources.dingtalk.dingtalk_adapter import (
                        DingtalkPlatformAdapter,  # noqa: F401
                    )
                case "telegram":
                    from .sources.telegram.tg_adapter import (
                        TelegramPlatformAdapter,  # noqa: F401
                    )
                case "wecom":
                    from .sources.wecom.wecom_adapter import (
                        WecomPlatformAdapter,  # noqa: F401
                    )
                case "wecom_ai_bot":
                    from .sources.wecom_ai_bot.wecomai_adapter import (
                        WecomAIBotAdapter,  # noqa: F401
                    )
                case "weixin_official_account":
                    from .sources.weixin_official_account.weixin_offacc_adapter import (
                        WeixinOfficialAccountPlatformAdapter,  # noqa: F401
                    )
                case "discord":
                    from .sources.discord.discord_platform_adapter import (
                        DiscordPlatformAdapter,  # noqa: F401
                    )
                case "misskey":
                    from .sources.misskey.misskey_adapter import (
                        MisskeyPlatformAdapter,  # noqa: F401
                    )
                case "weixin_oc":
                    from .sources.weixin_oc.weixin_oc_adapter import (
                        WeixinOCAdapter,  # noqa: F401
                    )
                case "slack":
                    from .sources.slack.slack_adapter import SlackAdapter  # noqa: F401
                case "satori":
                    from .sources.satori.satori_adapter import (
                        SatoriPlatformAdapter,  # noqa: F401
                    )
                case "line":
                    from .sources.line.line_adapter import (
                        LinePlatformAdapter,  # noqa: F401
                    )
                case "kook":
                    from .sources.kook.kook_adapter import (
                        KookPlatformAdapter,  # noqa: F401
                    )
                case "mattermost":
                    from .sources.mattermost.mattermost_adapter import (
                        MattermostPlatformAdapter,  # noqa: F401
                    )
        except (ImportError, ModuleNotFoundError) as e:
            logger.error(
                f"Failed to load platform adapter {platform_config['type']}: {e}. "
                "Check whether its dependencies are installed. You can install "
                "them from Dashboard -> Logs -> Install Pip Package.",
            )
        except Exception as e:
            logger.error(
                f"Failed to load platform adapter {platform_config['type']}: {e}."
            )

        if platform_config["type"] not in platform_cls_map:
            logger.error(
                f"Platform adapter not found: {platform_config['type']}({platform_config['id']}).",
            )
            return
        cls_type = platform_cls_map[platform_config["type"]]
        inst: Platform = cls_type(platform_config, self.settings, self.event_queue)
        self._inst_map[platform_config["id"]] = {
            "inst": inst,
            "client_id": inst.client_self_id,
        }
        self.platform_insts.append(inst)
        self._start_platform_task(
            f"platform_{platform_config['type']}_{platform_config['id']}",
            inst,
        )
        handlers = star_handlers_registry.get_handlers_by_event_type(
            EventType.OnPlatformLoadedEvent,
        )
        for handler in handlers:
            try:
                logger.info(
                    f"hook(on_platform_loaded) -> {star_map[handler.handler_module_path].name} - {handler.handler_name}",
                )
                await handler.handler()
            except Exception:
                logger.error(traceback.format_exc())

    async def _task_wrapper(
        self, task: asyncio.Task, platform: Platform | None = None
    ) -> None:
        # 设置平台状态为运行中
        if platform:
            platform.status = PlatformStatus.RUNNING

        try:
            await task
        except asyncio.CancelledError:
            if platform:
                platform.status = PlatformStatus.STOPPED
        except Exception as e:
            error_msg = str(e)
            tb_str = traceback.format_exc()
            logger.error(f"------- Task {task.get_name()} failed: {e}")
            for line in tb_str.split("\n"):
                logger.error(f"|    {line}")
            logger.error("-------")

            # 记录错误到平台实例
            if platform:
                platform.record_error(error_msg, tb_str)

    async def reload(self, platform_config: dict) -> None:
        await self.terminate_platform(platform_config["id"])
        if platform_config["enable"]:
            await self.load_platform(platform_config)

        # 和配置文件保持同步
        config_ids = [provider["id"] for provider in self.platforms_config]
        for key in list(self._inst_map.keys()):
            if key not in config_ids:
                await self.terminate_platform(key)

    async def terminate_platform(self, platform_id: str) -> None:
        if platform_id in self._inst_map:
            logger.info(f"Attempting to terminate platform adapter {platform_id} ...")

            # client_id = self._inst_map.pop(platform_id, None)
            info = self._inst_map.pop(platform_id)
            client_id = info["client_id"]
            inst: Platform = info["inst"]
            try:
                self.platform_insts.remove(
                    next(
                        inst
                        for inst in self.platform_insts
                        if inst.client_self_id == client_id
                    ),
                )
            except Exception:
                logger.warning(
                    f"Platform adapter {platform_id} may not have been fully removed."
                )

            await self._terminate_inst_and_tasks(inst)

    async def terminate(self) -> None:
        terminated_client_ids: set[str] = set()
        for platform_id in list(self._inst_map.keys()):
            info = self._inst_map.get(platform_id)
            if info:
                terminated_client_ids.add(info["client_id"])
            await self.terminate_platform(platform_id)

        for inst in list(self.platform_insts):
            client_id = inst.client_self_id
            if client_id in terminated_client_ids:
                continue
            await self._terminate_inst_and_tasks(inst)

        self.platform_insts.clear()
        self._inst_map.clear()
        self._platform_tasks.clear()

    def get_insts(self):
        return self.platform_insts

    def get_all_stats(self) -> dict:
        """获取所有平台的统计信息

        Returns:
            包含所有平台统计信息的字典
        """
        stats_list = []
        total_errors = 0
        running_count = 0
        error_count = 0

        for inst in self.platform_insts:
            try:
                stat = inst.get_stats()
                stats_list.append(stat)
                total_errors += stat.get("error_count", 0)
                if stat.get("status") == PlatformStatus.RUNNING.value:
                    running_count += 1
                elif stat.get("status") == PlatformStatus.ERROR.value:
                    error_count += 1
            except Exception as e:
                # 如果获取统计信息失败，记录基本信息
                logger.warning(f"Failed to get platform statistics: {e}")
                stats_list.append(
                    {
                        "id": getattr(inst, "config", {}).get("id", "unknown"),
                        "type": "unknown",
                        "status": "unknown",
                        "error_count": 0,
                        "last_error": None,
                    }
                )

        return {
            "platforms": stats_list,
            "summary": {
                "total": len(stats_list),
                "running": running_count,
                "error": error_count,
                "total_errors": total_errors,
            },
        }
