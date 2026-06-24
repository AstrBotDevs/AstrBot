# Dashboard ChatUI「Git Diff Sidebar」— 设计文档

| 项目 | 内容 |
|------|------|
| 主题 | Dashboard ChatUI 联动 spcode 插件的 Git Diff 侧边栏 |
| 日期 | 2026-06-17（创建）；2026-06-24（chip 文案/图标变更） |
| 作者 | elecvoid243 |
| 状态 | Implemented — 2026-06-24 chip 文案改为「查看工作区」/icon 改为 `mdi-folder-open` |
| 关联插件 | `astrbot_plugin_spcode_toolkit`（**源码路径**：`F:\github\astrbot_plugin_spcode_toolkit`，由 AstrBot 加载时复制到 `F:\github\Astrbot\data\plugins\astrbot_plugin_spcode_toolkit`，两者内容以源码为准） |
| 关联端点 | `GET /plugins/extensions/spcode/git-diff`（handler `handle_get_git_diff`，定义于源码 `main.py:1603`；路由注册于 `main.py:1130-1135`） |
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

1. 在「加载项目」chip 同一行右侧看到一个 outlined「查看工作区」chip（icon `mdi-folder-open`），**仅当 chip 自身可见且项目已载入时显示**
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
- ❌ **不**实现 staged vs unstaged 切换（看 §9 未来扩展）
- ❌ **不**在 sidebar 里直接 commit / revert
- ❌ **不**做 i18n 之外的国际化（如 RTL、自适应字号）
- ❌ **不**写 Vitest 单元测试（沿用姊妹 spec §1.4 决定：dashboard 尚未配置 vitest；用 `pnpm typecheck` + `pnpm lint` + 手动验证 §7.2 端到端验收清单）

---

## 2. 设计决策（已与用户确认）

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | spcode git-diff 端点响应形状 | **A+B 混合**（`files_changed` 列表 + 完整 `diff` 字符串） | 后端已实现；前端用 `files_changed` 渲染列表，用正则按 `diff --git` 切片喂 `DiffPreview` |
| 2 | 与 `ReasoningSidebar` 等其它侧边的关系 | **A 互斥**（沿用现有 `openXxxPanel` 模式） | 与 Chat.vue 现状完全一致；用户场景上同时看 reasoning + diff 不常见 |
| 3 | diff 刷新策略 | **B**：打开时拉取 + 打开期间每 10s 静默轮询 + header 手动 refresh 按钮 | 端点 ~47ms；自动跟着 bot/编辑器变；轮询期间静默替换不闪烁 |
| 4 | 加载中 / 空态 / 截断 / 失败 / 网络错误 / 轮询过渡 | 按推荐方案（见 §5.1 表） | 用户对所有六类状态逐一确认 |
| 5 | 按钮视觉风格 | **B**：outlined v-chip + 文字「查看工作区」 + icon `mdi-folder-open`（2026-06-24 由 "Git Diff" / `mdi-source-pull` 改） | 与现有「加载项目」chip 视觉对仗；扫一眼即知是同类操作；放 status row 右侧通过 `justify-content: space-between` 自然分隔 |
| 6 | 单文件 diff 切片策略 | **预切 + 整段切片 + 二进制单独占位** | 收到 response 立即按 `^diff --git /m` 切；每段原样传给 `DiffPreview.extractDiffContent`（其内部跳到 `@@`）；二进制文件（切片含 "Binary files ... differ"）渲染 `v-alert` 占位 |
| 7 | i18n 键命名 | `spcodeProjectLoad.diffSidebar.*`（中/英/俄三语） | 挂在现有 `spcodeProjectLoad` 根下，与 `dialog.*` / `indicator.*` 同级；英俄翻译由实现者填写 |
| 8 | 后端 reason 枚举完整覆盖 | 7 个值全 i18n：`feature_disabled` / `no_project_loaded` / `directory_missing` / `not_a_git_repo` / `git_unavailable` / `git_error` / `null` | 与源码 `handle_get_git_diff` 完全对齐（见 `main.py:1640-1705`），不留"未知 reason 兜底"盲区 |
| 9 | git status 码范围 | `M / A / D / R / C / T` + 兜底 `unknown` | 源码 `_parse_files_changed`（`main.py:1189-1226`）含 T（type-change）；spec 原始版本漏了 T |

---

## 3. 架构与文件改动

### 3.1 架构原则

- **零后端改动**：完全复用 spcode 现有 `git-diff` 端点
- **零 spcode 改动**：通过标准 HTTP endpoint 调用（端点 `GET /spcode/git-diff` 已在源码 `main.py:1130-1135` 注册；本 spec 不修改 spcode 任何代码）
- **零 `DiffPreview.vue` 改动**：作为子组件复用，原样式零侵入
- **零 `useSpcodeProjectStatus.ts` 改动**：composable 是单例，由 sidebar 内部读 `status.value.loaded` 做自动关闭
- **Inline-first**：helpers 写在 composable / 组件文件顶部，不强行抽公共文件
- **AGENTS.md 适用条款**：Google-style docstring（前端用 TSDoc 等价物）、英文注释、conventional commit messages；本 spec 不涉及 Python 故 `pathlib` / `ruff` 不适用

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
| 改动 | `dashboard/src/i18n/locales/zh-CN/features/chat.json` | 修改 | 新增 i18n 键（见 §5.1.1，共 17 个） |
| 改动 | `dashboard/src/i18n/locales/en-US/features/chat.json` | 修改 | 新增 i18n 键 |
| 改动 | `dashboard/src/i18n/locales/ru-RU/features/chat.json` | 修改 | 新增 i18n 键 |

> **测试文件**：本 spec 沿用姊妹 spec 决定不写 Vitest（dashboard 尚未配置）；改为依赖 `pnpm typecheck` + `pnpm lint` + 手动跑 §7.2 端到端验收清单。

### 3.3 改动量估算

- 新增代码：~500-600 行（3 个组件 + 1 个 composable + 1 个纯函数模块）
- 改动现有代码：~30-40 行（ChatInput 加 1 个 emit 声明 + 1 个 `<GitDiffChip/>` 节点 + 1 个 emit 转发；Chat.vue 加 import + 1 个 `<GitDiffSidebar/>` + 1 个 `openGitDiffSidebar()` + currSessionId watcher 1 行；3 个 i18n json 各加 ~17 行）
- ChatInput.vue `defineEmits` 块当前未声明 `open-diff-sidebar`（见 `ChatInput.vue:408-422`），实施时需追加
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
export type FileStatus = 'M' | 'A' | 'D' | 'R' | 'C' | 'T' | 'unknown'

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
        prepend-icon="mdi-folder-open"
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

`.input-area__status-row` 加 `justify-content: space-between`，让现有 chip 靠左、「查看工作区」chip 靠右自然分开（chip 不可见时不影响布局）。

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

- **始终显示行**：status icon（按 §4.2.5 映射）+ path + (+N −N) + chevron
- **expanded 时显示 body**：
  - `file.isBinary === true` → `v-alert` "二进制文件改动（无文本预览）"
  - `file.slice` 非 null → `<DiffPreview :content="file.slice" :file-path="file.path" :collapsible="true" :is-dark="isDark" />`（显式传值，避免依赖 default 变更）
  - `file.slice === null && !file.isBinary` → "无内容"占位（truncated 边界或解析异常）

#### 4.2.5 status → 图标/颜色映射

| status | mdi icon | color |
|---|---|---|
| `M` | `mdi-pencil` | primary |
| `A` | `mdi-plus-circle` | success |
| `D` | `mdi-minus-circle` | error |
| `R` | `mdi-rename-box` | warning |
| `C` | `mdi-content-copy` | info |
| `T` | `mdi-swap-horizontal` | info |
| 其它 | `mdi-file-document-edit-outline` | grey |

---

## 5. 错误处理 & 互斥逻辑

### 5.1 错误分类与文案

| 来源 | 检测 | UI | 用户动作 |
|---|---|---|---|
| HTTP 4xx/5xx | axios reject 或 `status:"error"` | 居中错误块 + 重试 | 点重试 |
| HTTP 网络错误 | axios reject | 同上，文案"网络连接失败" | 点重试 |
| `data.loaded=false` | snapshot.meta.loaded=false | reason → i18n 映射（见下表） | 按 reason 处理 |
| `reason: "feature_disabled"` | 同上 | 功能未启用（请检查 spcode 配置 agentsmd_enabled / codegraph_enabled） | 改插件配置 |
| `reason: "no_project_loaded"` | 同上（防御性；理论上 chip 此时不显示） | 项目未载入 | 重新 `/project load` |
| `reason: "directory_missing"` | 同上 | 已加载的目录不存在（被删除/移动） | 重新载入或换目录 |
| `reason: "not_a_git_repo"` | 同上 | 当前目录不是 Git 仓库 | `git init` 或换目录 |
| `reason: "git_unavailable"` | 同上 | 未检测到 git 可执行文件 | 安装 git 或配 `git_path` |
| `reason: "git_error"` | 同上 | Git 执行失败（{reason}） | 看 stderr 排查 |
| 未知 reason | 不在映射表（防御未来扩展） | 获取改动失败（{reason}） | 点重试或回报 |
| 轮询中途错误 | tick 内 fetch reject | 保留上次 snapshot，底部 banner | 点 banner 重试 |
| truncated | `meta.truncated === true` | sidebar 顶部黄色 warning 横条 | （无） |
| `slice=null, isBinary=false` | path 在 files_changed 但 diff 里找不到 | 文件行下"内容已截断或不完整" | （无） |
| 二进制文件 | slice 含 `Binary files ... differ` | v-alert 二进制占位 | （无） |

**reason → i18n 键映射**：

```typescript
const REASON_I18N_KEYS: Record<string, string> = {
  feature_disabled: 'spcodeProjectLoad.diffSidebar.error.reason.feature_disabled',
  no_project_loaded: 'spcodeProjectLoad.diffSidebar.error.reason.no_project_loaded',
  directory_missing: 'spcodeProjectLoad.diffSidebar.error.reason.directory_missing',
  not_a_git_repo: 'spcodeProjectLoad.diffSidebar.error.reason.not_a_git_repo',
  git_unavailable: 'spcodeProjectLoad.diffSidebar.error.reason.git_unavailable',
  git_error: 'spcodeProjectLoad.diffSidebar.error.reason.git_error',
}

function localizedReason(reason: string | null, tm: Function): string {
  if (!reason) return tm('spcodeProjectLoad.diffSidebar.error.reason.generic', { reason: 'unknown' })
  const key = REASON_I18N_KEYS[reason]
  return key ? tm(key) : tm('spcodeProjectLoad.diffSidebar.error.reason.generic', { reason })
}
```

#### 5.1.1 完整 i18n 键清单（zh-CN / en-US / ru-RU 三语）

| 键 | 中文 | English | Русский |
|---|---|---|---|
| `spcodeProjectLoad.diffSidebar.chip` | `查看工作区` | `Workspace` | `Рабочая область` |
| `spcodeProjectLoad.diffSidebar.chipTooltip` | `查看工作区文件、改动和历史` | `Browse workspace files, changes, and history` | `Просмотр файлов, изменений и истории рабочей области` |
| `spcodeProjectLoad.diffSidebar.title` | `项目改动` | `Project changes` | `Изменения проекта` |
| `spcodeProjectLoad.diffSidebar.refreshTooltip` | `刷新` | `Refresh` | `Обновить` |
| `spcodeProjectLoad.diffSidebar.loading` | `加载中…` | `Loading…` | `Загрузка…` |
| `spcodeProjectLoad.diffSidebar.empty` | `暂无文件改动` | `No file changes` | `Нет изменений файлов` |
| `spcodeProjectLoad.diffSidebar.truncated` | `⚠ diff 已截断（仅显示前 {shown} / {max} 字节，可能不完整）` | `⚠ diff truncated (showing first {shown} / {max} bytes, may be incomplete)` | `⚠ diff обрезан (показано первые {shown} / {max} байт, возможно неполный)` |
| `spcodeProjectLoad.diffSidebar.binaryFile` | `二进制文件改动（无文本预览）` | `Binary file changed (no text preview)` | `Бинарный файл изменён (без предпросмотра)` |
| `spcodeProjectLoad.diffSidebar.error.networkTitle` | `网络连接失败` | `Network connection failed` | `Ошибка сетевого подключения` |
| `spcodeProjectLoad.diffSidebar.error.retry` | `重试` | `Retry` | `Повторить` |
| `spcodeProjectLoad.diffSidebar.error.reason.feature_disabled` | `功能未启用（请检查 spcode 配置 agentsmd_enabled / codegraph_enabled）` | `Feature disabled (check spcode config agentsmd_enabled / codegraph_enabled)` | `Функция отключена (проверьте spcode config agentsmd_enabled / codegraph_enabled)` |
| `spcodeProjectLoad.diffSidebar.error.reason.no_project_loaded` | `项目未载入` | `No project loaded` | `Проект не загружен` |
| `spcodeProjectLoad.diffSidebar.error.reason.directory_missing` | `已加载的目录不存在` | `Loaded directory no longer exists` | `Загруженный каталог больше не существует` |
| `spcodeProjectLoad.diffSidebar.error.reason.not_a_git_repo` | `当前目录不是 Git 仓库` | `Current directory is not a Git repository` | `Текущий каталог не является репозиторием Git` |
| `spcodeProjectLoad.diffSidebar.error.reason.git_unavailable` | `未检测到 git 可执行文件` | `Git executable not found` | `Исполняемый файл git не найден` |
| `spcodeProjectLoad.diffSidebar.error.reason.git_error` | `Git 执行失败（{reason}）` | `Git execution failed ({reason})` | `Ошибка выполнения Git ({reason})` |
| `spcodeProjectLoad.diffSidebar.error.reason.generic` | `获取改动失败（{reason}）` | `Failed to fetch changes ({reason})` | `Не удалось получить изменения ({reason})` |

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

// 切换会话时统一关闭所有 secondary panel（沿用 `closeSecondaryPanels()` 模式）
// 注意：Chat.vue 现有 watcher（line 1066-1074）只刷新 spcode status，
// 并未调用 `closeSecondaryPanels()`；本 spec 需新增一行关闭 gitDiffSidebarOpen。
// 至于 `todoSidebarOpen` 是否随会话切换关闭，spec 不强制约束；保持现状行为一致。
watch(currSessionId, () => {
  gitDiffSidebarOpen.value = false
})
```

### 5.3 项目卸载自动关闭（GitDiffSidebar 内部）

```typescript
watch(() => spcodeStatus.status.value.loaded, (loaded) => {
  if (!loaded) emit('update:modelValue', false)
})
```

链路：用户 `/project unload` → spcode plugin 更新 `loaded_projects` → ChatInput 检测到 `/project unload` 关键字调 `applyOptimistic()` 把 `ProjectStatus` 设为 unloaded（即时 chip 消失）→ `send` 触发 SSE 流 → `Chat.vue onStreamEnd` 调 `useSpcodeProjectStatus.refresh()` → 后端 `/spcode/project-status` 返回 loaded=false → `status.loaded` 翻 false → 上面 watcher 触发 → sidebar 关闭 → onBeforeUnmount → dispose。

> 关键：`applyOptimistic` / `setUnloaded` 由姊妹 spec `2026-06-16-chatui-project-load-button-design.md` 定义；本 spec 不重复定义，仅按依赖使用。

### 5.4 轮询期间的"静默替换"

```typescript
// composable 实例级别的闭包变量；onBeforeUnmount → dispose() 时翻 false
let isMounted = true

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
    state.value = { kind: 'error', reason: classifyError(err), previousSnapshot: prev }
  }
}

function dispose(): void {
  isMounted = false
  stopPolling()
  if (abortController) abortController.abort()
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
  │ 2. click "查看工作区" chip       │                       │                          │                          │                              │
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
  │                                  │ applyOptimistic       │                          │                          │                              │
  │                                  │  ProjectStatus        │                          │                          │                              │
  │                                  │  .setUnloaded()       │                          │                          │                              │
  │                                  │  (即时 chip 消失)      │                          │                          │                              │
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

### 7.1 验证策略（沿用姊妹 spec 决定）

dashboard 尚未配置 Vitest（见姊妹 spec `2026-06-16` §1.4）。本 spec 不引入测试框架，依赖：

1. **`pnpm typecheck`**（dashboard 已有 TypeScript 严格模式）：所有新文件编译通过
2. **`pnpm lint`**：ESLint 规则通过
3. **手动跑 §7.2 端到端验收清单**：覆盖所有关键路径，包括正常态、错误态、边界条件
4. **手工 visual 验证**：在开发服务器 `pnpm dev` 中逐项核对 UI 表现

实施者若后续决定引入 Vitest，本 spec 涵盖的 case 至少包括：`parseSpcodeGitDiff` 7 类输入（含截断 / 二进制 / rename / path 缺失 / reason 保留）、`useSpcodeGitDiff` 6 类行为（refresh 成功失败 / startPolling 幂等 / dispose / umo 缺失）、`GitDiffSidebar` 7 类生命周期（v-model 切换 / watcher 联动 / 拖拽 / 移动端 / unmount 清理等）、`GitDiffBodyContent` 5 类状态分支、`GitDiffFileItem` 6 类渲染分支。覆盖范围见姊妹 spec `2026-06-16` §1.4 的"N 不写自动化测试，本节是验证清单"惯例。

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
2. feat(chatui): add parseSpcodeGitDiff pure function
3. feat(chatui): add useSpcodeGitDiff composable
4. feat(chatui): add GitDiffFileItem component
5. feat(chatui): add GitDiffBodyContent component
6. feat(chatui): add GitDiffSidebar shell
7. feat(chatui): add GitDiffChip + wire to ChatInput status row
8. feat(chatui): wire GitDiffSidebar to Chat.vue with mutual exclusion
9. chore(chatui): pnpm lint + pnpm typecheck
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
| i18n key 命名拼错 | 提交前 grep `spcodeProjectLoad\.diffSidebar` 三个 locale json 都覆盖 |
| 后端端点契约漂移 | spcode `git-diff` 端点是外部契约（不在本 spec 范围内修改）。如果未来 `handle_get_git_diff` 改动字段，本 spec 的 `SpcodeGitDiffRawResponse` 类型与 `parseSpcodeGitDiff` 会失配。缓解：① `parseSpcodeGitDiff` 内部对未知 reason / 未知 status 码都走兜底分支，不抛错；② 字段访问全部 `?.` / `?? null` 兜底；③ 联调时锁定源码 `main.py` 版本号或 commit hash |
| i18n key 拼错或缺翻译 | 提交前 grep `spcodeProjectLoad\.diffSidebar` 三个 locale json 都覆盖；CI 跑 `pnpm typecheck` 捕获硬编码字符串 |
| 端点响应体超过 1MB | `MAX_GIT_DIFF_BYTES=1MB` 由 spcode 端截断（`main.py:1710-1711`），本 spec 已 `truncated` 字段处理截断 UI；极端大仓库单文件 diff 仍可能溢出 `DiffPreview.maxChars`（默认 2000） |
| `defineEmits` 声明遗漏 | `ChatInput.vue` 当前未声明 `open-diff-sidebar`，本 spec 已在 §3.3 标注需追加 |

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

- **总文件改动**：3 新增组件 + 1 新增 composable + 1 新增纯函数模块 + 2 处现有文件小幅修改 + 3 个 i18n json
- **代码行数估算**：新增 ~500-600 行；改动 ~30-40 行
- **外部契约依赖**：spcode `GET /spcode/git-diff` 端点（已在源码 `main.py:1130-1135` 注册，本 spec 不修改）
- **依赖**：零新 npm 依赖（vue 3 / vuetify / i18next 已就绪）
- **向后兼容**：100%（仅新增；现有组件、composable、API 调用零修改）
- **配套文档**：本 spec 设计文档 + 前置 spec（chatui-project-load-button）+ 后续 writing-plans 产出的实现计划
