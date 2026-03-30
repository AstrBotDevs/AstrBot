## Why

ABP 协议实现第一阶段完成了核心握手、传输层和事件系统。当前 PluginLoader trait 和 InProcess 插件加载尚未实现，工具发现依赖 `tools/list`，FFI 绑定也未完成。这些是 ABP 插件系统真正可用的最后几块拼图。

## What Changes

- **PluginLoader  trait**：定义插件加载抽象，支持进程内/外两种模式
- **InProcessPluginLoader**：实现 Python 模块直接加载（无需进程通信）
- **tools/list 端点**：插件暴露可用工具列表
- **工具 Schema 验证**：JSON Schema Draft-07 校验
- **跨插件工具发现**：统一聚合所有插件的工具
- **FFI 绑定**：Python 胶水层调用 Rust ABP 核心
- **配置集成**：config.yaml 插件配置落地，PluginRegistry 实现
- **测试完善**：单元测试 + 集成测试覆盖

## Capabilities

### New Capabilities

- `abp-plugin-loader`: 插件加载器 trait 和实现（InProcess/OutOfProcess）
- `abp-tool-discovery`: 工具注册、Schema 验证、跨插件发现

### Modified Capabilities

- `abp-protocol`: FFI 绑定补充（Python → Rust 核心调用链路）
- `abp-tool-router`: 增加 `tools/list` 端点实现

## Impact

- **新增**：`astrbot/core/plugin/` 扩展（loader 模块）
- **修改**：`astrbot/core/plugin/plugin_manager.py`（FFI 绑定）
- **依赖**：Rust 核心 `_core.so` 已编译，源码待提交 `astrbot/rust/src/`
