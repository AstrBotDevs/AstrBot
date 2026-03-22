# AstrBot SDK 接入实施计划

> 本文档基于用户 `whatevertogo` 的分析文档，补充具体实施细节。

## 一、架构验证结果

经代码审查确认：

| 组件 | 路径 | 状态 |
|------|------|------|
| Core Context | `astrbot/core/star/context.py` | ✅ 包含所有核心能力方法 |
| CapabilityRouter | `src-new/astrbot_sdk/runtime/capability_router.py` | ✅ 已实现内置能力注册 |
| StarHandlerMetadata | `astrbot/core/star/star_handler.py` | ✅ 定义清晰，可扩展 |
| HandlerDescriptor | `src-new/astrbot_sdk/protocol/descriptors.py` | ✅ Pydantic 模型，类型安全 |
| SupervisorRuntime | `src-new/astrbot_sdk/runtime/bootstrap.py` | ✅ 已实现完整生命周期 |
| CoreLifecycle | `astrbot/core/core_lifecycle.py` | ✅ 接入点明确 |

---

## 二、实施阶段

### Phase 1: 基础桥接层 (预计 2-3 天)

#### 1.1 创建目录结构

```
astrbot/core/sdk_bridge/
├── __init__.py
├── capability_bridge.py    # CoreCapabilityBridge
├── supervisor_bridge.py    # SdkPluginBridge
├── event_bridge.py         # 事件转换
├── handler_bridge.py       # Handler 注册桥接
└── transport_adapter.py    # Transport 适配
```

#### 1.2 实现 `capability_bridge.py`

```python
"""CoreCapabilityBridge: 把 astrbot.core.Context 能力映射到 CapabilityRouter。"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from astrbot.core.star.context import Context as CoreContext
    from astrbot_sdk.runtime.capability_router import CapabilityRouter

logger = logging.getLogger("astrbot.sdk_bridge")


class CoreCapabilityBridge:
    """把 astrbot.core.Context 的真实实现注入进 SDK CapabilityRouter。

    SupervisorRuntime 初始化后，Core 侧的 Peer 调用此 Bridge 来响应插件发来的能力请求。
    """

    def __init__(self, core_context: CoreContext, router: CapabilityRouter) -> None:
        self.ctx = core_context
        self.router = router
        self._wire()

    def _wire(self) -> None:
        """注册所有能力处理器到 router。"""
        # 替换 router 的内置 echo 实现为真实实现
        self._wire_llm()
        self._wire_db()
        self._wire_platform()
        self._wire_memory()
        self._wire_metadata()
        logger.info("SDK CapabilityBridge 已连接")

    def _wire_llm(self) -> None:
        """连接 LLM 能力。"""
        async def llm_chat(request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
            # 从 payload 提取参数
            prompt = payload.get("prompt", "")
            provider_id = payload.get("provider_id")
            # 调用 core 的 llm_generate
            if provider_id:
                resp = await self.ctx.llm_generate(
                    chat_provider_id=provider_id,
                    prompt=prompt,
                    # ... 其他参数
                )
            else:
                # 使用默认 provider
                prov = self.ctx.get_using_provider()
                if prov:
                    resp = await self.ctx.llm_generate(
                        chat_provider_id=prov.meta().id,
                        prompt=prompt,
                    )
                else:
                    return {"text": f"Echo (no provider): {prompt}"}
            return {"text": resp.completion_text or ""}

        # 注册到 router (覆盖默认 echo 实现)
        self.router.unregister("llm.chat")
        self.router.register(
            self.router._registrations["llm.chat"].descriptor,  # 复用 descriptor
            call_handler=llm_chat,
        )

    def _wire_db(self) -> None:
        """连接数据库能力。"""
        async def db_get(request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
            key = str(payload.get("key", ""))
            # 使用 core 的数据库
            db = self.ctx.get_db()
            value = await db.get(key)
            return {"value": value}

        async def db_set(request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
            key = str(payload.get("key", ""))
            value = payload.get("value")
            db = self.ctx.get_db()
            await db.set(key, value)
            return {}

        # 覆盖注册
        self.router.unregister("db.get")
        self.router.unregister("db.set")
        # ... 类似注册其他 db 方法

    def _wire_platform(self) -> None:
        """连接平台消息发送能力。"""
        async def platform_send(request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
            from astrbot.core.platform.astr_message_event import MessageSesion
            from astrbot.core.message.message_event_result import MessageChain

            session_str = payload.get("session", "")
            text = payload.get("text", "")

            # 构建 MessageChain
            chain = MessageChain().message(text)

            # 调用 core 的 send_message
            success = await self.ctx.send_message(session_str, chain)
            return {"message_id": f"msg_{request_id}", "success": success}

        self.router.unregister("platform.send")
        self.router.register(
            self.router._registrations["platform.send"].descriptor,
            call_handler=platform_send,
        )

    def _wire_memory(self) -> None:
        """连接记忆/会话管理能力。"""
        async def memory_save(request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
            # 使用 conversation_manager
            key = str(payload.get("key", ""))
            value = payload.get("value")
            # 实现具体逻辑
            return {}

        # 注册...

    def _wire_metadata(self) -> None:
        """连接插件元数据能力。"""
        # metadata.get_config -> context.get_config()
        # metadata.get_star -> star_registry 查询
        pass
```

#### 1.3 实现 `event_bridge.py`

```python
"""事件双向转换模块。"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


def astr_event_to_sdk_payload(event: AstrMessageEvent) -> dict[str, Any]:
    """把旧版 AstrMessageEvent 转成 SDK MessageEvent 的 to_payload() 格式。"""
    return {
        "text": event.message_str,
        "user_id": event.get_sender_id(),
        "group_id": event.get_group_id() if event.is_group_message() else None,
        "platform": event.get_platform_name(),
        "session_id": event.unified_msg_origin,
        "target": {
            "conversation_id": event.unified_msg_origin,
            "platform": event.get_platform_name(),
        },
        # 保留原始消息对象引用
        "_raw_message_obj": event.message_obj,
        "_raw_platform_meta": event.platform_meta,
        # 保留原始 event 引用，供后续处理
        "_core_event": event,
    }


def sdk_payload_to_event_context(payload: dict[str, Any]) -> dict[str, Any]:
    """从 SDK payload 提取事件上下文信息。"""
    return {
        "session": payload.get("session_id", ""),
        "user_id": payload.get("user_id"),
        "group_id": payload.get("group_id"),
        "platform": payload.get("platform"),
        "text": payload.get("text"),
    }
```

#### 1.4 实现 `handler_bridge.py`

```python
"""Handler 注册桥接：把 SDK HandlerDescriptor 转换为 StarHandlerMetadata。"""
from __future__ import annotations

import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from astrbot.core.star.filter import HandlerFilter
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata

if TYPE_CHECKING:
    from astrbot_sdk.protocol.descriptors import HandlerDescriptor
    from astrbot_sdk.runtime.bootstrap import WorkerSession

logger = logging.getLogger("astrbot.sdk_bridge")


# SDK 事件类型到 Core 事件类型的映射
TRIGGER_TO_EVENT_TYPE = {
    "message": EventType.AdapterMessageEvent,
    "command": EventType.AdapterMessageEvent,
    "event": EventType.AdapterMessageEvent,  # 需要根据具体 event_type 细分
    "schedule": EventType.OnAstrBotLoadedEvent,  # 定时任务特殊处理
}


@dataclass
class SdkHandlerWrapper:
    """包装 SDK handler 的调用闭包。"""
    session: WorkerSession
    handler_id: str

    async def __call__(self, *args, **kwargs) -> Any:
        """调用 SDK handler。"""
        # 从 args/kwargs 提取事件信息
        event = kwargs.get("event") or (args[0] if args else None)
        if event is None:
            raise ValueError("SDK handler 需要 event 参数")

        # 转换事件格式
        from .event_bridge import astr_event_to_sdk_payload
        payload = astr_event_to_sdk_payload(event)

        # 通过 session 调用远程 handler
        return await self.session.invoke_handler(self.handler_id, payload)


def handler_descriptor_to_metadata(
    descriptor: HandlerDescriptor,
    session: WorkerSession,
) -> StarHandlerMetadata:
    """把 SDK HandlerDescriptor 转换为 Core 的 StarHandlerMetadata。

    Args:
        descriptor: SDK handler 描述符
        session: Worker 会话，用于调用远程 handler

    Returns:
        StarHandlerMetadata: Core 兼容的 handler 元数据
    """
    # 创建包装器
    wrapper = SdkHandlerWrapper(session=session, handler_id=descriptor.id)

    # 确定 Core 事件类型
    trigger = descriptor.trigger
    event_type = TRIGGER_TO_EVENT_TYPE.get(trigger.type, EventType.AdapterMessageEvent)

    # 构建 event_filters
    event_filters = _build_event_filters(trigger)

    # 构建 extras_configs
    extras_configs = {
        "priority": descriptor.priority,
        "require_admin": descriptor.permissions.require_admin,
        "level": descriptor.permissions.level,
        "sdk_handler": True,  # 标记为 SDK handler
    }

    # 解析 handler_full_name
    parts = descriptor.id.rsplit(".", 1)
    if len(parts) == 2:
        module_path, handler_name = parts
    else:
        module_path = descriptor.id
        handler_name = descriptor.id

    return StarHandlerMetadata(
        event_type=event_type,
        handler_full_name=descriptor.id,
        handler_name=handler_name,
        handler_module_path=module_path,
        handler=wrapper,  # 使用包装器
        event_filters=event_filters,
        desc=getattr(trigger, "description", "") or "",
        extras_configs=extras_configs,
    )


def _build_event_filters(trigger: Any) -> list[HandlerFilter]:
    """根据 trigger 类型构建事件过滤器。"""
    from astrbot.core.star.filter.command import CommandFilter
    from astrbot.core.star.filter.regex import RegexFilter

    filters: list[HandlerFilter] = []

    if trigger.type == "command":
        # 命令触发器 -> CommandFilter
        filters.append(CommandFilter(
            command_name=trigger.command,
            # handler_md 需要稍后设置
        ))
    elif trigger.type == "message":
        # 消息触发器 -> RegexFilter
        if trigger.regex:
            filters.append(RegexFilter(regex=trigger.regex))
        # keywords 过滤需要在运行时检查

    return filters
```

#### 1.5 实现 `supervisor_bridge.py`

```python
"""SdkPluginBridge: 在 Core 侧管理 SupervisorRuntime。"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.star.context import Context as CoreContext

logger = logging.getLogger("astrbot.sdk_bridge")


class SdkPluginBridge:
    """在 Core 侧管理 SupervisorRuntime，并把 SDK handler 注册进 pipeline。"""

    def __init__(
        self,
        core_context: CoreContext,
        sdk_plugins_dir: Path,
    ) -> None:
        from astrbot_sdk.runtime.capability_router import CapabilityRouter
        from astrbot_sdk.runtime.bootstrap import SupervisorRuntime
        from astrbot_sdk.transport.stdio import StdioTransport

        self.ctx = core_context
        self.plugins_dir = sdk_plugins_dir

        # 创建 CapabilityRouter 和 Bridge
        self.capability_router = CapabilityRouter()
        self.capability_bridge = None  # 延迟初始化

        # 创建 Transport (使用 stdio 进行进程间通信)
        self.transport = StdioTransport()

        # 创建 Supervisor
        self.supervisor = SupervisorRuntime(
            transport=self.transport,
            plugins_dir=sdk_plugins_dir,
        )

        # 已注册的 handler 映射
        self._registered_handlers: dict[str, str] = {}  # handler_id -> plugin_name

    async def start(self) -> None:
        """启动 SDK 插件桥接。"""
        # 初始化 CapabilityBridge (替换默认 echo 实现)
        from .capability_bridge import CoreCapabilityBridge
        self.capability_bridge = CoreCapabilityBridge(self.ctx, self.capability_router)

        # 启动 Supervisor
        await self.supervisor.start()

        # 注册所有 handler 到 pipeline
        self._register_handlers_into_pipeline()

        logger.info(f"SDK 插件桥接已启动，共加载 {len(self._registered_handlers)} 个 handler")

    async def stop(self) -> None:
        """停止 SDK 插件桥接。"""
        await self.supervisor.stop()
        self._registered_handlers.clear()
        logger.info("SDK 插件桥接已停止")

    def _register_handlers_into_pipeline(self) -> None:
        """把 supervisor 聚合的所有 HandlerDescriptor 注册进 star_handlers_registry。"""
        from astrbot.core.star.star_handler import star_handlers_registry

        from .handler_bridge import handler_descriptor_to_metadata

        for handler_id, session in self.supervisor.handler_to_worker.items():
            # 获取 handler 的 descriptor
            descriptor = self._get_handler_descriptor(handler_id)
            if descriptor is None:
                logger.warning(f"无法获取 handler descriptor: {handler_id}")
                continue

            # 转换为 StarHandlerMetadata
            metadata = handler_descriptor_to_metadata(descriptor, session)

            # 注册到全局 registry
            star_handlers_registry.append(metadata)

            self._registered_handlers[handler_id] = descriptor.id.split(".")[0]
            logger.debug(f"注册 SDK handler: {handler_id}")

    def _get_handler_descriptor(self, handler_id: str):
        """从 supervisor 获取 handler descriptor。"""
        # 遍历所有 session 的 loaded_plugin 找到对应的 handler
        for plugin_id, session in self.supervisor._plugin_sessions.items():
            if session.loaded_plugin:
                for handler in session.loaded_plugin.handlers:
                    if handler.id == handler_id:
                        return handler
        return None
```

---

### Phase 2: 生命周期集成 (预计 1 天)

#### 2.1 修改 `core_lifecycle.py`

```python
# 在 CoreLifecycle 类中添加

def __init__(self, ...):
    # ... 现有代码 ...
    self.sdk_bridge: SdkPluginBridge | None = None

async def initialize(self) -> None:
    # ... 现有初始化代码 ...

    # 在 PluginManager 初始化后，初始化 SDK Bridge
    if self.astrbot_config.get("enable_sdk_plugins", False):
        from pathlib import Path
        from astrbot.core.sdk_bridge.supervisor_bridge import SdkPluginBridge

        sdk_plugins_dir = Path("data/sdk_plugins")
        sdk_plugins_dir.mkdir(parents=True, exist_ok=True)

        self.sdk_bridge = SdkPluginBridge(
            core_context=self.star_context,
            sdk_plugins_dir=sdk_plugins_dir,
        )

async def start(self) -> None:
    self._load()

    # 启动 SDK Bridge
    if self.sdk_bridge:
        await self.sdk_bridge.start()
        logger.info("SDK 插件桥接启动完成")

    # ... 现有代码 ...

async def stop(self) -> None:
    # 停止 SDK Bridge
    if self.sdk_bridge:
        await self.sdk_bridge.stop()

    # ... 现有代码 ...
```

---

### Phase 3: 测试与验证 (预计 2 天)

#### 3.1 单元测试

```python
# tests/test_sdk_bridge.py

import pytest
from astrbot.core.sdk_bridge.capability_bridge import CoreCapabilityBridge
from astrbot.core.sdk_bridge.event_bridge import astr_event_to_sdk_payload
from astrbot.core.sdk_bridge.handler_bridge import handler_descriptor_to_metadata


class TestEventBridge:
    def test_astr_event_to_sdk_payload(self, mock_event):
        payload = astr_event_to_sdk_payload(mock_event)
        assert payload["text"] == mock_event.message_str
        assert payload["user_id"] == mock_event.get_sender_id()
        assert "_core_event" in payload


class TestCapabilityBridge:
    async def test_llm_chat_capability(self, mock_core_context, mock_router):
        bridge = CoreCapabilityBridge(mock_core_context, mock_router)
        # 验证 llm.chat 已被覆盖
        assert "llm.chat" in mock_router._registrations


class TestHandlerBridge:
    def test_command_handler_conversion(self, mock_descriptor, mock_session):
        metadata = handler_descriptor_to_metadata(mock_descriptor, mock_session)
        assert metadata.handler_full_name == mock_descriptor.id
        assert len(metadata.event_filters) > 0
```

#### 3.2 集成测试

```python
# tests/integration/test_sdk_integration.py

import pytest
from pathlib import Path


@pytest.fixture
async def sdk_bridge(test_context, tmp_path):
    from astrbot.core.sdk_bridge.supervisor_bridge import SdkPluginBridge

    bridge = SdkPluginBridge(
        core_context=test_context,
        sdk_plugins_dir=tmp_path / "sdk_plugins",
    )
    await bridge.start()
    yield bridge
    await bridge.stop()


async def test_sdk_plugin_loading(sdk_bridge):
    """测试 SDK 插件能被正确加载。"""
    assert len(sdk_bridge._registered_handlers) > 0


async def test_sdk_handler_invocation(sdk_bridge, mock_event):
    """测试 SDK handler 能被正确调用。"""
    from astrbot.core.star.star_handler import star_handlers_registry

    # 查找 SDK 注册的 handler
    handlers = [h for h in star_handlers_registry if h.extras_configs.get("sdk_handler")]
    assert len(handlers) > 0

    # 调用 handler
    handler = handlers[0]
    result = await handler.handler(event=mock_event)
    # 验证结果
```

---

### Phase 4: 配置与文档 (预计 1 天)

#### 4.1 配置项

```yaml
# config/astrbot_config.yaml
sdk_plugins:
  enabled: true
  plugins_dir: "data/sdk_plugins"
  worker_timeout: 30  # Worker 启动超时（秒）
  max_restarts: 3     # Worker 崩溃后最大重启次数
```

#### 4.2 用户文档

创建 `docs/sdk_plugin_development.md`，说明：
- SDK 插件目录结构
- `plugin.yaml` 配置格式
- Handler 注册方式
- Capability 调用示例

---

## 三、能力映射详细表

| SDK Capability | Core Context 方法 | 实现状态 |
|----------------|------------------|----------|
| `llm.chat` | `context.llm_generate()` | 待实现 |
| `llm.chat_raw` | `context.llm_generate()` | 待实现 |
| `llm.stream_chat` | `context.llm_generate()` + stream | 待实现 |
| `db.get` | `context.get_db().get()` | 待实现 |
| `db.set` | `context.get_db().set()` | 待实现 |
| `db.delete` | `context.get_db().delete()` | 待实现 |
| `db.list` | `context.get_db().list()` | 待实现 |
| `platform.send` | `context.send_message()` | 待实现 |
| `platform.send_image` | `context.send_message()` + image | 待实现 |
| `platform.send_chain` | `context.send_message()` | 待实现 |
| `memory.search` | `context.conversation_manager.*` | 待实现 |
| `memory.save` | `context.conversation_manager.*` | 待实现 |
| `metadata.get_config` | `context.get_config()` | 待实现 |
| `metadata.get_star` | `star_registry` 查询 | 待实现 |

---

## 四、风险与缓解措施

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Worker 进程崩溃 | 插件不可用 | 实现自动重启机制 |
| 事件格式不兼容 | 功能异常 | 完善事件转换层 |
| 性能下降 | 用户体验变差 | 优化序列化，考虑共享内存 |
| 旧插件迁移成本 | 用户流失 | 保持 legacy 兼容层 |

---

## 五、后续优化

1. **Worker 崩溃重启**：在 `SupervisorRuntime` 中添加指数退避重启机制
2. **性能优化**：考虑使用共享内存传输大消息
3. **调试支持**：添加 SDK 插件调试模式
4. **热重载**：支持 SDK 插件热更新

---

## 六、实施检查清单

- [ ] 创建 `astrbot/core/sdk_bridge/` 目录
- [ ] 实现 `capability_bridge.py`
- [ ] 实现 `event_bridge.py`
- [ ] 实现 `handler_bridge.py`
- [ ] 实现 `supervisor_bridge.py`
- [ ] 修改 `core_lifecycle.py` 集成
- [ ] 添加配置项
- [ ] 编写单元测试
- [ ] 编写集成测试
- [ ] 编写用户文档
- [ ] 处理 `legacy_adapter.py` 死代码
- [ ] 给 `CommandComponent` 添加 DeprecationWarning
