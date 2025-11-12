# AstrBor SDK 与 Core 通信的数据交换实现

这个包下存储了 AstrBot 插件运行时与 AstrBot Core 之间通信的数据交换实现。

AstrBot SDK 设计了两种传输协议，即 stdio 和 WebSockets，用于实现 AstrBot 插件与 AstrBot Core 之间的双向通信。

在这两种传输协议之上，我们使用 JSON-RPC 2.0 作为通信的消息格式和调用规范。
