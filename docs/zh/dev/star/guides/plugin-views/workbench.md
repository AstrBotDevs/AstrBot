# 工作台页面

> [!NOTE]
> 目前仅支持 AstrBot ChatUI。

使用 `target="chat_workbench"` 在 ChatUI 右侧展示界面。文件预览可以由消息或工具打开；笔记、会话分析等常驻页面可以从工作台「＋」入口打开。

![上下文用量常驻工作台：当前会话的 token 估算及来源分布](/images/plugin-views/context-workbench.jpg)

下载[上下文用量示例插件](/examples/astrbot_plugin_context_workbench.zip)。安装后，打开 ChatUI 会话，点击工作台「＋」，在「新工作台」中选择「上下文用量」，无需工具调用。页面从 bridge context 获取当前 `sessionId`，展示系统指令、工具定义、对话和工具结果的 token 估算。

发送一条消息后点击「刷新」，可以查看最近请求的完整来源分布；未观测过请求的来源显示为未知。数值是估算，不代表模型实际计费 token。常驻页面的注册方式见[添加常驻入口](#注册常驻页面)。

## 从消息或工具打开

注册 `preview` 视图，让工具返回 `event.view_result()`。`title` 是标签标题，消息中会保留重新打开的入口。线程面板没有工作台，会将视图显示在消息中。

```python
from pathlib import Path

from astrbot.api import chatui
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Star

class PreviewPlugin(Star):
    chatui_views = [
        chatui.ViewSpec(
            name="preview",
            entry=Path("views/preview/index.html"),
            target="chat_workbench",
        ),
    ]

    @filter.llm_tool(name="open_preview")
    async def open_preview(self, event: AstrMessageEvent):
        """Open a preview in the workbench.

        Args:
            event: Incoming tool event.

        Returns:
            A view and a text result for the model.
        """
        return event.view_result(
            name="preview",
            title="Notes",
            data={"content": "Notes to review."},
            text="Opened notes in the workbench.",
        )
```

在 `views/preview/index.html` 和同目录的 `app.js` 中显示工具返回的数据：

```html
<!doctype html>
<html>
  <head><meta charset="utf-8" /><title>Notes</title></head>
  <body>
    <pre id="content"></pre>
    <script type="module" src="./app.js"></script>
  </body>
</html>
```

```javascript
const bridge = window.AstrBotPluginView;
await bridge.ready();
bridge.view.subscribe(({ data }) => {
  document.getElementById("content").textContent = data.content;
});
```

工具执行后，工作台显示 **Notes** 标签和正文。需要操作回调时，按[消息交互组件](./chat-message.md)声明 `actions`，并使用 `bridge.view.action()`。

## 注册常驻页面

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

将声明加入 `Star.chatui_views`，创建对应的入口文件后重载插件。在 ChatUI 顶部打开工作台，点击「＋」进入“新工作台”，选择 **上下文用量**。同一个注册视图在每个会话中只打开一个标签。

常驻视图复用独立插件页面的 Web API、文件传输和 SSE bridge，不声明消息 `actions`，也没有 `context.view` 消息快照。`sessionId` 是当前打开的聊天会话 ID；未打开会话时为 `null`。切换会话时重新挂载对应会话的视图，并传入该会话的 context：

```javascript
const bridge = window.AstrBotPluginView;
await bridge.ready();
bridge.onContext(({ sessionId }) => {
  // Fetch session-specific aggregates from your authenticated plugin API.
  if (sessionId) bridge.apiGet("usage", { session_id: sessionId });
});
```

插件后端必须用 `request.username` 校验会话归属，不能把前端传入的 `sessionId` 当作授权。异步请求要避免旧会话的响应覆盖新会话。三个 target 继续共用主题 CSS tokens 和 `onContext()`。

## 从常驻视图填入或发送消息

仅 `chat_workbench` 常驻视图（没有 `context.view`）提供以下接口，通常绑定到用户点击操作：

```javascript
await bridge.chat.fill("请帮我修改这段文字。");
await bridge.chat.send("请总结我选中的内容。");
```

`fill` 将文字追加到当前草稿并聚焦聊天框；`send` 直接发到当前会话，保留已有草稿与暂存附件。没有打开会话、会话已经切换或正在生成时，发送会被拒绝。Promise 在发送请求被接受时完成，不等待 bot 回复完成。

如果插件允许 agent 编辑文档，应在插件后端记录用户提交时的选区和版本，让工具只接收选区 ID 与替换文字。不要依赖提示词要求 agent 保留全文。工具保存后可以通过插件 SSE 通知常驻视图重新读取，客户端仍需保护未保存的本地编辑。

## 本地偏好存储

每个用户的标签、选中项和展开/收起状态按会话保存在浏览器中。切换会话时恢复对应的工作台；刷新不会自动打开已关闭的标签。插件业务数据需要由插件后端持久化。

主题、文件传输和 SSE 接口见[共享 Bridge API](./bridge.md)，后端鉴权与数据访问见[后端 Web API](./web-api.md)。
