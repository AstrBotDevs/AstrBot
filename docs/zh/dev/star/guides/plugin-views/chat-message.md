# 消息交互组件

> [!NOTE]
> AstrBot 内置的卡片渲染端是 ChatUI。

插件可以在聊天消息里创建自定义 HTML 卡片。命令、消息事件处理器、UI 回调和本地 LLM 工具都可以返回同一种 `event.view_result()`，不要求先经过 tool call。

<script setup>
import ReadingViewDemo from "../../../../../.vitepress/theme/components/ReadingViewDemo.vue"
</script>

<ReadingViewDemo lang="zh" />

下载[阅读清单示例插件](/examples/astrbot_plugin_reading_view.zip)，在 ChatUI 发送 `/reading` 即可使用真实卡片；也可以让模型调用 `open_reading_list`。下面用更小的计数器示例说明注册和回调。


卡片使用受限 iframe，资源随插件分发；用户操作通过 `filter.ui_action` 回到 Python。第一版 `ui_action` **只处理 view 交互**，与已有 `filter.button_action`、`ButtonInteraction` 独立。
## 注册并创建组件

目录结构：

```text
astrbot_plugin_view_demo/
├── metadata.yaml
├── main.py
└── views/
    └── counter/
        ├── index.html
        └── app.js
```



在 `metadata.yaml` 中添加：

```yaml
views:
  - name: counter
    target: chat_message
    title: Counter
    version: 1
    actions: ["view_demo:increment"]
```

`main.py`：

```python
from pydantic import BaseModel, ConfigDict, Field

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Star


class IncrementInput(BaseModel):
    """Validated increment submitted by the user."""

    model_config = ConfigDict(extra="forbid", strict=True)
    amount: int = Field(ge=1, le=10)


class ViewDemo(Star):
    """Demonstrate a card created directly from a command."""

    @filter.command("counter")
    async def counter(self, event: AstrMessageEvent):
        """Create a counter card.

        Args:
            event: Incoming command event.

        Yields:
            A newly created card.
        """
        yield event.view_result(
            name="counter",
            data={"count": 0},
            text="计数器已创建，当前值为 0。",
        )

    @filter.ui_action("view_demo:increment")
    async def increment(self, event: AstrMessageEvent):
        """Increment the card without calling the model.

        Args:
            event: Authenticated interaction event.

        Yields:
            A replacement snapshot for the current card.
        """
        interaction = event.get_ui_interaction()
        if interaction is None:
            return
        payload = IncrementInput.model_validate(interaction.data)
        yield event.view_result(
            data={"count": interaction.view.data["count"] + payload.amount},
        )
```

`name` 在插件内唯一。入口必须为 `views/<name>/index.html`；资源不能通过路径或符号链接逃出插件目录。

每次提供 `name` 都创建一个新卡片；省略 `name` 只更新当前 UI 回调所属的卡片。普通事件不能省略 `name`。创建时必须提供非空 `text`，用于不支持卡片的平台及加载失败时的文字回退。

本地工具也可以直接返回相同结果，不需要 `ToolResult` 或 `View` 包装：

```python
@filter.llm_tool(name="open_counter")
async def open_counter(self, event: AstrMessageEvent):
    """Open an interactive counter.

    Returns:
        A new card and a text result for the model.
    """
    return event.view_result(
        name="counter", data={"count": 0}, text="计数器已创建。",
    )
```

工具的 `text` 进入模型上下文，`data` 默认不进入。普通事件创建卡片时不会因此调用模型。需要在 Python 中引用声明和结果类型时，从 `astrbot.api.interactive_ui` 导入 `ViewSpec` 和 `ViewResult`。

核心把新卡片转为出站 `InteractiveView`，用户操作由适配器转换为入站 `UIInteraction`。两个消息组件都从 `astrbot.api.message_components` 导入。自定义适配器实现本平台的卡片渲染和通过认证的操作转换后，可在注册参数和事件元数据中启用 `support_ui_interaction`。未启用的平台使用文字回退。

适配器处理点击时，先用卡片 ID 读取快照，核对平台实例、会话、用户和允许的动作，再通过共享存储登记本次操作。提交事件时，用已保存的快照填充 `UIInteraction.view`，并把卡片所属的插件模块写入事件的 `ui_plugin_module`。

## 显示数据并提交操作 {#前端}

`index.html`：

```html
<!doctype html>
<html lang="zh-CN">
  <head><meta charset="utf-8" /><title>计数器</title></head>
  <body>
    <p id="count"></p>
    <button id="increment" type="button">增加 1</button>
    <p id="error" role="alert"></p>
    <script type="module" src="./app.js"></script>
  </body>
</html>
```

`app.js`：

```javascript
const bridge = window.AstrBotPluginView;
await bridge.ready();
const view = bridge.view;
const button = document.querySelector("#increment");
const error = document.querySelector("#error");

view.subscribe(({ data }) => {
  document.querySelector("#count").textContent = String(data.count);
});
bridge.onContext(({ locale }) => {
  document.documentElement.lang = locale;
});

button.onclick = async () => {
  button.disabled = true;
  error.textContent = "";
  try {
    await view.action("view_demo:increment", { amount: 1 });
  } catch (failure) {
    error.textContent = failure.message;
  } finally {
    button.disabled = false;
  }
};
```

两种宿主注入同一份 `/api/plugin/page/bridge-sdk.js`。`bridge.ready()` 等待上下文就绪；`bridge.view.subscribe()` 立即提供初始快照，并在快照更新时通知，返回取消订阅函数。主题、语言统一通过 `bridge.onContext()` 监听。`bridge.view.action()` 只能调用当前 view 声明的动作，自动携带实例、revision 和交互 ID。返回的 Promise 在回调结束、状态提交后完成；有模型回答时，回答继续进入聊天流，无需等待生成结束。错误带有 `code` 和 `message`。

bridge 自动注入 `--astrbot-color-*` CSS tokens 并更新 `data-theme`，完整列表见[跟随用户配色](./bridge.md#跟随用户配色)。主题变化不会触发聊天生成或改变卡片 revision。

```css
body { color: var(--astrbot-color-text); background: transparent; }
button { color: var(--astrbot-color-primary); border-color: var(--astrbot-color-border); }
```

可使用打包后的 Vue 或 React，但资源应采用相对路径，不依赖父窗口 DOM、登录凭据、通用管理 API 或 iframe 的本地存储。

## 交互数据与回复

`event.get_ui_interaction()` 返回 `UIInteraction`；普通事件和按钮事件返回 `None`。

| 字段 | 含义 |
| --- | --- |
| `action_id` | 业务动作名，例如 `view_demo:increment` |
| `interaction_id` | 本次操作的标识，同请求重试时保持不变 |
| `data` | 用户本次提交的参数，需要插件校验 |
| `source` | 当前为 `view` |
| `source_message_id` | 来源消息 ID；消息尚未落盘时可能为空 |
| `view.id` / `view.name` | 卡片实例 ID 与注册名称 |
| `view.version` | 卡片契约版本 |
| `view.revision` | 当前数据的修订号 |
| `view.data` | 后端读取的已保存快照，不由本次客户端请求提供 |

操作者、会话和平台仍通过 `AstrMessageEvent` 读取。`view.data` 应视为只读快照，更新通过 `event.view_result(data=...)` **完整替换**，不能依赖原地修改。状态数据最大 1 MiB，操作参数最大 64 KiB，必须可以 JSON 序列化。

回调还可以 `yield event.plain_result(...)`、`yield event.chain_result(...)`，或者显式 `yield event.request_llm(prompt="...")`。提供 `name` 时，回调也可以创建另一张卡片。一个交互处理器链最多更新原卡片一次、请求模型一次。原卡片更新与模型请求先暂存，正常结束后才提交；回调已发送的消息或外部副作用不会自动回滚。回调执行预算为 120 秒。

`@filter.ui_action()` 不传动作 ID 时匹配当前插件的所有 view 操作，不会接收其他插件或按钮事件。插件加载时检查动作是否有对应处理器。

## 历史、并发与限制

- 主聊天、独立聊天和 thread 使用同一渲染组件。重开消息读取已保存的数据，不重跑命令、tool 或回调。
- `version` 表示数据和动作契约，兼容样式修改不用递增；不兼容升级后，旧卡片回退到文字，不自动迁移。`revision` 在成功更新数据后自动递增。
- 仅会话所有者可以操作，后端同时检查来源消息、插件状态、会话插件配置与动作白名单。插件仍须检查自己的业务权限。
- 同实例的后端操作串行保留执行权；旧 revision 返回 `REVISION_CONFLICT`，SDK 先同步最新快照，再报告错误。
- 已完成的相同请求返回已记录结果；相同 ID 携带不同输入会被拒绝。新点击是新操作，外部副作用应使用 `interaction_id` 做业务幂等。
- 断线或进程中断后，不自动重跑未知结果的动作。第一版不提供后台任务推送、旧前端 bundle 归档、执行中动作的自动恢复或跨平台按钮接入。模型生成沿用现有运行管理，不承诺进程重启后自动重新生成。
- 删除会话会清理对应卡片与交互记录；删除或改写来源消息后，该卡片不再可操作。

HTTP 接口使用 `chat` scope：`GET /api/v1/chat/views/{view_id}` 获取快照，`POST .../actions` 提交操作，`GET .../actions/{interaction_id}` 查询已接受操作。插件前端应使用 SDK，不自行构造登录请求。
