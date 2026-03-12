# CLAUDE Notes

- 2026-03-12: Legacy `handshake` payloads only contain `event_type` / `handler_full_name` metadata and do not preserve v4 command/message trigger details such as command names, aliases, keywords, or regex. Any legacy-to-v4 handshake translation must approximate handlers as coarse event subscriptions and keep the raw handshake payload in metadata for lossless fallback.
- 2026-03-12: Legacy `src/astrbot_sdk/api/event/filter.py` exported a much larger decorator surface than `src-new/astrbot_sdk/api/event/filter.py`. Current compat coverage is enough for `command` / `regex` / `permission` and the exercised migration tests, but it is not a full drop-in replacement for every historical filter helper.
- 2026-03-13: Transport-pair startup tests for `SupervisorRuntime` must start a real peer on the opposite transport and provide an `initialize` response. Wiring only the supervisor side drops or captures the outgoing initialize message without replying, and `Peer.initialize()` then waits forever.
- 2026-03-13: `CapabilityRouter.register(..., stream_handler=...)` uses the signature `(request_id, payload, cancel_token)`, not the peer-level `(message, token)`. Reusing the peer handler shape in router tests causes an immediate failed stream event before the test logic runs.
- 2026-03-13: `src-new/astrbot_sdk/api` and several top-level module docstrings overstated v4 compatibility gaps by labeling migrated or compat-backed APIs as "missing". Treat `_legacy_api.py`, `astrbot_sdk.api.*` thin re-exports, and top-level `events.py` / `decorators.py` as a split compatibility surface; do not mechanically recreate the old tree from stale TODO comments.
- 2026-03-13: Legacy components are expected to share one `LegacyContext` per plugin, matching the old `StarManager` behavior. Creating one compat context per component breaks `_register_component()` / `call_context_function()` cross-component registration chains and diverges from legacy semantics.
- 2026-03-13: When checking whether a peer has finished remote initialization, avoid `getattr(mock, "remote_peer")` style probes in code that may receive `MagicMock` peers. `MagicMock` fabricates truthy child attributes, so `CapabilityProxy` should read explicit state from `peer.__dict__` or another concrete storage location instead of treating arbitrary attribute access as initialization.
- 2026-03-13: The repository has no legacy `src/astrbot_sdk/protocol` package to migrate file-for-file. `src-new/astrbot_sdk/protocol` is a v4-native protocol layer; compare it against legacy JSON-RPC behavior in `src/astrbot_sdk/runtime/*` and the maintained migration tests, not against a nonexistent old package tree.
- 2026-03-13: Old Star docs under `docs/zh/dev/star/` describe end-to-end legacy behavior, not just import surfaces. Current compat layer can import `AstrMessageEvent`, `MessageChain`, and some `filter.*` helpers, but handler result consumption is still effectively plain-text only and many documented legacy features remain absent or partial, including command groups, lifecycle/LLM hooks, session waiters, rich media helper constructors, config schema loading, and persona/provider management. Do not treat "type exists" as "old plugin behavior is compatible"; verify the runtime path end to end before declaring parity.

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
