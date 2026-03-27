## ADDED Requirements

### Requirement: Initialize Handshake
AstrBot 主进程 SHALL 发送 `initialize` 请求到插件，交换协议版本、客户端信息和配置。

#### Scenario: Successful Initialization
- **WHEN** 插件进程启动并准备就绪
- **THEN** 主进程发送 `initialize` 请求，包含 `protocolVersion`、`clientInfo`、`capabilities`、`pluginConfig`、`dataDirs`
- **AND** 插件返回 `initialized` 响应，包含 `protocolVersion`、`serverInfo`、`capabilities`、`configSchema`、`metadata`

#### Scenario: Version Mismatch
- **WHEN** 插件不支持客户端的协议版本
- **THEN** 插件返回 `-32211` (Version Mismatch) 错误码

### Requirement: Plugin Lifecycle Management
主进程 SHALL 管理插件的启动、停止、重载和配置更新。

#### Scenario: Start Plugin
- **WHEN** 主进程需要激活插件
- **THEN** 发送 `plugin.start` 请求
- **AND** 插件进入工作状态

#### Scenario: Stop Plugin
- **WHEN** 主进程需要停用插件
- **THEN** 发送 `plugin.stop` 请求
- **AND** 插件清理资源并进入空闲状态

#### Scenario: Reload Plugin
- **WHEN** 插件需要热重载
- **THEN** 发送 `plugin.reload` 请求
- **AND** 插件重新初始化但保持进程

#### Scenario: Config Update
- **WHEN** 用户更新插件配置
- **THEN** 主进程发送 `plugin.config_update` 通知
- **AND** 插件更新内部配置

### Requirement: Plugin Error Handling
插件 SHALL 返回标准错误码用于问题诊断。

#### Scenario: Plugin Not Found
- **WHEN** 请求的插件不存在
- **THEN** 返回 `-32200` (Plugin Not Found) 错误码

#### Scenario: Plugin Not Ready
- **WHEN** 请求时插件未完成初始化
- **THEN** 返回 `-32201` (Plugin Not Ready) 错误码

#### Scenario: Plugin Crashed
- **WHEN** 插件进程异常退出
- **THEN** 主进程检测到并返回 `-32202` (Plugin Crashed) 错误码
