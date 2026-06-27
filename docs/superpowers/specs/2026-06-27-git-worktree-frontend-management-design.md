# Git Worktree 前端管理功能 — 前端设计方案

> **作者**：elecvoid243
> **生成时间**：2026-06-27 19:30 (CST)
> **范围**：基于 `astrbot_plugin_spcode_toolkit` v2.14.0 新增的 4 个 worktree 写端点（ADD / REMOVE / LOCK / UNLOCK），在 `GitDiffSidebar.vue` 中提供对应的前端管理 UI
> **遵循原则**：KISS / 复用现有 pattern / 不引入外部框架 / 与 spcode 文档错误矩阵保持一致

> **实施状态**: ✅ 已完成 (2026-06-27)
> **实施计划**: `docs/superpowers/plans/2026-06-27-git-worktree-frontend-management.md`
> **相关 PR**: <TBD — 用户未要求 PR>

## 0. 现状摘要（基于代码阅读）

| 关注点 | 现状 | 复用方式 |
|--------|------|---------|
| Worktree 列表 | `useSpcodeWorktrees` 仅暴露 `state / refresh / startPolling / stopPolling / dispose`（只读） | **扩展**该 composable，加入 4 个 mutation 方法 |
| 现有 worktree UI | `GitDiffSidebar.vue` 中的 tab 行（`worktreeList` 渲染为 `v-for`），只有"切换"功能 | **就地扩展**：每个 tab 增加右键菜单；tab 行末尾追加 `+` 按钮 |
| 错误处理 | `classifyReason(reason, endpoint)` + `RESTORE_REASON_I18N_KEYS` 字典 | **新建** `WORKTREE_MGMT_REASON_CODES` 字典 + 端点 `'add'\|'remove'\|'lock'\|'unlock'` |
| 确认弹窗 | 已有 `confirmDialogOpen / confirmTargetPath` + `v-dialog persistent` 模式 | **复用** 该模式，3 个新弹窗（ADD / REMOVE / LOCK） |
| Snackbar（带 stderr 块） | 已有 `snackbar: SnackbarState` + `<pre>` 渲染 | **直接复用** |
| i18n | `useModuleI18n("features/chat")` + `tm(key)` | 在 `chat.json` 的 `spcodeProjectLoad.diffSidebar.worktreeMgmt` 子树下新增键 |
| 提交/工作流按钮 | `GitCommitBar` 粘性底部条 | **不涉及**（避免破坏现有 diff 视图密度） |
| 项目状态 | `useSpcodeProjectStatus` 提供 `umo / directory` | **直接使用** 注入到 mutation 请求 |

## 1. 架构决策

### 1.1 Composable 整合策略：扩展而非新建

**推荐方案**：扩展现有 `useSpcodeWorktrees` composable，新增 `add / remove / lock / unlock` 四个方法。

**理由**：
1. 4 个 mutation 都返回 `data.worktrees[]`（已刷新列表）—— **必须同步更新 `state`**，避免额外一次 GET
2. 现有 `useSpcodeWorktrees` 已经管理 polling / dispose / umo 监听 — 在同一 composable 内访问这些状态零成本
3. 新建独立 composable 会导致"读"和"写"两个实例间 `state` 不一致（写完后读不到新列表）
4. 与 `useSpcodeGitCommit` 等 workflow composable 不同（commit 不改 worktree 列表），worktree 写端点必须跟读端点共享 state

**新增方法签名**（追加到 `UseSpcodeWorktrees` 接口）：

```ts
add(params: AddParams): Promise<WorktreeMgmtResult>
remove(params: RemoveParams): Promise<WorktreeMgmtResult>
lock(params: LockParams): Promise<WorktreeMgmtResult>
unlock(params: UnlockParams): Promise<WorktreeMgmtResult>
```

每个 mutation 都返回 discriminated union：

```ts
type WorktreeMgmtResult =
  | { ok: true; snapshot: SpcodeGitWorktreesSnapshot }
  | { ok: false; reason: string; stderr?: string };
```

### 1.2 Parser 与 reason 字典

**新建** `parseSpcodeWorktreeManagement.ts`：

- 4 个 parser：`parseSpcodeWorktreeAdd / Remove / Lock / Unlock`
- 全部返回 `ParseResult<SpcodeGitWorktreesSnapshot>`（**复用**现有 snapshot 类型，4 个端点都返回同样的 `data.worktrees[]`）
- 暴露 `WORKTREE_MGMT_REASON_CODES` 字典（与 `GIT_WORKFLOW_REASON_CODES` 同构，但 reason 集合更窄）

### 1.3 UI 入口选择

**推荐方案 A（采纳）**：就地扩展现有 worktree tab 行
- 在每个 tab 上增加 `@contextmenu.prevent` 打开 `v-menu`
- 在 tab 行末尾追加 `+` 圆点按钮
- 不新增 viewMode（Files / Diff / History 三个 tab 保持不变）

**理由**：
1. 用户已经知道"这里管 worktree"——把"管理 worktree"按钮也放这里符合 mental model
2. 避免"再加一个 tab"导致 tab 数量膨胀
3. 主 worktree 的"删除"按钮被业务闸禁用，正好可以作为 disable / tooltip 模式的范例

**被否方案 B**：新增第 4 个 viewMode "Worktrees"
- 缺点：把列表与操作分离，用户得切换 3 次才能 ADD → 切到主 worktree → 看 diff
- 优点：能在同一视图批量管理；本设计暂不需要批量操作（仅 LOCK/UNLOCK/REMOVE 是单条的，ADD 是单条的）

## 2. 详细 UI 设计

### 2.1 Worktree Tab 行（修改后）

```
┌─ 工作树 ───────────────────────────────────────────────  [+] ┐
│  [🏠 main]  [feat-foo 游离]  [feat-bar 🔒]   ...         │  ← + 按钮在最后
└──────────────────────────────────────────────────────────┘
       ↓ 右键任一 tab
┌──────────────────────────────┐
│ 🔒 锁定 / 解锁   (按状态切换)  │
│ 🗑  删除                    │  ← main 灰显 + tooltip
│ ⓘ  在文件浏览器中打开  (TODO?)│
└──────────────────────────────┘
```

**修改点**（在 `GitDiffSidebar.vue` 模板中）：
1. 每个 `<button class="git-diff-sidebar-tab">` 加 `@contextmenu.prevent="(e) => openContextMenu(e, wt)"`
2. tab 行最右侧加 `<button class="git-diff-sidebar-tab-add" @click="openAddDialog">+</button>`
3. 行级 `<v-menu>` 用于承载右键菜单

**新 CSS**（追加到 `<style scoped>`）：
- `.git-diff-sidebar-tab-add`（22×22 圆形 dashed 边框）
- `.git-diff-sidebar-tab[aria-disabled="true"]`（main 不可删除的视觉提示）

### 2.2 4 个 Dialog 组件

#### A. `WorktreeCreateDialog.vue`（新增独立组件）

触发：tab 行 `+` 按钮 / 上下文菜单"新建 worktree"

表单字段：

| 字段 | 类型 | 必填 | 校验 | 默认值 |
|------|------|------|------|--------|
| 模式 | radio | ✓ | 互斥 | `create` |
| 分支名 | text | 条件 | git ref 格式 | （空） |
| 路径 | text | ✓ | 必填，绝对路径 | `.worktrees/<branch-sanitized>` 自动填充 |
| 起始点 | text | 条件 | git ref 格式 | `main` |

模式 radio 互斥逻辑（对齐后端 5 步互斥）：

```ts
type CreateMode = 'create' | 'force' | 'detach';
// 仅 create 模式显示「起始点」
// detach 模式禁用「分支名」(后端 detach 不接 branch)
```

提交后：
- 成功：用 `data.worktrees` 替换 composable state
- 成功且 `data.worktree` 存在：自动切到新 worktree（设置 `selectedWorktree.value = data.worktree`）并切到 Files 视图
- 失败：行内 error + stderr 块（沿用现有 snackbar 模式）

#### B. REMOVE 确认弹窗（内联 `v-dialog`，与 `confirmDialogOpen` 同模式）

触发：上下文菜单"删除" / `WorktreeDeleteButton`

表单：
- 路径 + 分支名（只读）
- dirty 文件计数（来自 `/spcode/git-status?worktree=<path>`，lazy 加载）
- 复选框"强制删除（丢弃未提交改动）"—— 仅在 dirty > 0 时可见
- 取消 / 确认（warning 色）

disabled 规则（前端硬守）：
- `is_main === true` → 整个入口不可见（更安全：直接不让用户产生"想删 main"的念头）
- `locked === true` → 入口可见但 disabled，tooltip `"已锁定：<locked_reason>。请先解锁"`

#### C. LOCK 子弹窗（内联 `v-dialog`）

触发：上下文菜单"锁定"

表单：
- 路径 + 分支名（只读）
- "锁定原因" textarea（可选，200 字符限制 —— 前端校验对齐 spcode 建议）

#### D. UNLOCK 确认（**独立** dialog，对称 confirmStageAll / confirmUnstageAll 模式）

> **2026-06-27 决策更新**：推翻原"复用 confirmDialogOpen"方案，改用**独立 dialog**。

**新决策**：
- unlock 操作使用独立的 `confirmUnlockOpen` ref + 独立 `<v-dialog>` 块
- 与 `confirmStageAllOpen` / `confirmUnstageAllOpen` 的"对称双弹窗"模式完全一致
- 状态完全隔离：独立的 `confirmUnlockPath` / `isUnlocking` ref，无 action 状态机

**理由**（完整分析见 11.3 节"复用 vs 独立 dialog 的影响对比"）：
1. **一致性 > 复用**：项目里 `confirmStageAllOpen` 和 `confirmUnstageAllOpen` **也是两个独立弹窗**，独立 dialog 与现有哲学完全一致；**复用 confirmDialogOpen 反而成了特例**
2. **状态隔离更安全**：restore（文件级 undo）和 unlock（worktree 级 lock 释放）是语义完全不同的操作，共用弹窗的 loading / target state 容易在快速点击时产生"上一个操作的 loading 被下一个操作覆盖"的 bug
3. **未来扩展无成本**：如果未来 spec 升级（比如 unlock 后展示"已解锁 + 列出被锁文件"），独立 dialog 改起来零摩擦；共用 dialog 要继续加 `v-if` 链

**新增状态**：

```ts
// 保持现有 confirmDialogOpen / confirmTargetPath 专用于 restore（不改动）
const confirmUnlockOpen = ref(false);
const confirmUnlockPath = ref<string | null>(null);
const isUnlocking = ref(false);
```

### 2.3 上下文菜单的 Vuetify 模式

`v-menu` + 手动控制 `location-strategy="absolute"` + `position-x / position-y`：

```vue
<v-menu
  v-model="contextMenu.open"
  :location-strategy="'absolute'"
  :position-x="contextMenu.x"
  :position-y="contextMenu.y"
>
  <v-list density="compact">
    <v-list-item :disabled="!targetWt" @click="onLockToggle">
      <template #prepend><v-icon>mdi-lock{{ targetWt?.locked ? '-open-variant' : '' }}</v-icon></template>
      <v-list-item-title>{{ targetWt?.locked ? '解锁' : '锁定…' }}</v-list-item-title>
    </v-list-item>
    <v-list-item :disabled="targetWt?.is_main" @click="onRemoveClick">
      <template #prepend><v-icon color="error">mdi-trash-can-outline</v-icon></template>
      <v-list-item-title>删除…</v-list-item-title>
    </v-list-item>
  </v-list>
</v-menu>
```

`contextMenu` 状态（`GitDiffSidebar.vue` 新增）：

```ts
const contextMenu = ref<{ open: boolean; x: number; y: number; wt: SpcodeGitWorktree | null }>({
  open: false, x: 0, y: 0, wt: null,
});
function openContextMenu(e: MouseEvent, wt: SpcodeGitWorktree): void {
  contextMenu.value = { open: false, x: e.clientX, y: e.clientY, wt };
  // 微 task 等 DOM 更新后 v-model 触发
  nextTick(() => { contextMenu.value.open = true; });
}
```

> 决策：用 `nextTick` 显式打开而非 `@contextmenu.prevent="openContextMenu"`，因为 Vuetify 在 `position-x/y` 改变时需要 reflow，nextTick 保证 `x/y` 落定后再设 `open=true`，避免菜单闪到 (0, 0) 位置。

### 2.4 状态机（弹窗切换）

> **2026-06-27 决策更新**：4 个 worktree 操作**全部使用独立 dialog**，不复用 `confirmDialogOpen`。

`GitDiffSidebar.vue` 现有的弹窗状态（不改动）：

```ts
// 现有，专用于 restore + 未来可能加的简单 confirm
const confirmDialogOpen = ref(false);
const confirmTargetPath = ref<string | null>(null);
const restoringFile = ref<string | null>(null);  // restore 专用 loading

// 现有，stage/unstage 批量操作（已存在）
const confirmStageAllOpen = ref(false);
const confirmUnstageAllOpen = ref(false);
const pendingStageAllCount = ref(0);
const pendingUnstageAllCount = ref(0);
```

**新增 4 个独立 ref**（worktree 管理专用）：

```ts
const createDialogOpen = ref(false);     // ADD 表单
const removeDialogOpen = ref(false);     // REMOVE 二次确认
const lockDialogOpen = ref(false);       // LOCK 表单（带 reason）
const confirmUnlockOpen = ref(false);    // UNLOCK 二次确认（独立）
const confirmUnlockPath = ref<string | null>(null);
const isUnlocking = ref(false);          // unlock 飞行状态
const isRemoving = ref(false);           // remove 飞行状态
const isLocking = ref(false);            // lock 飞行状态
const dirtyCount = ref<number | null>(null);  // REMOVE 弹窗专用
```

> **设计哲学**：每个危险/可恢复的操作都配一个**独立 dialog + 独立 loading ref**，避免 action 状态机的状态污染问题。这与 `confirmStageAllOpen` / `confirmUnstageAllOpen` 的对称拆分哲学完全一致 —— 即使这两个操作在功能上**几乎一样**，代码里也保留了两个独立 ref。

### 2.5 dirty 文件计数（REMOVE 流程专用）

弹窗打开时按需触发：

```ts
const dirtyCount = ref<number | null>(null);
async function loadDirtyFor(target: SpcodeGitWorktree): Promise<void> {
  if (target.isMain) { dirtyCount.value = null; return; }
  try {
    const resp = await pluginExtensionApi.get<{ data: { files_changed: number } }>(
      'spcode/git-status',
      { params: { umo: spcodeStatus.status.value.umo, worktree: target.path } }
    );
    dirtyCount.value = resp.data?.data?.files_changed ?? 0;
  } catch {
    dirtyCount.value = null; // 网络错不阻塞 UI,让后端兜底
  }
}
```

`force` 复选框默认勾选条件：`dirtyCount.value > 0`（与 spcode 文档 §3.2.5 一致：UI 自动勾选但仍需二次确认）。

## 3. 数据流：Mutation 端到端

以 REMOVE 为例（最复杂的流程）：

```
右键 tab "feat-foo"
        ↓
openContextMenu(e, featFoo)
        ↓
v-menu 显示 → 点 "删除…"
        ↓
onRemoveClick(featFoo)
  - main / locked 前端校验
  - 打开 removeDialogOpen
  - loadDirtyFor(featFoo) ←-- 触发 GET /spcode/git-status
        ↓
用户勾选 force（如 dirty>0）→ 点 "确认删除"
        ↓
onConfirmRemove()
  - worktrees.remove({ path, force, umo, worktree: selectedWorktree })
        ↓
POST /spcode/git-worktree-remove
        ↓
成功：state.value = { kind: 'ok', snapshot: parse(response.data.worktrees) }
  - 如果被删的 == selectedWorktree → 切回 main
  - 关闭 dialog → snackbar success
失败：snackbar error + stderr <pre> 块
        ↓
轮询定时器（30s）会与新 state 对比，仅在拓扑变化时触发现有 watcher
```

**乐观更新策略**：**不**做乐观更新（不同于 stage/unstage），理由：
- worktree 列表是**强结构化**数据，错一个会污染整个 tab 行
- 后端返回 `data.worktrees` 已经覆盖了完整的最新状态
- 直接套用响应是最简单且最安全的路径
- 与 `useSpcodeGitStage` 的 `stagedFiles.value = new Set(result.snapshot.files)` 同模式

## 4. 错误处理矩阵（对齐 spcode §4.3）

| reason 类别 | UI 处理 | 备注 |
|------------|---------|------|
| `feature_disabled` / `no_project_loaded` / `directory_missing` / `not_a_git_repo` | 顶部 banner + 禁用所有 worktree 写按钮 | 复用现有 `isProjectLoaded` 计算属性 |
| `git_unavailable` / `git_error` | 红色 banner + stderr <pre> 块 | 复用 `snackbar.stderr` 渲染 |
| `invalid_body` / `invalid_branch` / `invalid_param` | 表单字段高亮（红框 + helper text） | 在 `WorktreeCreateDialog.vue` 内做字段级 error |
| `path_unsafe` | toast `"路径命中黑名单"` | **不**展示 stderr（避免泄露黑名单） |
| `path_exists_nonempty` | 内联提示"目标路径已被占用" + "换一个路径"按钮 | 在 ADD dialog 内联处理 |
| `cannot_create_existing` | 内联提示"分支已存在，请勾选强制覆盖" | 自动勾选 `force=true` 模式 radio |
| `worktree_not_found` | snackbar warning + 触发 `worktrees.refresh()` | 列表自动收敛 |
| `cannot_remove_main` | **不该到达前端**（前端已硬禁 main）；若发生记监控 | toast error |
| `worktree_locked` | snackbar warning + 引导到 unlock UI | 显示 stderr 携带的 locked_reason |
| `worktree_dirty` | snackbar warning + 提示用户重提交时勾选 force | 后端**不**支持 auto-retry（spec §3.2.4），由用户主动重试 |
| `already_locked` / `not_locked` | snackbar warning + 刷新按钮 | 前端应已通过 `locked` 字段预防 |

**通用映射表**（`parseSpcodeWorktreeManagement.ts`）：

```ts
export const WORKTREE_MGMT_REASON_CODES: Record<string, ReasonMeta> = {
  // 前置
  feature_disabled:        { i18nKey: 'error.reason.feature_disabled', color: 'error' },
  no_project_loaded:       { i18nKey: 'error.reason.no_project_loaded', color: 'error' },
  worktree_invalid:        { i18nKey: 'error.reason.worktree_invalid', color: 'error' },
  directory_missing:       { i18nKey: 'error.reason.directory_missing', color: 'error' },
  not_a_git_repo:          { i18nKey: 'error.reason.not_a_git_repo', color: 'error' },
  git_unavailable:         { i18nKey: 'error.reason.git_unavailable', color: 'error' },
  git_error:               { i18nKey: 'error.reason.git_error', color: 'error', withStderr: true },
  // body
  invalid_body:            { i18nKey: 'error.reason.invalid_body', color: 'error' },
  invalid_branch:          { i18nKey: 'error.reason.invalid_branch', color: 'error' },
  invalid_param:           { i18nKey: 'error.reason.invalid_param', color: 'error' },
  // 路径
  path_unsafe:             { i18nKey: 'error.reason.path_unsafe', color: 'error' },
  // 业务
  path_exists_nonempty:    { i18nKey: 'error.reason.path_exists_nonempty', color: 'warning' },
  cannot_create_existing:  { i18nKey: 'error.reason.cannot_create_existing', color: 'warning' },
  worktree_not_found:      { i18nKey: 'error.reason.worktree_not_found', color: 'warning' },
  cannot_remove_main:      { i18nKey: 'error.reason.cannot_remove_main', color: 'error' },
  worktree_locked:         { i18nKey: 'error.reason.worktree_locked', color: 'warning' },
  worktree_dirty:          { i18nKey: 'error.reason.worktree_dirty', color: 'warning' },
  already_locked:          { i18nKey: 'error.reason.already_locked', color: 'warning' },
  not_locked:              { i18nKey: 'error.reason.not_locked', color: 'warning' },
  // 网络/未知
  network:                 { i18nKey: 'error.reason.network', color: 'error' },
  unknown:                 { i18nKey: 'error.reason.unknown', color: 'error', withReason: true },
};
```

## 5. 待修改 / 新增文件清单

### 5.1 新增文件

| 路径 | 用途 | 行数估算 |
|------|------|---------|
| `dashboard/src/composables/parseSpcodeWorktreeManagement.ts` | 4 个 mutation 端点的 response parser + reason 字典 | ~180 |
| `dashboard/src/components/chat/message_list_comps/WorktreeCreateDialog.vue` | ADD 表单弹窗 | ~280 |
| `dashboard/src/components/chat/WorktreeContextMenu.vue` | 右键菜单（可选独立组件或内联） | 推荐**内联**到 `GitDiffSidebar.vue`（< 80 行） |

> 决策：`WorktreeContextMenu` 内联，避免组件碎片化（与现有 `RESTORE_REASON_I18N_KEYS` 内联字典哲学一致）。

### 5.2 修改文件

| 路径 | 改动 |
|------|------|
| `dashboard/src/composables/useSpcodeWorktrees.ts` | 扩展 `UseSpcodeWorktrees` 接口，新增 `add / remove / lock / unlock` 4 个方法（约 +150 行） |
| `dashboard/src/components/chat/GitDiffSidebar.vue` | tab 行加 `+` 按钮 + `contextmenu` + 4 个新 dialog（+状态机 + 4 个新方法） + 2 处 CSS（+50 行） |
| `dashboard/src/i18n/locales/zh-CN/features/chat.json` | 在 `spcodeProjectLoad.diffSidebar.worktreeMgmt` 子树下新增键（~30 keys） |
| `dashboard/src/i18n/locales/en-US/features/chat.json` | 同上 |
| `dashboard/src/i18n/locales/ru-RU/features/chat.json` | 同上（必要时） |

### 5.3 i18n 新增键结构

```jsonc
"worktreeMgmt": {
  "addButton": "新建 worktree",          // tab 行 + 按钮 tooltip
  "addButtonAria": "新建一个 git worktree",
  "contextMenu": {
    "ariaLabel": "worktree 管理",
    "lock": "锁定…",
    "unlock": "解锁",
    "remove": "删除…"
  },
  "create": {
    "title": "新建 worktree",
    "modeCreate": "创建新分支 (-b)",
    "modeForce": "强制覆盖 (-B)",
    "modeDetach": "分离 HEAD",
    "branch": "分支名",
    "branchRequired": "请输入分支名",
    "path": "路径",
    "pathRequired": "请输入路径",
    "base": "起始点",
    "baseHint": "仅创建新分支模式生效",
    "submit": "创建",
    "cancel": "取消",
    "success": "已创建 worktree {branch}"
  },
  "remove": {
    "confirmTitle": "删除 worktree",
    "confirmMessage": "确认删除 {path} ({branch})?{dirtyHint}",
    "dirtyHint": "\\n该 worktree 有 {count} 个未提交改动,勾选「强制删除」可继续。",
    "force": "强制删除(丢弃 {count} 个未提交改动)",
    "confirm": "删除",
    "cancel": "取消",
    "success": "已删除 {path}"
  },
  "lock": {
    "dialogTitle": "锁定 worktree",
    "reason": "锁定原因(可选)",
    "reasonHint": "建议 200 字符以内",
    "submit": "锁定",
    "cancel": "取消",
    "success": "已锁定 {path}"
  },
  "unlock": {
    "confirmTitle": "解锁 worktree",
    "confirmMessage": "确认解锁 {path}?",
    "confirm": "解锁",
    "cancel": "取消",
    "success": "已解锁 {path}"
  }
},
"error": {
  "reason": {
    "invalid_branch": "分支名格式错误",
    "invalid_param": "起始点格式错误",
    "path_exists_nonempty": "目标路径已被占用",
    "cannot_create_existing": "分支已存在,请勾选强制覆盖",
    "worktree_not_found": "该 worktree 已不存在",
    "cannot_remove_main": "主 worktree 不可删除",
    "worktree_locked": "worktree 已锁定,请先解锁",
    "worktree_dirty": "worktree 有未提交改动",
    "already_locked": "该 worktree 已锁定",
    "not_locked": "该 worktree 未锁定"
  }
}
```

## 6. 复用现有代码的关键点

| 复用对象 | 用途 | 备注 |
|---------|------|------|
| `useSpcodeWorktrees.refresh()` | 写后兜底刷新（防止服务端响应与本地状态漂移） | 可选,因为响应已含 `data.worktrees` |
| `useSpcodeWorktrees.startPolling` / `stopPolling` | **不需要修改**,自动反映到新 state | 现有 watcher 已有 `topologyChanged` 检测 |
| `classifyReason` | 扩展出 4 个新 endpoint id | 新建 `parseSpcodeWorktreeManagement.ts` 而非修改 `parseSpcodeGitWorkflow.ts`（关注点分离） |
| `RESTORE_REASON_I18N_KEYS` 字典 | **不**直接复用,新建 `WORKTREE_MGMT_REASON_CODES` 字典（reason 集不同） |  |
| `snackbar: SnackbarState` | **直接复用**,写入 `(message, color, stderr)` 三元组 |  |
| `confirmDialogOpen` 模式 | **直接复用** (用于 unlock) | action 状态机扩展 |
| `onFileBrowserNavigate` | ADD 成功后导航到新 worktree 的根目录 | 复用,无需新增 |
| `spcodeStatus.status.value.umo` | mutation 请求必带 | 直接读 |
| `useSpcodeProjectStatus` | 提供 `directory / umo`,无变更 |  |
| `pluginExtensionApi.post` | 4 个端点统一调用入口 |  |

## 7. 关键 UX 细节

### 7.1 前端硬守的 disabled 规则

> 与 spcode 文档 §3.2.5 + §3.3.5 + §3.4.5 一致
> **2026-06-27 决策更新**：主 worktree 的 LOCK / UNLOCK / REMOVE 入口**全部完全隐藏**（推翻原"保留可见 + tooltip 警告"方案）

| 操作 | 主 worktree | locked | not locked | dirty |
|------|------------|--------|------------|-------|
| ADD | ✅ 可用 | n/a | n/a | n/a |
| REMOVE | ❌ 入口**完全隐藏** | ❌ disabled（tooltip "locked: <reason>"） | ✅ | ✅（force 可选） |
| LOCK | ❌ 入口**完全隐藏** | ❌ disabled | ✅ | n/a |
| UNLOCK | ❌ 入口**完全隐藏** | ❌ disabled | ✅ | n/a |

> **决策理由**：
> 1. 实战中 lock main 几乎 100% 是误操作 —— 锁定主 worktree 后用户**自己也无法在该 worktree 正常工作**（很多 git 命令会失败）
> 2. "保留可见 + warning tooltip" 的方案给用户制造了"看起来可以做"的认知陷阱
> 3. 完全隐藏比"灰色 + tooltip" 更安全：用户不会产生"我有这个权限"的错觉
> 4. 对齐产品意图：spec §3.3.2 的"git 自身允许 lock main"是**技术正确**而非**产品决策**；UI 应反映后者
> 5. 对 backend 的影响：无。前端不让用户发请求 = 后端不会拒绝 = `cannot_remove_main` 这类 reason **永远不该到达前端**（已符合 spec §4.3 的"前端硬守"原则）

### 7.2 路径自动填充

ADD dialog 打开时,默认路径 = `<projectRoot>/.worktrees/<branch-sanitized>`，其中 `branch-sanitized` 把 `/` 替换为 `-`：

```ts
function defaultPath(branch: string, projectRoot: string): string {
  const sep = projectRoot.includes('\\') ? '\\' : '/';
  return `${projectRoot}${sep}.worktrees${sep}${branch.replace(/\//g, '-')}`;
}
```

用户可在表单中改写（spec §3.1.6：默认建议但不强制）。

### 7.3 模式 radio 互斥

```ts
// ADD dialog 内部
const createMode = ref<'create' | 'force' | 'detach'>('create');
// 监听 createMode 切换：
//   - create=true 时,显示「起始点」input
//   - detach=true 时,禁用「分支名」input
//   - force=true 时,显示警告 chip "该操作会覆盖已存在分支"
```

### 7.4 成功后自动切到新 worktree

```ts
// onConfirmCreate 内
if (result.ok && result.snapshot.worktrees.length > 0) {
  const newWt = result.snapshot.worktrees.find(w => w.path === result.snapshot.worktrees[0].worktree);
  if (newWt) {
    selectedWorktree.value = newWt.isMain ? null : newWt.path;
    viewMode.value = 'files';
    fileBrowserCurrentPath.value = newWt.path;
  }
}
```

> 对齐 spcode 文档 §3.1.6 "成功后续 → 刷新 worktree 列表(直接用响应里的 `data.worktrees`,无需再调 GET);跳转至 worktree 文件浏览器"。

### 7.5 REMOVE 后回退

```ts
// onConfirmRemove 内
if (result.ok) {
  if (selectedWorktree.value === targetPath) {
    selectedWorktree.value = null; // 切回主 worktree
    fileBrowserCurrentPath.value = mainWorktreePath.value ?? projectRoot.value;
  }
}
```

## 8. 测试要点

> 实际编写时按 TDD 进行(在 `composables/` 旁新建 `tests/parseSpcodeWorktreeManagement.test.mjs` 等)

| 维度 | 覆盖点 |
|------|--------|
| Parser | 4 端点的 success envelope 解析 + 各 reason 分类 |
| Composable | add/remove/lock/unlock 状态机 + abort 路径 + umo 为 null 时的 early-return |
| UI | 主 worktree 不可见 delete 入口 / locked 时按钮 disabled / dirty 计数加载 |
| 端到端 | mock `pluginExtensionApi.post` 跑 4 流程,断言 `worktrees.value` 同步更新 |

## 9. 实施分阶段

> **阶段 0**（基础设施，先行）：
1. `parseSpcodeWorktreeManagement.ts` + 单测
2. `useSpcodeWorktrees.ts` 扩展 4 个方法 + 单测
3. i18n 三语种键补齐

> **阶段 1**（read-only 入口）：
4. `GitDiffSidebar.vue` 加 `+` 按钮 + WorktreeCreateDialog 组件

> **阶段 2**（变更类操作）：
5. 上下文菜单（lock / unlock / remove 三个 item）
6. 复用 `confirmDialogOpen` 支持 unlock action
7. REMOVE 弹窗（含 dirty 计数）

> **阶段 3**（联动与收尾）：
8. ADD 成功后自动切 worktree + 切 Files 视图
9. REMOVE 后回退到主 worktree
10. `ruff format` / `pnpm generate:api`（如有涉及）

## 10. 关键决策摘要

> **2026-06-27 用户反馈后更新**：决策 #4 / #5 / #7 都有更新

| # | 决策 | 备选 | 选择理由 |
|---|------|------|---------|
| 1 | 扩展 `useSpcodeWorktrees` | 新建独立 mutation composable | 写后必须同步 state,共享单实例零成本 |
| 2 | tab 行加 `+` + 右键菜单 | 新增第 4 个 viewMode | 符合 mental model,避免 tab 膨胀 |
| 3 | REMOVE 弹窗独立（dirty UI 复杂） | 复用 confirmDialogOpen | 与现有 stage-all / unstage-all 拆分哲学一致 |
| 4 | **UNLOCK 独立 dialog**（已更新） | 复用 confirmDialogOpen | 状态隔离更安全;与 stage-all / unstage-all 双弹窗模式对齐（详见 §11.3） |
| 5 | **ADD 成功后自动切到新 worktree + Files 视图**（已确认） | 留在 Diff 视图 | spec §3.1.6 明确建议,且新 worktree 通常没 diff;符合用户预期 |
| 6 | 不做乐观更新 | 立即本地移除 + 失败回滚 | 列表是强结构化数据,后端响应已含完整列表 |
| 7 | **主 worktree 的 LOCK / UNLOCK / REMOVE 入口全部完全隐藏**（已更新） | 保留可见 + warning tooltip | 实战中 lock main 100% 是误操作;完全隐藏避免"看起来可以做"的认知陷阱 |
| 8 | 上下文菜单内联 | 独立 `WorktreeContextMenu.vue` | < 80 行,组件碎片化代价大于复用收益 |
| 9 | dirty 计数 lazy 加载 | 列表渲染时批量预拉 | 节省不必要的网络;只在用户真的点删除时才需要 |
| 10 | reason 字典独立成文件 | 合并到 `parseSpcodeGitWorkflow.ts` | 端点集不同,关注点分离 |

## 11. 关键决策复盘（2026-06-27 用户反馈后）

### 11.1 ADD 成功后行为

**决策**：自动切到新 worktree + 切到 Files 视图

**实现**：

```ts
if (result.ok) {
  const newWt = result.snapshot.worktrees.find(
    (w) => w.path === result.snapshot.worktrees[0].worktree
  );
  if (newWt) {
    selectedWorktree.value = newWt.isMain ? null : newWt.path;
    viewMode.value = 'files';
    fileBrowserCurrentPath.value = newWt.path;
    fileBrowserPreviewPath.value = null;
  }
  createDialogOpen.value = false;
  showSnackbar(
    tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.success', { branch: data.branch }),
    'success',
  );
}
```

**联动保证**：
- `selectedWorktree` watcher 已自动重置 `fileBrowserCurrentPath`（spec §5.1）
- 现有 `topologyChanged` 检测处理 tab 切换
- `onBeforeUnmount` 内的 `composable.dispose()` abort 飞行中请求
- 30s 轮询会自然收敛（即使 ADD 失败但服务端已创建）

### 11.2 主 worktree 的 LOCK / UNLOCK 入口处理

**决策**：LOCK / UNLOCK / REMOVE 三个入口在主 worktree 上**全部完全隐藏**

**实施**（上下文菜单模板）：

```vue
<template v-if="targetWt && !targetWt.isMain">
  <v-list-item :disabled="targetWt.locked" @click="onLockToggle">
    <template #prepend><v-icon>{{ targetWt.locked ? 'mdi-lock-open-variant' : 'mdi-lock' }}</v-icon></template>
    <v-list-item-title>{{ targetWt.locked ? '解锁' : '锁定…' }}</v-list-item-title>
  </v-list-item>
  <v-list-item :disabled="targetWt.locked" @click="onRemoveClick">
    <template #prepend><v-icon color="error">mdi-trash-can-outline</v-icon></template>
    <v-list-item-title>删除…</v-list-item-title>
  </v-list-item>
</template>
<template v-else>
  <v-list-item disabled>
    <v-list-item-title class="text-caption">
      {{ tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.contextMenu.mainDisabled') }}
    </v-list-item-title>
  </v-list-item>
</template>
```

**i18n 新增键**：`worktreeMgmt.contextMenu.mainDisabled = "主 worktree 不可锁定/删除"`

**对 backend 的影响**：零。`cannot_remove_main` / `already_locked_on_main` 这类 reason **永远不该到达前端**。

### 11.3 UNLOCK 复用 confirmDialogOpen vs 独立 dialog 的影响对比

#### 方案 A：复用 confirmDialogOpen（action 状态机扩展）

```ts
const confirmDialogAction = ref<'restore' | 'unlock'>('restore');
const confirmDialogOpen = computed({
  get: () => _confirmDialogOpen.value,
  set: (v) => { _confirmDialogOpen.value = v; },
});
const _confirmDialogOpen = ref(false);
const confirmTargetPath = ref<string | null>(null);  // 共享
const confirmLoading = ref(false);  // 新增：通用 loading（替换 restoringFile）
```

**模板变化**：restore 模板块改为 `v-if="confirmDialogAction === 'restore'"`，新增 `v-else-if="confirmDialogAction === 'unlock'"` 块。

**影响矩阵**：

| 维度 | 影响 |
|------|------|
| **代码量** | +30 行（action 状态机 + 条件模板 + 新 handler），减少一个 `<v-dialog>` 块（约 -25 行）→ 净 +5 行 |
| **可读性** | 模板里 `v-if` 链增多，新读者需理解"为什么 restore 和 unlock 共用弹窗" |
| **可扩展性** | 未来加新弹窗需再次扩展 action 联合类型 + 模板判断 |
| **样式一致性** | 100% 一致（同 CSS 作用域、同一样式细节） |
| **状态泄漏风险** | **高** — `confirmDialogAction` / `confirmTargetPath` / `confirmLoading` 三个 ref 共享于 restore 和 unlock，快速点击时易出现**状态污染**（需要在 onClickRestore / onClickUnlock 都加"先关再开"逻辑） |
| **测试** | 单测需覆盖 action 切换 + 状态隔离逻辑 |
| **未来扩展成本** | 高（每次加新弹窗都需扩 action 类型） |
| **与项目现有哲学一致性** | **不一致**（项目里 stage-all / unstage-all 均为独立 dialog） |

#### 方案 B：独立 confirmUnlockOpen（推荐，对称 confirmStageAll / confirmUnstageAll）

```ts
// 保持 confirmDialogOpen / confirmTargetPath / restoringFile 专用于 restore
// 新增 3 个独立 ref
const confirmUnlockOpen = ref(false);
const confirmUnlockPath = ref<string | null>(null);
const isUnlocking = ref(false);
```

**新增独立 `<v-dialog>` 块**（紧贴 `confirmDialogOpen` 之后）：

```vue
<v-dialog v-model="confirmUnlockOpen" persistent max-width="440">
  <v-card>
    <v-card-title class="text-h6">
      {{ tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.unlock.confirmTitle') }}
    </v-card-title>
    <v-card-text>
      {{ tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.unlock.confirmMessage', { path: confirmUnlockPath ?? '' }) }}
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn variant="text" :disabled="isUnlocking" @click="onCancelUnlock">
        {{ tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.unlock.confirmCancel') }}
      </v-btn>
      <v-btn variant="flat" color="primary" :loading="isUnlocking" @click="onConfirmUnlock">
        {{ tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.unlock.confirmAction') }}
      </v-btn>
    </v-card-actions>
  </v-card>
</v-dialog>
```

**影响矩阵**：

| 维度 | 影响 |
|------|------|
| **代码量** | +50 行（独立 dialog 块 + 3 个独立 ref + 独立 handler） |
| **可读性** | **高** — 命名直接，读者无需追状态机 |
| **可扩展性** | **优** — 未来想给 unlock 加 UI（展示 locked_reason / 警告"将解除所有 lock"），只改 `confirmUnlockOpen` 这块即可 |
| **样式一致性** | 与 confirmStageAll / confirmUnstageAll 完全对齐（用户已习惯） |
| **状态泄漏风险** | **低** — 独立 ref，独立 loading，**完全无交叉污染可能** |
| **测试** | 单测更简单，无 action 切换 |
| **未来扩展成本** | 低（每个新操作独立块） |
| **与项目现有哲学一致性** | **完全一致**（`confirmStageAllOpen` / `confirmUnstageAllOpen` 也是独立双弹窗） |

#### 决策：方案 B（独立 dialog）

**3 个核心理由**：

1. **一致性 > 复用**：项目里 `confirmStageAllOpen` 和 `confirmUnstageAllOpen` **也是两个独立弹窗**（虽然它们结构相似），所以"独立 unlock dialog" 与项目现有哲学完全一致。**复用 confirmDialogOpen 反而成了特例**。

2. **状态隔离更安全**：restore（文件级 undo）和 unlock（worktree 级 lock 释放）是语义完全不同的操作，共用一个弹窗的 loading / target state 容易在快速点击时产生"上一个操作的 loading 被下一个操作覆盖"的 bug。

3. **未来扩展无成本**：如果未来 spec 升级（比如 unlock 后展示"已解锁 + 列出被锁文件"），独立 dialog 改起来零摩擦；共用 dialog 要在模板里继续加 `v-if` 链。

**接受的成本**：+20 行代码。考虑到这个项目的迭代速度（一个 spec 一个 spec 加），**这 20 行的投资回报率很高**。

---

## 12. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 右键菜单在 macOS Safari 上与系统右键冲突 | 仅在 `e.button === 2` 时打开（鼠标右键），触屏长按用 `touchstart` 兜底（v3 迭代再做） |
| ADD dialog 关闭瞬间提交中,用户切 worktree | `onBeforeUnmount` 内的 `composable.dispose()` 已 abort 任何 in-flight 请求 |
| 多个 dialog 同时打开 | 互斥:打开 A 时先关 B（与现有 confirmStageAllOpen / confirmUnstageAllOpen 模式一致） |
| 用户在 dialog 内 race-condition 改 worktree 列表 | mutation 返回后用响应 `worktrees[]` 整体替换;不在 dialog 内做"假"状态 |
| dirty 计数查询失败 | `dirtyCount.value = null` 不阻塞 UI,后端兜底,失败时再二次确认 |
| 后端在 ADD 后返回的 `worktrees[]` 不含新条目 | 罕见;30s 轮询会收敛;UI 暂时无新 tab 可见不算 bug |
| 锁定 reason 含 200+ 字符 | 前端 `maxlength=200` 限制 + helper text 提示 |

---

**作者**：elecvoid243 · **生成时间**：2026-06-27 19:30 (CST) · **修订**：2026-06-27 19:38 (CST)（采纳 3 项用户决策：ADD 自动切换、主 worktree 入口完全隐藏、UNLOCK 独立 dialog）
