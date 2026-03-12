# CLAUDE Notes

- 2026-03-12: Legacy `handshake` payloads only contain `event_type` / `handler_full_name` metadata and do not preserve v4 command/message trigger details such as command names, aliases, keywords, or regex. Any legacy-to-v4 handshake translation must approximate handlers as coarse event subscriptions and keep the raw handshake payload in metadata for lossless fallback.
- 2026-03-12: `src/astrbot_sdk/tests/start_client.py` and `benchmark_8_plugins_resource_usage.py` still reference legacy `astrbot_sdk.runtime.galaxy`, but `src-new/astrbot_sdk/runtime/galaxy.py` no longer exists. Treat `tests_v4/test_script_migrations.py` as the maintained replacement instead of reviving the old Galaxy path.
- 2026-03-12: Legacy `src/astrbot_sdk/api/event/filter.py` exported a much larger decorator surface than `src-new/astrbot_sdk/api/event/filter.py`. Current compat coverage is enough for `command` / `regex` / `permission` and the exercised migration tests, but it is not a full drop-in replacement for every historical filter helper.
- 2026-03-13: Transport-pair startup tests for `SupervisorRuntime` must start a real peer on the opposite transport and provide an `initialize` response. Wiring only the supervisor side drops or captures the outgoing initialize message without replying, and `Peer.initialize()` then waits forever.
- 2026-03-13: `CapabilityRouter.register(..., stream_handler=...)` uses the signature `(request_id, payload, cancel_token)`, not the peer-level `(message, token)`. Reusing the peer handler shape in router tests causes an immediate failed stream event before the test logic runs.
- 2026-03-13: `Peer` had an early-cancel race for inbound invokes: if `CancelMessage` arrived before the invoke task executed its first line, the task could be cancelled before sending any terminal event, leaving the caller's stream iterator waiting forever. Preserve a per-request start event and pre-check the cancel token at the top of `_handle_invoke`.
- 2026-03-13: `src-new/astrbot_sdk/api` and several top-level module docstrings overstated v4 compatibility gaps by labeling migrated or compat-backed APIs as "missing". Treat `_legacy_api.py`, `astrbot_sdk.api.*` thin re-exports, and top-level `events.py` / `decorators.py` as a split compatibility surface; do not mechanically recreate the old tree from stale TODO comments.
- 2026-03-13: Legacy components are expected to share one `LegacyContext` per plugin, matching the old `StarManager` behavior. Creating one compat context per component breaks `_register_component()` / `call_context_function()` cross-component registration chains and diverges from legacy semantics.
- 2026-03-13: `WorkerSession` cannot assume the caller-provided `repo_root` contains `src-new/astrbot_sdk`. Tests and external bootstraps may pass a temporary repo root while still expecting the in-tree SDK package to launch worker subprocesses via `python -m astrbot_sdk`. Resolve the SDK source directory from the real package location when the supplied root does not contain it.
- 2026-03-13: `MemoryClient.get()` is part of the supported v4 client surface and must stay in sync with `CapabilityRouter` built-ins. The client method existed while the router forgot to register `memory.get`, which caused a real runtime gap hidden by API shape alone.
- 2026-03-13: When checking whether a peer has finished remote initialization, avoid `getattr(mock, "remote_peer")` style probes in code that may receive `MagicMock` peers. `MagicMock` fabricates truthy child attributes, so `CapabilityProxy` should read explicit state from `peer.__dict__` or another concrete storage location instead of treating arbitrary attribute access as initialization.
- 2026-03-13: The repository has no legacy `src/astrbot_sdk/protocol` package to migrate file-for-file. `src-new/astrbot_sdk/protocol` is a v4-native protocol layer; compare it against legacy JSON-RPC behavior in `src/astrbot_sdk/runtime/*` and the maintained migration tests, not against a nonexistent old package tree.
- 2026-03-13: `load_plugin()` must not blindly `getattr()` every name from `dir(instance)` during handler discovery. Real plugins may expose properties or descriptors with side effects or exceptions; inspect attributes statically first, and only bind names that actually carry handler metadata.
- 2026-03-13: In `Peer`, “remote initialized” and “transport still alive” are separate states. Waiting for initialization must fail when the connection closes first, and malformed inbound protocol messages should actively fail pending calls instead of leaving futures/streams hanging.
- 2026-03-13: Several first-layer files under `src-new/astrbot_sdk/*.py` carried stale migration comparison blocks that claimed missing CLI help, missing compat APIs, or other gaps already covered by tests and current implementations. Treat those comments as historical noise; verify behavior against code and tests before "restoring" features from the comments.
- 2026-03-13: The v4 design already defines built-in capability schema governance and reserved namespaces at the protocol layer. Keeping anonymous schema builders only inside `runtime/capability_router.py` drifts runtime behavior away from the protocol contract; centralize built-in schemas and namespace constants in `protocol/descriptors.py`.

# 开发命令

## 格式化与检查

在提交代码前，请依次运行以下命令：

```bash
pyclean .          # 清理 Python 缓存文件
ruff format .      # 使用 ruff 格式化代码
ruff check . --fix # 使用 ruff 检查并自动修复问题
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
