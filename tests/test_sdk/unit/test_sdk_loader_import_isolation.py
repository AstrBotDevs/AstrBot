from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from astrbot_sdk.context import CancelToken
from astrbot_sdk.protocol.descriptors import SessionRef
from astrbot_sdk.runtime.handler_dispatcher import HandlerDispatcher
from astrbot_sdk.runtime.loader import (
    _plugin_package_name,
    load_plugin,
    load_plugin_spec,
    validate_plugin_spec,
)
from astrbot_sdk.testing import SDKTestEnvironment


class _Peer:
    def __init__(self) -> None:
        descriptor = SimpleNamespace(supports_stream=False)
        self.remote_peer = {"name": "dummy-core"}
        self.remote_capability_map = {
            "platform.send": descriptor,
            "platform.send_chain": descriptor,
            "platform.send_by_session": descriptor,
            "system.session_waiter.register": descriptor,
            "system.session_waiter.unregister": descriptor,
        }
        self.sent_messages: list[dict[str, object]] = []

    async def invoke(
        self,
        capability: str,
        payload: dict[str, object],
        *,
        stream: bool = False,
        request_id: str | None = None,
    ) -> dict[str, object]:
        del stream, request_id
        if capability == "platform.send":
            self.sent_messages.append(
                {
                    "kind": "text",
                    "session": payload.get("session"),
                    "text": payload.get("text"),
                }
            )
            return {"message_id": f"text-{len(self.sent_messages)}"}
        if capability in {"platform.send_chain", "platform.send_by_session"}:
            self.sent_messages.append(
                {
                    "kind": "chain",
                    "session": payload.get("session"),
                    "chain": payload.get("chain"),
                }
            )
            return {"message_id": f"chain-{len(self.sent_messages)}"}
        if capability in {
            "system.session_waiter.register",
            "system.session_waiter.unregister",
        }:
            return {}
        raise AssertionError(f"unexpected capability: {capability}")


def _event_payload(
    text: str,
    *,
    session_id: str = "demo:private:user-1",
) -> dict[str, object]:
    return {
        "text": text,
        "session_id": session_id,
        "user_id": "user-1",
        "group_id": None,
        "platform": "demo",
        "platform_id": "demo",
        "message_type": "private",
        "target": SessionRef(conversation_id=session_id, platform="demo").to_payload(),
    }


def _write_sdk_plugin(
    plugin_dir: Path,
    *,
    name: str,
    source_path: str = "main.py",
    class_path: str = "main:DemoPlugin",
    source: str,
    extra_files: dict[str, str] | None = None,
) -> Path:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                f"name: {name}",
                "author: tests",
                f"repo: {name}",
                "runtime:",
                '  python: "3.11"',
                "components:",
                f"  - class: {class_path}",
            ]
        ),
        encoding="utf-8",
    )
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    target = plugin_dir / source_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    for relative_path, content in (extra_files or {}).items():
        extra_path = plugin_dir / relative_path
        extra_path.parent.mkdir(parents=True, exist_ok=True)
        extra_path.write_text(content, encoding="utf-8")
    return plugin_dir


def _load_sdk_plugin(plugin_dir: Path):
    plugin = load_plugin_spec(plugin_dir)
    validate_plugin_spec(plugin)
    return load_plugin(plugin)


async def _invoke_handler(
    dispatcher: HandlerDispatcher,
    *,
    handler_id: str,
    text: str,
    request_id: str,
) -> dict[str, object]:
    message = SimpleNamespace(
        id=request_id,
        input={
            "handler_id": handler_id,
            "event": _event_payload(text),
            "args": {},
        },
    )
    return await dispatcher.invoke(message, CancelToken())


@pytest.mark.unit
def test_loader_isolates_top_level_plugin_modules(tmp_path: Path) -> None:
    env = SDKTestEnvironment(tmp_path)
    plugin_a_dir = _write_sdk_plugin(
        env.plugin_dir("loader_top_level_a"),
        name="loader_top_level_a",
        source="\n".join(
            [
                "from astrbot_sdk import Star",
                "import helper",
                "",
                "class DemoPlugin(Star):",
                "    def __init__(self) -> None:",
                "        super().__init__()",
                "        self.helper_value = helper.VALUE",
            ]
        ),
        extra_files={"helper.py": "VALUE = 'A'\n"},
    )
    plugin_b_dir = _write_sdk_plugin(
        env.plugin_dir("loader_top_level_b"),
        name="loader_top_level_b",
        source="\n".join(
            [
                "from astrbot_sdk import Star",
                "import helper",
                "",
                "class DemoPlugin(Star):",
                "    def __init__(self) -> None:",
                "        super().__init__()",
                "        self.helper_value = helper.VALUE",
            ]
        ),
        extra_files={"helper.py": "VALUE = 'B'\n"},
    )

    loaded_a = _load_sdk_plugin(plugin_a_dir)
    loaded_b = _load_sdk_plugin(plugin_b_dir)

    assert loaded_a.instances[0].helper_value == "A"
    assert loaded_b.instances[0].helper_value == "B"
    assert "helper" not in sys.modules
    assert f"{_plugin_package_name('loader_top_level_a')}.helper" in sys.modules
    assert f"{_plugin_package_name('loader_top_level_b')}.helper" in sys.modules


@pytest.mark.unit
def test_loader_isolates_dotted_plugin_modules(tmp_path: Path) -> None:
    env = SDKTestEnvironment(tmp_path)
    plugin_a_dir = _write_sdk_plugin(
        env.plugin_dir("loader_dotted_a"),
        name="loader_dotted_a",
        source="\n".join(
            [
                "from astrbot_sdk import Star",
                "import utils.helper",
                "",
                "class DemoPlugin(Star):",
                "    def __init__(self) -> None:",
                "        super().__init__()",
                "        self.helper_value = utils.helper.VALUE",
            ]
        ),
        extra_files={
            "utils/__init__.py": "",
            "utils/helper.py": "VALUE = 'A'\n",
        },
    )
    plugin_b_dir = _write_sdk_plugin(
        env.plugin_dir("loader_dotted_b"),
        name="loader_dotted_b",
        source="\n".join(
            [
                "from astrbot_sdk import Star",
                "from utils import helper",
                "",
                "class DemoPlugin(Star):",
                "    def __init__(self) -> None:",
                "        super().__init__()",
                "        self.helper_value = helper.VALUE",
            ]
        ),
        extra_files={
            "utils/__init__.py": "",
            "utils/helper.py": "VALUE = 'B'\n",
        },
    )

    loaded_a = _load_sdk_plugin(plugin_a_dir)
    loaded_b = _load_sdk_plugin(plugin_b_dir)

    assert loaded_a.instances[0].helper_value == "A"
    assert loaded_b.instances[0].helper_value == "B"
    assert "utils" not in sys.modules
    assert "utils.helper" not in sys.modules
    assert f"{_plugin_package_name('loader_dotted_a')}.utils.helper" in sys.modules
    assert f"{_plugin_package_name('loader_dotted_b')}.utils.helper" in sys.modules


@pytest.mark.unit
def test_loader_supports_non_main_component_module(tmp_path: Path) -> None:
    env = SDKTestEnvironment(tmp_path)
    plugin_dir = _write_sdk_plugin(
        env.plugin_dir("loader_nested_entry"),
        name="loader_nested_entry",
        source_path="feature/entry.py",
        class_path="feature.entry:DemoPlugin",
        source="\n".join(
            [
                "from astrbot_sdk import Star",
                "",
                "class DemoPlugin(Star):",
                "    def __init__(self) -> None:",
                "        super().__init__()",
                "        self.marker = 'nested-entry'",
            ]
        ),
        extra_files={"feature/__init__.py": ""},
    )

    loaded = _load_sdk_plugin(plugin_dir)

    assert loaded.instances[0].marker == "nested-entry"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handler_lazy_import_uses_calling_plugin_namespace(
    tmp_path: Path,
) -> None:
    env = SDKTestEnvironment(tmp_path)
    plugin_a_dir = _write_sdk_plugin(
        env.plugin_dir("loader_lazy_a"),
        name="loader_lazy_a",
        source="\n".join(
            [
                "from astrbot_sdk import Context, MessageEvent, Star, on_command",
                "",
                "class DemoPlugin(Star):",
                '    @on_command("lazy")',
                "    async def lazy(self, event: MessageEvent, ctx: Context) -> None:",
                "        import helper",
                "        await event.reply(helper.VALUE)",
            ]
        ),
        extra_files={"helper.py": "VALUE = 'A'\n"},
    )
    plugin_b_dir = _write_sdk_plugin(
        env.plugin_dir("loader_lazy_b"),
        name="loader_lazy_b",
        source="\n".join(
            [
                "from astrbot_sdk import Star",
                "import helper",
                "",
                "class DemoPlugin(Star):",
                "    def __init__(self) -> None:",
                "        super().__init__()",
                "        self.helper_value = helper.VALUE",
            ]
        ),
        extra_files={"helper.py": "VALUE = 'B'\n"},
    )

    loaded_a = _load_sdk_plugin(plugin_a_dir)
    loaded_b = _load_sdk_plugin(plugin_b_dir)

    assert loaded_b.instances[0].helper_value == "B"

    peer = _Peer()
    dispatcher = HandlerDispatcher(
        plugin_id="group-loader-test",
        peer=peer,
        handlers=loaded_a.handlers,
    )

    await _invoke_handler(
        dispatcher,
        handler_id=loaded_a.handlers[0].descriptor.id,
        text="lazy",
        request_id="lazy-1",
    )

    assert [item["text"] for item in peer.sent_messages if item["kind"] == "text"] == [
        "A"
    ]


@pytest.mark.unit
def test_loader_reload_refreshes_namespaced_modules(tmp_path: Path) -> None:
    env = SDKTestEnvironment(tmp_path)
    plugin_dir = _write_sdk_plugin(
        env.plugin_dir("loader_reload_plugin"),
        name="loader_reload_plugin",
        source="\n".join(
            [
                "from astrbot_sdk import Star",
                "import helper",
                "",
                "class DemoPlugin(Star):",
                "    def __init__(self) -> None:",
                "        super().__init__()",
                "        self.helper_value = helper.VALUE",
            ]
        ),
        extra_files={"helper.py": "VALUE = 'before'\n"},
    )

    first = _load_sdk_plugin(plugin_dir)
    (plugin_dir / "helper.py").write_text("VALUE = 'after'\n", encoding="utf-8")
    second = _load_sdk_plugin(plugin_dir)

    assert first.instances[0].helper_value == "before"
    assert second.instances[0].helper_value == "after"
