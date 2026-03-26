# AstrBot SDK


优雅、安全、强大的机器人插件开发框架
<p align="center">
  <a href="https://deepwiki.com/united-pooh/astrbot-sdk"><img src="https://deepwiki.com/badge.svg" alt="Ask DeepWiki"></a>
  <a href="https://zread.ai/united-pooh/astrbot-sdk" target="_blank"><img src="https://img.shields.io/badge/Ask_Zread-_.svg?style=flat&color=00b0aa&labelColor=000000&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTQuOTYxNTYgMS42MDAxSDIuMjQxNTZDMS44ODgxIDEuNjAwMSAxLjYwMTU2IDEuODg2NjQgMS42MDE1NiAyLjI0MDFWNC45NjAxQzEuNjAxNTYgNS4zMTM1NiAxLjg4ODEgNS42MDAxIDIuMjQxNTYgNS42MDAxSDQuOTYxNTZDNS4zMTUwMiA1LjYwMDEgNS42MDE1NiA1LjMxMzU2IDUuNjAxNTYgNC45NjAxVjIuMjQwMUM1LjYwMTU2IDEuODg2NjQgNS4zMTUwMiAxLjYwMDEgNC45NjE1NiAxLjYwMDFaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00Ljk2MTU2IDEwLjM5OTlIMi4yNDE1NkMxLjg4ODEgMTAuMzk5OSAxLjYwMTU2IDEwLjY4NjQgMS42MDE1NiAxMS4wMzk5VjEzLjc1OTlDMS42MDE1NiAxNC4xMTM0IDEuODg4MSAxNC4zOTk5IDIuMjQxNTYgMTQuMzk5OUg0Ljk2MTU2QzUuMzE1MDIgMTQuMzk5OSA1LjYwMTU2IDE0LjExMzQgNS42MDE1NiAxMy43NTk5VjExLjAzOTlDNS42MDE1NiAxMC42ODY0IDUuMzE1MDIgMTAuMzk5OSA0Ljk2MTU2IDEwLjM5OTlaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik0xMy43NTg0IDEuNjAwMUgxMS4wMzg0QzEwLjY4NSAxLjYwMDEgMTAuMzk4NCAxLjg4NjY0IDEwLjM5ODQgMi4yNDAxVjQuOTYwMUMxMC4zOTg0IDUuMzEzNTYgMTAuNjg1IDUuNjAwMSAxMS4wMzg0IDUuNjAwMUgxMy43NTg0QzE0LjExMTkgNS42MDAxIDE0LjM5ODQgNS4zMTM1NiAxNC4zOTg0IDQuOTYwMVYyLjI0MDFDMTQuMzk4NCAxLjg4NjY0IDE0LjExMTkgMS42MDAxIDEzLjc1ODQgMS42MDAxWiIgZmlsbD0iI2ZmZiIvPgo8cGF0aCBkPSJNNCAxMkwxMiA0TDQgMTJaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00IDEyTDEyIDQiIHN0cm9rZT0iI2ZmZiIgc3Ryb2tlLXdpZHRoPSIxLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPgo8L3N2Zz4K&logoColor=ffffff" alt="zread"/></a>
</p>


AstrBot SDK 是一个基于 Python 3.12+ 的插件开发框架，采用**进程隔离**和**能力路由**架构，让插件崩溃不影响系统稳定，支持流式 LLM、语义记忆、跨平台消息收发。

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **进程隔离** | 每个插件独立进程运行，单个插件崩溃不影响其他插件 |
| **能力路由** | 显式声明能力(Capability)，支持 JSON Schema 验证和流式调用 |
| **内置 AI** | 集成 LLM 对话、语义记忆、知识库等 AI 能力 |
| **跨平台** | 统一 API 支持多平台消息收发（QQ、微信等） |
| **类型安全** | Pydantic 模型 + 类型注解，IDE 友好 |

---

## 分层架构

```
┌────────────────────────────────────────────────────────────┐
│                    插件开发者 API                          │
│   Star, Context, MessageEvent, 装饰器, 过滤器            │
└──────────────────────┬─────────────────────────────────────┘
                       │
┌──────────────────────▼─────────────────────────────────────┐
│                    高层客户端 API                          │
│   ctx.llm.chat() / ctx.memory.save() / ctx.db.set()       │
└──────────────────────┬─────────────────────────────────────┘
                       │ CapabilityProxy
┌──────────────────────▼─────────────────────────────────────┐
│                   运行时 & 协议层                          │
│   HandlerDispatcher / CapabilityRouter / Peer / Transport  │
└──────────────────────┬─────────────────────────────────────┘
                       │
┌──────────────────────▼─────────────────────────────────────┐
│                   AstrBot Core (Supervisor)                │
└────────────────────────────────────────────────────────────┘
```

**关键概念**：
- **Star**: 插件基类，所有插件都继承它
- **Context**: 运行时上下文，提供 `llm`、`memory`、`db`、`platform` 等客户端
- **Capability**: 能力，插件能做的事情（如 `llm.chat`、`platform.send`）
- **Handler**: 处理器，响应命令/消息的函数

---

## 快速开始

### 安装

```bash
pip install astrbot-sdk
```

### 初始化插件

```bash
# 生成插件骨架
astr init my-plugin

# 生成骨架 + AI 辅助开发配置（可选）
astr init my-plugin --agents claude,codex
```

### 第一个插件

```python
# main.py
from astrbot_sdk import Star, Context, MessageEvent
from astrbot_sdk.decorators import on_command, on_message

class MyPlugin(Star):
    @on_command("hello", aliases=["hi"])
    async def hello(self, event: MessageEvent, ctx: Context):
        """打招呼命令"""
        await event.reply(f"你好，{event.sender_name}!")

    @on_message(keywords=["帮助"])
    async def help_handler(self, event: MessageEvent, ctx: Context):
        """关键词触发"""
        await event.reply("可用命令: /hello")
```

```yaml
# plugin.yaml
_schema_version: 2
name: my_plugin
author: your_name
version: 1.0.0
components:
  - class: main:MyPlugin
```

### 常用功能

```python
# LLM 对话
reply = await ctx.llm.chat("你好")
async for chunk in ctx.llm.stream_chat("讲故事"):
    print(chunk)

# 数据存储
await ctx.db.set("user:123", {"name": "Alice"})
data = await ctx.db.get("user:123")

# 语义记忆（需要 embedding provider）
await ctx.memory.save("pref", {"theme": "dark"})
results = await ctx.memory.search("用户喜欢什么")

# 发送消息
await ctx.platform.send(event.session_id, "消息内容")
await ctx.platform.send_image(event.session_id, "https://example.com/img.jpg")
```

---

## 我该看哪篇文档？

| 你的目标 | 推荐文档 |
|----------|----------|
| 刚开始写第一个插件 | [事件与组件](docs/02_event_and_components.md) → [装饰器](docs/03_decorators.md) |
| 想了解所有可用的客户端方法 | [常用客户端速查](docs/05_clients.md) |
| 插件需要生命周期钩子（启动/停止） | [Star 生命周期](docs/04_star_lifecycle.md) |
| 处理错误、调试问题 | [错误处理与调试](docs/06_error_handling.md) |
| 并发、性能、安全最佳实践 | [高级主题](docs/07_advanced_topics.md) |
| 写测试 | [测试指南](docs/08_testing_guide.md) |
| 从旧版迁移 | [迁移指南](docs/10_migration_guide.md) |
| 查完整 API 签名 | [客户端 API 参考](docs/api/clients.md) |
| 了解架构设计 | [架构文档](docs/PROJECT_ARCHITECTURE.md) |

---

## 文档目录

### 入门（初级）

| 文档 | 内容 |
|------|------|
| [Context API](docs/01_context_api.md) | Context 类完整参考 |
| [事件与组件](docs/02_event_and_components.md) | MessageEvent 和消息组件使用 |
| [装饰器](docs/03_decorators.md) | 所有装饰器详细说明 |
| [Star 生命周期](docs/04_star_lifecycle.md) | 插件基类和生命周期钩子 |
| [常用客户端](docs/05_clients.md) | LLM/Memory/DB/Platform 快速上手 |

### 进阶（中级）

| 文档 | 内容 |
|------|------|
| [错误处理](docs/06_error_handling.md) | 错误体系、处理模式、调试技巧 |
| [高级主题](docs/07_advanced_topics.md) | 并发、性能、安全、架构模式 |
| [测试指南](docs/08_testing_guide.md) | 单元测试、集成测试、Mock 使用 |

### 参考（高级）

| 文档 | 内容 |
|------|------|
| [API 索引](docs/09_api_reference.md) | 所有导出类和函数入口 |
| [客户端 API](docs/api/clients.md) | 17 个客户端完整签名和示例 |
| [迁移指南](docs/10_migration_guide.md) | 从旧版本迁移 |
| [安全清单](docs/11_security_checklist.md) | 安全开发检查清单 |
| [架构文档](docs/PROJECT_ARCHITECTURE.md) | SDK 架构设计 |

---

## 开发

```bash
# 开发安装
pip install -e .

# 运行测试
python -m pytest tests -q

# 代码格式化
ruff format .
ruff check . --fix
```

---

## 相关资源

- **AstrBot 主项目**: https://github.com/AstrBotDevs/AstrBot
- **Python 版本**: >= 3.12
- **SDK 版本**: v4.0
- **协议版本**: P0.6
