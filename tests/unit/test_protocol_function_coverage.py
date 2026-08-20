import importlib
import inspect
from typing import Protocol

import pytest

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.utils.plugin_kv_store import PluginKVStoreMixin


def _protocol_classes(module) -> list[type]:
    found: list[type] = []
    for value in vars(module).values():
        if not isinstance(value, type):
            continue
        if value is Protocol:
            continue
        if Protocol in getattr(value, "__mro__", ()):
            found.append(value)
    return found


@pytest.mark.asyncio
async def test_plugin_kv_store_mixin_delegates_to_storage():
    calls: list[tuple[str, tuple, dict]] = []

    class Storage:
        async def put(self, *args, **kwargs):
            calls.append(("put", args, kwargs))

        async def get(self, *args, **kwargs):
            calls.append(("get", args, kwargs))
            return "value"

        async def remove(self, *args, **kwargs):
            calls.append(("remove", args, kwargs))

    class Plugin(PluginKVStoreMixin):
        plugin_id = "demo"
        context = type("Ctx", (), {"storage": Storage()})()

    plugin = Plugin()
    await plugin.put_kv_data("k", "v")
    assert await plugin.get_kv_data("k", None) == "value"
    await plugin.delete_kv_data("k")
    assert [item[0] for item in calls] == ["put", "get", "remove"]


@pytest.mark.asyncio
async def test_base_agent_run_hooks_are_noops():
    hooks = BaseAgentRunHooks[object]()
    await hooks.on_agent_begin(None)  # type: ignore[arg-type]
    await hooks.on_tool_start(None, None, None)  # type: ignore[arg-type]
    await hooks.on_tool_end(None, None, None, None)  # type: ignore[arg-type]
    await hooks.on_agent_done(None, None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_database_protocol_stubs_are_callable():
    module = importlib.import_module("astrbot.core.db.protocols")
    invoked = 0
    for cls in _protocol_classes(module):
        for name, member in vars(cls).items():
            if name.startswith("_") or not callable(member):
                continue
            if inspect.iscoroutinefunction(member):
                try:
                    signature = inspect.signature(member)
                except TypeError, ValueError:
                    signature = None
                args = [object()]
                kwargs: dict[str, object] = {}
                if signature is not None:
                    for parameter in list(signature.parameters.values())[1:]:
                        if parameter.default is not inspect.Parameter.empty:
                            continue
                        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
                            continue
                        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
                            continue
                        if parameter.kind is inspect.Parameter.KEYWORD_ONLY:
                            kwargs[parameter.name] = object()
                        else:
                            args.append(object())
                result = member(*args, **kwargs)
                if inspect.isawaitable(result):
                    await result
                invoked += 1
            else:
                try:
                    member(object())
                    invoked += 1
                except TypeError:
                    continue
    assert invoked >= 20
