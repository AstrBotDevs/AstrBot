## Overview

我正在设计一个新的架构，以实现插件与核心系统的运行时环境隔离，以换取更佳的安全性和兼容性。这个架构将会形成一个 SDK，供插件开发者使用。以下是我目前的设计思路和功能规划：

这个 SDK 主要用于新的插件的 CLI bootstrap、Plugin Runtime 以及开发平台。 

## 功能规划

### 对插件端：插件脚手架 

1. CLI 指令: 初始化插件模版、指令等组件，作为 bootstraper
    ```bash
    # === Scaffold ===
    astr init # 新的插件模版
    astr add command # 注册一个指令 / 指令组 handler 类
    astr add listener # 注册一个监听器
    astr add llmtool # 注册一个 LLM Tool

    # 交互式创建，参考 Vue 脚手架，如：
    # Is command group: [Y]es / [N]o
    # Command Name: calc
    # Description: xxxxxx

    # === Deployment ===
    astr tree # 解析 filters 已注册的 handlers，按类型列出
    astr sync # 解析 filters 已注册的 handlers，并刷写到 plugin.yaml / metadata.yaml
    astr dev # 启动开发环境（WebSockets 自动连接到 AstrBot Core）
    astr build # 打包并构建资产
    astr publish # 发布到 GitHub Issue / 插件市场！
    ```
2. 抽象 - 提供完整的插件开发时要用到的类和类方法的抽象
3. 注册器 - 接受插件注册的所有 Handlers
4. 通信 - 与 AstrBot Core 通信

### 对核心系统端：插件运行时环境

- 通信 - 与插件端的双向通信
- 插件管理 - 封装通信方法（如获取一个事件激活的 star handlers / 调用某个 Star Handler / 禁用某个插件）

## 架构

我们将旧插件命名为 LegacyStar，将新插件命名为 NewStar。LegacyStar 直接运行在 AstrBot Core 进程中，而 NewStar 则运行在一个独立的进程中，通过 IPC 与 AstrBot Core 通信。NewStar 进程将使用 astrbot-sdk 作为其运行时环境。

对于 NewStar 与 Core 之间的通信，我们将使用 stdio 或者 WebSockets 作为 IPC 的通信通道。

我们会设计一个 VirtualPluginLayer，以让 Core 端可以透明地调用 NewStar 的 Handlers，就像调用 LegacyStar 一样。

## 通信过程

通信过程应该是全双工的。

1. Core 调用 `VirtualPluginLayer.initialize`，启动插件进程。
2. 插件进程启动后，Core 调用 `VirtualPluginLayer.handshake()`，进行握手，获取插件的元数据，如支持的 Handlers 列表等。
3. 当消息平台有事件（AstrMessageEvent）下发时，Core 调用 `VirtualPluginLayer.get_triggered_handlers(event)`，获取需要处理该事件的 Handlers 列表。这一步不需要通信，因为 SDK 已经在上一步缓存了插件的 Handlers 列表元数据。
4. 如果有 handler 触发，Core 调用 `VirtualPluginLayer.call_handler(event, xxxx)`，调用某个 Handler 处理事件，等待结果返回。
5. 4 步骤期间，handler 可能会调用一些 Core 中的方法，如发送消息、获取对话历史等，这些调用通过 RPC 方式进行。
6. 插件 handler 处理完事件后，返回结果给 Core，Core 继续后续的事件处理流程。
7. 插件可能会主动向 Core 发送事件通知，Core 接收到后，进行相应的处理。
