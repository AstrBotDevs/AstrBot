# 为什么要有peer
它做的事情非常纯粹：

握手协议：协商协议版本、交换元数据
请求-响应匹配：通过 request_id 关联发出的请求和收到的结果
流式支持：将 EventMessage 投递到对应的流式队列
取消传播：转发 CancelMessage 并终止对应任务
为什么不直接用 Transport？
Transport 只负责字节流传输（发送字符串、接收字符串），
它不知道：
- 哪条消息是对哪条请求的响应
- 如何处理流式事件
- 如何进行协议版本协商
- 如何优雅地处理取消

Peer 通过 v4 协议实现了这些功能，使得上层调用者（如 CapabilityProxy）可以专注于业务逻辑，而不必关心底层通信细节

Peer 作为一个抽象层，屏蔽了底层 Transport 的复杂性，提供了一个更高层次的接口来进行消息交换和任务管理。这种设计使得系统更加模块化、可维护，并且能够适应未来可能的协议变化或扩展。

Peer 能让多语言支持变得更简单，因为它定义了一个统一的消息格式和交互模式，无论底层实现是 Python、JavaScript 还是其他语言，都可以通过实现 Peer 接口来参与通信。这种抽象使得系统具有更好的可扩展性和灵活性。


## 例子
当你在插件中调用 ctx.llm.chat()：

### 用户代码
``` python
response = await ctx.llm.chat(prompt="hello")
```
实际流程是：

LLMClient 通过 CapabilityProxy 发起调用
CapabilityProxy 调用 Peer.invoke("llm.chat", {...})
Peer 生成 request_id，序列化 InvokeMessage，通过 Transport 发送
Supervisor 的 Peer 接收消息，路由到 CapabilityRouter
CapabilityRouter 执行 LLM 调用，返回结果
Supervisor 的 Peer 发送 ResultMessage
Worker 的 Peer 根据 request_id 唤醒等待的 Future，返回结果