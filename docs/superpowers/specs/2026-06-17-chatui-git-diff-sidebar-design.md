# Dashboard ChatUI「Git Diff Sidebar」— 设计文档

| 项目 | 内容 |
|------|------|
| 主题 | Dashboard ChatUI 联动 spcode 插件的 Git Diff 侧边栏 |
| 日期 | 2026-06-17 |
| 作者 | elecvoid243 |
| 状态 | Draft — 待用户审阅 |
| 关联插件 | `astrbot_plugin_spcode_toolkit`（路径：`F:\github\astrbot_plugin_spcode_toolkit`） |
| 关联代码 | `dashboard/src/components/chat/*`、`dashboard/src/composables/useSpcode*` |
| 前置 spec | `docs/superpowers/specs/2026-06-16-chatui-project-load-button-design.md`（chip 可见性门控 / 项目状态 composable 的同源设计） |

---

## 1. 背景与目标

### 1.1 现状

前一份 spec（`2026-06-16`）已交付 ChatInput 左下角的「加载项目」chip：

- **spcode 插件启用 + `/project*` 指令已注册** → 显示 chip
- chip 点击 → 弹出 `ProjectLoadDialog`，用户输入绝对路径 → 等价于手动键入 `/project load <path>`
- 项目载入成功后，`useSpcodeProjectStatus().status.loaded === true`
- spcode 插件（后端）已实现 `GET /plugins/extensions/spcode/git-diff` 端点（响应见 §2.2）

但用户在项目载入后**无法在 UI 里直观看到 bot 改了什么**：必须切到外部 git 工具或者翻 bot 的流式消息文本拼 diff。

### 1.2 痛点

1. 用户无法在 WebChat 里直接 review 当前项目里 bot 的改动
2. 即便 bot 报告了"已修改文件 X/Y/Z"，没有 diff 上下文，用户难以判断是否需要进一步指令
3. 现有的 `ReasoningSidebar` 只能展示 bot 的推理过程，与项目文件状态无关

### 1.3 目标

在 ChatUI 中**新增一个轻量入口 + 侧边栏**，让用户能：

1. 在「加载项目」chip 同一行右侧看到一个 outlined `Git Diff` chip，**仅当 chip 自身可见且项目已载入时显示**
2. 点击 chip → 右侧弹出可拖拽侧边栏，列出所有改动的文件（path + status + +/-）
3. 点击某个文件 → 展开显示该文件的 unified diff（复用 `DiffPreview.vue`）
4. sidebar 打开期间每 10s 静默刷新一次（不打断 UI）
5. 项目卸载时 sidebar 自动关闭
6. 与现有 `ReasoningSidebar` / `RefsSidebar` / `TodoSidebar` 互斥（沿用现有 `openXxxPanel` 模式）

### 1.4 非目标

- ❌ **不**修改 spcode 插件代码（git-diff 端点已就绪）
- ❌ **不**修改 AstrBot 核心（后端、协议、消息总线）
- ❌ **不**在客户端做 git 解析（diff 字符串来自后端，前端只切片）
- ❌ **不**实现多项目同时 diff（umo 单值）
- ❌ **不**实现文件级过滤、搜索、commit history
- ❌ **不**实现 staged vs unstaged 切换（看 §6.5 未来扩展）
- ❌ **不**在 sidebar 里直接 commit / revert
- ❌ **不**做 i18n 之外的国际化（如 RTL、自适应字号）

---

## 2. 设计决策（已与用户确认）

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | spcode git-diff 端点响应形状 | **A+B 混合**（`files_changed` 列表 + 完整 `diff` 字符串） | 后端已实现；前端用 `files_changed` 渲染列表，用正则按 `diff --git` 切片喂 `DiffPreview` |
| 2 | 与 `ReasoningSidebar` 等其它侧边的关系 | **A 互斥**（沿用现有 `openXxxPanel` 模式） | 与 Chat.vue 现状完全一致；用户场景上同时看 reasoning + diff 不常见 |
| 3 | diff 刷新策略 | **B**：打开时拉取 + 打开期间每 10s 静默轮询 + header 手动 refresh 按钮 | 端点 ~47ms；自动跟着 bot/编辑器变；轮询期间静默替换不闪烁 |
| 4 | 加载中 / 空态 / 截断 / 失败 / 网络错误 / 轮询过渡 | 按推荐方案（见 §5.1 表） | 用户对所有六类状态逐一确认 |
| 5 | 按钮视觉风格 | **B**：outlined v-chip + 文字 "Git Diff" + icon `mdi-source-pull` | 与现有「加载项目」chip 视觉对仗；扫一眼即知是同类操作；放 status row 右侧通过 `justify-content: space-between` 自然分隔 |
| 6 | 单文件 diff 切片策略 | **预切 + 整段切片 + 二进制单独占位** | 收到 response 立即按 `^diff --git /m` 切；每段原样传给 `DiffPreview.extractDiffContent`（其内部跳到 `@@`）；二进制文件（切片含 "Binary files ... differ"）渲染 `v-alert` 占位 |
| 7 | i18n 键命名 | `spcodeProjectLoad.diffSidebar.*`（中/英/俄三语） | 挂在现有 `spcodeProjectLoad` 根下，与 `dialog.*` / `indicator.*` 同级；英俄翻译由实现者填写 |

---

## 3. 架构与文件改动

### 3.1 架构原则

- **零后端改动**：完全复用 spcode 现有 `git-diff` 端点
- **零 spcode 改动**：通过标准 HTTP endpoint 调用
- **零 `DiffPreview.vue` 改动**：作为子组件复用，原样式零侵入
- **零 `useSpcodeProjectStatus.ts` 改动**：composable 是单例，由 sidebar 内部读 `status.value.loaded` 做自动关闭
- **Inline-first**：helpers 写在 composable / 组件文件顶部，不强行抽公共文件
- **AGENTS.md 遵守**：Google-style docstring、`pathlib` 习惯、ruff format + check、英文注释

### 3.2 文件改动清单

| 层级 | 文件 | 性质 | 说明 |
|------|------|------|------|
| 新增 | `dashboard/src/composables/parseSpcodeGitDiff.ts` | 纯函数模块 | 把 raw response 解析成 `SpcodeGitDiffSnapshot`（见 §4.2） |
| 新增 | `dashboard/src/composables/useSpcodeGitDiff.ts` | composable | fetch + 状态机 + 10s 轮询 + AbortController + dispose |
| 新增 | `dashboard/src/components/chat/GitDiffChip.vue` | 新组件 | outlined v-chip，emit `open-diff-sidebar` |
| 新增 | `dashboard/src/components/chat/GitDiffSidebar.vue` | 新组件 | 拖拽外壳（镜像 ReasoningSidebar 结构） |
| 新增 | `dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue` | 新组件 | 状态机渲染（loading / error / 空态 / 文件列表 / error banner） |
| 新增 | `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue` | 新组件 | 单文件行 + 展开 DiffPreview 或二进制占位 |
| 改动 | `dashboard/src/components/chat/ChatInput.vue` | 修改 | status row 加 `space-between` + 新 chip + 转发 `open-diff-sidebar` 事件 |
| 改动 | `dashboard/src/components/chat/Chat.vue` | 修改 | 引入 `GitDiffSidebar` + `openGitDiffSidebar()` + 互斥逻辑 + currSessionId watcher |
| 改动 | `dashboard/src/i18n/locales/zh-CN/features/chat.json` | 修改 | 新增 12 个键 |
| 改动 | `dashboard/src/i18n/locales/en-US/features/chat.json` | 修改 | 新增 12 个键 |
| 改动 | `dashboard/src/i18n/locales/ru-RU/features/chat.json` | 修改 | 新增 12 个键 |
| 新增 | `dashboard/src/composables/parseSpcodeGitDiff.test.ts` | 测试 | 纯函数单测（vitest） |
| 新增 | `dashboard/src/composables/useSpcodeGitDiff.test.ts` | 测试 | composable 单测（fake timers） |
| 新增 | `dashboard/src/components/chat/GitDiffChip.test.ts` | 测试 | 组件单测 |
| 新增 | `dashboard/src/components/chat/GitDiffSidebar.test.ts` | 测试 | 组件单测 |
| 新增 | `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.test.ts` | 测试 | 组件单测 |

### 3.3 改动量估算

- 新增代码：~600-700 行（含组件 + composable + 测试）
- 改动现有代码：~30-40 行（ChatInput + Chat.vue + 3 个 i18n 文件）
- 风险面：3 个新组件 + 1 个 composable；与现有 sidebar 同构，零破坏性

### 3.4 模块依赖图

```
Chat.vue
  ├─ ChatInput.vue
  │    ├─ SpcodeProjectIndicator.vue
  │    ├─ GitDiffChip.vue               [NEW]
  │    └─ useSpcodeProjectStatus.ts     (existing)
  │         ↑
  ├─ GitDiffSidebar.vue                [NEW]
  │    ├─ useSpcodeGitDiff.ts           [NEW]
  │    │    └─ parseSpcodeGitDiff.ts    [NEW]
  │    ├─ useSpcodeProjectStatus.ts     (existing, for auto-close)
  │    └─ GitDiffBodyContent.vue        [NEW]
  │         └─ GitDiffFileItem.vue      [NEW]
  │              └─ DiffPreview.vue     (existing, read-only)
  └─ ReasoningSidebar / RefsSidebar / TodoSidebar (existing, mutual exclusion)
```

---

## 4. 组件结构

### 4.1 Composables

#### 4.1.1 `parseSpcodeGitDiff.ts` — 纯函数解析器

```typescript
// 入参：spcode git-diff 端点的 data 字段
export interface SpcodeGitDiffRawResponse {
  loaded: boolean
  directory: string | null
  umo: string | null
  diff: string | null
  stat: string | null
  files_changed: Array<{
    path: string
    status: string  // 'M' | 'A' | 'D' | 'R' | 'C' | '?' | 其它
    additions: number
    deletions: number
  }>
  truncated: boolean
  truncated_at_bytes: number
  max_bytes: number
  elapsed_ms: number
  reason: string | null
}

// 出参：UI 直接消费
export type FileStatus = 'M' | 'A' | 'D' | 'R' | 'C' | '?' | 'unknown'

export interface SpcodeGitDiffFile {
  path: string
  status: FileStatus
  additions: number
  deletions: number
  slice: string | null          // 含 diff --git / index / --- a/ / +++ b/ / @@ hunks；二进制或缺段时为 null
  isBinary: boolean             // 切片含 "Binary files ... differ"
}

export interface SpcodeGitDiffMeta {
  directory: string | null
  umo: string | null
  loaded: boolean
  truncated: boolean
  truncatedAtBytes: number
  maxBytes: number
  reason: string | null
  elapsedMs: number
  fetchedAt: number             // Date.now()
}

export interface SpcodeGitDiffSnapshot {
  meta: SpcodeGitDiffMeta
  files: SpcodeGitDiffFile[]
  rawDiff: string | null
}

export function parseSpcodeGitDiff(data: SpcodeGitDiffRawResponse): SpcodeGitDiffSnapshot
```

**切片算法**（在 parseSpcodeGitDiff 内部实现）：
1. `data.diff` 非 null → 按 `^diff --git ` 多行模式 `split`（保留分隔符），得到 N 段
2. 每段解析 `path`：正则 `/^diff --git a\/(\S+) b\/(\S+)/m` 提取 `b/` 后路径（rename 时是 b/ 的目标）
3. 检测 `Binary files` 关键字 → `isBinary=true, slice=null`
4. 若 `files_changed` 里**没有**匹配 path（truncated 边界）→ `slice=null, isBinary=false`
5. 否则 → `slice = 该段原文（含 diff --git / index / --- a/ / +++ b/ / hunks）`

#### 4.1.2 `useSpcodeGitDiff.ts` — 数据获取 + 状态机

```typescript
export type GitDiffFetchState =
  | { kind: 'idle' }
  | { kind: 'loading' }                                              // 首次打开、尚未成功过
  | { kind: 'ok'; snapshot: SpcodeGitDiffSnapshot }
  | { kind: 'error'; reason: string; previousSnapshot?: SpcodeGitDiffSnapshot }

export interface UseSpcodeGitDiffReturn {
  state: Ref<GitDiffFetchState>
  refresh: () => Promise<void>                                      // 手动/轮询触发
  startPolling: (intervalMs?: number) => void                       // 默认 10000
  stopPolling: () => void
  dispose: () => void                                              // stopPolling + abort
}
```

**关键实现细节**：

- **每次 refresh 创建新 AbortController**，旧的 abort；manual 与轮询共用通道
- **轮询静默替换**：tick 内不显示 loading state；保留上次 snapshot
- **错误保留上次数据**：`error.kind` 携带 `previousSnapshot`，UI 渲染底部 banner
- **请求失败但有 previousSnapshot → error + 保留列表**
- **请求失败且无 previousSnapshot → error + 居中错误块**
- **`umo` 缺失时**不发请求，直接 error reason=`'not_loaded'`
- **`startPolling` 幂等**：多次调用只保留一个 timer；用 `isRunning: boolean` 闭包变量
- **`dispose()` 在 `onBeforeUnmount` 调**：stopPolling + abort in-flight + 清 timer

### 4.2 组件

#### 4.2.1 `<GitDiffChip/>`

```vue
<template>
  <v-tooltip location="bottom" :open-delay="200">
    <template #activator="{ props: tipProps }">
      <v-chip
        v-bind="tipProps"
        variant="outlined"
        size="small"
        density="comfortable"
        prepend-icon="mdi-source-pull"
        class="git-diff-chip"
        @click="open"
      >
        {{ tm('spcodeProjectLoad.diffSidebar.chip') }}
      </v-chip>
    </template>
    <span>{{ tm('spcodeProjectLoad.diffSidebar.chipTooltip') }}</span>
  </v-tooltip>
</template>

<script setup lang="ts">
import { useModuleI18n } from '@/i18n/composables'
const { tm } = useModuleI18n('features/chat')
const emit = defineEmits<{ (e: 'open-diff-sidebar'): void }>()
function open() { emit('open-diff-sidebar') }
</script>
```

**可见性**：写在 `ChatInput.vue` 的 status row 内：

```vue
<div class="input-area__status-row">
  <SpcodeProjectIndicator v-if="showSpcodeIndicator" @open-load-dialog="openLoadDialog" />
  <GitDiffChip
    v-if="showSpcodeIndicator && spcodeStatus.status.value.loaded"
    @open-diff-sidebar="$emit('open-diff-sidebar')"
  />
</div>
```

`.input-area__status-row` 加 `justify-content: space-between`，让现有 chip 靠左、Git Diff chip 靠右自然分开（chip 不可见时不影响布局）。

#### 4.2.2 `<GitDiffSidebar/>` — 外壳

镜像 `ReasoningSidebar.vue` 的拖拽 + slide-left 模式：

- `MIN_WIDTH=320`, `MAX_WIDTH=1200`, `DEFAULT_WIDTH=420`（比 reasoning 的 380 略宽，因为要装文件路径）
- header：title + 目录路径 tooltip + 手动 refresh 按钮 + 关闭按钮
- 顶部 warning 条（truncated 时）
- body：委托给 `<GitDiffBodyContent/>`

```typescript
// GitDiffSidebar.vue
import { useSpcodeGitDiff, type UseSpcodeGitDiffReturn } from '@/composables/useSpcodeGitDiff'
import { useSpcodeProjectStatus } from '@/composables/useSpcodeProjectStatus'

const props = defineProps<{
  modelValue: boolean
  isDark?: boolean
}>()
const emit = defineEmits<{
  'update:modelValue': [v: boolean]
}>()

const { tm } = useModuleI18n('features/chat')
const composable = useSpcodeGitDiff()
const spcodeStatus = useSpcodeProjectStatus()

// 自动关闭（项目卸载）
watch(() => spcodeStatus.status.value.loaded, (loaded) => {
  if (!loaded) emit('update:modelValue', false)
})

// 打开时立即拉取 + 启动轮询；关闭/卸载时清理
watch(() => props.modelValue, async (open) => {
  if (open) {
    await composable.refresh()
    composable.startPolling(10_000)
  } else {
    composable.stopPolling()
  }
}, { immediate: true })

onBeforeUnmount(() => composable.dispose())
```

#### 4.2.3 `<GitDiffBodyContent/>` — 状态机渲染

```typescript
// props
state: GitDiffFetchState
expanded: Set<string>              // 已展开文件 path 集合
isDark: boolean

// emits
toggle: [path: string]
retry: []                          // 触发父组件 refresh
```

渲染分支（按优先级）：

1. `state.kind === 'loading'` → 居中 spinner + "加载中…"
2. `state.kind === 'error' && !previousSnapshot` → 居中错误块（icon + title + detail + retry 按钮）
3. `state.kind === 'ok' && files.length === 0` → 居中空态（icon + "暂无文件改动"）
4. `state.kind === 'ok' && files.length > 0` → 渲染 `GitDiffFileItem` 列表
5. `state.kind === 'error' && previousSnapshot` → 渲染列表 + 底部 error banner（banner 含 retry）

#### 4.2.4 `<GitDiffFileItem/>` — 单文件行 + 展开

```typescript
// props
file: SpcodeGitDiffFile
expanded: boolean
isDark: boolean

// emits
toggle: []
```

渲染：

- **始终显示行**：status icon（按 §4.3 映射）+ path + (+N −N) + chevron
- **expanded 时显示 body**：
  - `file.isBinary === true` → `v-alert` "二进制文件改动（无文本预览）"
  - `file.slice` 非 null → `<DiffPreview :content="file.slice" :file-path="file.path" collapsible :is-dark="isDark" />`
  - `file.slice === null && !file.isBinary` → "无内容"占位（truncated 边界或解析异常）

#### 4.2.5 status → 图标/颜色映射

| status | mdi icon | color |
|---|---|---|
| `M` | `mdi-pencil` | primary |
| `A` | `mdi-plus-circle` | success |
| `D` | `mdi-minus-circle` | error |
| `R` | `mdi-rename-box` | warning |
| `C` | `mdi-content-copy` | info |
| `?` | `mdi-help-circle` | grey |
| 其它 | `mdi-file-document-edit-outline` | grey |

---

## 5. 错误处理 & 互斥逻辑

### 5.1 错误分类与文案

| 来源 | 检测 | UI | 用户动作 |
|---|---|---|---|
| HTTP 4xx/5xx | axios reject 或 `status:"error"` | 居中错误块 + 重试 | 点重试 |
| HTTP 网络错误 | axios reject | 同上，文案"网络连接失败" | 点重试 |
| `data.loaded=false` | snapshot.meta.loaded=false | reason → i18n 映射（见下表） | 卸载/重载/切目录 |
| `reason: "not_a_git_repo"` | 同上 | 当前目录不是 Git 仓库 | git init 或换路径 |
| `reason: "not_loaded"` | 同上（防御性） | 项目未载入 | 重新载入项目 |
| 未知 reason | 不在映射表 | 获取改动失败（{reason}） | 点重试或回报 |
| 轮询中途错误 | tick 内 fetch reject | 保留上次 snapshot，底部 banner | 点 banner 重试 |
| truncated | `meta.truncated === true` | sidebar 顶部黄色 warning 横条 | （无） |
| `slice=null, isBinary=false` | path 在 files_changed 但 diff 里找不到 | 文件行下"内容已截断或不完整" | （无） |
| 二进制文件 | slice 含 `Binary files ... differ` | v-alert 二进制占位 | （无） |

**reason → i18n 键映射**：

```typescript
const REASON_I18N_KEYS: Record<string, string> = {
  not_a_git_repo: 'spcodeProjectLoad.diffSidebar.error.reason.not_a_git_repo',
  not_loaded: 'spcodeProjectLoad.diffSidebar.error.reason.not_loaded',
}

function localizedReason(reason: string | null, tm: Function): string {
  if (!reason) return tm('spcodeProjectLoad.diffSidebar.error.reason.generic', { reason: 'unknown' })
  const key = REASON_I18N_KEYS[reason]
  return key ? tm(key) : tm('spcodeProjectLoad.diffSidebar.error.reason.generic', { reason })
}
```

### 5.2 与其它 sidebar 的互斥（Chat.vue）

```typescript
function openGitDiffSidebar() {
  threadPanelOpen.value = false
  activeThread.value = null
  reasoningPanelOpen.value = false
  activeReasoningTarget.value = null
  refsSidebarOpen.value = false
  selectedRefs.value = null
  todoSidebarOpen.value = false
  gitDiffSidebarOpen.value = true
}

// currSessionId 切换时统一关闭
watch(currSessionId, () => {
  // ... 现有逻辑
  gitDiffSidebarOpen.value = false
})
```

### 5.3 项目卸载自动关闭（GitDiffSidebar 内部）

```typescript
watch(() => spcodeStatus.status.value.loaded, (loaded) => {
  if (!loaded) emit('update:modelValue', false)
})
```

链路：用户 `/project unload` → spcode plugin 更新 → `useSpcodeProjectStatus.refresh()`（由 Chat.vue 的 `currSessionId` watcher 或 ChatInput 的 `showSpcodeIndicator` watcher 触发）→ `status.loaded` 翻 false → 上面 watcher 触发 → sidebar 关闭 → onBeforeUnmount → dispose。

### 5.4 轮询期间的"静默替换"

```typescript
async function tick(): Promise<void> {
  if (!isMounted) return
  // 不显示 loading：保留旧 state
  try {
    const res = await fetch()
    if (!isMounted) return
    state.value = { kind: 'ok', snapshot: parse(res.data.data) }
  } catch (err) {
    if (!isMounted) return
    const prev = state.value.kind === 'ok' ? state.value.snapshot : undefined
    state.value = { kind: 'error', reason: classify(err), previousSnapshot: prev }
  }
}
```

`isMounted` 闭包变量在 `dispose()` 时翻 false；fetch 期间组件已卸载也丢弃结果。

### 5.5 移动端（<760px）

完全沿用 `ReasoningSidebar` 的 mobile 模式：

- aside 变成全屏 overlay (`position: fixed; inset: 0`)
- resizer 隐藏
- header 高度自适应 safe-area-inset
- 文件列表不受影响；二进制占位照常显示

---

## 6. 数据流（端到端时序）

```
[用户]                          [ChatInput]              [Chat.vue]              [GitDiffSidebar]          [useSpcodeGitDiff]              [spcode plugin]
  │                                  │                       │                          │                          │                              │
  │ 1. /project load /tmp/repo       │                       │                          │                          │                              │
  ├──────────────────────────────────>│                       │                          │                          │                              │
  │                                  │ applyOptimistic        │                          │                          │                              │
  │                                  │  ProjectStatus         │                          │                          │                              │
  │                                  │                       │                          │                          │                              │
  │                                  │ send ─────────────────>│                          │                          │                              │
  │                                  │                       │ sendCurrentMessage        │                          │                              │
  │                                  │                       │                          │                          │  POST /api/chat              │
  │                                  │                       │                          │                          ├─────────────────────────────>│
  │                                  │                       │                          │                          │  SSE stream                  │
  │                                  │                       │                          │                          │<─────────────────────────────┤
  │                                  │                       │ onStreamEnd ──────────────│                          │                              │
  │                                  │                       │ spcodeStatus.refresh()    │                          │  GET spcode/git-diff         │
  │                                  │                       ├─────────────────────────>│                          ├─────────────────────────────>│
  │                                  │                       │                          │  parse → snapshot         │                              │
  │                                  │                       │                          │<─────────────────────────┤                              │
  │                                  │  status.loaded=true   │                          │                          │                              │
  │                                  │  → GitDiffChip v-if   │                          │                          │                              │
  │                                  │  → chip appears       │                          │                          │                              │
  │                                  │                       │                          │                          │                              │
  │ 2. click "Git Diff" chip         │                       │                          │                          │                              │
  ├──────────────────────────────────>│                       │                          │                          │                              │
  │                                  │ emit "open-diff-      │                          │                          │                              │
  │                                  │       sidebar"        │                          │                          │                              │
  │                                  ├──────────────────────>│ openGitDiffSidebar()      │                          │                              │
  │                                  │                       │ gitDiffSidebarOpen=true   │                          │                              │
  │                                  │                       ├─────────────────────────>│ modelValue=true           │                              │
  │                                  │                       │                          │ refresh()                 │  GET spcode/git-diff         │
  │                                  │                       │                          ├─────────────────────────>├─────────────────────────────>│
  │                                  │                       │                          │                          │  response → parse            │
  │                                  │                       │                          │  state=ok {snapshot}      │<─────────────────────────────┤
  │                                  │                       │                          │<─────────────────────────┤                              │
  │                                  │                       │                          │ startPolling(10000)       │                              │
  │                                  │                       │                          │                          │                              │
  │ 3. sidebar 打开期间，10s tick    │                       │                          │                          │  GET spcode/git-diff         │
  │                                  │                       │                          │                          ├─────────────────────────────>│
  │                                  │                       │                          │                          │  response → parse            │
  │                                  │                       │                          │  state=ok {snapshot}      │<─────────────────────────────┤
  │                                  │                       │                          │  (静默替换)               │                              │
  │                                  │                       │                          │                          │                              │
  │ 4. /project unload               │                       │                          │                          │                              │
  ├──────────────────────────────────>│                       │                          │                          │                              │
  │                                  │ send ─────────────────>│ onStreamEnd              │                          │  refresh → loaded=false      │
  │                                  │                       ├─────────────────────────>│ watcher → loaded=false    │                              │
  │                                  │                       │                          │ emit update:modelValue    │                              │
  │                                  │                       │                          │   false                   │                              │
  │                                  │                       │  gitDiffSidebarOpen=false │                          │                              │
  │                                  │                       ├─────────────────────────>│ onBeforeUnmount           │                              │
  │                                  │                       │                          │ dispose()                 │  stopPolling + abort         │
  │                                  │                       │                          ├─────────────────────────>│                              │
```

---

## 7. 测试与验收

### 7.1 单元测试（Vitest）

| 文件 | 关键 case |
|---|---|
| `parseSpcodeGitDiff.test.ts` | (1) 标准 unified diff 多文件 → 切片正确<br>(2) 单文件 → 一个 slice<br>(3) `Binary files` → `isBinary=true, slice=null`<br>(4) `truncated=true, diff=null` → files_changed 仍解析，slice 全 null<br>(5) rename（R）→ path 取 b/ 路径<br>(6) `files_changed` 里有但 diff 里找不到 → slice=null, isBinary=false<br>(7) `data.loaded=false, reason='not_a_git_repo'` → meta.loaded=false, reason 保留 |
| `useSpcodeGitDiff.test.ts` | (1) refresh 成功 → state=ok<br>(2) refresh 失败 + 有上次数据 → state=error + previousSnapshot<br>(3) refresh 失败 + 无上次数据 → state=error 无 previousSnapshot<br>(4) startPolling(50) 50ms 内多次调只触发一次 timer<br>(5) dispose 后 timer 停 + abort in-flight<br>(6) umo 缺失不发请求 |
| `GitDiffChip.test.ts` | (1) 默认渲染 chip + tooltip<br>(2) click emit `open-diff-sidebar` |
| `GitDiffSidebar.test.ts` | (1) v-model=false 不渲染 aside<br>(2) v-model=true 渲染 aside + 立即 refresh + startPolling<br>(3) v-model 翻 false → stopPolling<br>(4) onBeforeUnmount → dispose<br>(5) `spcodeStatus.status.value.loaded` 翻 false → emit update:modelValue(false)<br>(6) 拖拽改变 width<br>(7) 移动端样式切换（视口 <760px） |
| `GitDiffBodyContent.test.ts` | (1) state=loading → spinner<br>(2) state=error 无 previous → 错误块 + retry emit<br>(3) snapshot.files=[] → 空态<br>(4) snapshot.files>0 → 列表<br>(5) state=error 有 previous → 列表 + 底部 banner + retry emit |
| `GitDiffFileItem.test.ts` | (1) collapsed → 只显示 row<br>(2) click → emit toggle<br>(3) expanded + 普通 slice → 渲染 DiffPreview<br>(4) expanded + isBinary → v-alert<br>(5) expanded + slice=null, isBinary=false → "无内容"占位<br>(6) status 映射（M/A/D/R/C/?/unknown） |

mock：`pluginExtensionApi` 用 vitest mock；`setInterval`/`clearInterval` 用 fake timers。

### 7.2 端到端验收清单（手工）

| # | 场景 | 期望 |
|---|---|---|
| E1 | spcode 未启用 | chip 不出现 |
| E2 | spcode 启用但未载入项目 | chip 不出现 |
| E3 | `/project load /tmp/repo`（git 仓库） | chip 出现，点开 sidebar 显示文件列表，header 显示目录路径 |
| E4 | 修改 `/tmp/repo` 文件，10s 后 | 列表自动更新（增删文件、stats 变） |
| E5 | 手动点 header 的 refresh 按钮 | 立即 fetch，按钮短暂 loading |
| E6 | sidebar 打开时点击 reasoning 按钮 | sidebar 互斥关闭，reasoning 出现 |
| E7 | `/project unload` | sidebar 自动关闭，chip 也消失 |
| E8 | 载入非 git 目录 | chip 出现，点开 sidebar 显示 reason 错误 + 重试 |
| E9 | 大仓库 diff > 1MB | 顶部黄色 truncated warning |
| E10 | 修改一个二进制文件（图片） | 列表显示该文件，展开看到 v-alert 二进制占位 |
| E11 | sidebar 打开时断网 5s | 不立刻报错；10s tick 后底部出现 banner；恢复网络点重试恢复 |
| E12 | 移动端（<760px）打开 sidebar | 全屏 overlay；关闭按钮回到顶部 |
| E13 | 切换会话（currSessionId 变化） | sidebar 随其它 sidebar 一起关闭 |
| E14 | 切到英文 / 俄文 | 所有新文案翻译生效 |

### 7.3 落地步骤（commit 顺序）

```
1. feat(i18n): add spcodeProjectLoad.diffSidebar keys (zh-CN/en-US/ru-RU)
2. feat(chatui): add parseSpcodeGitDiff pure function + tests
3. feat(chatui): add useSpcodeGitDiff composable + tests
4. feat(chatui): add GitDiffFileItem component + tests
5. feat(chatui): add GitDiffBodyContent component + tests
6. feat(chatui): add GitDiffSidebar shell + tests
7. feat(chatui): add GitDiffChip + wire to ChatInput status row
8. feat(chatui): wire GitDiffSidebar to Chat.vue with mutual exclusion
9. chore(chatui): pnpm lint + pnpm typecheck (run ruff format if any .py)
10. docs: update CHANGELOG (按社区规范)
```

每步独立可跑，commit message 走 conventional commits。

---

## 8. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 大仓库 1MB diff 切片 O(n)，前端卡 | 切片算法单次 `split`；正则预编译；diff 字段已受 `max_bytes=1MB` 限制 |
| 轮询期间频繁 re-render | 列表渲染用 keyed v-for；只在 `snapshot.files` 引用变化时整体替换 |
| 多个 sidebar 同时打开 | 互斥逻辑在 Chat.vue 单点处理（§5.2） |
| 卸载时 setInterval 没清理 | `onBeforeUnmount` 调 `dispose()`，composable 内部 stopPolling + abort |
| 后端端点路径变更 | 集中在 `useSpcodeGitDiff.ts` 一处调用 |
| chip 与 status 联动偶尔错位 | chip 的 v-if 直接读 `spcodeStatus.status.value.loaded`，与 sidebar 的 watcher 同源 |
| i18n key 拼错 | 提交前 grep `spcodeProjectLoad\.diffSidebar` 三个 locale json 都覆盖 |
| Vitest 不在 dashboard 已配置中 | 前置 spec 已说明未配置；本次若不便引入，本 spec 的测试章节标注"按团队后续决定"（见 §1.4 范围声明） |

---

## 9. 未来扩展（不在本 spec）

- 多项目同时 diff（umo 列表 + 切换）
- diff 搜索 / 过滤 / 按 status 折叠
- 文件级 diff view 切换（unified ↔ split）
- commit history / log
- staged vs unstaged 切换
- 在 diff 里直接 commit / revert
- 暗色/亮色主题切换动画

---

## 10. 元数据

- **总文件改动**：3 新增组件 + 1 新增 composable + 1 新增纯函数模块 + 2 处现有文件小幅修改 + 3 个 i18n json + 5 个测试文件
- **代码行数估算**：新增 ~600-700 行（含测试）；改动 ~30-40 行
- **依赖**：零新 npm 依赖（vue 3 / vuetify / i18next 已就绪）
- **向后兼容**：100%（仅新增；现有组件、composable、API 调用零修改）
- **配套文档**：本 spec 设计文档 + 前置 spec（chatui-project-load-button）+ 后续 writing-plans 产出的实现计划
