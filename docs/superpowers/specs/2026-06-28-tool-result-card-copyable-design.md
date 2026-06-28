# 工具调用结果卡片：可复制文本 + 显式复制入口

| 项目 | 内容 |
|------|------|
| 主题 | 在工具调用结果展示的卡片式组件里，让文本可选可复制，并在 hover 时提供显式的复制按钮 |
| 日期 | 2026-06-28 |
| 作者 | elecvoid243 |
| 状态 | Implemented — 2026-06-28 |
| 关联代码 | `dashboard/src/components/chat/message_list_comps/`（8 个文件） + i18n 3 个 locale |
| 前置 spec | 无（独立增强） |

---

## 1. 背景与目标

### 1.1 现状

AstrBot Dashboard 在 `dashboard/src/components/chat/message_list_comps/` 下用卡片式布局展示工具调用结果：

- **ToolCallCard.vue**：每个工具调用的 args 渲染为可点击展开/收起的 row
- **CodeCheckResult.vue / CodeCheckResultList.vue**：lint issue 渲染为可点击展开/收起的 row
- **CodeExploreResult.vue**：符号信息渲染为可点击展开/收起的 card
- **EsSearchResult.vue**：搜索结果项渲染为可点击展开/收起的 row
- **IntaShellToolResultView.vue**：交互式 shell 会话/输出
- **ToolResultView.vue**：通用工具结果（文件内容、shell 输出、Python 输出、grep 结果）

行/卡片的整行 `cursor: pointer` + `@click` 触发展开。**但**：

1. **缺少显式复制入口**：除 `IntaShellToolResultView` 里的内联 `SessionIdCopy` 外，参数值、文件路径、错误消息、符号名、shell 输出、grep 命中的文件路径等高频"复制目标"都没有 hover 出现的复制按钮。
2. **可点击整行的视觉信号让用户难以发现"可复制"**：虽然技术上 `.args-row` 等容器并未设置 `user-select: none`（只有 `.tool-call-header` 按钮有），浏览器默认 `user-select: text` 仍生效，拖选能选中。但 `cursor: pointer` 叠加整行 `@click` 的视觉信号让用户习惯性地不去尝试拖选，倾向于去找专门的"复制"按钮——而这个按钮并不存在。
3. **现有 `SessionIdCopy` 没被复用**：作为内联子组件被埋在 `IntaShellToolResultView.vue` 里，无法被其它组件使用。

### 1.2 目标

1. 在所有"卡片式工具结果"内提供**统一的 hover 复制按钮**，覆盖高频复制目标。
2. 在 `CopyableText` 内部显式声明 `user-select: text` + `cursor: text`，让文本可选这一事实变得"明显"。
3. 抽出可复用的 `CopyableText` 组件，**替代**现有 `SessionIdCopy`，作为单一来源。
4. 不破坏现有"点击整行展开"的交互（用户明确要求保留）。

### 1.3 非目标（显式不做）

- ❌ **不**改"点击整行展开"的交互模型
- ❌ **不**改任何工具结果的数据 schema（args、result 字符串不变）
- ❌ **不**改 LLM 后端契约
- ❌ **不**在 `CodeIndexResult.vue` / `TodoListResult.vue` / `TodoListPanel.vue` / `FileDiffResult.vue` 内加复制入口（这些场景不构成高频复制需求，避免 YAGNI）
- ❌ **不**在 `FileRemoveResult.vue` 内加复制入口（该组件的 `error-row` 含 `error-path`，虽是文件路径但低频；如未来需要可后续追加）
- ❌ **不**改 i18n 工具的使用方式
- ❌ **不**做双击复制、键盘快捷键复制等扩展形式（hover 按钮 + 键盘 Tab/Enter 已覆盖主要可访问性场景；避免 YAGNI）
- ❌ **不**新增前端单元测试基础设施（项目当前无 vitest 在 devDependencies 中，`pnpm test` 不存在）

---

## 2. 设计决策（已与用户确认）

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 改造范围 | **A：全部统一改造**（**8** 个文件） | 用户体验最一致；改动虽然涉及多文件，但每处改造都是机械的 |
| 2 | 整行 click 行为 | **保留** | 用户明确要求；不影响复制按钮本身（按钮用 `@click.stop` 阻止冒泡） |
| 3 | 复制按钮展示方式 | **Hover 时浮现** | 符合现代 UI 习惯；静止状态简洁；不影响阅读 |
| 4 | 组件实现方式 | **A1：独立 `CopyableText.vue` 组件** | 模板可读性最高（`<CopyableText :value="x" />`）；与现有 `SessionIdCopy` 设计哲学一致；未来扩展（tooltip / 双击复制）集中改一处 |
| 5 | `CopyableText` 的 mode | **3 种：inline / code / block** | inline 短文本行内、code 等宽短文本、block 多行内容（含 `<pre>` 风格） |
| 6 | i18n 键 | **新增 `copy.copy` / `copy.copied`**（3 个 locale） | `useModuleI18n("features/chat")` 自动前置 `features.chat.`，调用时只写 `tm("copy.copy")` 即可（key path 在 JSON 里就是 `copy.copy.copy`，但调用处是 `copy.copy`） |
| 7 | 暗色模式 | **不需额外适配** | 全部使用 `--v-theme-on-surface` 变量，自动跟随 |
| 8 | `SessionIdCopy` 命运 | **删除，被 `CopyableText` 替代** | 单一来源；功能等价；约 50 行代码缩减 |
| 9 | `SessionIdCopy` 的 8 字符截断 | **保留截断**（最小破坏） | `CopyableText` 增加可选 `displayValue` prop（不传则 `value` 既作显示也作复制源；传则 `value` 仍为复制源，`displayValue` 为显示文本） |
| 10 | 大块 code/result 块 | **复用 `CopyableText` block 模式 + `default` 插槽** | 让高亮后的 Shiki 渲染保留在内部；按钮浮在右上角；复制源是 `value` 字符串 |
| 11 | i18n key 调用方式 | **`tm("copy.copy")` / `tm("copy.copied")`** | 现有 `useModuleI18n("features/chat")` 在 `composables.ts:131-134` 自动拼接前缀为 `features.chat.copy.copy` / `features.chat.copy.copied`；JSON 中放在 `copy` 命名空间下 |
| 12 | 缺失的 vitest | **不写单元测试** | 项目当前 `package.json` 没有 `vitest` devDependency 也没有 `test` 脚本；新增测试基础设施超出本次 scope。改用手测矩阵 + lint + typecheck + build 验证 |

---

## 3. 数据流与状态

### 3.1 新增的组件（无新数据流）

`CopyableText` 是纯展示组件，不引入新的 store / composable / 跨组件通信。复制操作走项目已有的 `@/utils/clipboard.ts` 的 `copyToClipboard` 函数（**async**）。

### 3.2 `CopyableText.vue` 内部状态

```ts
interface Props {
  value: string                       // 必填：复制源（始终是复制目标）
  displayValue?: string               // 可选：显示文本，不传则用 value
  mode?: 'inline' | 'code' | 'block'  // 默认 'inline'
  placeholder?: string                // 空值时显示，默认 '—'
  multiline?: boolean                 // block 模式下保留换行，默认 false
  showIcon?: boolean                  // 是否显示复制按钮，默认 true
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'inline',
  placeholder: '—',
  multiline: false,
  showIcon: true,
})

const copied = ref(false)             // 复制成功反馈，1.2s 后重置

async function handleCopy() {
  // 必须 await：copyToClipboard 返回 Promise<boolean>，不 await 就立刻翻 copied=true
  const ok = await copyToClipboard(props.value)
  if (ok) {
    copied.value = true
    setTimeout(() => { copied.value = false }, 1200)
  }
  // 失败时静默：copied 不变，按钮不翻转；可考虑 console.warn，但 UX 不反馈
}
```

### 3.3 Slots

`CopyableText` 提供 1 个 slot：

| Slot | 用途 | 与 `value` 关系 |
|------|------|----------------|
| `default` | 自定义显示内容（高亮 HTML、`<pre>` 等） | 传插槽时 `displayValue` 与 `value` 都被忽略；`value` 仍作为复制源 |

`mode="inline"` 不建议与 `default` 插槽混用（行内布局不适合塞大块 HTML）。其它两种 mode 正常使用。

### 3.4 改造前后对比（以 args 为例）

**Before**：
```vue
<span class="args-value">{{ entry.display }}</span>
<span v-if="entry.long && !expandedArgs[i]" class="args-expand-hint">…</span>
```
文本通过 Vue 模板插值直接渲染；`user-select` 走浏览器默认（text 可选）；但 `cursor: pointer` 来自父 `.args-row.clickable`，让人误以为不可选。

**After**（**保留 60 字符截断**和 `…` 提示）：
```vue
<CopyableText
  :value="entry.raw"
  :display-value="entry.display"
  mode="code"
  class="args-value"
  :show-icon="entry.long"
/>
<span v-if="entry.long && !expandedArgs[i]" class="args-expand-hint">…</span>
```

- `value`（= `entry.raw`）始终是完整文本（复制源）
- `displayValue`（= `entry.display`）控制显示文本：长值时为截断的 60 字符 + 可展开
- 复制按钮仅在 `entry.long` 时显示（避免短文本视觉噪声）
- `…` 提示符逻辑不变（与展开状态联动）
- `args-value` CSS 类只保留布局（`min-width: 0` 等），等宽字体/颜色由 `CopyableText` 内部 `code` mode 提供

---

## 4. 架构与组件

### 4.1 目录结构

```
dashboard/src/components/chat/message_list_comps/
├── __shared__/                          ← 新建目录，放 chat 子树内的共享小组件
│                                         （注意：项目另有 dashboard/src/components/shared/，
│                                          那是全局共享；本目录只放 chat-local 共享组件，
│                                          避免污染全局命名空间）
│   └── CopyableText.vue                 ← 新组件（~180 行）
├── ToolCallCard.vue                     ← 改造 #1
├── ToolResultView.vue                   ← 改造 #2
├── IntaShellToolResultView.vue          ← 改造 #3（删除内联 SessionIdCopy）
├── IPythonToolBlock.vue                 ← 改造 #4
├── ToolCallItem.vue                     (不变)
├── SpcodeToolResultView.vue             (不变，分发入口)
└── spcode_tools/
    ├── CodeCheckResult.vue              ← 改造 #5
    ├── CodeCheckResultList.vue          ← 改造 #6（与 #5 完全相同的改动）
    ├── CodeExploreResult.vue            ← 改造 #7
    ├── EsSearchResult.vue               ← 改造 #8
    ├── FileRemoveResult.vue             (不变)
    ├── FileDiffResult.vue               (不变，状态行)
    ├── CodeIndexResult.vue              (不变，统计数字)
    ├── TodoListResult.vue / TodoListPanel.vue  (不变)
    └── icons.ts                         (不变)
```

### 4.2 `CopyableText.vue` 设计

#### Props

| Prop | 类型 | 默认 | 说明 |
|------|------|------|------|
| `value` | `string` | 必填 | 复制源（始终是复制目标） |
| `displayValue` | `string` | undefined | 显示文本；不传则用 `value` |
| `mode` | `'inline' \| 'code' \| 'block'` | `'inline'` | 视觉模式 |
| `placeholder` | `string` | `'—'` | 空值（`!value`）时显示 |
| `multiline` | `boolean` | `false` | block 模式下保留换行 |
| `showIcon` | `boolean` | `true` | 是否显示复制按钮 |

#### 三种 mode 的视觉

- **`inline`**：行内文本。容器预留 `padding-right: 18px` 给图标留位（不挤压文本），hover 时图标以 `position: absolute` 浮在预留位置之上。点击目标 = 图标本身（`@click.stop`）。**布局不抖动**。
- **`code`**：等宽字体（继承 monospace），浅灰背景；hover 时图标以 `position: absolute` 浮在右上角。
- **`block`**：块级，`<pre>` 风格保留换行；容器 `position: relative`；复制按钮固定在右上角，hover 时浮现（GitHub code block 风格）。支持 `default` 插槽嵌入任意内容（Shiki HTML、`<pre>`、嵌套组件等）。

#### 行为细节

- 容器默认 `user-select: text` + `cursor: text`，确保文本可选
- 复制按钮 `position: absolute`（block/code 模式）或预留位置（inline 模式）
- 默认 `opacity: 0`；`:hover` 与 `:focus-within` 时 `opacity: 1`，过渡 `0.15s`
- 触发复制：`async function handleCopy() { const ok = await copyToClipboard(value); if (ok) { copied = true; setTimeout(() => copied = false, 1200) } }` —— **必须 await**，否则 `copied=true` 会在复制实际完成前翻转
- 按钮用 `@click.stop` 阻止冒泡到外层可点击的 row，避免误触发展开
- `<button type="button" :aria-label="tm('copy.copy')">` —— 键盘 Tab 可聚焦，Enter 触发
- 复制成功时按钮的 `aria-label` 切换为 `tm('copy.copied')`
- 空值处理：`!value` 时渲染 `placeholder` 文案（不应用 `displayValue`），`show-icon` 强制为 `false`

#### `position: absolute` 与 `overflow: hidden` 冲突的处理

审查代码后识别出下列父容器**可能**会裁掉 `position: absolute` 的按钮：

| 父选择器 | 文件 | 当前 `overflow` | 处理方式 |
|----------|------|---------------|---------|
| `.args-table` | `ToolCallCard.vue:265` | `hidden` | 在 `.args-table` 加 `overflow: visible`（仅 args 表格需要） |
| `.issues-block.is-expanded` | `CodeCheckResult.vue:204` / `CodeCheckResultList.vue:159` | `auto`（展开时才有滚动） | **接受裁切**：只在展开态时父容器有滚动条，按钮浮在 issue-row 内，裁切无影响（按钮在 row 内顶部；row 自身 `overflow: visible`） |
| `.session-list` | `IntaShellToolResultView.vue:583` | `auto`（仅当会话数 > 7 时滚动） | 同上，CopyableText 内的 `meta-value` / `output-value` 不在 list 滚动区里 |
| `.issues-block`（非展开） | 同上 | visible | OK |

`CopyableText` 自身**不**设 `overflow`，让按钮自然外溢。**唯一需要改的父容器是 `.args-table`**（实施步骤 3.1 中处理）。

### 4.3 各文件改造点

#### 4.3.1 `ToolCallCard.vue` — args value 列

```vue
<!-- Before -->
<span class="args-value">{{ entry.display }}</span>
<span v-if="entry.long && !expandedArgs[i]" class="args-expand-hint">…</span>

<!-- After -->
<CopyableText
  :value="entry.raw"
  :display-value="entry.display"
  mode="code"
  class="args-value"
  :show-icon="entry.long"
/>
<span v-if="entry.long && !expandedArgs[i]" class="args-expand-hint">…</span>
```

样式调整：`.args-value` 类只保留 `min-width: 0` 等布局属性；等宽字体/颜色由 `CopyableText` 内部 `code` mode 提供。

`.args-row` 的 `@click="entry.long && toggleArgExpand(i)"` 保留。复制按钮 `@click.stop` 阻止冒泡。

**`.args-row.args-more`（"Show fewer / +N more" 行的 label）保留为 `<span class="args-value args-more-text">` 不动**——它不是数据，是操作标签。

**`.args-table` 的 CSS** 加 `overflow: visible`（替换原来的 `hidden`），避免裁切 args-row 内的 hover 按钮（见 §4.2 冲突分析）。

#### 4.3.2 `CodeCheckResult.vue` — issue 三件套

```vue
<!-- Before -->
<span class="issue-loc">{{ getLocText(iss) }}</span>
<span class="issue-code">{{ getCode(iss) }}</span>
<span class="issue-msg">{{ getMessage(iss) }}</span>

<!-- After -->
<CopyableText :value="getLocText(iss)" mode="code" class="issue-loc" />
<CopyableText :value="getCode(iss)" mode="code" class="issue-code" />
<CopyableText :value="getMessage(iss)" mode="block" :multiline="true" class="issue-msg" />
```

`.issue-row` 的 `@click="toggleIssue(i)"` 保留。

#### 4.3.3 `CodeCheckResultList.vue` — issue 三件套（merge 模式）

**与 §4.3.2 完全相同**，逐行 apply：`<span class="issue-loc">` / `<span class="issue-code">` / `<span class="issue-msg">` 全部替换。

> **重复实施风险提示**：§4.3.2 与 §4.3.3 的改造点字面完全相同；实施时按"先 #5 后 #6"或"先 #6 后 #5"的顺序都无所谓，但完成时必须两个文件都已检查。

#### 4.3.4 `CodeExploreResult.vue` — symbol & callers

```vue
<!-- Before -->
<span class="symbol-name">{{ sym.name }}</span>
<span class="symbol-loc">{{ sym.file }}:{{ sym.line }}</span>
<code v-for="c in data.callers[sym.name]" :key="c" class="caller-chip">{{ c }}</code>

<!-- After -->
<CopyableText :value="sym.name" mode="inline" class="symbol-name" />
<CopyableText :value="`${sym.file}:${sym.line}`" mode="code" class="symbol-loc" />
<CopyableText
  v-for="c in data.callers[sym.name]"
  :key="c"
  :value="c"
  mode="code"
  class="caller-chip"
/>
```

#### 4.3.5 `EsSearchResult.vue` — file 路径

```vue
<!-- Before -->
<span class="item-name">{{ item.name }}</span>
<span class="item-path">{{ item.path }}</span>

<!-- After -->
<CopyableText :value="item.name" mode="inline" class="item-name" />
<CopyableText :value="item.path" mode="code" class="item-path" />
```

#### 4.3.6 `IntaShellToolResultView.vue`

a) **删除内联 `SessionIdCopy` 子组件**（约 50 行），改用 `CopyableText`：

```vue
<!-- Before -->
<SessionIdCopy v-if="parsed.session" :session-id="parsed.session.session_id" />

<!-- After -->
<CopyableText
  v-if="parsed.session"
  :value="parsed.session.session_id"
  :display-value="parsed.session.session_id.length > 12
    ? `${parsed.session.session_id.slice(0, 8)}…`
    : parsed.session.session_id"
  mode="code"
  class="session-id"
/>
```

b) **为 meta-value / output-value / meta-value-dim / session-list-cmd / initial_output 添加复制**：

```vue
<!-- start: command + initial_output -->
<!-- Before -->
<code class="meta-value">{{ parsed.session.command }}</code>
...
<pre v-if="hasInitialOutput" class="output-value">{{ parsed.initial_output }}</pre>

<!-- After -->
<CopyableText :value="parsed.session.command" mode="code" class="meta-value" />
...
<CopyableText
  v-if="hasInitialOutput"
  :value="parsed.initial_output"
  mode="block"
  :multiline="true"
  class="output-value"
/>
```

```vue
<!-- read: output + pid/created_at (meta-value-dim) -->
<!-- Before -->
<pre v-if="hasOutput" class="output-value">{{ parsed.output }}</pre>
...
<span class="meta-value-dim">{{ parsed.session.pid }}</span>
<span v-if="parsed.session.created_at" class="meta-value-dim">{{ ... }}</span>

<!-- After -->
<CopyableText
  v-if="hasOutput"
  :value="parsed.output"
  mode="block"
  :multiline="true"
  class="output-value"
/>
...
<CopyableText :value="String(parsed.session.pid)" mode="code" class="meta-value-dim" />
<CopyableText
  v-if="parsed.session.created_at"
  :value="formatRelativeTime(parsed.session.created_at)"
  mode="code"
  class="meta-value-dim"
/>
```

```vue
<!-- list: 每个 session 的 command + pid + last_activity -->
<!-- Before -->
<code class="session-list-cmd">{{ s.command }}</code>
...
<span class="meta-value-dim">pid {{ s.pid }}</span>
<span v-if="s.last_activity" class="meta-value-dim">{{ formatRelativeTime(s.last_activity) }}</span>

<!-- After -->
<CopyableText :value="s.command" mode="code" class="session-list-cmd" />
...
<CopyableText :value="`pid ${s.pid}`" mode="code" class="meta-value-dim" />
<CopyableText
  v-if="s.last_activity"
  :value="formatRelativeTime(s.last_activity)"
  mode="code"
  class="meta-value-dim"
/>
```

> **`v-else class="empty-note"` 分支不受影响**：原本 `parsed.output` 为空时显示 `<span class="empty-note">{{ tm('intaShell.labels.noOutput') }}</span>`，这个分支在 CopyableText 的 `v-if="hasOutput"` 之外，**不经过 CopyableText**，保留原样。

#### 4.3.7 `ToolResultView.vue` — code/result 块 + 新增高价值文件路径

a) **file_read_tool 头部：file path 可复制**（reviewer 指出的高频目标）：

```vue
<!-- Before -->
<span class="result-header-text">{{ readFilePath }}</span>

<!-- After -->
<CopyableText :value="readFilePath" mode="code" class="result-header-text" />
```

b) **grep_tool：每条匹配的文件路径可复制**（reviewer 指出的高频目标）：

```vue
<!-- Before -->
<span v-if="line.file" class="grep-file">{{ line.file }}</span>

<!-- After -->
<CopyableText v-if="line.file" :value="line.file" mode="code" class="grep-file" />
```

c) **file_read_tool 主体 / shell stdout / python / fallback 全部用 `default` 插槽嵌入**：

```vue
<!-- file_read_tool: Before -->
<div v-if="shikiReady && detectedLanguage !== 'text'" class="result-code result-code-shiki" v-html="highlightedCode" />
<pre v-else class="result-code">{{ readFileContent }}</pre>

<!-- After -->
<CopyableText
  :value="readFileContent"
  mode="block"
  :multiline="true"
  class="result-code-wrap"
>
  <div v-if="shikiReady && detectedLanguage !== 'text'" class="result-code result-code-shiki" v-html="highlightedCode" />
  <pre v-else class="result-code">{{ readFileContent }}</pre>
</CopyableText>
```

```vue
<!-- shell stdout / stderr / fallback: Before -->
<pre class="shell-value" v-text="shellStdout"></pre>
<pre v-if="shellStderr" class="shell-value shell-stderr-text" v-text="shellStderr"></pre>
<pre class="result-terminal" v-text="resultText"></pre>
<pre class="result-raw">{{ formattedResult }}</pre>

<!-- After (同模板结构，包裹在 CopyableText 里) -->
<CopyableText :value="shellStdout" mode="block" :multiline="true" class="result-code-wrap">
  <pre class="shell-value" v-text="shellStdout"></pre>
</CopyableText>
<CopyableText v-if="shellStderr" :value="shellStderr" mode="block" :multiline="true" class="result-code-wrap">
  <pre class="shell-value shell-stderr-text" v-text="shellStderr"></pre>
</CopyableText>
<CopyableText :value="resultText" mode="block" :multiline="true" class="result-code-wrap">
  <pre class="result-terminal" v-text="resultText"></pre>
</CopyableText>
<CopyableText :value="formattedResult" mode="block" :multiline="true" class="result-code-wrap">
  <pre class="result-raw">{{ formattedResult }}</pre>
</CopyableText>
```

```vue
<!-- result-suffix ([SYSTEM NOTICE] 后缀): Before -->
<div v-if="resultSuffix && ..." class="result-suffix">{{ resultSuffix }}</div>

<!-- After -->
<CopyableText
  v-if="resultSuffix && ..."
  :value="resultSuffix"
  mode="block"
  :multiline="true"
  class="result-suffix"
/>
```

> **Shiki 嵌套细节**：Shiki 渲染通过 `v-html` 输出到 `<div class="result-code-shiki">` 内，CopyableText 的 `default` slot 包了一层 `<div class="CopyableText-wrap result-code-wrap">` 作为 `position: relative` 容器。`v-html` 输出的元素**不**会触发 CopyableText 的 hover —— 这是正确的（hover 应该由外层 CopyableText 根容器接收）。Shiki 自身的 `<pre class="shiki">` 仍允许文本可选。

#### 4.3.8 `IPythonToolBlock.vue` — code/result 块

```vue
<!-- Before -->
<div v-if="shikiReady && code" class="code-highlighted code-result-shiki" v-html="highlightedCode" />
<pre v-else class="code-fallback">{{ code || 'No code available' }}</pre>
...
<pre class="result-content">{{ formattedResult }}</pre>
<div v-if="resultNotice" class="result-suffix">{{ resultNotice }}</div>

<!-- After -->
<CopyableText :value="code || ''" mode="block" :multiline="true" class="result-code-wrap">
  <div v-if="shikiReady && code" class="code-highlighted code-result-shiki" v-html="highlightedCode" />
  <pre v-else class="code-fallback">{{ code || 'No code available' }}</pre>
</CopyableText>
...
<CopyableText :value="formattedResult" mode="block" :multiline="true" class="result-code-wrap">
  <pre class="result-content">{{ formattedResult }}</pre>
</CopyableText>
<CopyableText v-if="resultNotice" :value="resultNotice" mode="block" :multiline="true" class="result-suffix" />
```

> `'No code available'` 这条 fallback 文案是给用户看的提示，不是数据；放在 `<pre>` 默认 slot 内合理。如果 `value` 为空字符串时 `CopyableText` 显示 placeholder 而不显示按钮，会出现 "No code available" 但无复制按钮的视觉不一致 —— **解决方案**：传 `:value="code || '\u200B'"`（零宽空格占位），保持 `value` 非空让按钮仍显示。实施时确定。

### 4.4 不变的组件（明确说明）

- `ToolCallItem.vue`：仅做容器插槽分发，本身无内容
- `SpcodeToolResultView.vue`：分发入口
- `FileDiffResult.vue`：状态行 + 复用 `DiffPreview`，无需复制
- `CodeIndexResult.vue`：统计数字，非文本
- `TodoListResult.vue` / `TodoListPanel.vue`：列表项不需要复制
- `FileRemoveResult.vue` 的 `error-row`：低频场景，避免 YAGNI

---

## 5. i18n 键

在 3 个 locale 的 `chat.json` 各加一个 `copy` 命名空间块：

| 调用 (`tm("...")`) | JSON key | zh-CN | en-US | ru-RU |
|---|---|---|---|---|
| `tm("copy.copy")` | `copy.copy` | 复制 | Copy | Копировать |
| `tm("copy.copied")` | `copy.copied` | 已复制 | Copied | Скопировано |

`useModuleI18n("features/chat")` 在 `composables.ts:131-134` 自动拼接前缀 `features.chat.`，因此 `tm("copy.copy")` 实际查找路径是 `features.chat.copy.copy`，对应 JSON 树：

```json
{
  "copy": {
    "copy": "复制",
    "copied": "已复制"
  }
}
```

文件路径：

- `dashboard/src/i18n/locales/zh-CN/features/chat.json`
- `dashboard/src/i18n/locales/en-US/features/chat.json`
- `dashboard/src/i18n/locales/ru-RU/features/chat.json`

---

## 6. 样式 / 主题 / 暗色支持

- 所有新样式使用现有 CSS 变量 `rgba(var(--v-theme-on-surface), 0.X)`，与项目其它卡片一致
- 复制按钮颜色：`color: rgba(var(--v-theme-on-surface), 0.45)` 默认，`0.85` hover/focus
- 暗色模式自动跟随 `--v-theme-on-surface` 变量，无需额外适配
- `cursor: text` 仅作用在文本区域（不作用在按钮）—— 视觉信号清晰

---

## 7. 测试与验证

### 7.1 手测矩阵

| # | 场景 | 期望结果 |
|---|------|---------|
| 1 | 鼠标 hover 长 args-value | 右侧出现复制图标 |
| 2 | 点击 args-value 的复制按钮 | 剪贴板内容为完整 `entry.raw`（非截断的 `entry.display`）；按钮变 ✓ 持续 1.2s；行不展开 |
| 3 | 在 args-value 文本上拖选 | 文本可选中（不触发 click） |
| 4 | 点击 args-row 空白处（不在按钮上） | 行展开（保留旧行为） |
| 5 | 短 args-value（无 `entry.long`） | 不显示复制按钮（视觉简洁） |
| 6 | 复制 file path（EsSearch） | 粘贴到编辑器得到正确路径 |
| 7 | 复制 issue-msg（CodeCheck） | 粘贴得到完整错误消息（含换行） |
| 8 | 复制 symbol-name（CodeExplore） | 粘贴得到完整符号名 |
| 9 | 复制 session_id（IntaShell） | 粘贴得到完整 session_id；显示仍为 8 字符截断 |
| 10 | 复制 shell stdout | 多行内容带换行 |
| 11 | 复制代码块内容（ToolResultView 的 Shiki 渲染） | 粘贴得到原始字符串（不带 HTML 标签） |
| 12 | 复制 file_read_tool 头部的 file path | 粘贴得到正确文件路径 |
| 13 | 复制 grep 命中的 `line.file` | 粘贴得到正确文件路径 |
| 14 | 复制 ipython 代码 | 粘贴得到完整 Python 代码 |
| 15 | 切换中/英/俄语言 | tooltip / aria-label 正确 |
| 16 | 暗色模式 | 按钮颜色/对比度正常 |
| 17 | 键盘 Tab 聚焦到复制按钮 | 边框/底色变明显（focus-visible 样式） |
| 18 | 键盘 Enter 触发复制 | 等同于鼠标点击 |

### 7.2 自动化验证

项目当前**没有**前端测试框架（`package.json` 无 vitest devDependency，无 `test` script）。本 spec 范围**不**新增测试基础设施。验证改用：

- `pnpm lint`（ESLint 全部通过）
- `pnpm typecheck`（vue-tsc 通过）
- `pnpm build`（生产构建通过，作为最终冒烟测试）
- `pnpm dev`（开发服务器无 console warning）

### 7.3 浏览器手测

按 7.1 矩阵，在 Chrome 最新版 + Edge 最新版各跑一遍；如时间允许，加 Firefox。

---

## 8. 风险与兼容性

| 风险 | 影响 | 缓解 |
|------|------|------|
| 行为变化：行内新增 hover 复制按钮 | 低 | 仅外观/交互细节变化；现有"点击行展开"行为不变 |
| 包大小 | +1 个 ~180 行 SFC，~3.5KB gzip | 接受 |
| i18n fallback 缺失 | 极低 | `useModuleI18n` 自动 fallback 已有键，不会崩 |
| 可访问性 | 低 | 按钮用 `<button type="button" aria-label>`，键盘 Tab + Enter 可触发；hover-only 不影响键盘用户 |
| `SessionIdCopy` 删除 | 极低 | 内联子组件被 `CopyableText` 替代，功能等价；通过 §7.1 #9 验证 |
| `position: absolute` 与 `overflow: hidden` 冲突 | 中 | §4.2 列出所有可能冲突的父选择器并逐一给出处理方式；唯一需改的是 `.args-table` 加 `overflow: visible` |
| Shiki 渲染的代码块复制 | 极低 | `value` 是原始字符串，不受 Shiki 渲染影响；测试 #11 已覆盖 |
| IPython `'No code available'` fallback 视觉不一致 | 低 | §4.3.8 已用 `\u200B` 占位方案处理 |
| IntaShell `parsed.output` 空时 `empty-note` 分支 | 极低 | §4.3.6 已说明该分支在 `v-if="hasOutput"` 之外，不受影响 |
| CodeCheckResultList 与 CodeCheckResult 重复改造遗漏 | 中 | §4.3.3 显式说明重复性风险；实施 DoD 要求两个文件都验证 |

---

## 9. 实施拆分（无重叠，可串行做；**步骤 2 后设检查点**）

1. **基础**
   - 新建 `CopyableText.vue`
   - i18n 3 个 locale 各加 `copy.copy` / `copy.copied` 键
   - `pnpm lint` + `pnpm typecheck` 通过
   - **检查点 1**：手动在 ChatMessageList 临时挂一个 `<CopyableText :value="'hello'" mode="block" />` 验证组件本身渲染 + 复制正常

2. **小范围验证**（先在 `IntaShellToolResultView.vue` 内用 `CopyableText` 替换 `SessionIdCopy`）
   - 删除内联 `SessionIdCopy` 子组件（约 50 行）
   - 加 meta-value / output-value / meta-value-dim / session-list-cmd / initial_output 复制
   - **检查点 2（rollback 决策点）**：跑 §7.1 #9 + #10 + #16。如果发现 `CopyableText` 与 IntaShell 集成有未预见的问题（高亮、滚动、布局），**回滚**本步骤并修复组件再重试

3. **横向接入**
   - `ToolCallCard.vue`（args-value）+ `.args-table` 加 `overflow: visible`
   - `EsSearchResult.vue`（item-name / item-path）
   - `CodeExploreResult.vue`（symbol-name / symbol-loc / caller-chip）
   - `CodeCheckResult.vue` **和** `CodeCheckResultList.vue`（issue-loc / issue-code / issue-msg）

4. **大块改造**
   - `ToolResultView.vue`（`CopyableText` block 模式 + `default` 插槽 + 新增 result-header-text / grep-file 复制）
   - `IPythonToolBlock.vue`（同上）

5. **收尾**
   - `pnpm lint` + `pnpm typecheck` + `pnpm build`
   - 按 §7.1 矩阵浏览器手测
   - `pnpm dev` 启动无 console warning

---

## 10. 验证完成判定（Definition of Done）

- [ ] 8 个文件按本设计完成改造（含 §4.3.1–§4.3.8 全部子节）
- [ ] §7.1 手测矩阵全部通过
- [ ] `pnpm lint` + `pnpm typecheck` + `pnpm build` 全部通过
- [ ] 暗色模式无视觉回归
- [ ] i18n 3 个 locale 都已加键
- [ ] 内联 `SessionIdCopy` 已删除
- [ ] `pnpm dev` 启动无 console warning
- [ ] `.args-table` 已加 `overflow: visible`
