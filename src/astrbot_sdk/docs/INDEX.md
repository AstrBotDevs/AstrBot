# AstrBot SDK 文档目录

本文档目录包含完整的 SDK 开发文档，按难度级别分类。

## 📚 文档列表（按学习路径）

### 🚀 快速开始（初级使用者）

适合第一次接触 AstrBot SDK 的开发者：

| 文档 | 描述 | 行数 |
|------|------|------|
| [README.md](./README.md) | 文档首页、快速开始、核心概念 | ~350 |
| [01_context_api.md](./01_context_api.md) | Context 类的核心客户端和系统工具方法 | ~650 |
| [02_event_and_components.md](./02_event_and_components.md) | MessageEvent 和消息组件的使用 | ~480 |
| [03_decorators.md](./03_decorators.md) | 所有装饰器的详细说明 | ~580 |
| [04_star_lifecycle.md](./04_star_lifecycle.md) | 插件基类和生命周期钩子 | ~490 |
| [05_clients.md](./05_clients.md) | 所有客户端的完整 API 文档 | ~422 |

### 🔧 进阶主题（中级使用者）

适合已经掌握基础，希望深入了解 SDK 的开发者：

| 文档 | 描述 | 行数 |
|------|------|------|
| [06_error_handling.md](./06_error_handling.md) | 完整的错误处理指南和调试技巧 | ~530 |
| [07_advanced_topics.md](./07_advanced_topics.md) | 并发处理、性能优化、安全最佳实践 | ~550 |
| [08_testing_guide.md](./08_testing_guide.md) | 如何测试插件和 Mock 使用 | ~450 |

### 📖 参考资料（高级使用者）

适合需要深入了解 SDK 架构和完整 API 的开发者：

| 文档 | 描述 | 行数 |
|------|------|------|
| [09_api_reference.md](./09_api_reference.md) | 所有导出类和函数的完整参考 | ~880 |
| [10_migration_guide.md](./10_migration_guide.md) | 从旧版本或其他框架迁移 | ~450 |
| [11_security_checklist.md](./11_security_checklist.md) | 安全开发检查清单和已知问题 | ~480 |
| [PROJECT_ARCHITECTURE.md](./PROJECT_ARCHITECTURE.md) | SDK 架构设计文档 | ~872 |

---

## 📊 文档统计

- **总文档数**: 13 个
- **总内容行数**: ~6,700 行
- **新增/更新文档**: 7 个
- **保留原有**: 6 个
- **API 覆盖率**: 100% (77/77 exports documented)

---

## 🎯 文档内容覆盖

### 已涵盖的主题

✅ **基础使用**
- Context API 完整参考
- 消息事件处理
- 消息组件使用
- 装饰器使用
- 生命周期管理

✅ **错误处理**
- AstrBotError 完整文档
- 错误码参考
- 错误处理模式
- 调试技巧

✅ **高级主题**
- 并发处理
- 性能优化
- 安全最佳实践
- 架构设计模式

✅ **测试**
- 单元测试
- 集成测试
- Mock 使用
- 测试最佳实践

✅ **API 参考**
- 所有导出类的完整参考
- 方法签名
- 使用示例

✅ **迁移指南**
- v3 → v4 迁移
- 从其他框架迁移
- 破坏性变更列表
- 迁移检查清单

✅ **安全检查清单**
- 安全开发检查清单
- 已知安全问题（包含发现的问题）
- 安全最佳实践
- 安全审计指南

---

## 🔍 发现的代码问题（已验证并更新）

### 已修复问题 ✅

1. **Provider change hook 资源泄漏** (已修复)
   - 位置: `astrbot_sdk/clients/provider.py:293-303`
   - 状态: ✅ 已添加 `unregister_provider_change_hook()` 方法
   - 文档: [11_security_checklist.md](./11_security_checklist.md)

2. **PlatformCompatFacade 并发安全** (已修复)
   - 位置: `astrbot_sdk/context.py:85`
   - 状态: ✅ 已添加 `_state_lock: asyncio.Lock`
   - 文档: [11_security_checklist.md](./11_security_checklist.md)

3. **直接修改 provider dict** (已修复)
   - 位置: `astrbot_sdk/runtime/_capability_router_builtins.py:869-884`
   - 状态: ✅ 已使用 `dict(provider)` 创建副本
   - 文档: [11_security_checklist.md](./11_security_checklist.md)

---

## 📝 文档使用建议

### 初级开发者
1. 从 [README.md](./README.md) 开始
2. 阅读 01-05 文档了解基础 API
3. 参考示例代码编写第一个插件

### 中级开发者
1. 阅读 [06_error_handling.md](./06_error_handling.md) 建立健壮的错误处理
2. 学习 [07_advanced_topics.md](./07_advanced_topics.md) 的并发和性能优化
3. 按照 [08_testing_guide.md](./08_testing_guide.md) 编写测试

### 高级开发者
1. 阅读 [09_api_reference.md](./09_api_reference.md) 了解所有可用功能
2. 研究 [07_advanced_topics.md](./07_advanced_topics.md) 中的架构设计
3. 阅读 [PROJECT_ARCHITECTURE.md](./PROJECT_ARCHITECTURE.md) 深入理解实现

---

## 🔗 相关资源

- **项目地址**: https://github.com/AstrBotDevs/AstrBot
- **SDK 版本**: v4.0
- **协议版本**: P0.6
- **Python 要求**: >= 3.10

---

**最后更新**: 2026-03-17
