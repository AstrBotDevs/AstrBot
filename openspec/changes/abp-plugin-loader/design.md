## Context

ABP 协议第一阶段完成了核心握手、传输层和事件系统。当前 `OutOfProcessPluginLoader` 已实现，但：
1. `PluginLoader` trait 未定义，InProcess 模式缺失
2. `tools/list` 端点未实现，工具发现依赖它
3. Python FFI 绑定未完成，Python 层无法调用 Rust 核心
4. 配置集成未落地，无 PluginRegistry

## Goals / Non-Goals

**Goals:**
- 实现 `PluginLoader` trait，统一进程内/外加载逻辑
- 实现 `InProcessPluginLoader`，Python 模块直接加载
- 实现 `tools/list` 端点和工具 Schema 验证
- 完成 Python FFI 绑定链路
- 落地 config.yaml 插件配置和 PluginRegistry

**Non-Goals:**
- 不实现 Stars → ABP 插件迁移（下一阶段）
- 不实现 WebUI 插件配置界面（config.yaml 落地即可）
- 不改变 Rust 核心源码（仅调用已有接口）

## Decisions

### 1. PluginLoader Trait 设计

**决定**：定义抽象 trait，包含 `load()`、`unload()`、`reload()`、`get_plugin_info()` 方法。

```python
class PluginLoader(ABC):
    @abstractmethod
    async def load(self, config: PluginConfig) -> PluginInstance: ...

    @abstractmethod
    async def unload(self, plugin_id: str) -> None: ...

    @abstractmethod
    async def reload(self, plugin_id: str) -> PluginInstance: ...
```

**替代方案**：
- 工厂模式（被否定）：增加抽象层级，当前场景不需要
- 统一接口参数（被否定）：进程内/外行为差异大，分离更清晰

### 2. InProcessPluginLoader 实现

> **⚠️ 架构约束**：核心加载逻辑在 Rust FFI，Python 仅做胶水层

**决定**：`PluginLoader` trait 定义在 Python，`load/unload/reload` 实现调用 Rust FFI（`load_plugin()`/`unload_plugin()`）。

```python
class InProcessPluginLoader(PluginLoader):
    async def load(self, plugin_id, config, data_dirs):
        # 调用 Rust FFI: _core.load_plugin(config)
        result = await rust_ffi.load_plugin(plugin_id, config, data_dirs)
        return PluginInstance(plugin_id, result.instance, ...)
```

**理由**：
- 核心加载逻辑在 Rust（线程安全、错误隔离）
- Python 胶水层仅做类型转换和聚合
- 符合 config.yaml `rust_core` 规范

### 3. 工具发现架构

**决定**：`ToolRegistry` 统一管理，`tools/list` 聚合所有插件工具。

```
ToolRegistry
├── register(plugin_id, tools)
├── unregister(plugin_id)
├── list_tools() -> List[ToolDef]
└── call_tool(name, args) -> ToolResult
```

**理由**：
- 中心化管理避免冲突
- Schema 验证在注册时执行
- 跨插件工具调用统一入口

### 4. FFI 绑定链路

> **⚠️ 禁止 ctypes**：所有 FFI 必须通过 PyO3（rust-ffi.md 规范）

**决定**：Python → PyO3 `_core.so` → ABP PluginLoader。

```
Python PluginRegistry (_internal/)
  → PyO3 调用 _core.so
  → Rust abp_plugin_loader_* 函数
  → 返回 Python 对象（通过 .pyi 类型提示）
```

**理由**：
- PyO3 是 Rust 官方 Python 绑定方案
- `rust-ffi.md` 明确禁止 ctypes
- `_core.pyi` 提供类型检查
- anyio 异步调用通过 `run_in_executor` 封装

## Risks / Trade-offs

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Rust 源码未提交，接口可能变 | FFI 调用失败 | 接口版本化，核心保持向后兼容 |
| InProcess 插件崩溃影响主进程 | 稳定性下降 | 进程内插件加超时保护 + 错误隔离 |
| 工具 Schema 验证复杂度 | 开发体验下降 | JSON Schema 仅校验格式，不校验业务逻辑 |

## Migration Plan

1. **Phase 1**：PluginLoader trait + Python 聚合层（调用 Rust FFI）
2. **Phase 2**：tools/list + ToolRegistry（Rust FFI + Python 聚合）
3. **Phase 3**：PyO3 FFI 绑定 + config.yaml 集成
4. **Phase 4**：测试覆盖 + 文档

## Open Questions

- Q1: InProcess 插件是否需要独立的沙箱隔离？（当前：无）
- Q2: 工具注册时 Schema 校验严格程度？（当前：格式校验 + 必需字段）
- Q3: PluginRegistry 是否需要持久化？（当前：内存，进程重启丢失）
