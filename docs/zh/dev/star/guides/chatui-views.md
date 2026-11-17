# ChatUI 交互卡片

插件可以在聊天消息里创建自定义 HTML 卡片。命令、消息事件处理器、UI 回调和本地 LLM 工具都可以返回同一种 `event.view_result()`，不要求先经过 tool call。

卡片使用受限 iframe，资源随插件分发；用户操作通过 `filter.ui_action` 回到 Python。第一版 `ui_action` **只处理 view 交互**，与已有 `filter.button_action`、`ButtonInteraction` 独立。

## 注册与创建

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

`metadata.yaml` 沿用现有插件格式。`main.py`：

```python
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from astrbot.api import chatui
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Star


class IncrementInput(BaseModel):
    """Validated increment submitted by the user."""

    model_config = ConfigDict(extra="forbid", strict=True)
    amount: int = Field(ge=1, le=10)


class ViewDemo(Star):
    """Demonstrate a card created directly from a command."""

    chatui_views = [
        chatui.ViewSpec(
            name="counter",
            entry=Path("views/counter/index.html"),
            target="chat_message",
            version=1,
            actions=["view_demo:increment"],
        ),
    ]

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

### 选择展示位置

在 `ViewSpec` 注册信息中设置 `target`，不在 `event.view_result()` 中指定：

| `target` | 展示位置 | 创建与交互 |
| --- | --- | --- |
| `chat_message`（默认） | 聊天消息正文 | `event.view_result()` 创建；`AstrBotPluginView.view` 与 `filter.ui_action` 交互 |
| `chat_workbench` | ChatUI 右侧工作台 | 消息创建的标签，或设置 `launcher=True` 后从“新工作台”主动打开 |
| `plugin_page` | 插件独立页面，沿用现有 WebUI 导航入口 | 页面通过 `window.AstrBotPluginView` 调用插件注册的 Web API |

例如，在同一插件的 `chatui_views` 中增加一个独立页面：

```python
chatui.ViewSpec(
    name="settings",
    entry=Path("views/settings/index.html"),
    target="plugin_page",
)
```

`chat_message` 和 `chat_workbench` 不会出现在独立页面列表或 WebUI 侧栏中；只提供聊天卡片的插件没有侧栏页面入口。`plugin_page` 不能通过 `event.view_result()` 创建聊天卡片，也不能声明聊天 `actions`。三种 target 复用同一份 `AstrBotPluginView` bridge、初始化接口和主题上下文。聊天卡片使用 `bridge.view` 能力；独立页面使用插件 Web API、上传下载和 SSE 能力。宿主分别校验可用操作。

已有插件未声明 `ViewSpec` 的 `views/`（或兼容的 `pages/`）目录仍自动发现为独立页面。省略 `target` 的现有 `ViewSpec` 保持聊天卡片行为。独立页面的开发方式见[插件可视化视图](./plugin-pages.md)。

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

工具的 `text` 进入模型上下文，`data` 默认不进入。普通事件创建卡片时不会因此调用模型。非 ChatUI 平台按文字回复处理，不实例化 iframe。

## 前端

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

bridge 自动注入 `--astrbot-color-*` CSS tokens 并更新 `data-theme`，完整列表见[跟随用户配色](./plugin-pages.md#跟随用户配色)。主题变化不会触发聊天生成或改变卡片 revision。旧示例的 `window.astrbot.view.connect()` 迁移为 `await AstrBotPluginView.ready()` 后使用 `AstrBotPluginView.view`；快照中的 `theme` / `locale` 监听改为公共 `onContext()`。仅样式适配直接使用 CSS tokens 即可。

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

## 工作台与常驻视图

`target="chat_workbench"` 将 iframe 放在 ChatUI 右侧，消息里保留重新打开的入口。创建时可以通过 `event.view_result(name="preview", title="notes.pdf", data={...}, text="已打开文档。")` 指定标签标题。消息创建的标签跟随所属会话；没有工作台的宿主（例如线程面板）仍以内联方式展示。

常驻视图不需要消息或工具调用。注册时增加 `launcher=True`：

```python
chatui.ViewSpec(
    name="context",
    entry=Path("views/context/index.html"),
    target="chat_workbench",
    launcher=True,
    title="上下文用量",
    description="查看当前会话的容量和来源分布。",
)
```

用户从 ChatUI header 右侧打开工作台，点击标签栏的「＋」，进入“新工作台”选择已启用插件的常驻视图。同一个注册视图只打开一个标签。常驻标签在当前 ChatUI 页面生命周期内跨会话保留；刷新页面后可再次从列表打开。

常驻视图复用独立插件页面的 Web API、文件传输和 SSE bridge，不声明消息 `actions`，也没有 `context.view` 消息快照。`sessionId` 是当前打开的聊天会话 ID；未打开会话时为 `null`。切换会话会更新 context，不重载 iframe：

```javascript
const bridge = window.AstrBotPluginView;
await bridge.ready();
bridge.onContext(({ sessionId }) => {
  // Fetch session-specific aggregates from your authenticated plugin API.
  if (sessionId) bridge.apiGet("usage", { session_id: sessionId });
});
```

插件后端必须用 `request.username` 校验会话归属，不能把前端传入的 `sessionId` 当作授权。异步请求要避免旧会话的响应覆盖新会话。三个 target 继续共用主题 CSS tokens 和 `onContext()`。

标签和操作按钮位于主 header，内容区不重复显示标题栏。可拖动工作台左边界调整宽度，也可聚焦分隔线后用左右键调整。收起保留标签，展开和收起采用缓动动画并遵守减少动态效果设置；窄屏使用全屏面板。


## 从常驻视图填入或发送消息

仅 `chat_workbench` 常驻视图（没有 `context.view`）提供以下接口，通常绑定到用户点击操作：

```javascript
await bridge.chat.fill("请帮我修改这段文字。");
await bridge.chat.send("请总结我选中的内容。");
```

`fill` 将文字追加到当前草稿并聚焦聊天框；`send` 直接发到当前会话，保留已有草稿与暂存附件。没有打开会话、会话已经切换或正在生成时，发送会被拒绝。Promise 在发送请求被接受时完成，不等待 bot 回复完成。

如果插件允许 agent 编辑文档，应在插件后端记录用户提交时的选区和版本，让工具只接收选区 ID 与替换文字。不要依赖提示词要求 agent 保留全文。工具保存后可以通过插件 SSE 通知常驻视图重新读取，客户端仍需保护未保存的本地编辑。
