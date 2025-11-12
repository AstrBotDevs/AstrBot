# AstrBot SDK Runtime Context API

这个包下存储了暴露给 AstrBot 插件的 Context API 的 RPC 实现。

## 组件

- `Context`：这是在实例化插件时，注入到插件中的上下文对象。它封装了插件可以调用的各种功能组件。
- `ConversationManager`：这是一个管理对话相关的功能组件。它提供了与对话历史、用户信息等相关的操作接口。
