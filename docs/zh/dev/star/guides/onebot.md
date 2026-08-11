# OneBot 插件 API

OneBot 事件和动作通过稳定、类型化的 facade 提供。facade 与当前事件绑定，
不会暴露 NapCat 适配器、WebSocket、token 或任意 raw `call_action` 方法。

```python
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.onebot import (
    OneBotActionTimeout,
    OneBotCapabilityUnavailable,
    OneBotMessageEvent,
)


@filter.command("delete")
async def delete_(self, event: AstrMessageEvent):
    onebot_event = self.context.onebot.event(event)
    if not isinstance(onebot_event, OneBotMessageEvent):
        return
    client = self.context.onebot.for_event(event)
    if client is None or not self.context.onebot.supports(
        event, "onebot.v11", "delete"
    ):
        return
    try:
        await client.messages.delete(message_id=onebot_event.message_id or "")
    except OneBotCapabilityUnavailable, OneBotActionTimeout:
        return
```

`OneBotEvent.payload` 会保留上游新增字段，并且是只读视图。SDK 不认识的消息段
会表示为 `OneBotSegment(type="unknown", data=...)`，不会使整个事件失效。DTO
中的用户、群组和消息 ID 统一为字符串。

标准动作按 `messages`、`directory`、`groups`、`requests`、`history` 分组；点赞、
戳一戳、群公告、在线文件、闪传、自定义表情和 AI 等 NapCat/QQ 扩展位于
`client.qq`。使用可选动作前先调用 `supports(event, capability, action)`。

能力不存在、参数错误、传输失败和超时都会使用稳定的 `OneBotError` 子类。请
不要访问 `event.bot`、`event.client`，也不要调用任意 raw action。

标准动作的能力版本是 `onebot.v11`，NapCat 专属动作的能力版本是
`napcat.qq`。能力检测只是调用前的提示；检测和调用之间如果发生断连，仍需
捕获能力或动作异常。
