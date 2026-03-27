## ADDED Requirements

### Requirement: In-Process Plugin Loading
进程内插件直接加载为 Python 模块，由 Rust 核心调用。

#### Scenario: Load In-Process Plugin
- **WHEN** 配置指定 `load_mode: "in_process"`
- **THEN** 主进程直接导入插件模块
- **AND** 创建插件实例，传入 context、user_config、data_dirs

#### Scenario: In-Process Plugin Invocation
- **WHEN** 调用插件方法
- **THEN** 直接通过 Python 对象调用
- **AND** 不经过序列化/反序列化

### Requirement: Out-of-Process Plugin Loading
进程外插件作为独立进程运行，通过传输层通信。

#### Scenario: Load Out-of-Process Plugin
- **WHEN** 配置指定 `load_mode: "out_of_process"`
- **THEN** 主进程启动插件子进程
- **AND** 建立传输层连接（Stdio/Unix Socket/HTTP）

#### Scenario: Plugin Process Management
- **WHEN** 插件进程异常退出
- **THEN** 主进程记录错误日志
- **AND** 通知相关系统组件
- **AND** 可选：自动重启插件

### Requirement: Plugin Configuration
插件配置通过配置文件声明，不包含敏感信息和内部配置。

#### Scenario: Plugin Config Declaration
- **WHEN** 用户在 AstrBot 配置中声明插件
- **THEN** 仅包含 name、load_mode、command、args、transport、url
- **AND** 不包含插件内部配置

#### Scenario: User Config Delivery
- **WHEN** 插件初始化时
- **THEN** 主进程通过握手将 user_config 传递给插件
- **AND** user_config 来自 secrets.yaml 或 WebUI
