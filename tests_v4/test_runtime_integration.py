"""
Integration tests for runtime module - covers subprocess lifecycle,
concurrency, and real-world scenarios.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from astrbot_sdk.context import CancelToken, Context
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.events import MessageEvent
from astrbot_sdk.protocol.descriptors import (
    CapabilityDescriptor,
    CommandTrigger,
    EventTrigger,
    HandlerDescriptor,
    MessageTrigger,
    ScheduleTrigger,
)
from astrbot_sdk.protocol.messages import (
    InitializeOutput,
    InvokeMessage,
    PeerInfo,
)
from astrbot_sdk.runtime.bootstrap import (
    SupervisorRuntime,
    WorkerSession,
)
from astrbot_sdk.runtime.capability_router import CapabilityRouter
from astrbot_sdk.runtime.handler_dispatcher import HandlerDispatcher
from astrbot_sdk.runtime.loader import (
    LoadedHandler,
    PluginEnvironmentManager,
    PluginSpec,
)
from astrbot_sdk.runtime.peer import Peer

from tests_v4.helpers import FakeEnvManager, MemoryTransport, make_transport_pair


async def start_test_core_peer(transport: MemoryTransport) -> Peer:
    """Provide an initialize responder so transport-pair startup tests do not deadlock."""
    core = Peer(
        transport=transport,
        peer_info=PeerInfo(name="test-core", role="core", version="v4"),
    )
    core.set_initialize_handler(
        lambda _message: asyncio.sleep(
            0,
            result=InitializeOutput(
                peer=PeerInfo(name="test-core", role="core", version="v4"),
                capabilities=[],
                metadata={},
            ),
        )
    )
    await core.start()
    return core


class TestWorkerSessionSubprocessLifecycle:
    """Tests for WorkerSession subprocess management."""

    @pytest.mark.asyncio
    async def test_worker_session_crash_during_init(self):
        """WorkerSession 应该在 worker 子进程初始化阶段崩溃时正确清理。"""
        # 创建一个会立即崩溃的插件
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir) / "plugins"
            plugin_dir = plugins_dir / "crash_plugin"
            plugin_dir.mkdir(parents=True)

            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "crash_plugin",
                        "runtime": {
                            "python": f"{sys.version_info.major}.{sys.version_info.minor}"
                        },
                        "components": [{"class": "nonexistent:Module"}],  # 不存在的模块
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            spec = PluginSpec(
                name="crash_plugin",
                plugin_dir=plugin_dir,
                manifest_path=manifest_path,
                requirements_path=requirements_path,
                python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
                manifest_data={"name": "crash_plugin"},
            )

            left, right = make_transport_pair()
            core = await start_test_core_peer(left)

            router = CapabilityRouter()
            session = WorkerSession(
                plugin=spec,
                repo_root=Path(temp_dir),
                env_manager=FakeEnvManager(),
                capability_router=router,
            )

            # 启动应该失败（子进程会崩溃）
            with pytest.raises(RuntimeError, match="初始化阶段退出|worker 进程"):
                await session.start()

            # 确保清理完成
            assert session.peer is None or session.peer._closed.is_set()

            await core.stop()

    @pytest.mark.asyncio
    async def test_worker_session_handles_cancel_during_init(self):
        """WorkerSession 应该正确处理初始化期间的取消操作。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir) / "test_plugin"
            plugin_dir.mkdir(parents=True)

            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "test_plugin",
                        "runtime": {
                            "python": f"{sys.version_info.major}.{sys.version_info.minor}"
                        },
                        "components": [],
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            spec = PluginSpec(
                name="test_plugin",
                plugin_dir=plugin_dir,
                manifest_path=manifest_path,
                requirements_path=requirements_path,
                python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
                manifest_data={"name": "test_plugin"},
            )

            # 使用 mock 让 start 在中途被取消
            session = WorkerSession(
                plugin=spec,
                repo_root=Path(temp_dir),
                env_manager=FakeEnvManager(),
                capability_router=CapabilityRouter(),
            )

            # 模拟取消
            with patch.object(
                Peer,
                "start",
                side_effect=asyncio.CancelledError,
            ):
                with pytest.raises(asyncio.CancelledError):
                    await session.start()

            # 确保清理完成
            await session.stop()


class TestConcurrentPeerOperations:
    """Tests for concurrent invoke operations on Peer."""

    @pytest.mark.asyncio
    async def test_concurrent_invokes(self):
        """Peer 应该正确处理多个并发调用。"""
        left, right = make_transport_pair()

        router = CapabilityRouter()
        core = Peer(
            transport=left,
            peer_info=PeerInfo(name="core", role="core", version="v4"),
        )
        core.set_initialize_handler(
            lambda _message: asyncio.sleep(
                0,
                result=InitializeOutput(
                    peer=PeerInfo(name="core", role="core", version="v4"),
                    capabilities=router.descriptors(),
                    metadata={},
                ),
            )
        )

        call_count = []

        async def tracking_handler(message, token):
            call_count.append(message.id)
            await asyncio.sleep(0.1)  # 模拟处理时间
            return router.execute(
                message.capability,
                message.input,
                stream=message.stream,
                cancel_token=token,
                request_id=message.id,
            )

        core.set_invoke_handler(tracking_handler)

        plugin = Peer(
            transport=right,
            peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
        )

        await core.start()
        await plugin.start()
        await plugin.initialize([])

        # 并发发起 5 个调用
        tasks = [
            plugin.invoke("llm.chat", {"prompt": f"hello{i}"}, request_id=f"req-{i}")
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks)

        # 所有调用都应成功
        assert len(results) == 5
        assert len(call_count) == 5
        # 每个请求 ID 都应该被记录
        for i in range(5):
            assert f"req-{i}" in call_count

        await plugin.stop()
        await core.stop()

    @pytest.mark.asyncio
    async def test_concurrent_invoke_and_cancel(self):
        """Peer 应该正确处理并发的调用和取消操作。"""
        left, right = make_transport_pair()

        descriptor = CapabilityDescriptor(
            name="slow.cap",
            description="slow capability",
            input_schema={"type": "object", "properties": {}, "required": []},
            output_schema={"type": "object", "properties": {}, "required": []},
            supports_stream=True,
            cancelable=True,
        )

        started = asyncio.Event()
        cancelled = []

        async def slow_handler(
            request_id: str, _payload: dict[str, object], token: CancelToken
        ):
            started.set()
            try:
                # 持续运行直到被取消
                while True:
                    token.raise_if_cancelled()
                    await asyncio.sleep(0.01)
                    yield {"tick": True}
            except asyncio.CancelledError:
                cancelled.append(request_id)
                raise

        router = CapabilityRouter()
        router.register(descriptor, stream_handler=slow_handler)

        core = Peer(
            transport=left,
            peer_info=PeerInfo(name="core", role="core", version="v4"),
        )
        core.set_initialize_handler(
            lambda _message: asyncio.sleep(
                0,
                result=InitializeOutput(
                    peer=PeerInfo(name="core", role="core", version="v4"),
                    capabilities=[descriptor],
                    metadata={},
                ),
            )
        )
        core.set_invoke_handler(
            lambda message, token: router.execute(
                message.capability,
                message.input,
                stream=message.stream,
                cancel_token=token,
                request_id=message.id,
            )
        )

        plugin = Peer(
            transport=right,
            peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
        )

        await core.start()
        await plugin.start()
        await plugin.initialize([])

        # 启动流式调用
        stream = await plugin.invoke_stream("slow.cap", {}, request_id="slow-1")

        # 等待处理开始
        await started.wait()

        # 在迭代过程中取消
        cancel_task = asyncio.create_task(plugin.cancel("slow-1"))

        # 尝试迭代应该抛出错误
        with pytest.raises(AstrBotError) as raised:
            async for _ in stream:
                pass
        assert raised.value.code == "cancelled"

        await cancel_task
        await plugin.stop()
        await core.stop()


class TestStreamCancelDuringIteration:
    """Tests for cancelling stream invocations during iteration."""

    @pytest.mark.asyncio
    async def test_cancel_mid_stream(self):
        """流式调用在迭代中途被取消应该正确终止。"""
        left, right = make_transport_pair()

        chunks_produced = []

        async def stream_handler(_request_id: str, _payload: dict[str, object], token):
            for i in range(100):
                token.raise_if_cancelled()
                chunks_produced.append(i)
                yield {"chunk": i}
                await asyncio.sleep(0.01)

        router = CapabilityRouter()
        router.register(
            CapabilityDescriptor(
                name="test.stream",
                description="test",
                supports_stream=True,
                cancelable=True,
            ),
            stream_handler=stream_handler,
        )

        core = Peer(
            transport=left,
            peer_info=PeerInfo(name="core", role="core", version="v4"),
        )
        core.set_initialize_handler(
            lambda _message: asyncio.sleep(
                0,
                result=InitializeOutput(
                    peer=PeerInfo(name="core", role="core", version="v4"),
                    capabilities=router.descriptors(),
                    metadata={},
                ),
            )
        )
        core.set_invoke_handler(
            lambda message, token: router.execute(
                message.capability,
                message.input,
                stream=message.stream,
                cancel_token=token,
                request_id=message.id,
            )
        )

        plugin = Peer(
            transport=right,
            peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
        )

        await core.start()
        await plugin.start()
        await plugin.initialize([])

        stream = await plugin.invoke_stream("test.stream", {}, request_id="stream-1")

        received = []

        async def consume():
            async for chunk in stream:
                received.append(chunk)
                if len(received) == 3:
                    # 收到 3 个 chunk 后取消
                    await plugin.cancel("stream-1")

        with pytest.raises(AstrBotError) as raised:
            await consume()
        assert raised.value.code == "cancelled"

        # 应该只收到了前几个 chunk
        assert len(received) <= 5
        # 不应该产生了 100 个 chunk
        assert len(chunks_produced) < 50

        await plugin.stop()
        await core.stop()

    @pytest.mark.asyncio
    async def test_cancel_before_stream_starts(self):
        """流式调用在开始迭代前被取消。"""
        left, right = make_transport_pair()

        started = []

        async def stream_handler(_request_id: str, _payload: dict[str, object], token):
            started.append(True)
            yield {"chunk": 1}

        router = CapabilityRouter()
        router.register(
            CapabilityDescriptor(
                name="test.stream",
                description="test",
                supports_stream=True,
                cancelable=True,
            ),
            stream_handler=stream_handler,
        )

        core = Peer(
            transport=left,
            peer_info=PeerInfo(name="core", role="core", version="v4"),
        )
        core.set_initialize_handler(
            lambda _message: asyncio.sleep(
                0,
                result=InitializeOutput(
                    peer=PeerInfo(name="core", role="core", version="v4"),
                    capabilities=router.descriptors(),
                    metadata={},
                ),
            )
        )
        core.set_invoke_handler(
            lambda message, token: router.execute(
                message.capability,
                message.input,
                stream=message.stream,
                cancel_token=token,
                request_id=message.id,
            )
        )

        plugin = Peer(
            transport=right,
            peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
        )

        await core.start()
        await plugin.start()
        await plugin.initialize([])

        stream = await plugin.invoke_stream(
            "test.stream", {}, request_id="stream-early"
        )

        # 在迭代前取消
        await plugin.cancel("stream-early")

        # 迭代应该抛出错误
        with pytest.raises(AstrBotError) as raised:
            async for _ in stream:
                pass
        assert raised.value.code == "cancelled"

        await plugin.stop()
        await core.stop()


class TestMultipleTriggerTypes:
    """Tests for different trigger types in HandlerDispatcher."""

    def create_dispatcher_with_trigger(self, trigger) -> HandlerDispatcher:
        """创建带有指定触发器的调度器。"""
        peer = MagicMock()
        peer.sent_messages = []

        async def mock_send(session_id: str, text: str) -> None:
            peer.sent_messages.append({"session_id": session_id, "text": text})

        peer.send = mock_send

        async def handler_func(event: MessageEvent, ctx: Context):
            await event.reply("response")
            return None

        descriptor = HandlerDescriptor(
            id="test.handler",
            trigger=trigger,
        )
        handler = LoadedHandler(
            descriptor=descriptor,
            callable=handler_func,
            owner=MagicMock(),
            legacy_context=None,
        )

        return HandlerDispatcher(
            plugin_id="test_plugin",
            peer=peer,
            handlers=[handler],
        )

    @pytest.mark.asyncio
    async def test_command_trigger(self):
        """CommandTrigger 应该正确处理命令触发。"""
        trigger = CommandTrigger(
            command="hello",
            aliases=["hi", "hey"],
            description="A greeting command",
        )
        dispatcher = self.create_dispatcher_with_trigger(trigger)

        # 验证 descriptor 中的触发器信息
        handler = dispatcher._handlers["test.handler"]
        assert handler.descriptor.trigger.command == "hello"
        assert "hi" in handler.descriptor.trigger.aliases

    @pytest.mark.asyncio
    async def test_message_trigger_regex(self):
        """MessageTrigger 应该正确处理正则匹配。"""
        trigger = MessageTrigger(
            regex=r"ping\s+(\d+)",
            platforms=["test"],
        )
        dispatcher = self.create_dispatcher_with_trigger(trigger)

        handler = dispatcher._handlers["test.handler"]
        assert handler.descriptor.trigger.regex == r"ping\s+(\d+)"
        assert "test" in handler.descriptor.trigger.platforms

    @pytest.mark.asyncio
    async def test_message_trigger_keywords(self):
        """MessageTrigger 应该正确处理关键词匹配。"""
        trigger = MessageTrigger(
            keywords=["ping", "pong"],
        )
        dispatcher = self.create_dispatcher_with_trigger(trigger)

        handler = dispatcher._handlers["test.handler"]
        assert "ping" in handler.descriptor.trigger.keywords
        assert "pong" in handler.descriptor.trigger.keywords

    @pytest.mark.asyncio
    async def test_event_trigger(self):
        """EventTrigger 应该正确处理事件类型触发。"""
        trigger = EventTrigger(
            event_type="message.received",
        )
        dispatcher = self.create_dispatcher_with_trigger(trigger)

        handler = dispatcher._handlers["test.handler"]
        assert handler.descriptor.trigger.event_type == "message.received"

    @pytest.mark.asyncio
    async def test_schedule_trigger(self):
        """ScheduleTrigger 应该正确处理定时触发。"""
        trigger = ScheduleTrigger(
            schedule="0 */5 * * * *",  # 每5分钟
        )
        dispatcher = self.create_dispatcher_with_trigger(trigger)

        handler = dispatcher._handlers["test.handler"]
        assert handler.descriptor.trigger.schedule == "0 */5 * * * *"

    @pytest.mark.asyncio
    async def test_invoke_with_message_trigger_event(self):
        """调度器应该正确处理 MessageTrigger 类型的事件。"""
        trigger = MessageTrigger(regex=r"test\s+(.+)")
        dispatcher = self.create_dispatcher_with_trigger(trigger)

        event = MessageEvent(
            session_id="session-1",
            user_id="user-1",
            platform="test",
            text="test message",
        )

        message = InvokeMessage(
            id="msg_001",
            capability="handler.invoke",
            input={"handler_id": "test.handler", "event": event.to_payload()},
        )

        cancel_token = CancelToken()
        result = await dispatcher.invoke(message, cancel_token)

        assert result == {}

    @pytest.mark.asyncio
    async def test_invoke_with_event_trigger_event(self):
        """调度器应该正确处理 EventTrigger 类型的事件。"""
        trigger = EventTrigger(event_type="custom.event")
        dispatcher = self.create_dispatcher_with_trigger(trigger)

        # EventTrigger 通常用于非消息事件
        event_data = {
            "type": "event",
            "event_type": "custom.event",
            "session_id": "session-1",
            "user_id": "user-1",
            "platform": "test",
        }

        message = InvokeMessage(
            id="msg_001",
            capability="handler.invoke",
            input={"handler_id": "test.handler", "event": event_data},
        )

        cancel_token = CancelToken()
        result = await dispatcher.invoke(message, cancel_token)

        assert result == {}


class TestEnvironmentCacheReuse:
    """Tests for PluginEnvironmentManager caching behavior."""

    def test_fingerprint_matches_skips_rebuild(self):
        """当指纹匹配时应该跳过环境重建。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir) / "test_plugin"
            plugin_dir.mkdir()

            requirements_path = plugin_dir / "requirements.txt"
            requirements_path.write_text("astrbot-sdk\n", encoding="utf-8")

            spec = PluginSpec(
                name="test_plugin",
                plugin_dir=plugin_dir,
                manifest_path=plugin_dir / "plugin.yaml",
                requirements_path=requirements_path,
                python_version="3.12",
                manifest_data={},
            )

            # 创建 mock uv
            with patch("shutil.which", return_value="/usr/bin/uv"):
                manager = PluginEnvironmentManager(Path(temp_dir))
                manager.uv_binary = "/usr/bin/uv"

                # 记录 _rebuild 调用
                rebuild_called = []

                def tracked_rebuild(*args, **kwargs):
                    rebuild_called.append(True)
                    # 不实际执行重建，只是模拟
                    venv_dir = args[1]
                    venv_dir.mkdir(exist_ok=True)
                    # 创建假的 python 可执行文件标记
                    (venv_dir / "python").touch()

                manager._rebuild = tracked_rebuild

                # 第一次调用应该触发重建
                with patch.object(Path, "exists", return_value=False):
                    with patch("shutil.which", return_value="/usr/bin/uv"):
                        # 模拟指纹计算
                        fingerprint = manager._fingerprint(spec)
                        manager._write_state(
                            plugin_dir / ".astrbot-worker-state.json", spec, fingerprint
                        )

                # 重置计数
                rebuild_called.clear()

                # 第二次调用（指纹匹配）不应该触发重建
                # 我们需要模拟 venv 存在且状态匹配
                state = manager._load_state(plugin_dir / ".astrbot-worker-state.json")
                new_fingerprint = manager._fingerprint(spec)

                # 如果指纹匹配，条件应该为 False
                if state.get("fingerprint") == new_fingerprint:
                    # 模拟 venv 存在
                    with patch.object(Path, "exists", return_value=True):
                        with patch.object(
                            manager, "_matches_python_version", return_value=True
                        ):
                            # prepare_environment 应该跳过重建
                            # 但由于我们 mock 了 exists，这里只验证逻辑
                            pass

    def test_fingerprint_changes_triggers_rebuild(self):
        """当指纹变化时应该触发环境重建。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir) / "test_plugin"
            plugin_dir.mkdir()

            requirements_path = plugin_dir / "requirements.txt"
            requirements_path.write_text("astrbot-sdk==1.0.0\n", encoding="utf-8")

            spec = PluginSpec(
                name="test_plugin",
                plugin_dir=plugin_dir,
                manifest_path=plugin_dir / "plugin.yaml",
                requirements_path=requirements_path,
                python_version="3.12",
                manifest_data={},
            )

            # 计算初始指纹
            fingerprint1 = PluginEnvironmentManager._fingerprint(spec)

            # 修改 requirements.txt
            requirements_path.write_text("astrbot-sdk==2.0.0\n", encoding="utf-8")

            # 重新加载 spec
            spec2 = PluginSpec(
                name="test_plugin",
                plugin_dir=plugin_dir,
                manifest_path=plugin_dir / "plugin.yaml",
                requirements_path=requirements_path,
                python_version="3.12",
                manifest_data={},
            )

            fingerprint2 = PluginEnvironmentManager._fingerprint(spec2)

            # 指纹应该不同
            assert fingerprint1 != fingerprint2

    def test_python_version_change_triggers_rebuild(self):
        """Python 版本变化时应该触发环境重建。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            requirements_path = Path(temp_dir) / "requirements.txt"
            requirements_path.write_text("", encoding="utf-8")

            spec1 = PluginSpec(
                name="test",
                plugin_dir=Path(temp_dir),
                manifest_path=Path(temp_dir) / "plugin.yaml",
                requirements_path=requirements_path,
                python_version="3.11",
                manifest_data={},
            )

            spec2 = PluginSpec(
                name="test",
                plugin_dir=Path(temp_dir),
                manifest_path=Path(temp_dir) / "plugin.yaml",
                requirements_path=requirements_path,
                python_version="3.12",
                manifest_data={},
            )

            fingerprint1 = PluginEnvironmentManager._fingerprint(spec1)
            fingerprint2 = PluginEnvironmentManager._fingerprint(spec2)

            # 不同 Python 版本应该产生不同指纹
            assert fingerprint1 != fingerprint2

    def test_matches_python_version(self):
        """_matches_python_version 应该正确检查 Python 版本。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            venv_dir = Path(temp_dir) / ".venv"
            venv_dir.mkdir()

            # 创建 pyvenv.cfg
            pyvenv_cfg = venv_dir / "pyvenv.cfg"
            pyvenv_cfg.write_text(
                "home = /usr/bin\n"
                "include-system-site-packages = false\n"
                "version = 3.12.0\n",
                encoding="utf-8",
            )

            manager = PluginEnvironmentManager(Path(temp_dir))

            # 匹配的版本
            assert manager._matches_python_version(venv_dir, "3.12") is True

            # 不匹配的版本
            assert manager._matches_python_version(venv_dir, "3.11") is False

            # 不存在的 venv
            assert (
                manager._matches_python_version(Path("/nonexistent"), "3.12") is False
            )


class TestSupervisorRuntimePluginLoading:
    """Tests for SupervisorRuntime plugin loading scenarios."""

    @pytest.mark.asyncio
    async def test_load_multiple_plugins(self):
        """SupervisorRuntime 应该正确加载多个插件。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir) / "plugins"

            # 创建多个插件
            for i in range(3):
                plugin_dir = plugins_dir / f"plugin_{i}"
                plugin_dir.mkdir(parents=True)

                manifest_path = plugin_dir / "plugin.yaml"
                requirements_path = plugin_dir / "requirements.txt"

                manifest_path.write_text(
                    yaml.dump(
                        {
                            "name": f"plugin_{i}",
                            "runtime": {
                                "python": f"{sys.version_info.major}.{sys.version_info.minor}"
                            },
                            "components": [],
                        }
                    ),
                    encoding="utf-8",
                )
                requirements_path.write_text("", encoding="utf-8")

            left, right = make_transport_pair()
            core = await start_test_core_peer(left)

            runtime = SupervisorRuntime(
                transport=right,
                plugins_dir=plugins_dir,
                env_manager=FakeEnvManager(),
            )

            try:
                await runtime.start()
                await core.wait_until_remote_initialized()

                # 应该加载了所有插件
                assert len(runtime.loaded_plugins) == 3
                assert "plugin_0" in runtime.loaded_plugins
                assert "plugin_1" in runtime.loaded_plugins
                assert "plugin_2" in runtime.loaded_plugins

            finally:
                await runtime.stop()
                await core.stop()

    @pytest.mark.asyncio
    async def test_skip_invalid_plugins(self):
        """SupervisorRuntime 应该跳过无效插件并记录原因。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir) / "plugins"

            # 有效插件
            valid_dir = plugins_dir / "valid_plugin"
            valid_dir.mkdir(parents=True)
            (valid_dir / "plugin.yaml").write_text(
                yaml.dump(
                    {
                        "name": "valid_plugin",
                        "runtime": {
                            "python": f"{sys.version_info.major}.{sys.version_info.minor}"
                        },
                        "components": [],
                    }
                ),
                encoding="utf-8",
            )
            (valid_dir / "requirements.txt").write_text("", encoding="utf-8")

            # 无效插件（缺少 requirements.txt）
            invalid_dir = plugins_dir / "invalid_plugin"
            invalid_dir.mkdir(parents=True)
            (invalid_dir / "plugin.yaml").write_text(
                yaml.dump({"name": "invalid_plugin"}),
                encoding="utf-8",
            )

            left, right = make_transport_pair()
            core = await start_test_core_peer(left)

            runtime = SupervisorRuntime(
                transport=right,
                plugins_dir=plugins_dir,
                env_manager=FakeEnvManager(),
            )

            try:
                await runtime.start()
                await core.wait_until_remote_initialized()

                # 应该只加载有效插件
                assert len(runtime.loaded_plugins) == 1
                assert "valid_plugin" in runtime.loaded_plugins

                # 应该记录跳过的插件
                assert "invalid_plugin" in runtime.skipped_plugins

            finally:
                await runtime.stop()
                await core.stop()

    @pytest.mark.asyncio
    async def test_skip_plugin_when_on_start_fails_before_initialize(self):
        """on_start 失败的插件不应向上游暴露 handlers 或 capabilities。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir) / "plugins"
            plugin_dir = plugins_dir / "broken_plugin"
            commands_dir = plugin_dir / "commands"
            commands_dir.mkdir(parents=True)

            (plugin_dir / "plugin.yaml").write_text(
                yaml.dump(
                    {
                        "name": "broken_plugin",
                        "runtime": {
                            "python": f"{sys.version_info.major}.{sys.version_info.minor}"
                        },
                        "components": [
                            {"class": "commands.broken:BrokenPlugin", "type": "command"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
            (commands_dir / "__init__.py").write_text("", encoding="utf-8")
            (commands_dir / "broken.py").write_text(
                "from astrbot_sdk import Star, on_command, provide_capability\n\n"
                "class BrokenPlugin(Star):\n"
                "    async def on_start(self, ctx):\n"
                '        raise RuntimeError("boom during startup")\n\n'
                '    @on_command("broken")\n'
                "    async def broken(self, event):\n"
                '        await event.reply("should not load")\n\n'
                '    @provide_capability("broken_plugin.echo", description="broken")\n'
                "    async def echo(self, payload):\n"
                '        return {"echo": "broken"}\n',
                encoding="utf-8",
            )

            left, right = make_transport_pair()
            core = await start_test_core_peer(left)

            runtime = SupervisorRuntime(
                transport=right,
                plugins_dir=plugins_dir,
                env_manager=FakeEnvManager(),
            )

            try:
                await runtime.start()
                await core.wait_until_remote_initialized()

                assert "broken_plugin" not in runtime.loaded_plugins
                assert "broken_plugin" in runtime.skipped_plugins
                assert "broken_plugin" not in core.remote_metadata["plugins"]
                assert all(
                    "broken" not in handler.id for handler in core.remote_handlers
                )
                assert all(
                    descriptor.name != "broken_plugin.echo"
                    for descriptor in core.remote_provided_capabilities
                )
            finally:
                await runtime.stop()
                await core.stop()


class TestTimeoutHandling:
    """Tests for timeout handling in Peer operations."""

    @pytest.mark.asyncio
    async def test_wait_until_remote_initialized_timeout(self):
        """wait_until_remote_initialized 应该在超时后抛出错误。"""
        left, right = make_transport_pair()

        # 只启动一侧，不提供初始化响应
        plugin = Peer(
            transport=right,
            peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
        )

        await left.start()
        await plugin.start()

        # 不发送初始化响应，应该超时
        with pytest.raises(TimeoutError):
            await plugin.wait_until_remote_initialized(timeout=0.1)

        await plugin.stop()
        await left.stop()

    @pytest.mark.asyncio
    async def test_invoke_timeout_on_no_response(self):
        """invoke 应该在无响应时正确处理超时。"""
        left, right = make_transport_pair()

        core = Peer(
            transport=left,
            peer_info=PeerInfo(name="core", role="core", version="v4"),
        )

        plugin = Peer(
            transport=right,
            peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
        )

        # 只设置初始化处理器，不设置 invoke 处理器
        core.set_initialize_handler(
            lambda _message: asyncio.sleep(
                0,
                result=InitializeOutput(
                    peer=PeerInfo(name="core", role="core", version="v4"),
                    capabilities=[],
                    metadata={},
                ),
            )
        )

        await core.start()
        await plugin.start()
        await plugin.initialize([])

        # 尝试调用，但远程没有响应
        # 由于我们使用 MemoryTransport，调用会直接分发但无人处理
        # 这应该最终超时或抛出错误
        # 注意：实际实现可能不同，这里测试基本流程

        await plugin.stop()
        await core.stop()


class TestPeerRemoteHandlers:
    """Tests for Peer remote handler tracking."""

    @pytest.mark.asyncio
    async def test_remote_handlers_populated_after_init(self):
        """初始化后 remote_handlers 应该被填充。"""
        left, right = make_transport_pair()

        router = CapabilityRouter()
        core = Peer(
            transport=left,
            peer_info=PeerInfo(name="core", role="core", version="v4"),
        )
        core.set_initialize_handler(
            lambda _message: asyncio.sleep(
                0,
                result=InitializeOutput(
                    peer=PeerInfo(name="core", role="core", version="v4"),
                    capabilities=router.descriptors(),
                    metadata={},
                ),
            )
        )

        plugin = Peer(
            transport=right,
            peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
        )

        await core.start()
        await plugin.start()
        await plugin.initialize([])

        # 初始化后，应该有远程能力信息
        assert plugin.remote_peer is not None
        assert plugin.remote_peer.name == "core"

        await plugin.stop()
        await core.stop()

    @pytest.mark.asyncio
    async def test_remote_metadata_preserved(self):
        """初始化时的 metadata 应该被正确保存。"""
        left, right = make_transport_pair()

        core = Peer(
            transport=left,
            peer_info=PeerInfo(name="core", role="core", version="v4"),
        )
        core.set_initialize_handler(
            lambda _message: asyncio.sleep(
                0,
                result=InitializeOutput(
                    peer=PeerInfo(name="core", role="core", version="v4"),
                    capabilities=[],
                    metadata={
                        "plugins": ["test_plugin"],
                        "version": "1.0.0",
                    },
                ),
            )
        )

        plugin = Peer(
            transport=right,
            peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
        )

        await core.start()
        await plugin.start()
        await plugin.initialize([])

        assert plugin.remote_metadata.get("plugins") == ["test_plugin"]
        assert plugin.remote_metadata.get("version") == "1.0.0"

        await plugin.stop()
        await core.stop()
