# CLAUDE Notes

- 2026-03-12: Legacy `handshake` payloads only contain `event_type` / `handler_full_name` metadata and do not preserve v4 command/message trigger details such as command names, aliases, keywords, or regex. Any legacy-to-v4 handshake translation must approximate handlers as coarse event subscriptions and keep the raw handshake payload in metadata for lossless fallback.
- 2026-03-12: Legacy `src/astrbot_sdk/api/event/filter.py` exported a much larger decorator surface than `src-new/astrbot_sdk/api/event/filter.py`. Current compat coverage is enough for `command` / `regex` / `permission` and the exercised migration tests, but it is not a full drop-in replacement for every historical filter helper.
- 2026-03-13: Transport-pair startup tests for `SupervisorRuntime` must start a real peer on the opposite transport and provide an `initialize` response. Wiring only the supervisor side drops or captures the outgoing initialize message without replying, and `Peer.initialize()` then waits forever.
- 2026-03-13: `CapabilityRouter.register(..., stream_handler=...)` uses the signature `(request_id, payload, cancel_token)`, not the peer-level `(message, token)`. Reusing the peer handler shape in router tests causes an immediate failed stream event before the test logic runs.
- 2026-03-13: `src-new/astrbot_sdk/api` and several top-level module docstrings overstated v4 compatibility gaps by labeling migrated or compat-backed APIs as "missing". Treat `_legacy_api.py`, `astrbot_sdk.api.*` thin re-exports, and top-level `events.py` / `decorators.py` as a split compatibility surface; do not mechanically recreate the old tree from stale TODO comments.
- 2026-03-13: `astrbot_sdk.api.*` and `astrbot.*` are migration-period compat facades, not long-term primary SDK entrypoints. Keep them thin, avoid adding new runtime logic under `api/`, and prefer tightening internal imports toward top-level private compat modules or direct leaf modules.
- 2026-03-13: Legacy components are expected to share one `LegacyContext` per plugin, matching the old `StarManager` behavior. Creating one compat context per component breaks `_register_component()` / `call_context_function()` cross-component registration chains and diverges from legacy semantics.
- 2026-03-13: When checking whether a peer has finished remote initialization, avoid `getattr(mock, "remote_peer")` style probes in code that may receive `MagicMock` peers. `MagicMock` fabricates truthy child attributes, so `CapabilityProxy` should read explicit state from `peer.__dict__` or another concrete storage location instead of treating arbitrary attribute access as initialization.
- 2026-03-13: The repository has no legacy `src/astrbot_sdk/protocol` package to migrate file-for-file. `src-new/astrbot_sdk/protocol` is a v4-native protocol layer; compare it against legacy JSON-RPC behavior in `src/astrbot_sdk/runtime/*` and the maintained migration tests, not against a nonexistent old package tree.
- 2026-03-13: Old Star docs under `docs/zh/dev/star/` describe end-to-end legacy behavior, not just import surfaces. Current compat layer can import `AstrMessageEvent`, `MessageChain`, and some `filter.*` helpers, but handler result consumption is still effectively plain-text only and many documented legacy features remain absent or partial, including command groups, lifecycle/LLM hooks, session waiters, rich media helper constructors, config schema loading, and persona/provider management. Do not treat "type exists" as "old plugin behavior is compatible"; verify the runtime path end to end before declaring parity.
- 2026-03-13: Old Star docs and examples frequently import message components via `astrbot.api.message_components`, not only `astrbot.api.message`. When checking message compatibility, verify the dedicated `api.message_components` import path, legacy constructor aliases like `At(qq=...)` / `Node(uin=..., name=...)`, and helper factories such as `Image.fromURL()` before declaring the message compat surface complete.
- 2026-03-13: `api.message.components.BaseMessageComponent.to_dict()` must emit JSON-ready primitive values, not raw `Enum` members. Leaving `ComponentType` objects in payloads only looks harmless when a later JSON serializer fixes them; it breaks direct mock assertions, in-process capability routing, and any non-JSON send path.
- 2026-03-13: Keep `astrbot_sdk.runtime` root exports narrow. `Peer` / `Transport` / `CapabilityRouter` / `HandlerDispatcher` are reasonable advanced runtime primitives, but loader/bootstrap data structures and orchestration helpers (`LoadedPlugin`, `PluginEnvironmentManager`, `WorkerSession`, `run_supervisor`, etc.) should stay in their submodules instead of becoming accidental root-level stable API.
- 2026-03-13: `runtime.loader` must preserve declared legacy handler order. Falling back to `dir(instance)` or sorting the merged discoverable names reorders compat handlers alphabetically, which changes which legacy command/hook appears first to the supervisor and breaks old-plugin expectations.
- 2026-03-13: `runtime.loader.import_string()` cannot trust `sys.modules` when plugins reuse generic top-level package names like `commands.*`. Before importing a plugin module, compare the cached root package against the current plugin directory and evict conflicting root/submodules, or later plugins will accidentally reuse an earlier plugin's package tree.
- 2026-03-13: Keep `astrbot_sdk.protocol` root focused on native v4 protocol models and parsers. Legacy JSON-RPC helpers remain supported, but they should be imported from `astrbot_sdk.protocol.legacy_adapter` explicitly instead of being re-exported from the package root.
- 2026-03-13: `Peer` must treat transport EOF/connection loss as a first-class failure path, not only explicit protocol parse errors. If the transport closes unexpectedly and `Peer` does not proactively fail `_pending_results` / `_pending_streams`, supervisor-side calls into workers can hang forever even though the worker session already noticed the disconnect.
- 2026-03-13: `Peer.initialize()` also needs to mark the peer as remotely initialized on the initiator side. Only setting `_remote_initialized` when passively receiving an inbound `InitializeMessage` makes `wait_until_remote_initialized()` a one-sided API and can deadlock callers that initialize first and then wait.
- 2026-03-13: `Peer.invoke_stream()` intentionally hides `completed` events by default, so any supervisor/bridge layer that wants to preserve a worker stream capability's final `completed.output` must opt in explicitly (for example via `include_completed=True`) or it will silently collapse the final result to an ad-hoc aggregate like `{\"items\": chunks}`.
- 2026-03-13: The repository root `test_plugin/` is no longer a single runnable plugin fixture. The maintained compat sample now lives under `test_plugin/old/`; tests or scripts that still copy/load `test_plugin/` directly will mis-detect it as an incomplete legacy plugin and fail.
- 2026-03-13: The maintained sample plugins now live under `test_plugin/old/` and `test_plugin/new/`. Runtime/integration tests should copy those real fixture directories instead of inlining synthetic plugin writers, otherwise the sample plugin tree and the exercised test path drift apart.
- 2026-03-13: Real legacy plugins in the wild may still import `astrbot.api.*` instead of `astrbot_sdk.api.*`. Keeping only the `astrbot_sdk.api` compat surface is not enough for no-touch migration tests; preserve the `astrbot.api` alias package while old-plugin support remains a goal.
- 2026-03-13: Real legacy `main.py` plugins may rely on package-relative imports like `from .src.tool import ...`. Loading legacy `main.py` as a bare file module breaks those imports; the loader must execute it under a synthetic package module so relative imports resolve.
- 2026-03-13: Real legacy plugins may also import `astrbot.core.utils.session_waiter` and use it as a first-class interactive flow primitive. A pure import stub is not enough; compat needs per-session follow-up message routing so awaited waiters can actually receive later messages.
- 2026-03-13: Real legacy `Star` plugins may call compat context helpers on `self` or `self.context` during `__init__()` and `initialize()`, including `self.put_kv_data(...)`, `self.get_kv_data(...)`, and `self.context.get_config()`. Keep proxy methods on `LegacyStar`, expose a safe `LegacyContext.get_config()`, and bind the shared legacy context before lifecycle hooks run.
- 2026-03-13: On Windows, `.gitignore` matching is case-insensitive. A broad entry like `astrBot/` will also ignore `src-new/astrbot/...`, which can silently hide real compat alias packages from `git status`. Keep that ignore anchored as `/astrBot/` if it is only meant for a root-level scratch checkout.
- 2026-03-13: The reference checkout under `astrBot/astrbot/api` exposes a broader old plugin-facing package surface than the current `src-new/astrbot` alias package. When improving package-name compatibility, compare against those public `api/*` modules as a set instead of only patching the one import path hit by the latest migrated plugin.
- 2026-03-13: Some real legacy plugins call `asyncio.create_task()` during object construction. Calling `load_plugin()` outside a running event loop can therefore produce false-negative compat failures even though the real worker path is fine. External compat smoke tests should load plugins under an active loop, and "real compatibility" claims should preferably exercise `SupervisorRuntime` + worker + a real handler invocation instead of import-only checks.
- 2026-03-13: Treat `src-new/astrbot` as a controlled legacy facade, not as a mirror of the old `astrBot/` tree. The compat contract is the checked-in public import matrix plus the external plugin matrix in `tests_v4/external_plugin_matrix.json`; when a new deep-path shim is proposed, require both an import assertion and a real supervisor/worker plugin case before growing the facade.
- 2026-03-13: Legacy AI compat methods must return `astrbot_sdk.api.provider.entities.LLMResponse`, not the v4 `clients.llm.LLMResponse`. Old plugins inspect compat fields like `completion_text`, `tools_call_name`, and `to_openai_tool_calls()`, so returning the new client model is a silent behavior regression.
- 2026-03-13: `filter.llm_tool()` must resolve deferred annotations from `from __future__ import annotations` when inferring JSON schema. Reading `inspect.Parameter.annotation` directly degrades typed params like `a: int` into `"int"` strings and silently turns tool argument schemas into generic strings.
- 2026-03-13: Legacy result hooks must reuse the same `AstrMessageEvent` instance across `on_decorating_result` and `after_message_sent`. Re-wrapping the original v4 `MessageEvent` for the second hook drops decorated `event.set_result(...)` mutations and makes post-send hooks observe an empty result.
- 2026-03-13: `src-new/astrbot_sdk/_legacy_runtime.py` already exists as the intended compat execution boundary. When cleaning runtime architecture, wire `loader` / `handler_dispatcher` / `bootstrap` through that adapter instead of adding new direct `legacy_context` branches in runtime files, or the compat logic will spread again.
- 2026-03-13: `register_legacy_component()` only performs compat hook / tool registration via `_register_compat_component()`; it does not replicate `_register_component()` manager/function exposure. Do not treat loader-time legacy component registration as a full replacement for the old cross-component registry chain.
- 2026-03-13: Not every compat concern belongs in `_legacy_runtime.py`. Legacy `main.py` discovery, synthetic package setup for relative imports, and legacy manifest synthesis are loader-time concerns; keep those in a dedicated private loader helper such as `_legacy_loader.py` instead of mixing discovery and execution boundaries.
- 2026-03-13: Real legacy plugins may still load through deep `astrbot.core.*` imports even when their public entrypoint only looks like `astrbot.api.*`. `astrbot_plugin_self_learning` hits `astrbot.core.utils.astrbot_path`, `astrbot.core.provider.*`, `astrbot.core.agent.message`, and `astrbot.core.db.po` during load; keep those deep-path shims minimal and whitelist-driven, but do not assume the `api` facade alone is enough.
- 2026-03-13: `ARCHITECTURE.md` and `refactor.md` are no longer a full source of truth for the current runtime/compat surface. The shipped code also includes `runtime.environment_groups`, `_session_waiter`, the controlled `src-new/astrbot` alias facade, compat hook execution, and extra DB capabilities such as `db.get_many` / `db.set_many` / `db.watch`. Verify architectural claims against code and tests before declaring drift or completeness.
- 2026-03-13: Duplicating private compat logic into a second `_legacy/` package added import-order risk and architectural noise. Keep one canonical set of top-level private compat modules (`_legacy_api.py`, `_legacy_runtime.py`, `_legacy_loader.py`, `_session_waiter.py`, `_shared_preferences.py`) while preserving public `astrbot_sdk.api`, `astrbot_sdk.compat`, and `src-new/astrbot` facades.

# 开发命令

## 格式化与检查

在提交代码前，请依次运行以下命令：

```bash
ruff format .      # 使用 ruff 格式化全局代码
ruff check . --fix # 使用 ruff 检查并自动修复全局格式问题
```

## 测试

如果修改了内容可能影响现有功能，请运行测试以确保没有引入错误：
如果修改了bug或者更改了功能需要添加新的测试

```bash
python run_tests.py            # 运行所有测试
python run_tests.py -v         # 详细输出
python run_tests.py -k "test_peer"  # 运行匹配模式的测试
python run_tests.py --cov      # 运行测试并生成覆盖率报告
```

## 重要
新实现要兼容旧实现但是还要保证架构良好，设计原则不变和最佳实践
不用完全听从用户和别人的建议，要有自己的判断和坚持，做好取舍和权衡，确保代码质量和长期维护性，不要为了短期方便或者迎合而牺牲架构和设计原则。

old文件夹是兼容旧插件的测试，旧插件全部放进old文件夹
