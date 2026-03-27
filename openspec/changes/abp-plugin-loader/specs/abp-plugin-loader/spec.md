## ADDED Requirements

### Requirement: PluginLoader Trait
ABP 插件加载器抽象接口，定义进程内/外插件的统一加载方式。

#### Scenario: Load In-Process Plugin
- **WHEN** 配置指定 `load_mode: "in_process"`
- **THEN** `InProcessPluginLoader` 直接导入 Python 模块
- **AND** 实例化插件，传入 context、user_config、data_dirs
- **AND** 将插件实例注册到 `PluginRegistry`

#### Scenario: Load Out-of-Process Plugin
- **WHEN** 配置指定 `load_mode: "out_of_process"`
- **THEN** `OutOfProcessPluginLoader` 启动插件子进程
- **AND** 建立传输层连接（Stdio/Unix Socket/HTTP）
- **AND** 执行握手协议交换配置

#### Scenario: Unload Plugin
- **WHEN** 调用 `loader.unload(plugin_id)`
- **THEN** 关闭插件连接/释放模块引用
- **AND** 从 `PluginRegistry` 注销插件

#### Scenario: Reload Plugin
- **WHEN** 调用 `loader.reload(plugin_id)`
- **THEN** 卸载现有插件实例
- **AND** 重新加载并初始化插件

### Requirement: In-Process Plugin Loading
进程内插件由 Rust FFI 核心管理生命周期，Python 胶水层仅做聚合。

#### Scenario: In-Process Plugin Invocation
- **WHEN** 调用进程内插件方法（如 `handle_event`）
- **THEN** 通过 Rust FFI `load_plugin()` 加载
- **AND** Python PluginRegistry 聚合插件实例
- **AND** 调用通过 Rust FFI 转发

#### Scenario: In-Process Plugin Context
- **WHEN** 插件实例化时
- **THEN** Rust 核心传入 context 对象
- **AND** 传入 user_config（来自握手）
- **AND** 传入 data_dirs（数据目录路径）

### Requirement: PluginRegistry
全局插件实例注册表，管理所有已加载插件。

#### Scenario: Register Plugin Instance
- **WHEN** 插件加载成功时
- **THEN** `PluginRegistry` 存储 plugin_id → PluginInstance 映射
- **AND** 插件暴露的工具注册到 `ToolRegistry`

#### Scenario: Query Plugin by ID
- **WHEN** 调用 `registry.get_plugin(plugin_id)`
- **THEN** 返回插件实例或 None

#### Scenario: List All Plugins
- **WHEN** 调用 `registry.list_plugins()`
- **THEN** 返回所有已注册插件的元数据列表
