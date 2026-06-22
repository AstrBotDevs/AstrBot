# 增强评论 chip 交互（预览弹窗 + 一键清空）

| 项目 | 内容 |
|------|------|
| 主题 | 扩展 `ChatInput` 中已有的"N comments" chip：让 chip 主体可点击弹出预览弹窗，新增 chip 右上角 ✕ 按钮一键清空 |
| 日期 | 2026-06-22 |
| 作者 | elecvoid243 |
| 状态 | Draft — 待用户审阅 |
| 关联代码 | `dashboard/src/components/chat/ChatInput.vue`、`dashboard/src/components/chat/Chat.vue`、`dashboard/src/components/chat/StandaloneChat.vue`、`dashboard/src/composables/useFileComments.ts` |
| 前置 spec | `docs/superpowers/specs/2026-06-21-file-browser-inline-comments-design.md`（v1 的评论功能交付） |

---

## 1. 背景与目标

### 1.1 现状

v1 评论功能（`2026-06-21` spec）已交付：用户能在 `FileBrowserFilePreview` 里给代码行加评论，评论存储在 `useFileComments()` 单例 store 中，发送消息时 `formatForLLM()` 把所有评论以结构化文本附加到消息末尾。

`ChatInput.vue` 第 40–52 行有一个 `<v-chip>` 显示 "N comments"，但目前**只能看、不能操作**——用户想确认评论全文或删除某条评论，必须切回文件浏览器翻找，操作链路过长。

### 1.2 目标

在已有 chip 基础上扩展三个交互能力：

1. **chip 主体可点击** → 弹出全屏模态 `v-dialog`，按文件分组预览所有评论
2. **chip 右上角 ✕ 按钮** → 一键清空全部评论（带二次确认）
3. **预览弹窗里单条评论可删除** → 不带二次确认（影响面小）
4. **预览弹窗里"全部删除"按钮** → 走和 chip ✕ 完全相同的二次确认流程

### 1.3 非目标（显式不做）

- ❌ **不**在预览弹窗里编辑评论内容（编辑走文件浏览器的双击入口）
- ❌ **不**支持评论搜索/筛选/排序（v1 scope 内不必要）
- ❌ **不**做评论导入/导出（评论仅会话内内存存储）
- ❌ **不**改变评论数据模型（沿用 v1 的 `FileComment`）
- ❌ **不**改 `formatForLLM()` 的输出格式
- ❌ **不**改 LLM 后端契约

---

## 2. 设计决策（已与用户确认）

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 弹窗形式 | **`v-dialog`（全屏模态）** | 预览 + 多操作场景，中央模态最直观 |
| 2 | 数据流 | **去掉 `commentCount` prop，ChatInput 内部直接调用 `useFileComments()`** | 单例 store 自管，避免数据冗余；改动小但需要更新 `Chat.vue` / `StandaloneChat.vue` 的 prop 绑定 |
| 3 | chip ✕ 全部删除确认 | **小 `v-dialog` 二次确认** | 全部删除是高破坏性操作，强制二次确认最稳；snackbar 撤销的"5 秒内可恢复"对误触防护不够（一旦切窗口就错过了） |
| 4 | 弹窗里单条删除 | **无二次确认，直接删** | 影响面小，弹确认对话框太啰嗦；和现有 `gutter-add-btn` 的轻量交互一致 |
| 5 | 弹窗是否支持编辑 | **只读** | 弹窗只做"预览 + 删除"两个职责；编辑走文件浏览器双击原评论（避免两处入口状态不一致） |
| 6 | 弹窗内展示结构 | **按文件路径分组** | 评论和文件强关联；按文件分组最自然，跨文件查找清晰 |
| 7 | chip ✕ 显示逻辑 | **只在 hover chip 时才出现** | 简洁；和 chip "信息展示" 的本职不抢眼；避免静止状态下视觉杂乱 |
| 8 | 弹窗里"全部删除"按钮 | **弹窗 footer 也有"全部删除"按钮** | 走和 chip ✕ 一样的二次确认流程，用户在弹窗内也能一键清空，不用先关弹窗再点 chip |
| 9 | 二次确认组件 | **抽成独立的 `ConfirmDialog.vue` 通用组件** | 后续其它场景（如"删除 session"、"重置项目"）也可复用；避免在 ChatInput 里堆 v-dialog 代码 |

---

## 3. 数据流与状态

### 3.1 当前数据流

```
FileBrowserFilePreview  ─┐
                          ├─→ useFileComments()（模块单例）
Chat.vue (fileComments) ──┘              ↓
                                       comments[filePath]: FileComment[]
                                          ↓
                                   commentCount: number
                                          ↓
                                   ChatInput prop
                                          ↓
                                   <v-chip>{{ count }} comments</v-chip>
```

**问题**：ChatInput 拿不到评论详情（只有数字），无法做预览。

### 3.2 改造后数据流

```
FileBrowserFilePreview  ─┐
                          ├─→ useFileComments()（模块单例）
Chat.vue (fileComments) ──┘              ↓
                                       comments[filePath]: FileComment[]
                                          ↓
                          ┌── ChatInput 直接调用 useFileComments() ──┐
                          │   - fileComments.totalCount              │
                          │   - fileComments.commentsByFile() (新增) │
                          │   - fileComments.clearAll()        (新增) │
                          └─────────────────────────────────────────┘
```

**改动点**：
- 删除 `ChatInput` 的 `commentCount: number` prop
- `Chat.vue` / `StandaloneChat.vue` 移除 `:comment-count="..."` 绑定
- `ChatInput` 内部 `const fileComments = useFileComments()`
- `useFileComments()` 新增两个方法：
  - `commentsByFile(): Array<{ filePath: string; comments: FileComment[] }>` —— 按文件路径分组，每组按行号排序
  - `clearAll(): void` —— 清空所有评论

### 3.3 ChatInput 新增本地状态

| 状态 | 类型 | 用途 |
|------|------|------|
| `previewDialogOpen` | `Ref<boolean>` | 评论预览弹窗开关 |
| `confirmClearOpen` | `Ref<boolean>` | 全部删除的二次确认弹窗开关 |
| `chipHovered` | `Ref<boolean>` | chip 容器是否被 hover（控制 ✕ 按钮显隐） |

---

## 4. UI 结构

### 4.1 ChatInput 改造后的 chip（伪代码）

```vue
<div
  class="comment-count-chip d-none d-md-flex"
  :class="{ 'comment-count-chip--hovered': chipHovered }"
  variant="tonal"
  color="warning"
  size="small"
  @mouseenter="chipHovered = true"
  @mouseleave="chipHovered = false"
>
  <button
    type="button"
    class="comment-count-chip__main"
    @click="previewDialogOpen = true"
    :aria-label="tm('comment.previewDialog.open')"
  >
    <v-icon size="14" start>mdi-comment-text-outline</v-icon>
    {{ tm("...countLabel", { count: fileComments.totalCount.value }) }}
  </button>
  <button
    v-if="chipHovered"
    type="button"
    class="comment-count-chip__clear"
    :aria-label="tm('comment.chip.clearAll')"
    @click.stop="confirmClearOpen = true"
  >
    <v-icon size="14">mdi-close</v-icon>
  </button>
</div>
```

**关键点**：
- chip 不再用 `<v-chip>` 而是改成 `<button>` 套 `<button>`（v-chip 不支持嵌套交互元素），样式模仿 v-chip 的"tonal + warning"
- 内层 `__main` 触发打开预览弹窗
- 内层 `__clear` 默认 `v-if="chipHovered"`，点击用 `.stop` 阻止冒泡到外层（避免误触发打开弹窗）
- 外层用 `mouseenter`/`mouseleave` 维护 hover 状态

### 4.2 评论预览弹窗 `CommentsPreviewDialog.vue`（新组件）

```
┌──────────────────────────────────────────────────┐
│  评论预览 (N)                                  ×  │
├──────────────────────────────────────────────────┤
│                                                  │
│  ▾ src/foo.py                                    │
│    ┌──────────────────────────────────────────┐  │
│    │ L 35  │ from astrbot.core import ...    │  │
│    │ 这行代码是什么意思                      ✕ │  │
│    └──────────────────────────────────────────┘  │
│    ┌──────────────────────────────────────────┐  │
│    │ L 47  │ from astrbot.core.utils.io...  │  │
│    │ 123                                  ✕ │  │
│    └──────────────────────────────────────────┘  │
│                                                  │
│  ▾ src/bar.py                                    │
│    ┌──────────────────────────────────────────┐  │
│    │ L 12  │ def hello():                    │  │
│    │ 多行评论\n第二行\n第三行              ✕ │  │
│    └──────────────────────────────────────────┘  │
│                                                  │
├──────────────────────────────────────────────────┤
│                          [全部删除]      [关闭]   │
└──────────────────────────────────────────────────┘
```

**组件 props/emit**：

```ts
defineProps<{
  modelValue: boolean;  // dialog 开关（v-model）
  groups: Array<{
    filePath: string;
    comments: FileComment[];  // 已按行号排序
  }>;
}>()
const emit = defineEmits<{
  "update:modelValue": [v: boolean];
  "delete-comment": [commentId: string];
  "request-clear-all": [];  // 父组件负责弹二次确认
}>()
```

**为什么 emit 而不是直接调 `useFileComments()`**：保持组件纯展示，方便复用 / 测试。

### 4.3 二次确认弹窗 `ConfirmDialog.vue`（新通用组件）

```vue
<v-dialog :model-value="modelValue" max-width="420" @update:model-value="$emit('update:modelValue', $event)">
  <v-card>
    <v-card-title>{{ title }}</v-card-title>
    <v-card-text>
      <p>{{ message }}</p>
      <slot name="extra" />
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn variant="text" @click="$emit('cancel')">{{ cancelText }}</v-btn>
      <v-btn :color="confirmColor ?? 'error'" variant="flat" @click="$emit('confirm')">
        {{ confirmText }}
      </v-btn>
    </v-card-actions>
  </v-card>
</v-dialog>
```

**Props**：

```ts
defineProps<{
  modelValue: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  confirmColor?: string;
}>()
const emit = defineEmits<{
  "update:modelValue": [v: boolean];
  confirm: [];
  cancel: [];
}>()
```

**首次复用场景**：评论清空确认。后续可被 "删除项目会话"、"重置项目" 等场景复用。

---

## 5. 关键代码片段

### 5.1 `useFileComments()` 新增方法

```ts
/** All comments grouped by filePath, with each group sorted by line ASC.
 *  Returns a stable array structure suitable for v-for. */
function commentsByFile(): Array<{ filePath: string; comments: FileComment[] }> {
  const entries = Object.entries(comments)
    .filter(([, list]) => list.length > 0)
    .map(([filePath, list]) => ({
      filePath,
      comments: [...list].sort((a, b) => a.line - b.line),
    }));
  entries.sort((a, b) => a.filePath.localeCompare(b.filePath));
  return entries;
}

/** Delete every comment across all files. */
function clearAll(): void {
  for (const k of Object.keys(comments)) delete comments[k];
}
```

### 5.2 ChatInput 中的 chip 容器 CSS（替换 v-chip 的样式）

```css
.comment-count-chip {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 24px;
  padding: 0 10px;
  border-radius: 12px;
  background: rgba(var(--v-theme-warning), 0.16);
  color: rgb(var(--v-theme-warning));
  font-size: 12px;
  line-height: 1;
}
.comment-count-chip__main {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: 0;
  padding: 0;
  margin: 0;
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.comment-count-chip__main:hover,
.comment-count-chip__main:focus-visible {
  filter: brightness(1.1);
}
.comment-count-chip__clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: rgba(var(--v-theme-error), 0.85);
  color: rgb(var(--v-theme-on-error));
  border: 0;
  padding: 0;
  margin-left: 2px;
  cursor: pointer;
  opacity: 0.85;
  transition: opacity 0.12s, transform 0.12s;
}
.comment-count-chip__clear:hover {
  opacity: 1;
  transform: scale(1.08);
}
```

### 5.3 ChatInput 改动后的事件处理

```ts
import { useFileComments } from "@/composables/useFileComments";

const fileComments = useFileComments();
const previewDialogOpen = ref(false);
const confirmClearOpen = ref(false);
const chipHovered = ref(false);

function onDeleteComment(id: string): void {
  fileComments.deleteComment(id);
}
function onConfirmClearAll(): void {
  fileComments.clearAll();
  confirmClearOpen.value = false;
}
```

### 5.4 i18n key 清单

新增（`features/chat` namespace）：

| key | zh-CN | en-US |
|---|---|---|
| `comment.previewDialog.open` | 打开评论预览 | Open comments preview |
| `comment.previewDialog.title` | 评论预览 ({count}) | Comments preview ({count}) |
| `comment.previewDialog.empty` | 暂无评论 | No comments yet |
| `comment.previewDialog.closeButton` | 关闭 | Close |
| `comment.previewDialog.clearAllButton` | 全部删除 | Clear all |
| `comment.previewDialog.lineLabel` | L {line} | L {line} |
| `comment.chip.clearAll` | 清空全部评论 | Clear all comments |
| `comment.confirmClear.title` | 清空全部评论？ | Clear all comments? |
| `comment.confirmClear.message` | 将删除当前会话的全部 {count} 条评论，此操作不可撤销。 | This will delete all {count} comments in the current session. This action cannot be undone. |
| `comment.confirmClear.confirm` | 全部删除 | Clear all |
| `comment.confirmClear.cancel` | 取消 | Cancel |

`spcodeProjectLoad.fileBrowser.comment.countLabel` / `countTooltip` / `addButtonAria` / `indicatorAria` 沿用 v1。

---

## 6. 风险与边界

### 6.1 数据流改动

- **风险**：删除 `commentCount` prop 后，`Chat.vue` / `StandaloneChat.vue` 仍有遗留引用 → TypeScript / 运行时错误。
- **缓解**：改完后跑 `pnpm tsc --noEmit` 和 `pnpm build`；`grep` 全仓确认 `commentCount` / `:comment-count` 没有遗漏引用。

### 6.2 `chipHovered` 在触摸设备上的行为

- **风险**：移动端 `< md` chip 默认 `d-none`，不显示，所以触摸场景不在范围内。但若以后解除移动端隐藏，`@mouseenter`/`@mouseleave` 在触屏上不触发。
- **缓解**：保持现有 `d-none d-md-flex` 不变；chip ✕ 仅 desktop 可见。移动端如需清空评论，走预览弹窗里的"全部删除"按钮（永远可见）。

### 6.3 chip 内嵌按钮的可访问性

- **风险**：`<button>` 嵌套在另一个交互元素里，屏幕阅读器可能报"interactive nested"问题。
- **缓解**：每个按钮都有 `aria-label`；主按钮和清除按钮的 `aria-label` 不同；外层用 `<div>` 而非 `<button>` 避免嵌套按钮的 HTML 违规。

### 6.4 二次确认组件的复用面

- **风险**：可能过度设计（YAGNI）。
- **缓解**：实现简洁（< 50 行），接受这个轻度复用成本；如果后续没复用，删除也容易。

### 6.5 弹窗打开时 chip 的 hover 状态残留

- **风险**：hover chip 时打开弹窗，chipHovered=true 状态不会自动清除。
- **缓解**：chip mouseleave 时 chipHovered=false，弹窗打开后用户鼠标自然移开；不强制清状态不影响功能。

---

## 7. 测试与验证

### 7.1 手动测试清单

1. **未加评论时**：chip 不显示（`v-if="totalCount > 0"`）
2. **加一条评论**：chip 出现，显示 "1 comments"
3. **hover chip**：✕ 按钮出现，红色圆形
4. **点 chip 主体**：打开预览弹窗，显示该评论
5. **点 chip ✕**：打开二次确认弹窗 "清空全部 1 条评论？"
6. **点确认**：评论清空，chip 消失，preview dialog 如果开着会自动关闭（因为 v-if）
7. **点取消**：二次确认关闭，评论保留
8. **预览弹窗里加 2 个文件的评论**：弹窗按文件分组，每组按行号排序
9. **点预览里的单条 ✕**：该评论消失，弹窗不关
10. **点预览里的"全部删除"**：二次确认弹窗，确认后评论全清，弹窗关闭，chip 消失

### 7.2 自动化验证

- `pnpm tsc --noEmit` 无错
- `pnpm build` 通过
- `pnpm lint` 通过
- `grep -r "commentCount" dashboard/src` 不应再有任何活跃引用（仅 import / 类型定义除外）

### 7.3 国际化验证

- 切换 zh-CN / en-US / ru-RU，所有新增 key 都有非空翻译
- 新增 key 漏翻译 → 走 fallback（现有 `useModuleI18n` 已处理）

---

## 8. 实现清单（高层级）

| 文件 | 改动 | 类型 |
|------|------|------|
| `dashboard/src/composables/useFileComments.ts` | 新增 `commentsByFile()` 和 `clearAll()` | 修改 |
| `dashboard/src/components/chat/ChatInput.vue` | 替换 chip 为自定义容器，引入 useFileComments，加预览弹窗 + 二次确认弹窗 | 修改 |
| `dashboard/src/components/chat/CommentsPreviewDialog.vue` | 新建预览弹窗组件 | 新建 |
| `dashboard/src/components/chat/ConfirmDialog.vue` | 新建通用确认弹窗组件 | 新建 |
| `dashboard/src/components/chat/Chat.vue` | 移除 `:comment-count="..."` | 修改 |
| `dashboard/src/components/chat/StandaloneChat.vue` | 移除 `:comment-count="..."` | 修改 |
| `dashboard/src/i18n/locales/*/features/chat.json`（zh/en/ru） | 新增 11 个 key | 修改 |

---

## 9. 关联与影响

- **依赖**：v1 spec `2026-06-21-file-browser-inline-comments-design.md`（`FileComment` 数据模型、`useFileComments()` 单例）
- **影响**：仅前端；后端契约不变
- **用户感知**：发送消息前多了一个"管理评论"的便捷入口；行为不破坏现有评论流程