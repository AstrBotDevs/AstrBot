# CLAUDE Notes

- 2026-03-12: `refactor.md` on disk was empty, while the active collaboration context contained the full v4 refactor design. Treat the conversation-approved v4 design as source of truth unless a newer committed document replaces it.
- 2026-03-12: Legacy `handshake` payloads only contain `event_type` / `handler_full_name` metadata and do not preserve v4 command/message trigger details such as command names, aliases, keywords, or regex. Any legacy-to-v4 handshake translation must approximate handlers as coarse event subscriptions and keep the raw handshake payload in metadata for lossless fallback.
- 2026-03-12: `src/astrbot_sdk/tests/start_client.py` and `benchmark_8_plugins_resource_usage.py` still reference legacy `astrbot_sdk.runtime.galaxy`, but `src-new/astrbot_sdk/runtime/galaxy.py` no longer exists. Treat `tests_v4/test_script_migrations.py` as the maintained replacement instead of reviving the old Galaxy path.
- 2026-03-12: Legacy `src/astrbot_sdk/api/event/filter.py` exported a much larger decorator surface than `src-new/astrbot_sdk/api/event/filter.py`. Current compat coverage is enough for `command` / `regex` / `permission` and the exercised migration tests, but it is not a full drop-in replacement for every historical filter helper.
- 2026-03-13: Transport-pair startup tests for `SupervisorRuntime` must start a real peer on the opposite transport and provide an `initialize` response. Wiring only the supervisor side drops or captures the outgoing initialize message without replying, and `Peer.initialize()` then waits forever.
- 2026-03-13: `CapabilityRouter.register(..., stream_handler=...)` uses the signature `(request_id, payload, cancel_token)`, not the peer-level `(message, token)`. Reusing the peer handler shape in router tests causes an immediate failed stream event before the test logic runs.
- 2026-03-13: `Peer` had an early-cancel race for inbound invokes: if `CancelMessage` arrived before the invoke task executed its first line, the task could be cancelled before sending any terminal event, leaving the caller's stream iterator waiting forever. Preserve a per-request start event and pre-check the cancel token at the top of `_handle_invoke`.

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