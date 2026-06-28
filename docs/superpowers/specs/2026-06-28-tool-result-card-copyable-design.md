# 工具调用结果卡片：可复制文本 + 显式复制入口

| 项目 | 内容 |
|------|------|
| 主题 | 在工具调用结果展示的卡片式组件里，让文本可选可复制，并在 hover 时提供显式的复制按钮 |
| 日期 | 2026-06-28 |
| 作者 | elecvoid243 |
| 状态 | Draft — 待用户审阅 |
| 关联代码 | `dashboard/src/components/chat/message_list_comps/`（7 个文件） + i18n 3 个 locale |
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
- **ToolResultView.vue**：通用工具结果（文件内容、shell 输出、Python 输出）

行/卡片的整行 `cursor: pointer` + `@click` 触发展开。**但**：

1. **缺少显式复制入口**：除 `IntaShellToolResultView` 里的内联 `SessionIdCopy` 外，参数值、文件路径、错误消息、符号名、shell 输出等高频"复制目标"都没有 hover 出现的复制按钮。
2. **可点击整行的视觉信号让用户产生"不可选"的错觉**：虽然技术上 `user-select: text` 仍然生效，拖选能选中，但用户被 `cursor: pointer` 误导，倾向于去找专门的"复制"按钮。
3. **现有 `SessionIdCopy` 没被复用**：作为内联子组件被埋在 `IntaShellToolResultView.vue` 里，无法被其它组件使用。

### 1.2 目标

1. 在所有"卡片式工具结果"内提供**统一的 hover 复制按钮**，覆盖高频复制目标。
2. 显式声明文本可选（`user-select: text` + `cursor: text`），消除"不可选"的视觉误导。
3. 抽出可复用的 `CopyableText` 组件，**替代**现有 `SessionIdCopy`，作为单一来源。
4. 不破坏现有"点击整行展开"的交互（用户明确要求保留）。

### 1.3 非目标（显式不做）

- ❌ **不**改"点击整行展开"的交互模型
- ❌ **不**改任何工具结果的数据 schema（args、result 字符串不变）
- ❌ **不**改 LLM 后端契约
- ❌ **不**在 `FileRemoveResult` / `CodeIndexResult` / `TodoListResult` / `TodoListPanel` / `FileDiffResult` 内加复制入口（这些场景不构成高频复制需求，避免 YAGNI）
- ❌ **不**改 i18n 工具的使用方式
- ❌ **不**做双击复制、键盘快捷键复制等扩展形式（hover 按钮已足够，避免 YAGNI）

---

## 2. 设计决策（已与用户确认）

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 改造范围 | **A：全部统一改造**（7 个文件） | 用户体验最一致；改动虽然涉及多文件，但每处改造都是机械的"`<code>x</code>` → `<CopyableText :value="x" mode="code" />`" |
| 2 | 整行 click 行为 | **保留** | 用户明确要求；不影响复制按钮本身（按钮用 `@click.stop` 阻止冒泡） |
| 3 | 复制按钮展示方式 | **Hover 时浮现** | 符合现代 UI 习惯；静止状态简洁；不影响阅读 |
| 4 | 组件实现方式 | **A1：独立 `CopyableText.vue` 组件**（推荐） | 模板可读性最高（`<CopyableText :value="x" />`）；与现有 `SessionIdCopy` 设计哲学一致；未来扩展（tooltip / 双击复制）集中改一处。A2 composable + button 模板太啰嗦，A3 指令难定制 |
| 5 | `CopyableText` 的 mode | **3 种：inline / code / block** | inline 短文本行内、code 等宽短文本、block 多行内容（含 `<pre>` 风格）。覆盖所有场景 |
| 6 | i18n 键 | **新增 `chat.copy.copy` / `chat.copy.copied`**（3 个 locale） | tooltip/aria-label 必备；不引入新模块，挂在已有 `features/chat` 模块下 |
| 7 | 暗色模式 | **不需额外适配** | 全部使用 `--v-theme-on-surface` 变量，自动跟随 |
| 8 | `SessionIdCopy` 命运 | **删除，被 `CopyableText` 替代** | 单一来源；功能等价；约 50 行代码缩减 |
| 9 | `SessionIdCopy` 的 8 字符截断 | **保留截断**（最小破坏） | `CopyableText` 增加可选 `displayValue` prop（不传则 `value` 既作显示也作复制源；传则 `value` 仍为复制源，`displayValue` 为显示文本） |
| 10 | 大块 code/result 块（`ToolResultView`） | **复用 `CopyableText` block 模式 + `default` 插槽** | 让高亮后的 Shiki 渲染保留在内部；按钮浮在右上角；复制源是 `value` 字符串 |

---

## 3. 数据流与状态

### 3.1 新增的组件（无新数据流）

`CopyableText` 是纯展示组件，不引入新的 store / composable / 跨组件通信。复制操作走项目已有的 `@/utils/clipboard.ts` 的 `copyToClipboard` 函数。

### 3.2 `CopyableText.vue` 内部状态

```ts
const props = defineProps<{
  value: string                       // 必填：要复制的文本（始终是复制源）
  displayValue?: string               // 可选：显示文本，不传则用 value
  mode?: 'inline' | 'code' | 'block'  // 默认 'inline'
  placeholder?: string                // 空值时显示，默认 '—'
  multiline?: boolean                 // block 模式下保留换行，默认 false
  showIcon?: boolean                  // 是否显示复制按钮，默认 true
}>()

const copied = ref(false)             // 复制成功反馈，1.2s 后重置
```

### 3.3 改造前后对比（以 args 为例）

**Before**：
```vue
<span class="args-value">{{ entry.display }}</span>
```
文本通过 Vue 模板插值直接渲染；`user-select` 走浏览器默认（即 text 可选）；但 `cursor: pointer` 来自父 `.args-row.clickable`，让人误以为不可选。

**After**：
```vue
<CopyableText
  :value="entry.raw"
  mode="code"
  class="args-value"
  :show-icon="entry.long"
/>
```
- `entry.raw` 始终是完整文本（复制源）
- 按钮仅在 `entry.long` 时显示（避免短文本视觉噪声）
- `args-value` CSS 类只保留布局（`min-width: 0` 等），文本样式由 `CopyableText` 内部 `code` mode 提供

---

## 4. 架构与组件

### 4.1 目录结构

```
dashboard/src/components/chat/message_list_comps/
├── __shared__/                          ← 新建目录，集中放共享小组件
│   └── CopyableText.vue                 ← 新组件（~150 行）
├── ToolCallCard.vue                     ← 改造
├── ToolResultView.vue                   ← 改造
├── IntaShellToolResultView.vue          ← 改造（删除内联 SessionIdCopy）
├── IPythonToolBlock.vue                 ← 改造
├── ToolCallItem.vue                     (不变)
├── SpcodeToolResultView.vue             (不变，分发入口)
└── spcode_tools/
    ├── CodeCheckResult.vue              ← 改造
    ├── CodeCheckResultList.vue          ← 改造
    ├── CodeExploreResult.vue            ← 改造
    ├── EsSearchResult.vue               ← 改造
    ├── FileRemoveResult.vue             (不变，低频)
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

- **`inline`**：行内文本，hover 时右侧浮现小图标（`<v-icon size="12" class="mdi-content-copy">`）。不打断文本流。
- **`code`**：等宽字体（继承 monospace），hover 时图标浮在右上角（`position: absolute`）。
- **`block`**：块级，`<pre>` 风格保留换行；复制按钮固定在右上角，hover 时浮现（GitHub code block 风格）。

#### 行为细节

- 容器默认 `user-select: text` + `cursor: text`，确保文本可选
- 复制按钮使用 `position: absolute`（block/code 模式）或 `flex` 排列（inline 模式）
- 默认 `opacity: 0`；`:hover` 时 `opacity: 1`，过渡 `0.15s`
- 点击按钮调用 `copyToClipboard(value)`，成功后按钮变 `mdi-check` 并保持 1.2s
- 按钮用 `@click.stop` 阻止冒泡到外层可点击的 row，避免误触发展开
- `<button type="button" :aria-label="tm('chat.copy.copy')">` —— 键盘 Tab 可聚焦，Enter 触发
- 复制成功时按钮的 `aria-label` 切换为 `tm('chat.copy.copied')`

#### 错误处理

- `copyToClipboard` 返回 `false` 时，1.2s 后回退到 copy 状态（视觉无变化，避免误以为成功）
- `value` 为空字符串时，渲染 placeholder，不显示复制按钮（`show-icon` 强制为 `false`）

### 4.3 各文件改造点

#### 4.3.1 `ToolCallCard.vue` — args value 列

```vue
<!-- Before -->
<span class="args-value">{{ entry.display }}</span>

<!-- After -->
<CopyableText
  :value="entry.raw"
  mode="code"
  class="args-value"
  :show-icon="entry.long"
/>
```

样式：`.args-value` 类只保留 `min-width: 0`、`flex` 等布局属性；等宽字体/颜色由 `CopyableText` 内部 `code` mode 提供。

`.args-row` 的 `@click="entry.long && toggleArgExpand(i)"` 保留。复制按钮 `@click.stop` 阻止冒泡。

#### 4.3.2 `CodeCheckResult.vue` & `CodeCheckResultList.vue` — issue 三件套

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

#### 4.3.3 `CodeExploreResult.vue` — symbol & callers

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

#### 4.3.4 `EsSearchResult.vue` — file 路径

```vue
<!-- Before -->
<span class="item-name">{{ item.name }}</span>
<span class="item-path">{{ item.path }}</span>

<!-- After -->
<CopyableText :value="item.name" mode="inline" class="item-name" />
<CopyableText :value="item.path" mode="code" class="item-path" />
```

#### 4.3.5 `IntaShellToolResultView.vue`

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

b) **为 meta-value / output-value 添加复制**：

```vue
<!-- Before -->
<code class="meta-value">{{ parsed.session.command }}</code>
<pre v-if="hasOutput" class="output-value">{{ parsed.output }}</pre>

<!-- After -->
<CopyableText
  :value="parsed.session.command"
  mode="code"
  class="meta-value"
/>
<CopyableText
  v-if="hasOutput"
  :value="parsed.output"
  mode="block"
  :multiline="true"
  class="output-value"
/>
```

#### 4.3.6 `ToolResultView.vue` — code/result 块右上角"复制全部"

用 `CopyableText` 的 `default` 插槽语法：插槽渲染 Shiki 高亮/`<pre>` fallback，复制源仍是 `value` 字符串。

```vue
<!-- Before -->
<pre class="result-code">{{ readFileContent }}</pre>

<!-- After -->
<CopyableText
  :value="readFileContent"
  mode="block"
  :multiline="true"
  class="result-code-wrap"
>
  <div v-if="shikiReady && detectedLanguage !== 'text'" class="result-code-shiki" v-html="highlightedCode" />
  <pre v-else class="result-code">{{ readFileContent }}</pre>
</CopyableText>
```

同样改造 `.shell-value`、`.result-terminal`、`.result-raw`、`.result-suffix`、`IPythonToolBlock` 的 `.code-fallback` / `.result-content`。

### 4.4 不变的组件（明确说明）

- `ToolCallItem.vue`：仅做容器插槽分发，本身无内容
- `SpcodeToolResultView.vue`：分发入口
- `FileDiffResult.vue`：状态行 + 复用 `DiffPreview`，无需复制
- `CodeIndexResult.vue`：统计数字，非文本
- `TodoListResult.vue` / `TodoListPanel.vue`：列表项不需要复制
- `FileRemoveResult.vue` 的 `error-row`：低频场景，避免 YAGNI

---

## 5. i18n 键

在 3 个 locale 各加 2 个键：

| key | zh-CN | en-US | ru-RU |
|---|---|---|---|
| `chat.copy.copy` | 复制 | Copy | Копировать |
| `chat.copy.copied` | 已复制 | Copied | Скопировано |

文件路径：

- `dashboard/src/i18n/locales/zh-CN/features/chat.json`
- `dashboard/src/i18n/locales/en-US/features/chat.json`
- `dashboard/src/i18n/locales/ru-RU/features/chat.json`

---

## 6. 样式 / 主题 / 暗色支持

- 所有新样式使用现有 CSS 变量 `rgba(var(--v-theme-on-surface), 0.X)`，与项目其它卡片一致
- 复制按钮颜色：`color: rgba(var(--v-theme-on-surface), 0.45)` 默认，`0.85` hover，与现有 `.session-id-copy` 同色阶
- 暗色模式自动跟随 `--v-theme-on-surface` 变量，无需额外适配
- `cursor: text` 仅作用在文本区域（不作用在按钮）—— 视觉信号清晰

---

## 7. 测试与验证

### 7.1 手测矩阵

| # | 场景 | 期望结果 |
|---|------|---------|
| 1 | 鼠标 hover args-row 右侧 | 出现复制图标（仅当 `entry.long`） |
| 2 | 点击 args-value 的复制按钮 | 剪贴板内容正确；按钮变 ✓ 持续 1.2s；行不展开 |
| 3 | 在 args-value 文本上拖选 | 文本可选中（不触发 click） |
| 4 | 点击 args-row（不在按钮上） | 行展开（保留旧行为） |
| 5 | 复制 file path（EsSearch） | 粘贴到编辑器得到正确路径 |
| 6 | 复制 issue-msg（CodeCheck） | 粘贴得到完整错误消息（含换行） |
| 7 | 复制 symbol-name（CodeExplore） | 粘贴得到完整符号名 |
| 8 | 复制 session_id（IntaShell） | 粘贴得到完整 session_id（与现有 `SessionIdCopy` 行为一致） |
| 9 | 复制 shell stdout | 多行内容带换行 |
| 10 | 复制代码块内容（ToolResultView 的 Shiki 渲染） | 粘贴得到原始字符串（不带 HTML 标签） |
| 11 | 切换中/英/俄语言 | tooltip 正确 |
| 12 | 暗色模式 | 按钮颜色/对比度正常 |

### 7.2 自动化测试

新增一个轻量单元测试 `dashboard/src/components/chat/message_list_comps/__shared__/CopyableText.spec.ts`：

- 渲染正确（props → DOM）
- 点击调用 `copyToClipboard` 并切换 `copied` 状态
- `@click.stop` 防止冒泡（mock 外层 click handler，验证未被触发）
- 空值时显示 placeholder，不显示按钮

### 7.3 CI 验证

- `pnpm lint` 通过
- `pnpm typecheck` 通过
- `pnpm test` 通过（包含新增单元测试）
- `ruff format .` + `ruff check .` 通过（注：ruff 仅作用于 Python；前端 lint 用 pnpm scripts）

---

## 8. 风险与兼容性

| 风险 | 影响 | 缓解 |
|------|------|------|
| 行为变化：行内新增 hover 复制按钮 | 低 | 仅外观/交互细节变化；现有"点击行展开"行为不变 |
| 包大小 | +1 个 ~150 行 SFC，~3KB gzip | 接受 |
| i18n fallback 缺失 | 极低 | `useModuleI18n` 自动 fallback 已有键，不会崩 |
| 可访问性 | 低 | 按钮用 `<button type="button" aria-label>`，键盘 Tab + Enter 可触发；hover-only 不影响键盘用户 |
| `SessionIdCopy` 删除 | 极低 | 内联子组件被 `CopyableText` 替代，功能等价；通过单元测试 + 手测验证 |
| 复制按钮的 `position: absolute` 与父容器 `overflow: hidden` 冲突 | 中 | `CopyableText` 内部统一处理：`position: relative` 包裹 + `overflow: visible` 默认；父容器需 `overflow: visible` 才能让按钮溢出显示。改造前需要逐一检查父容器 CSS，对 `overflow: hidden` 的容器在 `CopyableText` 周围包一层 `overflow: visible` 包裹，或调整父容器的 `overflow` |
| Shiki 渲染的代码块复制 | 极低 | `value` 是原始字符串，不受 Shiki 渲染影响；测试 10 已覆盖 |

---

## 9. 实施拆分（无重叠，可串行做）

1. **基础**
   - 新建 `CopyableText.vue`
   - 新建 `CopyableText.spec.ts`
   - i18n 3 个 locale 各加 2 个键
   - 跑测试 + lint 验证

2. **小范围验证**（先在 `IntaShellToolResultView.vue` 内用 `CopyableText` 替换 `SessionIdCopy`）
   - 删除内联 `SessionIdCopy` 子组件
   - 加 meta-value / output-value 复制
   - 手测验证

3. **横向接入**
   - `ToolCallCard.vue`（args-value）
   - `EsSearchResult.vue`（item-name / item-path）
   - `CodeExploreResult.vue`（symbol-name / symbol-loc / caller-chip）
   - `CodeCheckResult.vue` / `CodeCheckResultList.vue`（issue-loc / issue-code / issue-msg）

4. **大块改造**
   - `ToolResultView.vue`（`CopyableText` block 模式 + `default` 插槽）
   - `IPythonToolBlock.vue`（同上）

5. **收尾**
   - `pnpm lint` + `pnpm typecheck` + `pnpm test`
   - 手动浏览器验证 7.1 矩阵
   - 跑 `pnpm dev` 确认无控制台 warning

---

## 10. 验证完成判定（Definition of Done）

- [ ] 7 个文件按本设计完成改造
- [ ] 7.1 手测矩阵全部通过
- [ ] 7.2 单元测试全部通过
- [ ] 7.3 CI 全部通过
- [ ] 暗色模式无视觉回归
- [ ] i18n 3 个 locale 都已加键
- [ ] 内联 `SessionIdCopy` 已删除
- [ ] 现有 `pnpm dev` 启动无控制台 warning
