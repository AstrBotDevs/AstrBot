
# 会话控制

> 大于等于 v3.4.36

为什么需要会话控制？考虑一个 成语接龙 插件，某个/群用户需要和机器人进行多次对话，而不是一次性的指令。这时候就需要会话控制。

```txt
用户: /成语接龙
机器人: 请发送一个成语
用户: 一马当先
机器人: 先见之明
用户: 明察秋毫
...
```

AstrBot 提供了开箱即用的会话控制功能：

```py
import astrbot.api.message_components as Comp
from astrbot.api.util import SessionController, session_waiter
from astrbot.api.event import filter, AstrMessageEvent

@filter.command("成语接龙")
async def handle_empty_mention(self, event: AstrMessageEvent):
    """成语接龙具体实现"""
    try:
        yield event.plain_result("请发送一个成语~")

        # 具体的会话控制器使用方法
        @session_waiter(timeout=60, record_history_chains=False) # 注册一个会话控制器，设置超时时间为 60 秒，不记录历史消息链
        async def empty_mention_waiter(controller: SessionController, event: AstrMessageEvent):
            idiom = event.message_str # 用户发来的成语，假设是 "一马当先"

            if idiom == "退出":   # 假设用户想主动退出成语接龙，输入了 "退出"
                controller.stop()    # 停止会话控制器，会立即结束。
                return event.plain_result("已退出成语接龙~")

            if len(idiom) != 4:   # 假设用户输入的不是4字成语
                return event.plain_result("成语必须是四个字的呢~")  # 返回后不执行后续逻辑，但此会话并未中断，后续的用户输入仍然会进入当前会话

            # ...
            controller.keep(timeout=60, reset_timeout=True) # 重置超时时间为 60s，如果不重置，则会继续之前的超时时间计时。

            # controller.stop() # 停止会话控制器，会立即结束。
            # 如果记录了历史消息链，可以通过 controller.get_history_chains() 获取历史消息链
            return event.plain_result("先见之明")  # 发送回复

        try:
            await empty_mention_waiter(event)
        except TimeoutError as _: # 当超时后，会话控制器会抛出 TimeoutError
            yield event.plain_result("你超时了！")
        except Exception as e:
            yield event.plain_result("发生错误，请联系管理员: " + str(e))
        finally:
            event.stop_event()
    except Exception as e:
        logger.error("handle_empty_mention error: " + str(e))
```

> [!TIP]
> 会话控制器处理函数内**不能使用 `yield`**，但可以 `return` 一个 `MessageEventResult`。返回的结果会被框架自动送入消息装饰流程后再发送，与普通指令回复的行为一致。\
> 如果直接调用 `event.send()`，消息会绕过装饰流程直接发送。

当激活会话控制器后，该发送人之后发送的消息会首先经过上面你定义的 `empty_mention_waiter` 函数处理，直到会话控制器被停止或者超时。

## SessionController

用于开发者控制这个会话是否应该结束，并且可以拿到历史消息链。

- keep(): 保持这个会话
  - timeout (float): 必填。会话超时时间。
  - reset_timeout (bool): 设置为 True 时, 代表重置超时时间, timeout 必须 > 0, 如果 <= 0 则立即结束会话。设置为 False 时, 代表继续维持原来的超时时间, 新 timeout = 原来剩余的 timeout + timeout (可以 < 0)
- stop(): 结束这个会话
- get_history_chains() -> List[List[Comp.BaseMessageComponent]]: 获取历史消息链

## 自定义会话 ID 算子

默认情况下，AstrBot 会话控制器会将基于 `sender_id` （发送人的 ID）作为识别不同会话的标识，如果想将一整个群作为一个会话，则需要自定义会话 ID 算子。

```py
import astrbot.api.message_components as Comp
from astrbot.api.utils import (
    session_waiter,
    SessionFilter,
    SessionController,
)

# 沿用上面的 handler
# ...
class CustomFilter(SessionFilter):
    def filter(self, event: AstrMessageEvent) -> str:
        return event.get_group_id() if event.get_group_id() else event.unified_msg_origin

await empty_mention_waiter(event, session_filter=CustomFilter()) # 这里传入 session_filter
# ...
```

这样之后，当群内一个用户发送消息后，会话控制器会将这个群作为一个会话，群内其他用户发送的消息也会被认为是同一个会话。

甚至，可以使用这个特性来让群内组队！
