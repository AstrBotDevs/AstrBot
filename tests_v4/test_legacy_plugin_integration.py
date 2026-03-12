"""旧版插件兼容性集成测试。

测试目标：验证 test_plugin 目录中的旧版插件能够正确加载和运行。
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

import pytest
import yaml

from astrbot_sdk.protocol.descriptors import CommandTrigger, MessageTrigger
from astrbot_sdk.runtime.loader import (
    load_plugin,
    load_plugin_spec,
)


class TestLegacyPluginImports:
    """测试旧版 API 导入路径是否可用。"""

    def test_import_command_component(self):
        """测试导入 CommandComponent。"""
        from astrbot_sdk.api.components.command import CommandComponent

        assert CommandComponent is not None

    def test_import_legacy_context(self):
        """测试导入 Legacy Context。"""
        from astrbot_sdk.api.star.context import Context

        assert Context is not None

    def test_import_filter_namespace(self):
        """测试导入 filter 命名空间。"""
        from astrbot_sdk.api.event import filter

        assert hasattr(filter, "command")
        assert hasattr(filter, "regex")
        assert hasattr(filter, "permission")
        assert hasattr(filter, "event_message_type")
        assert hasattr(filter, "platform_adapter_type")

    def test_import_astr_message_event(self):
        """测试导入 AstrMessageEvent。"""
        from astrbot_sdk.api.event import AstrMessageEvent

        assert AstrMessageEvent is not None

    def test_import_message_chain(self):
        """测试导入 MessageChain。"""
        from astrbot_sdk.api.message import MessageChain

        assert MessageChain is not None

    def test_import_message_components(self):
        """测试导入消息组件。"""
        from astrbot_sdk.api.message_components import (
            At,
            AtAll,
            Face,
            Image,
            Plain,
            Reply,
        )

        assert Plain is not None
        assert Image is not None
        assert At is not None
        assert AtAll is not None
        assert Reply is not None
        assert Face is not None


class TestMessageChainFeatures:
    """测试 MessageChain 功能。"""

    def test_message_chain_builder(self):
        """测试 MessageChain 构建器模式。"""
        from astrbot_sdk.api.message import MessageChain

        chain = (
            MessageChain()
            .message("Hello ")
            .at("user", "12345")
            .message("!")
            .url_image("https://example.com/img.png")
        )

        assert len(chain.chain) == 4
        payload = chain.to_payload()
        assert len(payload) == 4

    def test_is_plain_text_only(self):
        """测试纯文本检测。"""
        from astrbot_sdk.api.message import MessageChain

        # 纯文本
        plain_chain = MessageChain().message("Hello").message(" World")
        assert plain_chain.is_plain_text_only() is True

        # 包含非文本
        mixed_chain = MessageChain().message("Hello").at("user", "123")
        assert mixed_chain.is_plain_text_only() is False

    def test_get_plain_text(self):
        """测试获取纯文本。"""
        from astrbot_sdk.api.message import MessageChain

        chain = MessageChain().message("Hello").message(" World")
        assert chain.get_plain_text() == "Hello  World"


class TestMessageComponents:
    """测试消息组件。"""

    def test_plain_component(self):
        """测试 Plain 组件。"""
        from astrbot_sdk.api.message_components import Plain

        plain = Plain(text="Hello")
        d = plain.to_dict()

        assert d["type"] == "Plain"
        assert d["text"] == "Hello"

    def test_at_component_with_aliases(self):
        """测试 At 组件支持旧版字段别名。"""
        from astrbot_sdk.api.message_components import At

        # 新版字段
        at1 = At(user_id="123", user_name="test")
        assert at1.user_id == "123"
        assert at1.user_name == "test"

        # 旧版字段别名 (qq, name)
        at2 = At.model_validate({"qq": "456", "name": "legacy_user"})
        assert at2.user_id == "456"
        assert at2.user_name == "legacy_user"

    def test_image_from_url(self):
        """测试 Image.fromURL 工厂方法。"""
        from astrbot_sdk.api.message_components import Image

        img = Image.fromURL("https://example.com/test.png")
        assert img.file == "https://example.com/test.png"


class TestFilterDecorators:
    """测试 filter 装饰器。"""

    def test_command_decorator(self):
        """测试 command 装饰器。"""
        from astrbot_sdk.api.event import filter

        @filter.command("test", aliases=["t", "testing"])
        async def handler(event):
            pass

        meta = getattr(handler, "__astrbot_handler_meta__", None)
        assert meta is not None
        assert isinstance(meta.trigger, CommandTrigger)
        assert meta.trigger.command == "test"
        assert "t" in meta.trigger.aliases
        assert "testing" in meta.trigger.aliases

    def test_regex_decorator(self):
        """测试 regex 装饰器。"""
        from astrbot_sdk.api.event import filter

        @filter.regex(r"^ping.*")
        async def handler(event):
            pass

        meta = getattr(handler, "__astrbot_handler_meta__", None)
        assert meta is not None
        assert isinstance(meta.trigger, MessageTrigger)
        assert meta.trigger.regex == r"^ping.*"

    def test_event_message_type_decorator(self):
        """测试 event_message_type 装饰器。"""
        from astrbot_sdk.api.event import filter
        from astrbot_sdk.api.event.filter import EventMessageType

        @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
        @filter.command("group_cmd")
        async def handler(event):
            pass

        meta = getattr(handler, "__astrbot_handler_meta__", None)
        assert meta is not None
        assert isinstance(meta.trigger, CommandTrigger)
        assert "group" in meta.trigger.message_types

    def test_platform_adapter_type_decorator(self):
        """测试 platform_adapter_type 装饰器。"""
        from astrbot_sdk.api.event import filter

        @filter.platform_adapter_type("aiocqhttp")
        @filter.command("cqhttp_cmd")
        async def handler(event):
            pass

        meta = getattr(handler, "__astrbot_handler_meta__", None)
        assert meta is not None
        assert isinstance(meta.trigger, CommandTrigger)
        assert "aiocqhttp" in meta.trigger.platforms


class TestLegacyContextFeatures:
    """测试 LegacyContext 功能。"""

    def test_conversation_manager_exists(self):
        """测试 conversation_manager 存在。"""
        from astrbot_sdk._legacy_api import LegacyContext

        ctx = LegacyContext("test_plugin")
        assert ctx.conversation_manager is not None

    def test_register_component(self):
        """测试组件注册。"""

        class MockComponent:
            def echo(self, text: str) -> str:
                return f"echo: {text}"

        from astrbot_sdk._legacy_api import LegacyContext

        ctx = LegacyContext("test_plugin")
        ctx._register_component(MockComponent())

        assert "MockComponent" in ctx._registered_managers
        assert "MockComponent.echo" in ctx._registered_functions


class TestLoadLegacyStylePlugin:
    """测试加载旧版风格插件。"""

    def test_load_plugin_with_command_component(self):
        """测试加载使用 CommandComponent 的插件。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir) / "test_plugin"
            plugin_dir.mkdir()
            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            # 创建 commands 目录
            commands_dir = plugin_dir / "commands"
            commands_dir.mkdir()
            (commands_dir / "__init__.py").write_text("", encoding="utf-8")

            # 创建使用旧版 API 的组件
            (commands_dir / "hello.py").write_text(
                textwrap.dedent("""
                    from astrbot_sdk.api.components.command import CommandComponent
                    from astrbot_sdk.api.event import AstrMessageEvent, filter
                    from astrbot_sdk.api.star.context import Context

                    class HelloCommand(CommandComponent):
                        def __init__(self, context: Context):
                            self.context = context

                        @filter.command("hello")
                        async def hello(self, event: AstrMessageEvent):
                            yield event.plain_result("Hello!")
                """),
                encoding="utf-8",
            )

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "test_plugin",
                        "runtime": {"python": "3.12"},
                        "components": [
                            {
                                "class": "commands.hello:HelloCommand",
                                "type": "command",
                                "name": "hello",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            spec = load_plugin_spec(plugin_dir)

            if str(plugin_dir) not in sys.path:
                sys.path.insert(0, str(plugin_dir))

            try:
                loaded = load_plugin(spec)

                assert loaded.plugin.name == "test_plugin"
                assert len(loaded.instances) == 1
                assert len(loaded.handlers) >= 1

                # 验证 handler 触发器
                handler = loaded.handlers[0]
                assert isinstance(handler.descriptor.trigger, CommandTrigger)
                assert handler.descriptor.trigger.command == "hello"

                # 验证 LegacyContext 共享
                instance = loaded.instances[0]
                assert instance.context is not None
                assert instance.context.plugin_id == "test_plugin"
            finally:
                if str(plugin_dir) in sys.path:
                    sys.path.remove(str(plugin_dir))

    def test_load_plugin_with_message_chain(self):
        """测试加载使用 MessageChain 的插件。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir) / "chain_plugin"
            plugin_dir.mkdir()
            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            # 使用唯一的模块名避免与其他测试冲突
            handlers_dir = plugin_dir / "chain_handlers"
            handlers_dir.mkdir()
            (handlers_dir / "__init__.py").write_text("", encoding="utf-8")

            (handlers_dir / "chain_cmd.py").write_text(
                textwrap.dedent("""
                    from astrbot_sdk.api.components.command import CommandComponent
                    from astrbot_sdk.api.event import AstrMessageEvent, filter
                    from astrbot_sdk.api.star.context import Context
                    from astrbot_sdk.api.message import MessageChain
                    from astrbot_sdk.api.message_components import Plain, At

                    class ChainCommand(CommandComponent):
                        def __init__(self, context: Context):
                            self.context = context

                        @filter.command("chain")
                        async def chain_test(self, event: AstrMessageEvent):
                            chain = MessageChain().message("Hi ").at("user", "123")
                            payload = chain.to_payload()
                            yield event.plain_result(f"Chain: {len(payload)} components")
                """),
                encoding="utf-8",
            )

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "chain_plugin",
                        "runtime": {"python": "3.12"},
                        "components": [
                            {
                                "class": "chain_handlers.chain_cmd:ChainCommand",
                                "type": "command",
                                "name": "chain",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            spec = load_plugin_spec(plugin_dir)

            path_added = False
            if str(plugin_dir) not in sys.path:
                sys.path.insert(0, str(plugin_dir))
                path_added = True

            try:
                loaded = load_plugin(spec)

                assert len(loaded.instances) == 1
                assert len(loaded.handlers) >= 1
            finally:
                # 清理导入的模块
                modules_to_remove = [
                    k for k in list(sys.modules.keys()) if k.startswith("chain_handlers")
                ]
                for mod in modules_to_remove:
                    del sys.modules[mod]
                if path_added and str(plugin_dir) in sys.path:
                    sys.path.remove(str(plugin_dir))

    def test_load_plugin_with_regex_handler(self):
        """测试加载使用正则处理器的插件。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir) / "regex_plugin"
            plugin_dir.mkdir()
            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            # 使用唯一的模块名避免与其他测试冲突
            regex_handlers_dir = plugin_dir / "regex_handlers"
            regex_handlers_dir.mkdir()
            (regex_handlers_dir / "__init__.py").write_text("", encoding="utf-8")

            (regex_handlers_dir / "matcher.py").write_text(
                textwrap.dedent("""
                    from astrbot_sdk.api.components.command import CommandComponent
                    from astrbot_sdk.api.event import AstrMessageEvent, filter
                    from astrbot_sdk.api.star.context import Context

                    class RegexCommand(CommandComponent):
                        def __init__(self, context: Context):
                            self.context = context

                        @filter.regex(r"^ping.*")
                        async def ping(self, event: AstrMessageEvent):
                            yield event.plain_result("Pong!")
                """),
                encoding="utf-8",
            )

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "regex_plugin",
                        "runtime": {"python": "3.12"},
                        "components": [
                            {
                                "class": "regex_handlers.matcher:RegexCommand",
                                "type": "command",
                                "name": "regex",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            spec = load_plugin_spec(plugin_dir)

            path_added = False
            if str(plugin_dir) not in sys.path:
                sys.path.insert(0, str(plugin_dir))
                path_added = True

            try:
                loaded = load_plugin(spec)

                assert len(loaded.handlers) >= 1
                handler = loaded.handlers[0]
                assert isinstance(handler.descriptor.trigger, MessageTrigger)
                assert handler.descriptor.trigger.regex == r"^ping.*"
            finally:
                # 清理导入的模块
                modules_to_remove = [
                    k for k in sys.modules if k.startswith("regex_handlers")
                ]
                for mod in modules_to_remove:
                    del sys.modules[mod]
                if path_added and str(plugin_dir) in sys.path:
                    sys.path.remove(str(plugin_dir))


class TestRealTestPlugin:
    """测试真实的 test_plugin 目录。"""

    def test_load_test_plugin(self):
        """测试加载项目中的 test_plugin。"""
        project_root = Path(__file__).parent.parent
        test_plugin_dir = project_root / "test_plugin"

        if not test_plugin_dir.exists():
            pytest.skip("test_plugin directory not found")

        spec = load_plugin_spec(test_plugin_dir)

        # 添加项目根目录到 sys.path
        paths_to_add = []
        if str(test_plugin_dir) not in sys.path:
            sys.path.insert(0, str(test_plugin_dir))
            paths_to_add.append(str(test_plugin_dir))

        # 添加 src-new 到 sys.path 以便导入 astrbot_sdk
        src_new = project_root / "src-new"
        if str(src_new) not in sys.path:
            sys.path.insert(0, str(src_new))
            paths_to_add.append(str(src_new))

        try:
            loaded = load_plugin(spec)

            # 验证插件加载成功
            assert loaded.plugin.name == "astrbot_plugin_helloworld"
            assert len(loaded.instances) == 1
            assert len(loaded.handlers) >= 1

            # 验证处理器
            handler_ids = [h.descriptor.id for h in loaded.handlers]
            assert any("hello" in hid for hid in handler_ids)

            # 验证实例类型
            instance = loaded.instances[0]
            assert hasattr(instance, "context")
            assert instance.context.plugin_id == "astrbot_plugin_helloworld"

        finally:
            for p in paths_to_add:
                if p in sys.path:
                    sys.path.remove(p)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
