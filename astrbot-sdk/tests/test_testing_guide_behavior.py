from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio

from astrbot_sdk.testing import (
    InMemoryDB,
    InMemoryMemory,
    LocalRuntimeConfig,
    MockClock,
    MockContext,
    MockMessageEvent,
    PluginHarness,
    RecordedSend,
    SDKTestEnvironment,
)


def _write_testing_guide_plugin(plugin_dir: Path) -> Path:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                "_schema_version: 2",
                "name: testing_guide_plugin",
                "display_name: Testing Guide Plugin",
                "author: tests",
                "version: 1.0.0",
                "desc: plugin used by testing guide behavior tests",
                "runtime:",
                '  python: "3.12"',
                "",
                "components:",
                "  - class: main:TestingGuidePlugin",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_dir / "main.py").write_text(
        "\n".join(
            [
                "from astrbot_sdk import Context, MessageEvent, Star",
                "from astrbot_sdk.decorators import on_command, on_message, provide_capability, rate_limit",
                "",
                "",
                "class TestingGuidePlugin(Star):",
                '    @on_command("hello")',
                "    async def hello(self, event: MessageEvent, ctx: Context) -> None:",
                '        await event.reply("Hello!")',
                "",
                '    @on_message(keywords=["你好"])',
                "    async def greet(self, event: MessageEvent, ctx: Context) -> None:",
                '        await event.reply(f\"你好 {event.user_id} via {event.platform}\")',
                "",
                '    @rate_limit(1, 60, behavior="error")',
                '    @on_command("limited")',
                "    async def limited(self, event: MessageEvent, ctx: Context) -> None:",
                '        await event.reply("limited ok")',
                "",
                '    @on_command("broadcast")',
                "    async def broadcast(",
                "        self,",
                "        event: MessageEvent,",
                "        ctx: Context,",
                "        content: str,",
                "    ) -> None:",
                "        del ctx",
                "        await event.reply(content)",
                "",
                '    @on_command("help")',
                "    async def help(self, event: MessageEvent, ctx: Context) -> None:",
                "        del ctx",
                '        await event.reply("可用命令")',
                "",
                '    @on_command("about")',
                "    async def about(self, event: MessageEvent, ctx: Context) -> None:",
                "        del ctx",
                '        await event.reply("关于")',
                "",
                '    @on_command("version")',
                "    async def version(self, event: MessageEvent, ctx: Context) -> None:",
                "        del ctx",
                '        await event.reply("版本")',
                "",
                '    @provide_capability("testing_guide.custom_capability", description="Testing guide custom capability")',
                "    async def custom_capability(",
                "        self,",
                "        payload: dict[str, object],",
                "        ctx: Context,",
                "    ) -> dict[str, object]:",
                "        return {",
                '            "status": "success",',
                '            "param": payload.get("param"),',
                '            "plugin_id": ctx.plugin_id,',
                "        }",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return plugin_dir


@pytest.fixture
def sample_user_data() -> dict[str, str]:
    return {
        "user_id": "123",
        "name": "Alice",
        "email": "alice@example.com",
    }


@pytest.fixture
def test_env(tmp_path: Path) -> SDKTestEnvironment:
    return SDKTestEnvironment(root=tmp_path)


@pytest.fixture
def plugin_dir(test_env: SDKTestEnvironment) -> Path:
    return _write_testing_guide_plugin(test_env.plugin_dir("testing_guide_plugin"))


@pytest_asyncio.fixture
async def harness_with_plugin(plugin_dir: Path):
    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        yield harness


async def run_with_timeout(coro, timeout: float = 5) -> object:
    return await asyncio.wait_for(coro, timeout=timeout)


@asynccontextmanager
async def temporary_harness(plugin_dir: Path):
    harness = PluginHarness.from_plugin_dir(plugin_dir)
    async with harness:
        yield harness


def create_minimal_plugin(
    plugin_dir: Path,
    *,
    name: str = "test_plugin",
    code: str = "",
) -> Path:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                "_schema_version: 2",
                f"name: {name}",
                "version: 1.0.0",
                "author: test",
                "desc: Test plugin",
                "runtime:",
                '  python: "3.12"',
                "",
                "components:",
                "  - class: main:TestPlugin",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    default_code = "\n".join(
        [
            "from astrbot_sdk import Context, MessageEvent, Star",
            "from astrbot_sdk.decorators import on_command",
            "",
            "",
            "class TestPlugin(Star):",
            '    @on_command("test")',
            "    async def test(self, event: MessageEvent, ctx: Context) -> None:",
            "        del ctx",
            '        await event.reply("Test!")',
        ]
    )
    (plugin_dir / "main.py").write_text(
        code or default_code,
        encoding="utf-8",
    )
    return plugin_dir


@pytest.mark.unit
def test_testing_guide_environment_runtime_config_and_recorded_send_helpers(
    test_env: SDKTestEnvironment,
) -> None:
    plugin_path = test_env.plugin_dir("demo")
    config = LocalRuntimeConfig(plugin_dir=plugin_path, session_id="session-1")

    assert test_env.plugins_dir == test_env.root / "plugins"
    assert test_env.plugins_dir.exists()
    assert plugin_path.exists()
    assert config.plugin_dir == plugin_path
    assert config.session_id == "session-1"

    record = RecordedSend.from_payload(
        {
            "message_id": "msg-1",
            "session": "demo:private:user-1",
            "text": "hello",
            "target": {"conversation_id": "demo:private:user-1", "platform": "demo"},
        }
    )

    assert record.kind == "text"
    assert record.session == "demo:private:user-1"
    assert record.text == "hello"
    assert record.target == {
        "conversation_id": "demo:private:user-1",
        "platform": "demo",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_testing_guide_unit_examples_command_and_message_handlers(
    harness_with_plugin: PluginHarness,
) -> None:
    hello_sent = await harness_with_plugin.dispatch_text("hello")
    message_sent = await harness_with_plugin.dispatch_text(
        "你好，AstrBot",
        user_id="12345",
        session_id="session_1",
        platform="qq",
    )

    assert len(hello_sent) == 1
    assert hello_sent[0].text == "Hello!"
    assert len(message_sent) == 1
    assert message_sent[0].text == "你好 12345 via qq"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_testing_guide_rate_limit_platform_send_clear_and_capability_invocation(
    harness_with_plugin: PluginHarness,
) -> None:
    first_limited = await harness_with_plugin.dispatch_text("limited")
    assert len(first_limited) == 1
    assert first_limited[0].text == "limited ok"

    from astrbot_sdk.errors import AstrBotError, ErrorCodes

    with pytest.raises(AstrBotError) as exc_info:
        await harness_with_plugin.dispatch_text("limited")
    assert exc_info.value.code == ErrorCodes.RATE_LIMITED

    await harness_with_plugin.dispatch_text("broadcast 大家好")
    messages = harness_with_plugin.sent_messages
    assert any(item.text == "大家好" for item in messages)

    harness_with_plugin.clear_sent_messages()
    assert harness_with_plugin.sent_messages == []

    result = await harness_with_plugin.invoke_capability(
        "testing_guide.custom_capability",
        {"param": "value"},
    )
    assert result == {
        "status": "success",
        "param": "value",
        "plugin_id": "testing_guide_plugin",
    }


@pytest.mark.unit
def test_testing_guide_inmemory_db_and_memory_behave_as_documented() -> None:
    db_store: dict[str, object] = {}
    db = InMemoryDB(db_store)

    db.set("user:123", {"name": "Alice"})
    assert db.get("user:123") == {"name": "Alice"}
    assert db.list("user:") == ["user:123"]
    assert db.get_many(["user:123"]) == [{"key": "user:123", "value": {"name": "Alice"}}]
    db.set_many([{"key": "user:456", "value": {"name": "Bob"}}])
    assert db.get("user:456") == {"name": "Bob"}
    db.delete("user:123")
    assert db.get("user:123") is None

    memory_store: dict[str, dict[str, object]] = {}
    memory = InMemoryMemory(memory_store)

    memory.save("user_pref", {"theme": "dark", "lang": "zh", "content": "dark theme"})
    assert memory.get("user_pref") == {
        "theme": "dark",
        "lang": "zh",
        "content": "dark theme",
    }
    assert memory.search("dark")[0]["key"] == "user_pref"
    memory.delete("user_pref")
    assert memory.get("user_pref") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_testing_guide_mock_context_and_message_event_behave_as_documented() -> (
    None
):
    ctx = MockContext()
    ctx.llm.mock_response("Mocked response")

    response = await ctx.llm.chat("test")
    assert response == "Mocked response"

    runtime_event = MockMessageEvent(text="test", session_id="session_1", context=ctx)
    await runtime_event.reply(response)
    ctx.platform.assert_sent("Mocked response")
    assert ctx.sent_messages[-1].text == "Mocked response"

    plain_event = MockMessageEvent(
        text="测试消息",
        user_id="12345",
        session_id="session_1",
        platform="qq",
    )
    assert plain_event.text == "测试消息"
    assert plain_event.user_id == "12345"

    await plain_event.reply("回复内容")
    assert plain_event.replies == ["回复内容"]


@pytest.mark.unit
def test_testing_guide_mock_clock_and_isolation_patterns() -> None:
    class CounterPlugin:
        _instance_counter = 0

        def __init__(self) -> None:
            type(self)._instance_counter += 1
            self.id = type(self)._instance_counter

    CounterPlugin._instance_counter = 0
    plugin = CounterPlugin()
    assert plugin.id == 1
    CounterPlugin._instance_counter = 0

    clock = MockClock(now=1234567890.0)
    assert clock.time() == 1234567890.0
    assert clock.advance(60.0) == 1234567950.0
    assert clock.time() == 1234567950.0


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "expected_response"),
    [
        ("help", "可用命令"),
        ("about", "关于"),
        ("version", "版本"),
    ],
)
async def test_testing_guide_parametrized_commands(
    harness_with_plugin: PluginHarness,
    command: str,
    expected_response: str,
) -> None:
    sent = await harness_with_plugin.dispatch_text(command)
    assert len(sent) == 1
    assert expected_response in (sent[0].text or "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_testing_guide_async_patterns_and_helper_functions(
    test_env: SDKTestEnvironment,
    sample_user_data: dict[str, str],
) -> None:
    assert sample_user_data["name"] == "Alice"

    plugin_dir = create_minimal_plugin(test_env.plugin_dir("helper_plugin"))
    async with temporary_harness(plugin_dir) as harness:
        sent = await run_with_timeout(harness.dispatch_text("test"), timeout=1)
        assert [item.text for item in sent] == ["Test!"]

    async def slow_function() -> None:
        await asyncio.sleep(0.2)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(slow_function(), timeout=0.01)

    async def function_that_raises() -> None:
        raise ValueError("expected error")

    with pytest.raises(ValueError, match="expected error"):
        await function_that_raises()

