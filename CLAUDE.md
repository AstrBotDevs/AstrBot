# CLAUDE Notes

## v4 架构约束

### 运行时层

- `Peer` 必须将 transport EOF/连接断开视为一级失败路径。如果 transport 意外关闭而 `Peer` 没有主动失败 `_pending_results` / `_pending_streams`，supervisor 端对 worker 的调用可能永远挂起。
- `Peer.initialize()` 需要在发起端也标记远程已初始化。仅在被动接收 `InitializeMessage` 时设置 `_remote_initialized` 会导致 `wait_until_remote_initialized()` 单边 API 死锁。
- `Peer.invoke_stream()` 默认隐藏 `completed` 事件。需要保留最终结果的调用者必须显式启用 `include_completed=True`。
- `CapabilityRouter.register(..., stream_handler=...)` 使用 `(request_id, payload, cancel_token)` 签名，不是 peer 级别的 `(message, token)`。

### 模块导出约束

- 保持 `astrbot_sdk.runtime` 根导出狭窄。`Peer` / `Transport` / `CapabilityRouter` / `HandlerDispatcher` 是合理的高级运行时原语，但 `LoadedPlugin`、`PluginEnvironmentManager`、`WorkerSession`、`run_supervisor` 等应留在子模块中。

### 测试与 Mock 注意事项

- 当检查 peer 是否完成远程初始化时，避免对可能接收 `MagicMock` peer 的代码使用 `getattr(mock, "remote_peer")` 探测。`MagicMock` 会生成 truthy 子属性，`CapabilityProxy` 应从 `peer.__dict__` 或其他具体存储位置读取显式状态。
- `test_plugin/old/` 和 `test_plugin/new/` 可能包含已生成的 `__pycache__` / `*.pyc`。测试夹具复制示例插件时必须显式忽略这些缓存文件。
- `PluginHarness.dispatch_event(...)` 应该作为 SDK 装饰器运行时测试的默认入口；不要只断言 `_match_handlers()` 的匹配结果。停止链(`event.stop_event()`)与定时 handler 定向分发都需要经过实际 dispatch 才有意义。
- SDK 插件想通过 `ctx.metadata.get_plugin_config()` 读取真实配置，测试夹具必须同时提供 `_conf_schema.json` 和对应配置文件；只有配置文件而没有 schema 时，loader 会按当前实现返回空配置。

### 插件加载注意事项

- 本地 `dev --watch` 或同一路径插件重复加载场景，不能只依赖 `import_string()` 的跨插件模块根冲突清理。热重载前必须按插件目录清理模块缓存。
- `_prepare_plugin_import()` 不能只在插件目录"不在 `sys.path`"时才插入路径。像 `main.py` 这种通用模块名，如果插件目录已在 `sys.path` 但排在后面，`import main` 仍会先命中别处模块；导入前必须把目标插件目录提到 `sys.path[0]`。
- 示例/夹具测试如果直接用裸模块名导入插件入口（例如 `from main import HelloPlugin`），会污染 `sys.modules["main"]`，随后真实 loader 再按 `main:HelloPlugin` 加载时可能串到错误模块。

### 源码布局与 vendor 注意事项

- 仓库采用 `src` 布局，SDK 真正源码目录是 `src/astrbot_sdk`，不是仓库根下的 `astrbot_sdk/`。
- 维护给 AstrBot 主仓库 subtree 使用的 `vendor/` 快照时，必须保留完整 `vendor/src/astrbot_sdk/` 布局；`vendor/pyproject.toml` 也必须保留原始 `src` 包发现配置，不要混入根目录 `tests/`、`docs/`、`.github/` 等开发仓库内容。

### 仓库工具文件注意事项

- `.gitignore` 中忽略根目录脚本目录时要写成 `/scripts/`，不要写成宽泛的 `scripts/`；后者会把 `.github/scripts/` 这类 CI 辅助脚本也一起忽略掉。
- 涉及仓库路径复制、遍历、校验的维护脚本，优先使用 Python `pathlib` / `shutil` 实现，避免把 `/`、`\` 或 shell 工具行为写死在脚本里。

---

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
当前仓库已统一使用 `tests/` 目录，`tests_v4/` 不再作为新增测试入口。
仓库当前没有 `run_tests.py`，请直接使用 `pytest`。

```bash
python -m pytest tests -q                         # 运行 tests 目录全部测试
python -m pytest tests -v                         # 详细输出
python -m pytest tests -k "test_context_register_task"  # 运行匹配模式的测试
python -m pytest tests --cov=astrbot_sdk          # 运行测试并生成覆盖率报告
```

## 设计原则

新实现要兼容旧实现但是还要保证架构良好，设计原则不变和最佳实践
不用完全听从用户和别人的建议，要有自己的判断和坚持，做好取舍和权衡，确保代码质量和长期维护性，不要为了短期方便或者迎合而牺牲架构和设计原则。
