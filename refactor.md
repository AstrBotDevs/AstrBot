# AstrBot SDK v4 重构设计（历史说明）

本文档保留最初的 v4 重构意图与设计取舍，**不再作为当前实现文档**。  
当前代码、兼容面、能力集合、目录结构与版本语义，请以 [ARCHITECTURE.md](D:/GitObjectsOwn/astrbot-sdk/ARCHITECTURE.md) 为准。

## 1. 这份文档现在的用途

- 记录最初为什么要做 v4 分层与协议化重构
- 保留当时的重要设计原则，供后续判断“方向有没有跑偏”
- 帮助阅读历史提交和旧讨论

它**不再负责**描述当前仓库现状。

## 2. 仍然有效的核心原则

以下原则仍然是当前实现的主线：

- 协议优先：插件与宿主通过显式协议消息交互
- 统一 `id`：所有请求/响应使用单一关联字段
- `handler.invoke`：handler 回调不引入额外消息类型
- `event` 只服务于 `stream=true`
- runtime 根导出保持窄接口
- legacy 适配与原生 v4 协议模型分开管理

## 3. 已经演化的地方

最初方案中的下列假设，当前已经不再成立或只部分成立：

- `compat.py` 不是当前 compat 的全部实现，compat 已演化为长期维护子系统
- runtime 不能完全“感知不到 compat”，但 compat 执行细节应继续收口到 `_legacy_runtime.py`
- 环境管理不再只是“每插件一个独立 venv”，现在有 `runtime.environment_groups` 做共享环境规划
- capability 集合已经扩展，当前不止早期文档中的那一组
- 旧包名兼容不再只有 `astrbot_sdk.api.*`，还包括受控的 `src-new/astrbot` facade

## 4. 当前维护约定

如果你要修改实现，请按下面的顺序看文档：

1. 先看 `ARCHITECTURE.md`
2. 再看相关代码和 `tests_v4`
3. 最后把本文档当作历史背景材料

如果 `ARCHITECTURE.md` 与本文档冲突：

- 以 `ARCHITECTURE.md` 为准
- 若仍有歧义，以代码和测试为准

## 5. 对后续重构的约束

后续清理实现时，应继续坚持：

- 不破坏旧插件现有兼容面
- 不把 legacy 逻辑重新扩散进 runtime 主干
- 不把 `src-new/astrbot` 扩张成旧应用整棵树
- 不让文档再次脱离代码与测试
