"""真实 v4 示例插件集成测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from astrbot_sdk.protocol.descriptors import (
    CommandTrigger,
    EventTrigger,
    MessageTrigger,
    ScheduleTrigger,
)
from astrbot_sdk.runtime.loader import load_plugin, load_plugin_spec


class TestRealNewTestPlugin:
    """验证仓库中的真实 v4 示例插件目录。"""

    def test_load_new_plugin(self):
        project_root = Path(__file__).resolve().parent.parent
        test_plugin_dir = project_root / "test_plugin" / "new"

        if not test_plugin_dir.exists():
            pytest.skip("test_plugin/new directory not found")

        spec = load_plugin_spec(test_plugin_dir)

        paths_to_add = []
        if str(test_plugin_dir) not in sys.path:
            sys.path.insert(0, str(test_plugin_dir))
            paths_to_add.append(str(test_plugin_dir))

        src_new = project_root / "src-new"
        if str(src_new) not in sys.path:
            sys.path.insert(0, str(src_new))
            paths_to_add.append(str(src_new))

        try:
            loaded = load_plugin(spec)

            assert loaded.plugin.name == "astrbot_plugin_v4demo"
            assert len(loaded.instances) == 1

            command_triggers = [
                handler.descriptor.trigger
                for handler in loaded.handlers
                if isinstance(handler.descriptor.trigger, CommandTrigger)
            ]
            message_triggers = [
                handler.descriptor.trigger
                for handler in loaded.handlers
                if isinstance(handler.descriptor.trigger, MessageTrigger)
            ]
            event_triggers = [
                handler.descriptor.trigger
                for handler in loaded.handlers
                if isinstance(handler.descriptor.trigger, EventTrigger)
            ]
            schedule_triggers = [
                handler.descriptor.trigger
                for handler in loaded.handlers
                if isinstance(handler.descriptor.trigger, ScheduleTrigger)
            ]
            handler_map = {
                handler.descriptor.id: handler.descriptor for handler in loaded.handlers
            }

            assert {trigger.command for trigger in command_triggers} == {
                "announce",
                "hello",
                "platforms",
                "raw",
                "remember",
                "secure",
            }
            hello_trigger = next(
                trigger for trigger in command_triggers if trigger.command == "hello"
            )
            assert "hi" in hello_trigger.aliases
            secure_descriptor = next(
                descriptor
                for descriptor in handler_map.values()
                if getattr(descriptor.trigger, "command", None) == "secure"
            )
            assert secure_descriptor.permissions.require_admin is True

            assert len(message_triggers) == 1
            assert message_triggers[0].regex == r"^ping$"
            assert message_triggers[0].keywords == ["ping"]
            assert message_triggers[0].platforms == ["test"]

            assert len(event_triggers) == 1
            assert event_triggers[0].event_type == "group_join"

            assert len(schedule_triggers) == 1
            assert schedule_triggers[0].interval_seconds == 60

            capability_names = [item.descriptor.name for item in loaded.capabilities]
            assert capability_names == ["demo.echo", "demo.stream"]
            stream_descriptor = next(
                item.descriptor
                for item in loaded.capabilities
                if item.descriptor.name == "demo.stream"
            )
            assert stream_descriptor.supports_stream is True
            assert stream_descriptor.cancelable is True
        finally:
            for path in paths_to_add:
                if path in sys.path:
                    sys.path.remove(path)

            for module_name in list(sys.modules):
                if module_name == "commands" or module_name.startswith("commands."):
                    sys.modules.pop(module_name, None)
