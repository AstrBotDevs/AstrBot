# 杂项

## 调用 OneBot 能力

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.onebot import OneBotMessageEvent


@filter.command("test")
async def test_(self, event: AstrMessageEvent):
    onebot_event = self.context.onebot.event(event)
    if not isinstance(onebot_event, OneBotMessageEvent):
        return

    client = self.context.onebot.for_event(event)
    if client is not None and self.context.onebot.supports(
        event, "onebot.v11", "delete"
    ):
        await client.messages.delete(message_id=onebot_event.message_id or "")
```

插件不再暴露 `Platform` 实例或 `platform_manager`。常规平台 IO 请优先使用：

- `self.context.messages.send(...)`
- `self.context.platform_actions.invoke(...)`
- `self.context.platform_actions.invoke_for_event(...)`

只有在确实需要构造一条新的平台入站事件时，才使用
`self.context.messages.create_event(...)`。

## 调用 QQ 协议端 API

插件侧不要再直接依赖 `event.bot`、`event.client` 或平台 SDK client。

标准 OneBot v11 动作通过 `client.messages`、`client.directory`、`client.groups`、
`client.requests` 和 `client.history` 分组访问。NapCat 专属动作位于
`client.qq`，并应先用 `supports(event, "napcat.qq", action)` 检测。不要访问
`event.bot`、`event.client`，也不要调用任意 raw action。

关于 CQHTTP API，请参考如下文档：

Napcat API 文档：<https://napcat.apifox.cn/>

Lagrange API 文档：<https://lagrange-onebot.apifox.cn/>

## 获取载入的所有插件

```py
plugins = self.context.runtime_info.plugins()  # 返回只读 PluginInfo
```

## 获取加载的所有平台

插件侧不再提供“枚举所有平台实例”的接口。

如果插件需要对某个平台执行动作，应直接使用明确的平台 ID：

```py
client = self.context.onebot.for_event(event)
status = await client.directory.status() if client else None
```
