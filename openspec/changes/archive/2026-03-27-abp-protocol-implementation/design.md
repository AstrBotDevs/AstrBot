## Context

AstrBot 当前使用 Star 插件系统，插件与核心紧耦合。ABP 协议需要实现：
- 插件作为独立服务（进程内/外）
- 主进程不读取插件配置文件，通过协议握手交换
- 数据目录由主进程分配
- 支持 Stdio/Unix Socket/HTTP 三种传输方式
- Rust 核心实现协议逻辑（`astrbot/rust/src/abp/`）

## Goals / Non-Goals

**Goals:**
- 实现 ABP 协议核心：握手、消息路由、生命周期管理
- 支持进程内插件（Python 直接调用）和进程外插件（独立进程）
- 支持 Stdio/Unix Socket/HTTP 传输层
- 实现工具调用（tools/list, tools/call）和消息处理（plugin.handle_event）
- 实现事件订阅系统（plugin.subscribe, plugin.notify）

**Non-Goals:**
- 不实现 MCP 协议（独立协议）
- 不实现 A2A/ACP 协议（独立协议）
- 不在 Python 层重复核心逻辑

## Decisions

### 1. Rust 核心实现 vs Python 实现

**决定**：核心协议逻辑在 Rust 中实现（`astrbot/rust/src/abp/`），Python 只做 FFI 胶水层。

**理由**：
- ABP 协议是高性能路径，消息路由需要低延迟
- 与项目 "Rust 核心 + Python 胶水层" 架构一致
- 多语言插件需要稳定的 Rust FFI 接口

**替代方案**：
- Python 实现（被否定）：性能不足，违反项目架构
- Go 实现（被否定）：引入新语言栈，增加维护成本

### 2. 传输层选择

**决定**：支持 Stdio（进程启动）、Unix Socket（本地进程间）、HTTP/SSE（远程）三种。

**理由**：
- Stdio：最简单的跨语言方案，适合单次请求
- Unix Socket：低延迟，适合本地进程外插件
- HTTP/SSE：支持远程插件和 Webhook 通知

### 3. 插件配置管理

**决定**：主进程不读取插件配置文件，配置通过握手 `initialize` 传递。

**理由**：
- 零侵入性：插件无需了解 AstrBot 目录结构
- 统一管理：所有配置通过 WebUI 管理
- 安全：主进程控制插件可见的配置

### 4. JSON-RPC 2.0 vs 自定义协议

**决定**：采用 JSON-RPC 2.0。

**理由**：
- 成熟标准，生态丰富
- 多语言支持（Python、Rust、Go 等）
- 易于调试和测试

## Risks / Trade-offs

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Rust FFI 接口不稳定 | Python 胶水层需要频繁调整 | 接口版本化，保持向后兼容 |
| 进程外插件通信延迟 | 工具调用性能下降 | 使用 Unix Socket 代替 HTTP |
| 插件崩溃影响主进程 | 系统稳定性下降 | 进程隔离 + 超时控制 |
| 配置 Schema 同步 | WebUI 表单与实际不一致 | 握手时交换 Schema |
