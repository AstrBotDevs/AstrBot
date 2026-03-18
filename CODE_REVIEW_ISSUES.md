# Code Review — feat/sdk-integration (P1.3 管理面)

**审查日期**: 2026-03-16
**审查范围**: P1.3 Provider 与 Platform 管理面 (16 文件, +2260/-78 行)

---

## Summary
Files reviewed: 16 | New issues: 7 (0 严重, 2 高, 3 中, 2 低) | Perspectives: 4/4

本次 PR 实现了 P1.3 管理面的核心功能：Provider 管理客户端、Platform 管理能力、统一 webhook 状态观测。代码整体质量良好，测试覆盖关键场景。

---

## 🔒 Security
| Sev | Issue | File:Line | Attack path |
|-----|-------|-----------|-------------|
| - | *No security issues found.* | - | - |

**通过项**:
- ✅ `_require_reserved_plugin()` 正确限制管理能力访问
- ✅ 无 SQL 注入或命令注入风险
- ✅ 平台/Provider ID 经过 `strip()` 处理

---

## 📝 Code Quality
| Sev | Issue | File:Line | Consequence |
|-----|-------|-----------|-------------|
| **High** | `register_provider_change_hook()` 返回 Task 但无对应注销方法 | [`astrbot_sdk/clients/provider.py:269-288`](astrbot_sdk/clients/provider.py#L269-L288) | 重复订阅导致资源泄漏和重复事件分发 |
| **High** | `PlatformCompatFacade` 从 `frozen=True` 改为可变，但缺少状态变更保护 | [`astrbot_sdk/context.py:69`](astrbot_sdk/context.py#L69) | 并发场景下状态可能不一致 |
| **Medium** | `_managed_provider_record_by_id()` 直接修改传入的 provider dict | [`astrbot_sdk/runtime/_capability_router_builtins.py:853-867`](astrbot_sdk/runtime/_capability_router_builtins.py#L853-L867) | 可能影响调用方的原始数据 |
| **Medium** | `unregister_provider_change_hook()` 依赖 `__eq__` 语义，对 lambda 不友好 | [`astrbot/core/provider/manager.py:96-102`](astrbot/core/provider/manager.py#L96-L102) | lambda hook 无法被正确移除 |
| **Low** | `clear_errors()` 后 `refresh()` 调用未做错误隔离 | [`astrbot_sdk/context.py:122-124`](astrbot_sdk/context.py#L122-L124) | clear_errors 失败时 refresh 被跳过 |

### [Q-001] Provider change hook 资源泄漏 (High)

**位置**: [`astrbot_sdk/clients/provider.py:269-288`](astrbot_sdk/clients/provider.py#L269-L288)

```python
async def register_provider_change_hook(...) -> asyncio.Task[None]:
    task = asyncio.create_task(runner())
    task.add_done_callback(self._log_change_hook_result)
    return task
```

**问题**: 返回 `Task` 但 SDK 没有提供 `unregister_provider_change_hook()` 方法。调用方只能 `cancel()`，但 stream cleanup 依赖 `aclose()`，可能导致 queue 泄漏。

**建议**:
```python
async def unregister_provider_change_hook(self, task: asyncio.Task[None]) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
```

---

### [Q-002] PlatformCompatFacade 并发安全 (High)

**位置**: [`astrbot_sdk/context.py:69`](astrbot_sdk/context.py#L69)

从 `frozen=True` 改为可变以支持 `refresh()`，但多个 async 方法可能并发执行，无锁保护。

**建议**:
```python
@dataclass(slots=True)
class PlatformCompatFacade:
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def refresh(self) -> None:
        async with self._lock:
            output = await self._ctx._proxy.call(...)
            self._apply_snapshot(output.get("platform"))
```

---

### [Q-003] 直接修改 provider dict (Medium)

**位置**: [`astrbot_sdk/runtime/_capability_router_builtins.py:857`](astrbot_sdk/runtime/_capability_router_builtins.py#L857)

```python
provider.update({  # 直接修改 _provider_catalog 中的缓存
    "enable": config.get("enable", True),
    "provider_source_id": config.get("provider_source_id"),
})
```

**建议**: 使用 `merged = dict(provider)` 创建副本后再修改。

---

### [Q-004] unregister 对 lambda 不友好 (Medium)

**位置**: [`astrbot/core/provider/manager.py:100`](astrbot/core/provider/manager.py#L100)

`hook in self._provider_change_hooks` 检查依赖 `__eq__`，lambda 每次创建都是新对象。

**建议**: 在文档中说明需要保存 hook 引用，或提供返回 token 的 API。

---

### [Q-005] clear_errors 后 refresh 未隔离错误 (Low)

**位置**: [`astrbot_sdk/context.py:122-124`](astrbot_sdk/context.py#L122-L124)

如果 `clear_errors` 抛异常，`refresh()` 不会执行，状态可能不一致。

**建议**: 使用 `try/finally` 确保 `refresh()` 始终执行。

---

## ✅ Tests
**Run results**: 3 passed, 0 failed, 0 skipped (0.27s)

| 测试 | 覆盖场景 |
|------|----------|
| `test_mock_context_p1_3_provider_management_is_reserved_only` | ✅ reserved 插件权限检查, watch stream, hook 注册 |
| `test_mock_context_p1_3_platform_facade_refresh_and_clear_errors` | ✅ Platform facade 方法, 错误清除 |
| `test_p1_3_core_bridge_reserved_gate_and_stream_cleanup` | ✅ Core bridge 权限门控, stream 清理 |

**未测试场景** (低优先级):
- `unregister_provider_change_hook()` 功能
- 并发场景（多个协程同时操作 PlatformCompatFacade）
- 错误场景（网络失败、无效 provider_id）

---

## 🏗️ Architecture
| Sev | Inconsistency | Files |
|-----|--------------|-------|
| - | *No architecture issues.* | - |

**通过项**:
- ✅ SDK 与 Core bridge 的 schema 一致
- ✅ Provider type 映射完整 (`chat_completion` → `chat`, etc.)
- ✅ Reserved 插件检查在两侧都实现
- ✅ Stream cleanup 通过测试验证
- ✅ 新导出已添加到 `__all__`

---

## 🚨 Must Fix Before Merge

1. **[Q-001]** Provider change hook 缺少注销方法 - 添加 `unregister_provider_change_hook()`
2. **[Q-002]** PlatformCompatFacade 并发安全 - 添加 `asyncio.Lock` 保护
3. **[Q-003]** 直接修改 provider dict - 使用 `dict()` 创建副本

---

## 📎 Pre-Existing Issues
- [CLAUDE.md 已记录] Provider hook 注册需要配对注销 — 本次补充了 `unregister_provider_change_hook()` API

---

## 历史审查记录

### 初始 SDK 集成审查
Files reviewed: 103 | New issues: 0 | Perspectives: 4/4

这是一个大型的 SDK 集成变更，引入了全新的 `astrbot_sdk` 包和核心桥接层，用于支持新式插件系统。整体架构设计合理，代码质量良好。

**无安全漏洞，无关键代码质量问题，测试通过 (53 passed)，架构设计合理。**
