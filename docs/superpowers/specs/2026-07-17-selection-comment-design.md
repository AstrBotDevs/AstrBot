# 选中评论（Selection Comment）设计

- Author: elecvoid243
- Date: 2026-07-17
- Status: Approved (design), pending implementation plan
- Related:
  - `docs/superpowers/specs/2026-07-11-document-manager-design.md`
  - `dashboard/src/composables/useFileComments.ts`

## 1. 背景与目标

工作区（FileBrowserFilePreview）与文档管理（DocumentManager）共享同一套
行内评论系统： gutter 上的 "+" 按钮针对**单行**添加评论，评论经
`useFileComments` 单例 store 汇总后由 `formatForLLM` 渲染进 LLM 载荷。

实际阅读代码/文档时，用户想评论的往往是一个**片段**（几行代码、一段文字），
单行锚定表达力不足。本设计在**不改动现有单行评论**的前提下，新增：

1. 在代码视图内拖选文本后，鼠标松开处弹出小菜单：`[复制] [评论]`；
2. 「评论」针对选区（起始行–结束行）发表评论，与单行评论进入同一个
   评论列表，一并发送给 LLM；
3. 发送给 LLM 的信息包含：**文件绝对路径、起始行号、结束行号、选区内容**，
   其余格式与单行评论一致；
4. 两个页面（工作区、文档管理）同时获得该能力（二者共用
   `FileBrowserCodeView`）；
5. Markdown 渲染视图（文档管理渲染态、工作区 md 渲染态）弹同款菜单但
   仅含「复制」（渲染态无可靠的 DOM 选区→源码行号映射，已在评审中确认）。

## 2. 范围

### In scope

- 新组件 `SelectionActionMenu.vue`（固定定位小菜单）。
- `FileBrowserCodeView` 选区监听、行号映射、`request-add-range` 事件、
  范围评论 gutter 徽章覆盖。
- `useFileComments`：`FileComment` 增加可选 `endLine` / `selection` 字段；
  新增 `addSelectionComment()`；`formatForLLM` 范围渲染分支。
- `FileCommentEditor` 范围模式（头部 `L{start}-L{end}` + 选区预览）。
- 两个父组件（FileBrowserFilePreview / DocumentManager）的接线。
- 渲染容器（`.document-manager__rendered` / `.preview-markdown`）的
  仅复制菜单。
- `CommentsPreviewDialog` 预览镜像范围渲染。
- i18n（zh-CN / en-US / ru-RU）。

### Out of scope

- Diff 视图（`DiffPreview`）的选中评论——其评论走 `diffHunk` 另一套模型，
  选区对 diff 没有良好定义。
- 编辑模式（ShikiEditor / DocumentEditor）内的选中菜单。
- 历史原文（historical-raw）的评论（历史 blob 行号不应产生评论，
  通过 prop 关闭，仅保留「复制」）。
- `MarkdownView` 组件本身的改动（它还被聊天气泡使用；渲染态菜单在
  容器层实现）。
- 评论持久化（现状为内存 store，本设计不改变）。

## 3. 交互设计

| 场景 | 行为 |
|---|---|
| 代码视图拖选后松开鼠标 | 光标处弹出 `[复制] [评论]` 菜单 |
| 点「复制」 | 选区文本写入剪贴板（复用 `@/utils/clipboard`），短暂"已复制"反馈后关闭菜单；选区保留 |
| 点「评论」 | 菜单切换为评论输入框（FileCommentEditor 范围模式）；保存后写入评论 store，选区覆盖行 gutter 显示徽章 |
| 渲染视图拖选后松开鼠标 | 弹出同款菜单，仅 `[复制]` |
| 空选区 / 点击其他位置 / 滚动 / 缩放窗口 | 菜单关闭 |
| 切换文件、进入编辑模式、切换视图模式 | 菜单与未保存的评论输入一并关闭（沿用现有清理时机） |
| 历史原文 / diff / 编辑模式 / 二进制 / 过大占位 | 不弹菜单 |

定位细节：菜单使用视口固定定位（`position: fixed`），锚点为选区
`getRangeAt(0).getBoundingClientRect()` 的末端（即鼠标松开处）；接近视口
右/下边缘时向内偏移，防止溢出。

## 4. 组件设计

### 4.1 `SelectionActionMenu.vue`（新增，`message_list_comps/`）

职责：纯展示型小菜单，不感知行号与评论模型。

- Props:
  - `x: number`、`y: number` — 视口坐标（菜单左上角锚点）。
  - `showComment: boolean` — 是否显示「评论」项（渲染视图传 false）。
- Emits: `copy` / `comment` / `close`。
- 内部状态：复制反馈（`idle → copied`，1.5s 后自动关闭并 emit `close`）。
  菜单为纯展示组件：**剪贴板写入由父级**（CodeView / 渲染容器）在收到
  `copy` 事件后完成；菜单乐观显示"已复制"反馈（失败仅在控制台留
  `[clipboard]` 痕迹，与现有复制按钮的失败处理分级一致）。
- 样式：圆角浮层 + 阴影，与 `document-manager__notice` 同色系；
  按钮复用现有小型文本按钮规格；`role="menu"` + 两个 `role="menuitem"`。
- i18n：复制/已复制复用 `copy.copy` / `copy.copied`；评论复用
  `spcodeProjectLoad.fileBrowser.comment.add`（若无则用同级现有新增评论文案键）。

### 4.2 `FileBrowserCodeView.vue`（修改）

- 新增 prop `selectionCommentable?: boolean`（默认 `true`；历史原文用法
  传 `false`，此时菜单仅复制）。
- 选区监听：
  - `mouseup`（容器内）→ `window.getSelection()`；`isCollapsed` 或
    anchor/focus 不在容器内 → 忽略。
  - 行号映射：自 anchor/focus 节点向上找最近的 `.line` 祖先元素；
    取其在容器 `.line` 集合中的序号 +1。`startLine = min(anchor, focus)`，
    `endLine = max(...)`。任一端无法映射（如选中 gutter）→ 不弹菜单。
  - 选中文本：`selection.toString()`。
- 新增 emit：
  `(e: "request-add-range", payload: { startLine: number; endLine: number; selection: string }): void`。
- 菜单呈现：持有 `SelectionActionMenu` 状态（坐标/选区快照）；收到菜单
  `copy` 事件时由本组件完成剪贴板写入；收到 `comment` 时向上转发
  `request-add-range` 并关闭菜单。
- gutter 徽章范围覆盖：
  - `hasComment(line)` → `comments.some(c => c.line <= line && (c.endLine ?? c.line) >= line)`；
  - `commentIdFor(line)` / `commentText(line)` 同步按"第一个覆盖该行的评论"
    （保持数组顺序）取值。
- 关闭时机：`scroll`（捕获阶段，容器）、`mousedown`（菜单外）、
  `selectionchange` 折叠、`highlightedHtml`/`filePath` 变化、组件卸载。

### 4.3 `FileCommentEditor.vue`（修改）

- 新增可选 props：`endLine?: number | null`、`selectionContent?: string | null`。
- 范围模式（`endLine` 存在且 > `line`）：
  - 头部标签：`L{start}-L{end}`（新 i18n 键
    `spcodeProjectLoad.fileBrowser.comment.rangeLabel`，如
    "第 {start}–{end} 行"）。
  - 预览区：显示 `selectionContent`（冻结选区原文，等宽、限高滚动），
    替代单行的 `lineContent ±1` 预览。
- 编辑既有范围评论时，父组件从评论对象取 `endLine` / `selection` 回传，
  编辑器表现与新建一致；`save`/`delete` 载荷不变（按 `id` 处理）。

### 4.4 父组件接线（FileBrowserFilePreview / DocumentManager）

两者沿用各自现有单行评论接线，新增：

- `activeEditRange = ref<{ startLine: number; endLine: number; selection: string } | null>(null)`。
- `onRequestAddRange(payload)`：设置 `activeEditRange` 并打开
  `FileCommentEditor`（传 `:line="startLine"`、
  `:end-line="endLine"`、`:selection-content="selection"`）。
  （编辑模式下代码视图/渲染容器均不渲染，事件不可能触发，无需额外门控。）
- `onSaveComment` 分流：`activeEditRange` 非空 →
  `fileComments.addSelectionComment(...)`；否则原 `addComment` 路径。
- 历史原文的 `<FileBrowserCodeView>` 传 `:selection-commentable="false"`。
- 渲染容器（DocumentManager `.document-manager__rendered`、
  FileBrowserFilePreview `.preview-markdown`）：
  本地 `mouseup` → 选区非空且在容器内 → `SelectionActionMenu`
  （`show-comment=false`）→ `copy` 时写剪贴板。

## 5. 数据模型（向后兼容）

```ts
export interface FileComment {
  // ……现有字段保持不变……
  /** 范围评论的结束行（1-based）。缺省或 === line 表示单行评论。 */
  endLine?: number;
  /** 评论时冻结的选区原文（仅范围评论）。 */
  selection?: string;
}
```

`useFileComments` 新增：

```ts
function addSelectionComment(
  filePath: string,   // 绝对路径（与现有调用方一致）
  startLine: number,  // 1-based
  endLine: number,    // 1-based, >= startLine
  selection: string,  // 冻结选区原文
  text: string,       // 用户评论
): FileComment
```

字段填充规则：

- `line = startLine`，`endLine`，`selection`；
- `lineContent` = `selection` 的首行（继续充当 LLM 重定位指纹）；
- `contextBefore` = contentCache 中 `startLine - 1` 行（无则 null）；
- `contextAfter` = contentCache 中 `endLine + 1` 行（无则 null）。

单行评论的构造、序列化、比较逻辑完全不变（可选字段缺省）。

## 6. LLM 输出格式

`formatForLLM` 在 `renderWindow` 分支内识别范围评论
（`endLine !== undefined && endLine > line`）：

- 头部：`{filePath} L{start}-L{end}`（单行评论仍为原格式）；
- 正文：与单行评论相同的 ±`CONTEXT_LINES`(3) 行窗口（优先 contentCache），
  其中 `[startLine, endLine]` 区间内的**每一行**标 `>`；
- contentCache 缺失时：区间行用冻结的 `selection` 逐行填充，
  上下文行退化为 `contextBefore` / `contextAfter` 快照（与单行回退一致）。

`CommentsPreviewDialog.previewRows` 同步实现相同规则，保证"所见即
LLM 所得"。

## 7. 边界与错误处理

| 情况 | 处理 |
|---|---|
| 反向拖选（自下而上） | start/end 取 min/max |
| 选区含 gutter/行号列 | 行号列不可选（仅 `.line` 节点参与映射）；无法映射则不弹菜单 |
| 选区为空或仅空白字符 | 仍弹菜单（复制空白无害）；评论允许（用户负责） |
| 菜单溢出视口 | 右/下边缘内收 |
| 同一行被多个评论覆盖（单行 + 范围） | `commentIdFor` 取数组序首个；编辑入口不变 |
| 文件内容在评论后被编辑 | 与单行评论一致的漂移语义（行号 + 内容指纹） |
| 菜单打开时组件卸载 | 全部状态随组件销毁，无悬挂监听（`onBeforeUnmount` 移除全局监听） |

## 8. i18n

新增（zh-CN / en-US / ru-RU，`features/chat.json`）：

- `spcodeProjectLoad.fileBrowser.comment.rangeLabel`：
  "第 {start}–{end} 行" / "Lines {start}–{end}" / "Строки {start}–{end}"

复用：`copy.copy`、`copy.copied`、`spcodeProjectLoad.fileBrowser.comment.*`
（新增/保存/取消/删除等既有键）。

## 9. 验证

1. `cd dashboard && pnpm typecheck` 通过。
2. 手动走查：
   - 工作区代码文件：单行选中、跨行选中、反向拖选 → 复制/评论；
   - 文档管理原文视图：同上；
   - 评论 chip 数 +1，评论列表/预览弹窗显示范围标记与 `L{start}-L{end}`；
   - 预览弹窗展开内容与 `formatForLLM` 输出一致；
   - 文档管理渲染态、工作区 md 渲染态：菜单仅复制；
   - 历史原文 / diff / 编辑模式：无菜单；
   - gutter 徽章覆盖选区所有行，点击可编辑/删除范围评论；
   - 菜单在边缘不溢出，滚动/点击空白自动关闭。

## 10. 不做的事（YAGNI 备忘）

- 不做渲染态行号映射（已评审排除）；
- 不做 diff 选区评论；
- 不引入第三方 selection-menu 库（原生 Selection API 足够）；
- 不做评论持久化、多选区并存、选区高亮常驻。
