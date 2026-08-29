import asyncio
import traceback
from asyncio import Queue
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar, cast

from astrbot import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.db.protocols import WebChatStorageStore
from astrbot.core.star.star import PluginRegistry
from astrbot.core.star.star_handler import EventType, HandlerRegistry
from astrbot.core.utils.error_redaction import redact_sensitive_text, safe_error
from astrbot.core.utils.metrics import MetricsSink
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.core.utils.webhook_utils import (
    configure_webhook_utils,
    ensure_platform_webhook_config,
)
from astrbot.core.webchat.queue_manager import WebChatQueueManager

from .astrbot_message import AstrBotMessage
from .catalog import PlatformCatalog
from .contracts.onebot import (
    OneBotActionUnavailable,
    OneBotActionValidationError,
    OneBotCapabilityUnavailable,
    PlatformCapabilityDescriptor,
    get_capability_descriptor,
)
from .discovery import discover_platform_adapter
from .message_session import MessageSession
from .platform import Platform, PlatformStatus
from .send_result import PlatformSendResult


@dataclass
class PlatformTasks:
    platform: Platform
    run: asyncio.Task
    wrapper: asyncio.Task


_T = TypeVar("_T")


class _PlatformConfigSaveSupersededError(RuntimeError):
    """Raised when a platform configuration migration loses a save race."""


class PlatformManager:
    def __init__(
        self,
        config: AstrBotConfig,
        event_queue: Queue,
        webchat_queue_manager: WebChatQueueManager,
        catalog: PlatformCatalog,
        handler_registry: HandlerRegistry,
        plugin_registry: PluginRegistry,
        metrics: MetricsSink,
    ) -> None:
        if handler_registry.plugins is not plugin_registry:
            raise ValueError("Handler and plugin registries must share one runtime")
        configure_webhook_utils(config)
        self._platform_insts: list[Platform] = []
        """加载的 Platform 的实例"""

        self._inst_map: dict[str, dict] = {}
        # Tasks are owned by an adapter instance, not its transport-facing client
        # ID. Different configured adapters can legitimately expose the same
        # client ID, especially while a platform is being reconfigured.
        self._platform_tasks: dict[int, PlatformTasks] = {}
        self._platform_limiters: dict[str, asyncio.Semaphore] = {}
        self._platform_limit_settings: dict[str, int] = {}
        # Serialize all replacement and shutdown transitions.
        self._platform_lifecycle_lock = asyncio.Lock()

        self.astrbot_config = config
        self.catalog = catalog
        self.handler_registry = handler_registry
        self.plugin_registry = plugin_registry
        self.metrics = metrics
        self.platforms_config = config["platform"]
        self.settings = config["platform_settings"]
        """NOTE: 这里是 default 的配置文件，以保证最大的兼容性；
        这个配置中的 unique_session 需要特殊处理，
        约定整个项目中对 unique_session 的引用都从 default 的配置中获取"""
        self.event_queue = event_queue
        self.webchat_queue_manager = webchat_queue_manager
        # Only the WebChat adapter receives persisted attachment/history access.
        # PlatformManager must not depend on the concrete database implementation.
        self.database: WebChatStorageStore | None = None
        self.preferences: SharedPreferences | None = None
        self.typing_signal: Callable[[str, int], None] | None = None

    def _create_platform_instance(
        self,
        adapter_cls: type[Platform],
        platform_config: dict,
    ) -> Platform:
        """Instantiate an adapter with the runtime capabilities it declares."""
        if getattr(adapter_cls, "requires_webchat_queue_manager", False):
            webchat_adapter_factory = cast(
                Callable[[dict, dict, Queue, WebChatQueueManager], Platform],
                adapter_cls,
            )
            return webchat_adapter_factory(
                platform_config,
                self.settings,
                self.event_queue,
                self.webchat_queue_manager,
            )
        adapter_factory = cast(Callable[[dict, dict, Queue], Platform], adapter_cls)
        adapter = adapter_factory(platform_config, self.settings, self.event_queue)
        typing_signal = getattr(self, "typing_signal", None)
        if typing_signal is not None:
            adapter.typing_signal = typing_signal
        return adapter

    def _is_valid_platform_id(self, platform_id: str | None) -> bool:
        if not platform_id:
            return False
        return ":" not in platform_id and "!" not in platform_id

    def _sanitize_platform_id(self, platform_id: str | None) -> tuple[str | None, bool]:
        if not platform_id:
            return platform_id, False
        sanitized = platform_id.replace(":", "_").replace("!", "_")
        return sanitized, sanitized != platform_id

    def _configure_platform_instance(self, inst: Platform) -> None:
        """Inject manager-owned runtime services into an adapter instance."""

        inst.database = getattr(self, "database", None)
        inst.runtime_config = self.astrbot_config
        inst.preferences = getattr(self, "preferences", None)
        if isinstance(inst, Platform):
            inst.bind_metrics(self.metrics)
            inst.bind_runtime_registries(
                self.handler_registry,
                self.plugin_registry,
            )

    def _start_platform_task(self, task_name: str, inst: Platform) -> None:
        run_task = asyncio.create_task(inst.run(), name=task_name)
        wrapper_task = asyncio.create_task(
            self._task_wrapper(run_task, platform=inst),
            name=f"{task_name}_wrapper",
        )
        self._platform_tasks[id(inst)] = PlatformTasks(
            platform=inst,
            run=run_task,
            wrapper=wrapper_task,
        )

    async def _stop_platform_task(self, inst: Platform) -> None:
        tasks = self._platform_tasks.pop(id(inst), None)
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
                        "终止平台适配器失败: client_id=%s, error=%s",
                        client_id,
                        safe_error("", e),
                    )
                    logger.error(redact_sensitive_text(traceback.format_exc()))
        finally:
            try:
                await inst._cancel_background_tasks()
            finally:
                try:
                    await self._stop_platform_task(inst)
                finally:
                    # The run task may register its own final cleanup work when
                    # cancellation reaches the adapter. Sweep once more only
                    # after it has fully stopped.
                    await inst._cancel_background_tasks()

    def set_platform_concurrency_limit(
        self, platform_id: str, limit: int | None
    ) -> None:
        if limit is None:
            self._platform_limiters.pop(platform_id, None)
            self._platform_limit_settings.pop(platform_id, None)
            return
        if limit < 1:
            raise ValueError("platform concurrency limit must be >= 1")
        self._platform_limiters[platform_id] = asyncio.Semaphore(limit)
        self._platform_limit_settings[platform_id] = limit

    def get_platform_concurrency_limit(self, platform_id: str) -> int | None:
        return self._platform_limit_settings.get(platform_id)

    async def run_with_platform_limit(
        self,
        platform_id: str,
        operation: Callable[[], Awaitable[_T]],
    ) -> _T:
        limiter = self._platform_limiters.get(platform_id)
        if limiter is None:
            return await operation()
        async with limiter:
            return await operation()

    async def initialize(self) -> None:
        """初始化所有平台适配器"""
        for platform in self.platforms_config:
            if ensure_platform_webhook_config(platform):
                committed = await self.astrbot_config.save_config_async()
                if not committed:
                    raise _PlatformConfigSaveSupersededError(
                        "Platform webhook configuration save was superseded by "
                        "a newer revision."
                    )
            try:
                await self.load_platform(platform)
            except asyncio.CancelledError:
                raise
            except _PlatformConfigSaveSupersededError:
                raise
            except Exception as e:
                logger.error(
                    "初始化 %s 平台适配器失败: %s",
                    redact_sensitive_text(str(platform)),
                    safe_error("", e),
                )

        # 网页聊天 is built-in but follows the same lazy discovery boundary.
        webchat_cls = discover_platform_adapter("webchat", self.catalog)
        if webchat_cls is None:
            raise RuntimeError("Built-in webchat platform adapter was not registered")
        webchat_inst = self._create_platform_instance(webchat_cls, {})
        self._configure_platform_instance(webchat_inst)
        self._platform_insts.append(webchat_inst)
        self._start_platform_task("webchat", webchat_inst)

    async def load_platform(self, platform_config: dict) -> None:
        """实例化一个平台"""
        async with self._platform_lifecycle_lock:
            await self._load_platform_unlocked(platform_config)

    async def _prepare_platform_id_for_loading(self, platform_config: dict) -> bool:
        """Persist a legacy platform-ID normalization before adapter lifecycle work."""
        platform_id = platform_config.get("id")
        if self._is_valid_platform_id(platform_id):
            return True

        sanitized_id, changed = self._sanitize_platform_id(platform_id)
        if not sanitized_id or not changed:
            logger.error(
                "平台 ID %r 不能为空，跳过加载该平台适配器。",
                platform_id,
            )
            return False

        logger.warning(
            "平台 ID %r 包含非法字符 ':' 或 '!'，已替换为 %r。",
            platform_id,
            sanitized_id,
        )
        platform_config["id"] = sanitized_id
        configured_platform: dict | None = None
        for candidate in self.platforms_config:
            if candidate is platform_config:
                configured_platform = candidate
                break
            if candidate.get("id") == platform_id:
                candidate["id"] = sanitized_id
                configured_platform = candidate
                break

        committed = await self.astrbot_config.save_config_async()
        if not committed:
            if platform_config.get("id") == sanitized_id:
                platform_config["id"] = platform_id
            if (
                configured_platform is not None
                and configured_platform is not platform_config
                and configured_platform.get("id") == sanitized_id
            ):
                configured_platform["id"] = platform_id
            raise _PlatformConfigSaveSupersededError(
                "Platform ID migration save was superseded by a newer revision."
            )
        return True

    async def _load_platform_unlocked(self, platform_config: dict) -> None:
        # 动态导入
        cls_type: type | None = None
        try:
            if not platform_config["enable"]:
                return
            if not await self._prepare_platform_id_for_loading(platform_config):
                return

            logger.info(
                "Loading IM platform adapter %s(%s) ...",
                platform_config["type"],
                platform_config["id"],
            )
            cls_type = discover_platform_adapter(
                platform_config["type"],
                self.catalog,
            )
        except asyncio.CancelledError:
            raise
        except _PlatformConfigSaveSupersededError:
            raise
        except (ImportError, ModuleNotFoundError) as e:
            logger.error(
                "加载平台适配器 %s 失败，原因：%s。请检查依赖库是否安装。提示：可以在 管理面板->平台日志->安装Pip库 中安装依赖库。",
                platform_config["type"],
                safe_error("", e),
            )
        except Exception as e:
            logger.error(
                "加载平台适配器 %s 失败，原因：%s。",
                platform_config["type"],
                safe_error("", e),
            )

        if cls_type is None:
            logger.error(
                f"Platform adapter not found: {platform_config['type']}({platform_config['id']}).",
            )
            return
        inst = self._create_platform_instance(cls_type, platform_config)
        self._configure_platform_instance(inst)
        self._inst_map[platform_config["id"]] = {
            "inst": inst,
            "client_id": inst.client_self_id,
        }
        self._platform_insts.append(inst)
        self._start_platform_task(
            f"platform_{platform_config['type']}_{platform_config['id']}",
            inst,
        )
        handlers = self.handler_registry.get_handlers_by_event_type(
            EventType.OnPlatformLoadedEvent,
        )
        for handler in handlers:
            try:
                plugin = self.plugin_registry.get_by_module(
                    handler.handler_module_path,
                )
                logger.info(
                    "hook(on_platform_loaded) -> %s - %s",
                    plugin.name if plugin is not None else handler.handler_module_path,
                    handler.handler_name,
                )
                await handler.handler()
            except Exception:
                logger.error(redact_sensitive_text(traceback.format_exc()))

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
            raise
        except Exception as e:
            error_msg = safe_error("", e)
            tb_str = redact_sensitive_text(traceback.format_exc())
            logger.error("------- 任务 %s 发生错误: %s", task.get_name(), error_msg)
            for line in tb_str.split("\n"):
                logger.error(f"|    {line}")
            logger.error("-------")

            # 记录错误到平台实例
            if platform:
                platform.record_error(error_msg, tb_str)

    async def reload(self, platform_config: dict) -> None:
        async with self._platform_lifecycle_lock:
            original_platform_id = platform_config["id"]
            if platform_config[
                "enable"
            ] and not await self._prepare_platform_id_for_loading(platform_config):
                return
            await self._terminate_platform_unlocked(original_platform_id)
            if platform_config["enable"]:
                await self._load_platform_unlocked(platform_config)

            # 和配置文件保持同步
            config_ids = [provider["id"] for provider in self.platforms_config]
            for key in list(self._inst_map.keys()):
                if key not in config_ids:
                    await self._terminate_platform_unlocked(key)

    async def terminate_platform(self, platform_id: str) -> None:
        async with self._platform_lifecycle_lock:
            await self._terminate_platform_unlocked(platform_id)

    async def _terminate_platform_unlocked(self, platform_id: str) -> None:
        self._platform_limiters.pop(platform_id, None)
        self._platform_limit_settings.pop(platform_id, None)
        if platform_id in self._inst_map:
            logger.info(f"正在尝试终止 {platform_id} 平台适配器 ...")

            # client_id = self._inst_map.pop(platform_id, None)
            info = self._inst_map.pop(platform_id)
            inst: Platform = info["inst"]
            if not any(candidate is inst for candidate in self._platform_insts):
                logger.warning(f"可能未完全移除 {platform_id} 平台适配器")
            else:
                self._platform_insts = [
                    candidate
                    for candidate in self._platform_insts
                    if candidate is not inst
                ]

            await self._terminate_inst_and_tasks(inst)

    async def terminate(self) -> None:
        async with self._platform_lifecycle_lock:
            terminated_instances: set[int] = set()
            for platform_id in list(self._inst_map.keys()):
                info = self._inst_map.get(platform_id)
                if info:
                    terminated_instances.add(id(info["inst"]))
                await self._terminate_platform_unlocked(platform_id)

            for inst in list(self._platform_insts):
                if id(inst) in terminated_instances:
                    continue
                await self._terminate_inst_and_tasks(inst)

            self._platform_insts.clear()
            self._inst_map.clear()
            self._platform_tasks.clear()
            self._platform_limiters.clear()
            self._platform_limit_settings.clear()

    def get_platform_count(self) -> int:
        return len(self._platform_insts)

    def _find_inst_by_id(self, platform_id: str) -> Platform | None:
        info = self._inst_map.get(platform_id)
        if info:
            inst = info.get("inst")
            if isinstance(inst, Platform):
                return inst

        for inst in self._platform_insts:
            if inst.meta().id == platform_id or inst.config.get("id") == platform_id:
                return inst
        return None

    def _find_inst_by_name(self, platform_name: str) -> Platform | None:
        for inst in self._platform_insts:
            if inst.meta().name == platform_name:
                return inst
        return None

    def find_inst_by_webhook_uuid(self, webhook_uuid: str) -> Platform | None:
        for inst in self._platform_insts:
            if (
                inst.config.get("webhook_uuid") == webhook_uuid
                and inst.unified_webhook()
            ):
                return inst
        return None

    async def send_to_session(
        self,
        session: MessageSession,
        message_chain,
    ) -> PlatformSendResult:
        inst = self._find_inst_by_id(session.platform_id)
        if inst is None:
            return PlatformSendResult(
                platform_id=session.platform_id,
                success=False,
                target=session.session_id,
                message_count=len(message_chain.chain),
                error_message="platform adapter not found",
            )
        try:
            result = await self.run_with_platform_limit(
                session.platform_id,
                lambda: inst.send_by_session(session, message_chain),
            )
        except Exception as exc:
            logger.warning(
                "Failed to send message through platform %s: %s",
                session.platform_id,
                safe_error("", exc),
            )
            return PlatformSendResult(
                platform_id=session.platform_id,
                success=False,
                target=session.session_id,
                message_count=len(message_chain.chain),
                error_message="message delivery failed",
                status="unknown",
            )
        if isinstance(result, PlatformSendResult):
            return result
        return PlatformSendResult(
            platform_id=session.platform_id,
            success=False,
            target=session.session_id,
            message_count=len(message_chain.chain),
            error_message="platform did not return an acceptance receipt",
            status="unknown",
        )

    async def invoke_action(
        self,
        platform_id: str,
        action_name: str,
        **kwargs,
    ) -> dict[str, object]:
        inst = self._find_inst_by_id(platform_id)
        if inst is None:
            raise LookupError(f"Platform adapter not found: {platform_id}")
        if not inst.supports_action(action_name):
            raise NotImplementedError(
                f"Platform {platform_id} does not support action `{action_name}`"
            )

        method = getattr(inst, action_name, None)
        if method is None or not callable(method):
            raise NotImplementedError(
                f"Platform {platform_id} action handler missing: `{action_name}`"
            )
        action_handler = cast(Callable[..., Awaitable[dict[str, object]]], method)
        return await self.run_with_platform_limit(
            platform_id,
            lambda: action_handler(**kwargs),
        )

    async def invoke_capability(
        self,
        platform_id: str,
        capability_name: str,
        action_name: str,
        **kwargs,
    ) -> object:
        """Invoke an explicitly registered, versioned adapter capability."""
        descriptor: PlatformCapabilityDescriptor | None = get_capability_descriptor(
            capability_name
        )
        if descriptor is None:
            raise OneBotCapabilityUnavailable(
                f"Capability is unavailable: {capability_name}",
                action=action_name,
            )
        action = descriptor.action(action_name)
        if action is None:
            raise OneBotActionUnavailable(
                f"Action is unavailable: {capability_name}.{action_name}",
                action=action_name,
            )
        inst = self._find_inst_by_id(platform_id)
        if inst is None:
            raise OneBotCapabilityUnavailable(
                "Platform adapter is unavailable",
                action=action_name,
            )
        if isinstance(inst, Platform):
            declared = next(
                (item for item in inst.capabilities() if item.name == capability_name),
                None,
            )
            if declared is None or declared.action(action_name) is None:
                raise OneBotCapabilityUnavailable(
                    f"Platform does not provide capability {capability_name}",
                    action=action_name,
                )
        try:
            validated_kwargs = action.input_model.validate(kwargs)
        except OneBotActionValidationError as exc:
            raise OneBotActionValidationError(exc.message, action=action_name) from exc
        provider = getattr(inst, "invoke_capability", None)
        if not callable(provider):
            raise OneBotCapabilityUnavailable(
                f"Platform does not provide capability {capability_name}",
                action=action_name,
            )
        capability_provider = cast(Callable[..., Awaitable[object]], provider)
        return await self.run_with_platform_limit(
            platform_id,
            lambda: capability_provider(
                capability_name, action_name, **validated_kwargs
            ),
        )

    def get_platform_capabilities(
        self, platform_id: str
    ) -> tuple[PlatformCapabilityDescriptor, ...]:
        """Return a read-only capability snapshot for one loaded adapter."""
        inst = self._find_inst_by_id(platform_id)
        if inst is None:
            return ()
        return inst.capabilities()

    async def refresh_registered_commands(self) -> None:
        """Refresh native commands on every loaded platform adapter."""

        async def refresh(inst: Platform) -> None:
            try:
                await inst.refresh_registered_commands()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Failed to refresh native commands for platform %s: %s",
                    inst.meta().name,
                    safe_error("", exc),
                )

        await asyncio.gather(*(refresh(inst) for inst in self._platform_insts))

    def create_event(
        self,
        platform: str,
        event_message: object,
        *,
        is_wake: bool = True,
    ) -> None:
        inst = self._find_inst_by_id(platform)
        if inst is None:
            inst = self._find_inst_by_name(platform)
        if inst is None:
            raise ValueError(f"Platform not found: {platform}")

        event = inst.create_event(cast(AstrBotMessage, event_message))
        event.set_extra("adapter_preconfigured", bool(is_wake))
        inst.commit_event(event)

    def get_all_stats(self) -> dict:
        """获取所有平台的统计信息

        Returns:
            包含所有平台统计信息的字典
        """
        stats_list = []
        total_errors = 0
        running_count = 0
        error_count = 0

        for inst in self._platform_insts:
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
                logger.warning("获取平台统计信息失败: %s", safe_error("", e))
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
