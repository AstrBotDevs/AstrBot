# ChatUI inline work details

- Replaced the reasoning sidebar with two inline disclosure levels. The outer “Ran for …” summary contains all work before the final response, including intermediate assistant replies; adjacent thinking and tool calls have their own expandable summary.
- Previous entry → current entry: thinking/tool summary → right sidebar is now Ran for … → inline thinking/tool summary → downward expansion.
- The active thinking/tool group expands during execution and collapses when the next assistant reply starts; the first thought line toggles both ways.
- Run details expand during generation and collapse on completion. Summary rows align without borders or timeline rails; detail text aligns to the right of the leading icons.
- Thoughts expand in place without repeating the first line and show a single-line preview with an icon and expand arrow, aligned and sized like tool calls. Removed the small section labels and tightened summary spacing.
- Unified reasoning and tool icons with Lucide, including MessageCircleMore for thoughts. Thought text stays in one container with an animated height reveal and a stable first-line baseline.
- Preserved queued final SSE events at run completion and resynced interrupted streams, preventing missing final replies, tool results, and timing updates.
- WebSocket text chat now shares the resumable background run and persistence path with SSE. Refreshing during a tool call releases the subscriber without canceling history persistence; completed runs still release their queues.
- Added non-linear expand/collapse transitions with reduced-motion support and localized elapsed-time labels.

## 中文

- 思考侧边栏改为消息内两层折叠：“运行了 …”收起最终回复之前的全部过程，中间回复按顺序展示，相邻思考和工具调用可进一步展开。
- 旧入口 → 新入口：思考／工具摘要 → 右侧边栏，改为运行了 … → 消息内思考／工具摘要 → 向下展开详情。
- 当前思考／工具组执行时自动展开，在下一段 Assistant 正文出现时自动收起；思考首行支持双向切换。
- 生成时自动展开运行过程，完成后收起；各层摘要左对齐，去掉边框和步骤竖线；详情对齐图标右侧的文字。
- 思考原地展开全文，不重复第一行，收起时以带图标和展开箭头的单行预览显示，与工具调用字号一致；移除小标题并缩小摘要之间的间距。
- 思考和工具统一使用 Lucide 图标，思考采用 MessageCircleMore；正文保留在同一容器中，仅改变显示高度，首行基线保持稳定。
- 修复运行结束时丢弃末尾 SSE 事件的问题，并为中断的消息流补同步，避免最终回复、工具结果和耗时未更新。
- WebSocket 文字聊天与 SSE 共用可恢复的后台运行和落库流程；工具调用中刷新页面只释放订阅，不再取消历史保存，任务完成后仍清理队列。
- 展开和收起使用非线性缓动，并支持减少动态效果设置；耗时省略为零的前导单位。
