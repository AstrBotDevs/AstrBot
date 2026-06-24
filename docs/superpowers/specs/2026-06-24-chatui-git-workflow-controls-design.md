# GitDiff 侧边栏 ↔ Git Workflow 控制面板

| 项目 | 内容 |
|------|------|
| 主题 | 在 dashboard 的 `GitDiffSidebar` 中集成 `spcode_toolkit` v3.7 新增的 4 个 Git 工作流端点:`git-stage` / `git-unstage` / `git-commit` / `git-log`。覆盖"暂存 → 取消暂存 → 提交 → 查看历史"最小闭环 |
| 日期 | 2026-06-24 |
| 作者 | elecvoid243 |
| 状态 | Approved (v1.2) — 待实施 |
| 修订 | v1.1 → v1.2: critical review 后修复 6 项 P0 + 10 项 P1,共 16 项(详见头部修订记录) |
| 关联代码(前端) | `dashboard/src/components/chat/GitDiffSidebar.vue`、`dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue`、`dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue` |
| 关联代码(后端) | `astrbot_plugin_spcode_toolkit` v3.7:`POST /spcode/git-stage` · `POST /spcode/git-unstage` · `POST /spcode/git-commit` · `GET /spcode/git-log` |
| 前置 spec | `docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md`(GitDiff 侧边栏 v1)<br>`docs/superpowers/specs/2026-06-18-git-worktree-switcher-design.md`(worktree 切换)<br>`docs/superpowers/specs/2026-06-20-git-diff-scope-switcher-design.md`(scope 切换)<br>`docs/superpowers/specs/2026-06-22-chatui-git-diff-file-restore-design.md`(↩ 恢复按钮 — dialog / snackbar 模式参考) |
| 配套文档 | `astrbot_plugin_spcode_toolkit/docs/webapi-git-workflow-api.md`(v3.7 后端契约) |

---

## 1. 背景与目标

### 1.1 现状

`astrbot_plugin_spcode_toolkit` v3.7 暴露了 4 个新的 Git 工作流端点:

| 端点 | 方法 | 用途 | 当前 UI 入口 |
|------|------|------|--------------|
| `/spcode/git-stage` | POST | `git add`(指定文件或全部) | ❌ 无 |
| `/spcode/git-unstage` | POST | `git reset HEAD`(指定文件或全部) | ❌ 无 |
| `/spcode/git-commit` | POST | `git commit`(严格最小,仅 `message`) | ❌ 无 |
| `/spcode/git-log` | GET | git 历史(带 ETag 缓存) | ❌ 无 |

dashboard 的 `GitDiffSidebar` 目前**只能查看** diff(`git-diff` 端点)。所有写操作(暂存 / 提交)用户必须切到 terminal 手敲命令,断开了 spcode 在 chat UI 中管理代码的心智模型。

`GitDiffFileItem.vue`(2026-06-22 restore spec)已实现单文件恢复按钮,本方案在此基础上扩展:**行内增加暂存/取消暂存按钮、底部增加 commit bar、第 3 个 viewMode 渲染 commit 历史**。

### 1.2 目标

在 `GitDiffSidebar` 顶部与底部各增加一个**控制层**,完成"暂存 → 提交 → 查看历史"的最小闭环:

1. **行内暂存/取消暂存按钮**(按 scope 自动显隐:unstaged → 暂存,staged → 取消暂存,all → 不显示)
2. **底部 commit bar**(粘性,显示 staged_count + "全部暂存" + "提交" 入口)
3. **全部暂存确认弹窗**(`<v-dialog persistent>`,与 restore 同构,防止误操作大量文件)
4. **提交弹窗**(`<v-dialog>` + message textarea + staged 文件预览 + stderr 错误展示)
5. **第 3 个 viewMode: History**(调用 `git-log` + ETag + 过滤栏 + 分页)

### 1.3 非目标(显式不做)

- ❌ **不**做客户端预检(以服务端为准,失败 reason 直接走 toast)
- ❌ **不**做批量提交 / squash / amend / rebase / cherry-pick(后端 v1 不支持)
- ❌ **不**做交互式 rebase / 冲突解决 / 文件树 staging(超出 v1 范围)
- ❌ **不**做 commit message 模板自动填充(用户输入,仅提供 placeholder 提示)
- ❌ **不**做点击 commit 查看其 diff(后端 v1 不支持按 ref/parent 取 diff)
- ❌ **不**修改 spcode 端点契约,只消费
- ❌ **不**改 `useSpcodeGitDiff` 现有 10s 轮询节奏(写操作后追加一次手动 refresh,沿用 restore 模式)
- ❌ **不**持久化 commit message 草稿(不写 localStorage)
- ❌ **不**在 all scope 下显示行内 stage/unstage 按钮(后端 git-diff 未提供 `is_staged` 字段,本方案不破坏契约)

---

## 2. 设计决策(已与用户确认)

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 写端点 composable 拆分 | **3 个独立 composable**(stage / unstage / commit) | 与 `useSpcodeFileRestore` 模式 1:1 对齐;每个端点 reason 集合不完全重叠(commit 多出 `hook_rejected` / `identity_not_set` / `nothing_to_commit` / `invalid_message`),单独精化错误处理 |
| 2 | stage/unstage 是否合并 | **保持独立** | endpoint 路径不同、响应体相同但字段名(`staged` vs `unstaged`)不同,合并会引入条件分支,反而复杂 |
| 3 | 4 个端点共享解析器 | **新增 `parseSpcodeGitWorkflow.ts`**(纯函数模块) | 4 端点共享大量 envelope 字段(`umo`、`worktree`、`directory`、`elapsed_ms`、`reason`、`stderr`、`files`、`staged_count`);独立模块可被 `node --test` 单测;遵循既有 `parseSpcodeFileRestore.ts` + `useSpcodeFileRestore.ts` 同构拆分 |
| 4 | log 端点状态机 | **复用 `useSpcodeGitDiff` 的 idle/loading/ok/error 模式** | 一致的状态机 = 一致的模板;`GitLogView` 沿用 `GitDiffBodyContent` 的三段式(loading / error / ok) |
| 5 | ETag 实现位置 | **`useSpcodeGitLog` 内部维护 `Map<key, etag>`** | 1.5s TTL 太短,无业务必要做跨组件共享;Map 维度 = `umo + worktree + ref + path + author + since + until + n` |
| 6 | stage/unstage 按钮显隐规则 | **scope 决定**:unstaged → 显示 `↑`,staged → 显示 `↓`,all → **不显示** | all scope 的 `files_changed` 没有 `is_staged` 标志,加此字段需后端改契约(本方案不破坏);all scope 下让用户通过切到 staged 视图来 unstage,反之亦然 |
| 7 | commit 入口位置 | **粘性 commit bar** 在 `git-diff-sidebar-body` 底部 | 始终可见,与 staged_count 联动;mobile 上天然贴底 |
| 8 | commit 确认方式 | **`<v-dialog>` + textarea + staged 文件预览** + (失败时) stderr 预览 | 简单 `window.prompt` 不可控样式;与 restore 内联 dialog 一致 |
| 9 | commit 失败时 staged 是否清空 | **不清空**(后端既定) | API 文档 §7.2:commit 失败时 `data.files` 是失败前已暂存列表,UI 用响应 `files` 覆盖即可,自然不丢 |
| 10 | History viewMode 实现 | **3 个 tab:Files / Diff / History**(扩展现有 2-tab) | Files 与 Diff 已存在;History 是只读查看,与 Diff 写操作有不同心智模型,独立 tab 清晰 |
| 11 | 写端点失败 reason 展示 | **snackbar + `data.stderr` 渲染为 `<pre>`** | 简单情况(pre-commit 错误)需看原始输出;API 文档 §7.8 建议 |
| 12 | 行内 stage 按钮防双击 | **`isStaging: Set<string>` / `isUnstaging: Set<string>`**(单文件级,不是单 sidebar 级) | 行级 spinner 状态可读性高;同时多文件操作不互相阻塞 |
| 13 | i18n 命名空间 | **`spcodeProjectLoad.diffSidebar.gitWorkflow.*`** | 与既有 `restore.*` 同级;zh-CN/en-US/ru-RU 三语同步 |
| 14 | 暂存响应后是否自动刷 diff | **是**,沿用 restore 模式 | UI 立即收敛;乐观语义:用响应 `files` 覆盖 `stagedFiles` ref,再调 `useSpcodeGitDiff.refresh()` 拉最新 |
| 15 | commit 后是否自动刷 log | **仅当 `viewMode === 'history'` 时** | 避免在 diff 视图默默刷一个用户没看的面板;轮询已 10s 自然收敛 |
| 16 | "全部暂存" 按钮 | commit bar 右侧,unstaged_count>0 时显示;**点击弹出二次确认对话框** | 防止误操作大量文件;参照 restore 的内联 dialog 模式;调用 `git-stage { all: true }` |
| 17 | 提交对话框宽度 | `max-width="560"`(比 restore 的 440 宽) | 容纳 message textarea + 文件列表两栏布局 |
| 18 | 暂存/取消暂存按钮图标 | `mdi-arrow-up-bold-circle-outline`(暂存)/ `mdi-arrow-down-bold-circle-outline`(取消暂存) | 语义直观;Material Design Icons 通用 |
| 19 | history commit 列表项设计 | **紧凑型**:单行(SHA-7 + subject + author + 相对时间 + +N/−M),点击展开详情 | 与 GitHub commit list 视觉对齐;减少空间占用 |
| 20 | "全部暂存"确认对话框颜色 | `color="primary"`(非 warning) | 可逆操作(随时可取消暂存),不需要 warning 警示色;与 restore 不可逆的 `color="warning"` 区分 |
| 21 | 暂存/取消暂存响应后是否更新 `stagedFiles` | **是**,用响应 `files` 覆盖(乐观语义) | 与 API 文档 §7.1 一致;避免本地与服务端漂移 |
| 22 | 切 worktree 时 `stagedFiles` 行为 | **保留**(不重置) | 用户的暂存是项目级而非 session 级;不同 worktree 可能共享同一仓库根 |
| 23 | 切 project / 卸载项目时 `stagedFiles` 行为 | **清空** | 新项目与旧项目无任何共享状态语义 |
| 24 | 切 worktree 时 ETag 行为 | `useSpcodeGitLog` 内部 `etagMap.clear()` | API 文档 §7.5:切换 worktree 时 UI **必须**重新请求,不可复用上一个 worktree 的 ETag |
| 25 | log 端点 304 处理 | 304 时复用上次响应 snapshot,UI **不展示** loading | `axios` 默认不会自动 304 短路;需 composable 显式检查 `response.status === 304` 并返回上一次 snapshot |

---

## 3. 数据流与状态

### 3.1 现有数据流(节选)

```
GitDiffSidebar (持有 useSpcodeGitDiff / useSpcodeFileRestore / useSpcodeWorktrees / useSpcodeProjectStatus)
  ├─ selectedWorktree: ref<string|null>
  ├─ selectedScope: ref<GitDiffScope>
  ├─ viewMode: ref<"files" | "diff">
  ├─ snackbar / confirmDialog (restore 用)
  └─ onManualRefresh / onFileRestore / onScopeChange / onWorktreeChange
        ↓
GitDiffBodyContent (state: GitDiffFetchState, expanded: Set<string>, onRestore callback)
  └─ GitDiffFileItem[] (file: SpcodeGitDiffFile, expanded, isRestoring, onRestore)
        ├─ 状态图标 + 文件路径 + 添加/删除统计
        ├─ ↩ 恢复按钮 (existing)
        └─ ⌄ 展开箭头
```

### 3.2 改造后数据流

```
GitDiffSidebar (顶层 orchestrator — 扩展)
  ├─ useSpcodeGitDiff         (existing) → state / refresh / polling
  ├─ useSpcodeFileRestore     (existing) → restore()
  ├─ useSpcodeGitStage        [NEW]     → stage() + isStaging: Set<string>
  ├─ useSpcodeGitUnstage      [NEW]     → unstage() + isUnstaging: Set<string>
  ├─ useSpcodeGitCommit       [NEW]     → commit() + isCommitting
  ├─ useSpcodeGitLog          [NEW]     → state / refresh / loadMore / polling + 内部 ETag Map
  ├─ useSpcodeProjectStatus   (existing)
  ├─ useSpcodeWorktrees       (existing)
  ├─ selectedWorktree         (existing) → 取 worktree
  ├─ selectedScope            (existing) → 取 scope
  ├─ viewMode                 (extended) → "files" | "diff" | "history"
  ├─ stagedFiles              [NEW]     → ref<Set<string>> 缓存当前 staged 列表
  ├─ commitDialogOpen         [NEW]     → ref<boolean>
  ├─ confirmStageAllOpen      [NEW]     → ref<boolean>  全部暂存确认弹窗
  ├─ pendingStageAllCount     [NEW]     → ref<number>   确认前预知未暂存数量
  ├─ snackbar                 (existing, reason 集合扩展)
  └─ git-diff-sidebar-footer  [NEW]     → <GitCommitBar /> 粘性底部
        ├─ stagedFiles.size 派生
        ├─ "全部暂存" 按钮(unstaged_count > 0 时)
        └─ "提交" 按钮(stagedFiles.size > 0 时)

GitDiffFileItem (行级 — 扩展)
  ├─ showStage?: boolean      [NEW]   ← 父级派生(已计算好,本组件不感知 scope)
  ├─ showUnstage?: boolean    [NEW]   ← 同上
  ├─ onStage?: (path: string) => void  [NEW]
  ├─ onUnstage?: (path: string) => void  [NEW]
  ├─ isStaging?: boolean      [NEW]   ← 当前行是否在转圈(由父级派生)
  ├─ isUnstaging?: boolean    [NEW]   ← 同上
  └─ 按钮显隐:
       ├─ showStage=true   → ↑ 暂存按钮
       ├─ showUnstage=true → ↓ 取消暂存按钮
       └─ 两者都 false      → 不显示
       (scope='all' 时 showStage=showUnstage=false,与决策 #6 一致)

GitCommitDialog  [NEW]
  ├─ modelValue: boolean (v-model:open)         ← 双向绑定
  ├─ stagedFiles: string[]
  ├─ isCommitting: boolean
  ├─ lastError?: { reason: string; stderr: string }  (失败时显示 stderr 块)
  ├─ message: ref<string>                       ← 内部状态,emit('confirm', { message })
  └─ emit('update:modelValue', v) / emit('confirm', { message }) / emit('cancel')

GitLogView  [NEW]  完整接口:
  ```ts
  // Props
  defineProps<{
    state: LogFetchState;       // useSpcodeGitLog 暴露的 state
    hasMore: boolean;           // state.snapshot.hasMore 派生
    isLoading: boolean;         // state.kind === 'loading' || pending
  }>();
  // Emits
  defineEmits<{
    (e: 'apply', filter: LogFilter): void;   // 过滤栏"应用"按钮
    (e: 'loadMore'): void;                  // 分页"加载更多"按钮
  }>();
  // 内部状态
  const filter = ref<LogFilter>({ ref: 'HEAD', n: 20 });
  // 派生
  const commits = computed(() => {
    if (props.state.kind !== 'ok' && props.state.kind !== 'error') return [];
    return props.state.snapshot.commits;
  });
  const isEmptyRepository = computed(() =>
    props.state.kind === 'error' && props.state.reason === 'empty_repository'
  );
  // 模板分支(按优先级):
  //   1. isEmptyRepository → 空仓库插画(用 history.emptyRepository 文案)
  //   2. commits.length === 0 → "暂无提交记录"(用 history.empty 文案)
  //   3. 渲染 commit 列表
  ```
  GitLogView 内部不直接调 useSpcodeGitLog.refresh()(只 emit),refresh 由父级
  GitDiffSidebar 持有 composable 实例,响应 emit('apply') 与 emit('loadMore')。

GitCommitBar  [NEW]  (粘性底部)
  ├─ stagedCount: number      ← stagedFiles.size 派生
  ├─ unstagedCount: number    ← 派生自 snapshot.files.length - stagedFiles.size(见 §6.7.1)
  ├─ isStagingAll: boolean    ← composable 暴露的单值 flag
  ├─ onStageAll: () => void   ← 点击触发 confirmStageAllOpen
  └─ onCommit: () => void     ← 点击触发 commitDialogOpen
```

**`isStaging` 派生链(P1-4 修复)**:

```
useSpcodeGitStage.composable 内部:
  isStaging: Set<string>  (源,非响应式 Set)

GitDiffSidebar 派生:
  isStagingForPath = (path: string) => gitStage.isStaging.value.has(path)
  // 用 computed 包装以便响应式
  const isStagingForPath = (path: string) => gitStage.isStaging.value.has(path);

GitDiffBodyContent 透传:
  :is-staging="isStagingForPath(f.path)"
  :is-unstaging="gitUnstage.isStaging.value.has(f.path)"

GitDiffFileItem 接收 boolean:
  isStaging: boolean  // 当前行是否在转圈
```

### 3.3 状态机

> 约定:每个状态转换都**显式标注** `stagedFiles` / `commitDialogOpen` / `confirmStageAllOpen` 等关键状态的变化(P1-2 修复)。

#### 3.3.1 行内 stage 按钮

```
IDLE ──click──> STAGING
   ├─ isStaging.add(path)         // 行级 spinner 启动
   └─ isStagingForPath(path) = true

STAGING ──success──> IDLE
   ├─ isStaging.delete(path)
   ├─ stagedFiles = new Set(result.snapshot.files)   // 乐观语义
   ├─ isStagingForPath(path) = false
   ├─ await useSpcodeGitDiff.refresh()              // 立即刷 diff
   └─ snackbar: stage.success({path}), color=success

STAGING ──failure──> IDLE
   ├─ isStaging.delete(path)
   ├─ stagedFiles 不变(失败未触动)
   ├─ isStagingForPath(path) = false
   └─ snackbar: stage.error.reason.{reason},
         color=meta.color, stderr=meta.withStderr ? result.stderr : undefined

STAGING ──aborted──> IDLE(切 worktree / 卸载项目 / 组件卸载)
   ├─ isStaging.delete(path)                        // composable 内部清理
   └─ (无 UI 反馈;原因:中止非用户主动操作)
```

#### 3.3.2 行内 unstage 按钮(对称)

```
IDLE ──click──> UNSTAGING
   ├─ isUnstaging.add(path)
   └─ isUnstagingForPath(path) = true

UNSTAGING ──success──> IDLE
   ├─ isUnstaging.delete(path)
   ├─ stagedFiles = new Set(result.snapshot.files)   // 乐观语义(可能变小)
   ├─ isUnstagingForPath(path) = false
   ├─ await useSpcodeGitDiff.refresh()
   └─ snackbar: unstage.success({path}), color=success

UNSTAGING ──failure──> IDLE
   ├─ isUnstaging.delete(path)
   ├─ stagedFiles 不变
   └─ snackbar: unstage.error.reason.{reason}, color=meta.color

UNSTAGING ──aborted──> IDLE
```

#### 3.3.3 commit bar — "全部暂存" 按钮(Q4 加确认 + P1-3 修复)

```
IDLE ──click──> CONFIRMING                              // P1-3:进入时同步计算
   ├─ pendingStageAllCount = unstagedCount.value         // 派生自 snapshot.files.length - stagedFiles.size
   └─ confirmStageAllOpen = true                        // dialog 打开

CONFIRMING ──cancel──> IDLE
   ├─ confirmStageAllOpen = false
   └─ pendingStageAllCount 不变(不重置,无副作用)

CONFIRMING ──confirm──> STAGING_ALL
   ├─ confirmStageAllOpen = false                       // dialog 关闭
   └─ isStagingAll = true                               // composable 暴露的 flag

STAGING_ALL ──success──> IDLE
   ├─ isStagingAll = false
   ├─ stagedFiles = new Set(result.snapshot.files)      // 乐观语义
   ├─ await useSpcodeGitDiff.refresh()
   └─ snackbar: stage.successAll({count}), color=success

STAGING_ALL ──failure──> IDLE
   ├─ isStagingAll = false
   ├─ stagedFiles 不变
   └─ snackbar: stage.error.reason.{reason}, color=meta.color

STAGING_ALL ──aborted──> IDLE
```

#### 3.3.4 commit bar — "提交" 按钮

```
IDLE ──click──> DIALOG_OPEN
   ├─ message = ""                                       // 重置
   ├─ lastError = undefined                              // 清空上次的 stderr
   └─ commitDialogOpen = true

DIALOG_OPEN ──cancel──> IDLE
   └─ commitDialogOpen = false(emit('update:modelValue', false))

DIALOG_OPEN ──confirm(message)──> COMMITTING             // message.trim().length > 0 && length ≤ 8192
   ├─ isCommitting = true
   └─ lastError = undefined(进入提交前清空)

COMMITTING ──success──> IDLE
   ├─ isCommitting = false
   ├─ commitDialogOpen = false
   ├─ stagedFiles = new Set(result.snapshot.files)      // 通常为空数组(提交后 staged 清零)
   ├─ lastError = undefined
   ├─ await useSpcodeGitDiff.refresh()
   ├─ if (viewMode === 'history') await useSpcodeGitLog.refresh()
   └─ snackbar: commit.success({sha: result.snapshot.sha.slice(0,7)}), color=success

COMMITTING ──failure──> DIALOG_OPEN_KEEP_ERROR           // 与 DIALOG_OPEN 同 visual state,语义子集
   ├─ isCommitting = false
   ├─ commitDialogOpen = true(保持打开,允许修改重试)
   ├─ lastError = { reason, stderr }                    // 模板里显示 stderr 块
   ├─ stagedFiles 不变(响应 files === 失败前 files,后端既定)
   └─ snackbar: commit.error.reason.{reason}, color=meta.color,
         stderr=meta.withStderr ? result.stderr : undefined

COMMITTING ──aborted──> IDLE
   ├─ isCommitting = false
   └─ commitDialogOpen = false                          // 中止即关闭
```

#### 3.3.5 `useSpcodeGitLog.state`

完整类型定义(置于 `parseSpcodeGitWorkflow.ts`):

```ts
export type LogFetchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; snapshot: LogSnapshot; notModified?: boolean }
  | { kind: "error"; reason: string; previousSnapshot?: LogSnapshot };
```

状态机:

```
idle ──refresh()──> loading
loading ──200 ok─────> ok { snapshot, notModified: false }
loading ──304────────> ok { snapshot, notModified: true }    // snapshot 来自 prevSnapshot(上一次成功响应)
loading ──error──────> error { reason, previousSnapshot? }
error 持有 previousSnapshot(沿用 useSpcodeGitDiff)
notModified 持有旧 snapshot,UI 不显示 loading(避免闪烁)
```

**`notModified: true` 时 `snapshot` 的来源**:composable 内部维护 `let prevSnapshot: LogSnapshot | null = null;` —— 每次成功 200 时更新 `prevSnapshot = snapshot`;304 时复用 `prevSnapshot` 作为本次 `ok` 状态的 `snapshot` 字段。这样 UI 端通过 `state.snapshot` 访问**永远是当前可见的最新数据**。

### 3.4 关键不变量

- `stagedFiles` ref 在 stage/unstage/commit 后**用响应 `files` 字段覆盖**(乐观语义,API 文档 §7.1)
- commit 失败时 `stagedFiles` 不变(后端返回的 `files` 与失败前一致)
- 切 worktree 时 `stagedFiles` **不变**(决策 #22)
- 切 project / 卸载项目时 `stagedFiles` **清空**(决策 #23)
- ETag Map 在切 worktree / 切 umo 时**全部清空**(决策 #24)
- ETag 1.5s TTL 在前端不主动检查,只在下一次请求时携带 `If-None-Match` + 接收新 `ETag`
- 行内 stage/unstage 按钮在 `scope === 'all'` 时**不渲染**(决策 #6)

---

## 4. URL 契约(消费既有后端)

> 跨引用:URL 路径由 `dashboard/src/api/v1.ts:1299-1316` 的 `pluginExtensionApi.{get,post}(...)` 生成,后端注册于 `astrbot_plugin_spcode_toolkit/main.py`。

### 4.1 共享响应 Envelope

```ts
// 4 个端点共用的响应外壳
interface Envelope<T> {
  status: "ok";           // 框架层标识
  data: T;                // 业务字段(success, reason, stderr, ...)
}

// 注意:HTTP 总是 200;业务失败通过 data.success === false 表达
```

### 4.2 写端点契约

#### 4.2.1 `POST /spcode/git-stage` / `git-unstage`

```ts
// Request body(files 与 all 互斥)
interface StageRequest {
  umo?: string;
  worktree?: string;
  files?: string[];   // 长度 1-100
  all?: boolean;      // 仅 all=true 有效
}

// Response data
interface StageData {
  success: boolean;
  reason: string | null;
  stderr: string;
  elapsed_ms: number;
  umo: string;
  worktree: string;
  directory: string;
  staged: boolean;        // git-stage 专属
  unstaged: boolean;      // git-unstage 专属
  files: string[];        // 调用后**当前** staged 列表
  staged_count: number;
}
```

#### 4.2.2 `POST /spcode/git-commit`

```ts
// Request body
interface CommitRequest {
  umo?: string;
  worktree?: string;
  message: string;       // 1 ≤ length ≤ 8192
}

// Response data
interface CommitData {
  success: boolean;
  reason: string | null;
  stderr: string;
  elapsed_ms: number;
  umo: string;
  worktree: string;
  directory: string;
  committed: boolean;
  sha: string;            // 40 字符完整 SHA
  files: string[];        // 本次提交的文件
  committed_count: number;
  staged_count: number;   // 提交后应为 0;失败时仍保留
}
```

#### 4.2.3 失败分类(后端按 stderr 关键字符串映射)

| 4 类专属 reason | 触发关键词(任一) |
|------------------|------------------|
| `nothing_to_commit` | `nothing to commit` / `no changes added to commit` |
| `identity_not_set` | `please tell me who you are` / `author identity unknown` / `empty ident` |
| `hook_rejected` | `pre-commit hook` / `commit-msg hook` / `hook declined` / `rejected by hook` |
| `git_error` | 其他 |

### 4.3 读端点契约

#### 4.3.1 `GET /spcode/git-log`

```ts
// Query 参数
interface LogQuery {
  umo?: string;          // 默认最近加载项目
  worktree?: string;     // 默认 primary
  n?: number;            // 默认 20, 1 ≤ n ≤ 200
  ref?: string;          // 默认 HEAD
  path?: string;         // 路径过滤
  author?: string;       // 作者模糊匹配
  since?: string;        // ISO date
  until?: string;        // ISO date
}

// Response data
interface LogData {
  success: boolean;
  reason: string | null;
  loaded: boolean;
  elapsed_ms: number;
  umo: string;
  worktree: string;
  directory: string;
  ref: string;
  count: number;
  has_more: boolean;
  truncated: boolean;
  max_bytes: number;
  commits: Array<{
    sha: string;
    sha_short: string;
    author: { name: string; email: string };
    committer: { name: string; email: string };
    date: string;            // ISO 8601
    subject: string;
    body: string | null;
    parents: string[];
    shortstat: { files: number; additions: number; deletions: number };
  }>;
}
```

#### 4.3.2 ETag 协议

```
响应头:
  ETag: W/"<head_sha>-<worktree_mtime>-<index_mtime>"
  Cache-Control: private, max-age=1.5

请求头(复用):
  If-None-Match: W/"<etag>"

响应 304: 复用上次响应(前端不更新 ETag)
```

#### 4.3.3 304 错误原因

| reason | 触发 |
|--------|------|
| `invalid_param` | `n=abc` / `since=not-a-date` |
| `path_unsafe` | `path=../etc/passwd` |
| `worktree_invalid` | `worktree=C:/other/repo` |
| `empty_repository` | 仓库尚未首次 commit |
| `not_a_git_repo` / `git_unavailable` | 仓库探测失败 |

### 4.4 前端组装策略

| 端点 | umo | worktree |
|------|-----|----------|
| git-stage / git-unstage / git-commit | `spcodeStatus.status.value.umo` | `selectedWorktree.value`(为 null 时不传) |
| git-log | 同上 | 同上 |

| 场景 | 行为 |
|------|------|
| `umo` 为空 | 后端 fallback 到最近加载项目;UI 应尽量显式传 |
| `worktree` 为空 | 后端 fallback 到 primary;UI 应尽量显式传 |
| 项目未加载 | 写端点 → toast `no_project_loaded`;按钮 disabled(见 §6.2) |

---

## 5. 错误处理矩阵

### 5.1 共享 Reason 分类字典

`parseSpcodeGitWorkflow.ts` 暴露 `GIT_WORKFLOW_REASON_CODES` 常量,4 端点共享。`empty_repository` 是 git-log 的空状态 reason,**不在错误字典中**(详见 P0-3 注,GitLogView 单独处理)。

```ts
// 字典结构(完整 i18n key 见 §7)
export interface ReasonMeta {
  i18nKey: string;
  color: "error" | "warning";
  /** True 表示失败时 data.stderr 携带 git 原始输出,snackbar 模板里
   *  渲染 <pre>{{ stderr }}</pre>。当前字典里只有 git_error 与 hook_rejected
   *  携带 stderr(API 文档 §7.8)。 */
  withStderr?: boolean;
  /** True 表示 fallback reason 需要展示字面值(用于"未知 reason"兜底)。 */
  withReason?: boolean;
}

export const GIT_WORKFLOW_REASON_CODES: Record<string, ReasonMeta> = {
  // 前置类
  feature_disabled:    { i18nKey: "error.reason.feature_disabled", color: "error" },
  no_project_loaded:   { i18nKey: "error.reason.no_project_loaded", color: "error" },
  worktree_invalid:    { i18nKey: "error.reason.worktree_invalid", color: "error" },
  directory_missing:   { i18nKey: "error.reason.directory_missing", color: "error" },
  not_a_git_repo:      { i18nKey: "error.reason.not_a_git_repo", color: "error" },
  git_unavailable:     { i18nKey: "error.reason.git_unavailable", color: "error" },
  git_error:           { i18nKey: "error.reason.git_error", color: "error", withStderr: true },
  // Body 类
  invalid_body:        { i18nKey: "error.reason.invalid_body", color: "error" },
  invalid_files:       { i18nKey: "error.reason.invalid_files", color: "error" },
  invalid_all:         { i18nKey: "error.reason.invalid_all", color: "error" },
  invalid_message:     { i18nKey: "error.reason.invalid_message", color: "error" },
  invalid_param:       { i18nKey: "error.reason.invalid_param", color: "error" },
  // 路径类
  path_unsafe:         { i18nKey: "error.reason.path_unsafe", color: "error" },
  // 业务类
  nothing_to_commit:   { i18nKey: "error.reason.nothing_to_commit", color: "warning" },
  hook_rejected:       { i18nKey: "error.reason.hook_rejected", color: "warning", withStderr: true },
  identity_not_set:    { i18nKey: "error.reason.identity_not_set", color: "warning" },
  // 前端
  network:             { i18nKey: "error.reason.network", color: "error" },
  unknown:             { i18nKey: "error.reason.unknown", color: "error", withReason: true },
};

/** classifyReason: 把后端 reason 字符串映射到 ReasonMeta,未知/不允许的 reason
 *  一律降级为 unknown(避免 i18n key 字面值回退)。
 *
 *  返回类型:**ReasonMeta** 而非 string(与 §9.2 单测断言一致;P1-10 修复)。 */
export function classifyReason(
  reason: string | null | undefined,
  endpoint: GitWorkflowEndpoint,
): ReasonMeta {
  if (reason === null || reason === undefined) return GIT_WORKFLOW_REASON_CODES.unknown;
  if (reason === "network") return GIT_WORKFLOW_REASON_CODES.network;  // 客户端拦截的伪 reason
  if (!(ALLOWED_REASONS[endpoint] as readonly string[]).includes(reason)) {
    return GIT_WORKFLOW_REASON_CODES.unknown;
  }
  return GIT_WORKFLOW_REASON_CODES[reason] ?? GIT_WORKFLOW_REASON_CODES.unknown;
}
```

### 5.2 端点专属 reason 集合

每个 composable 单独导入允许的 reason 子集,未知 reason 降级为 `unknown`:

| 端点 | 允许的 reason 集合 |
|------|---------------------|
| git-stage | feature_disabled, no_project_loaded, worktree_invalid, directory_missing, not_a_git_repo, git_unavailable, invalid_body, invalid_files, invalid_all, path_unsafe, git_error, network |
| git-unstage | (同 git-stage) |
| git-commit | feature_disabled, no_project_loaded, worktree_invalid, directory_missing, not_a_git_repo, git_unavailable, invalid_body, invalid_message, nothing_to_commit, hook_rejected, identity_not_set, git_error, network |
| git-log(错误) | feature_disabled, no_project_loaded, worktree_invalid, directory_missing, not_a_git_repo, git_unavailable, invalid_param, path_unsafe, git_error, network |
| git-log(空状态) | `empty_repository` —— **不算 error**,GitLogView 模板单独分支渲染空仓库插画(API 文档 §4:success=false, reason=empty_repository, commits=[]) |

**实现细节**:`classifyReason('empty_repository', 'log')` 返回 `unknown` ReasonMeta(因为它不在错误集合中),`useSpcodeGitLog` 不调用 `classifyReason`,而是在状态机里直接检测 `state.kind === 'error' && state.reason === 'empty_repository'` 走空状态分支。这避免了"误把空仓库当错误弹 toast"的语义错误。

### 5.3 错误处理(以行内 stage 失败为例)

`SnackbarState` 扩展(P0-2 修复 —— stderr 单独字段,**不再**拼到 message 字符串里):

```ts
interface SnackbarState {
  show: boolean;
  message: string;
  color: "success" | "warning" | "error";
  /** git 原始输出(仅 withStderr reason 携带,模板里 <pre v-if="stderr"> 渲染)。 */
  stderr?: string;
}
```

`onStageFile` 完整实现:

```ts
async function onStageFile(path: string): Promise<void> {
  if (isStagingForPath(path)) return;       // 防双击
  isStaging.add(path);                       // composable 内部 Set
  forceUpdateIsStaging();                    // 触发响应式

  const umo = spcodeStatus.status.value.umo;
  const worktree = selectedWorktree.value;
  const result = await gitStage.stage({ files: [path], worktree, umo });

  isStaging.delete(path);
  forceUpdateIsStaging();

  if (!result.ok && result.reason === "aborted") return;
  if (result.ok) {
    // 乐观语义:用响应 files 覆盖本地 stagedFiles
    stagedFiles.value = new Set(result.snapshot.files);
    await gitDiff.refresh();                    // 立即刷 diff
    snackbar.value = {
      show: true,
      message: tm("gitWorkflow.stage.success", { path }),
      color: "success",
    };
  } else {
    // classifyReason 返回 ReasonMeta(见 P1-10);携带 stderr 的 reason
    // (git_error / hook_rejected)把 result.stderr 单独放到 snackbar.stderr,
    // 模板里 <pre v-if="snackbar.stderr"> 渲染;不污染 message 字符串。
    const meta = classifyReason(result.reason, "stage");
    const message = meta.withReason
      ? tm(meta.i18nKey, { reason: result.reason ?? "unknown" })
      : tm(meta.i18nKey);
    snackbar.value = {
      show: true,
      message,
      color: meta.color,
      stderr: meta.withStderr && result.stderr ? result.stderr : undefined,
    };
  }
}
```

### 5.4 错误展示规则

| color | 适用场景 | timeout |
|-------|---------|---------|
| `success` | 成功(暂存/取消暂存/全部暂存/提交) | 4000ms |
| `warning` | 业务失败(nothing_to_commit, hook_rejected, identity_not_set, empty_repository, ...) | 6000ms |
| `error` | 系统/网络/参数失败 | 6000ms |

`withStderr: true` 的 reason 在 snackbar 内部追加 `<pre class="spcode-stderr">{{ stderr }}</pre>`(API 文档 §7.8 建议)。

---

## 6. UI / UX 细节

### 6.1 整体布局(改造后)

```
┌─ GitDiffSidebar ─────────────────────────────────────┐
│  [Files] [Diff] [History]                ↻ ✕ │  ← 新增 History tab
│                                                       │
│  [Worktrees: main | feat-foo | feat-bar]              │  ← 已有
│                                                       │
│  [Unstaged] [Staged] [All]                            │  ← 仅 diff 视图
│                                                       │
│  ⚠ diff truncated (... ...)                          │  ← 已有
│                                                       │
│  ┌─ git-diff-sidebar-body ──────────────────────────┐ │
│  │  ● src/main.py                  +12 −3   ↓ ↩ ⌄ │ │  ← row
│  │  ● tests/test_foo.py             +5  −1   ↓ ↩ ⌄ │ │   (unstaged scope:显示 ↑ 暂存)
│  │  ● README.md                    +20 −10  ↑ ↩ ⌄ │ │   (staged scope  :显示 ↓ 取消)
│  │                                              ↑  │ │   (all scope     :不显示 ↑↓)
│  │  (History 视图时此处为 GitLogView)              │ │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│  ┌─ commit-bar (sticky) ─────────────────────────┐   │  ← 新增
│  │  ⓘ 已暂存 3 个文件      [全部暂存]   [提交 →] │   │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│  [Confirm Dialog 内部]  ← restore / stageAll 共用模式 │
│  [Commit Dialog 内部]                                │
│  [Snackbar 内部]        ← reason → i18n 映射         │
└──────────────────────────────────────────────────────┘
```

### 6.2 行内 stage/unstage 按钮(§6.1 中 ↑ / ↓ 位置)

#### 6.2.1 位置

位于 `GitDiffFileItem.vue` 现有结构中,在 `<span class="git-diff-file-stats">` 与 `<button class="git-diff-file-restore">` 之间。

#### 6.2.2 视觉

- Vuetify `v-btn` icon,`size="x-small"`,`density="comfortable"`,`variant="text"`
- 暂存按钮:`color="secondary"`(蓝色调),图标 `mdi-arrow-up-bold-circle-outline`
- 取消暂存按钮:`color="warning"`(橙色调),图标 `mdi-arrow-down-bold-circle-outline`
- 默认可见性:`opacity: 0.5`,hover 行时 `opacity: 1`(与 restore 按钮一致)
- 加载态:`v-progress-circular size=14` 替换图标,`aria-busy="true"`
- 焦点环:Vuetify 默认;不可用时 `disabled` + `opacity: 0.3`

#### 6.2.3 显隐条件(`GitDiffBodyContent` 派生,传给子组件)

子组件不感知 scope(scope 在父级已转换成布尔 props):

```ts
// 在 GitDiffBodyContent 中:
const showStageButton = computed(() => {
  // 1. 项目必须已加载
  if (!spcodeStatus.status.value.loaded) return false;
  // 2. umo 必须存在
  if (!spcodeStatus.status.value.umo) return false;
  // 3. scope 必须是 unstaged
  return selectedScope.value === "unstaged";
});

const showUnstageButton = computed(() => {
  if (!spcodeStatus.status.value.loaded) return false;
  if (!spcodeStatus.status.value.umo) return false;
  return selectedScope.value === "staged";
});
```

> 注:`loaded` / `umo` 是**前置**而非预检 — 后端会直接 `no_project_loaded`,前端拦下可省一次请求。

#### 6.2.4 props / events 扩展(`GitDiffFileItem.vue`)(P1-1 修复)

```ts
defineProps<{
  file: SpcodeGitDiffFile;
  expanded: boolean;
  isDark: boolean;
  // existing
  onRestore?: (path: string) => void;
  isRestoring?: boolean;
  // NEW(P1-1 修复:子组件不感知 scope,接布尔 props)
  showStage?: boolean;       // 父级根据 selectedScope 派生
  showUnstage?: boolean;     // 同上
  onStage?: (path: string) => void;
  onUnstage?: (path: string) => void;
  isStaging?: boolean;       // 当前行是否在转圈
  isUnstaging?: boolean;     // 同上
}>();

defineEmits<{
  (e: 'toggle'): void;
  (e: 'restore', path: string): void;
  // NEW
  (e: 'stage', path: string): void;
  (e: 'unstage', path: string): void;
}>();
```

> **P1-1 修复说明**:`GitDiffFileItem` 不直接 import `selectedScope`(避免与父组件耦合)。父级 `GitDiffBodyContent` 算出 `showStage` / `showUnstage` 布尔后透传,子组件零耦合。若后续 scope 列表扩展(如加 "modified"),只需改 `GitDiffBodyContent` 的派生逻辑,不动子组件。
> 
> **showStage / showUnstage 互斥**:scope=unstaged 时前者 true,scope=staged 时后者 true,scope=all 时两者都 false(决策 #6)。`GitDiffFileItem` 模板里两个 `<button>` 各自 `v-if="showStage"` / `v-if="showUnstage"`,互不干扰。

### 6.3 全部暂存确认弹窗(Q4 — 新增)

- 标题:`gitWorkflow.stage.stageAll.confirmTitle` = "全部暂存?"
- 正文:`gitWorkflow.stage.stageAll.confirmMessage({count})` = "当前有 {count} 个文件尚未暂存。\n\n此操作可随时通过"取消暂存"撤销。"
- 主按钮:`gitWorkflow.stage.stageAll.confirmAction` = "全部暂存",`color="primary"`,`variant="flat"`(决策 #20:可逆操作不需要 warning 色)
- 取消按钮:`gitWorkflow.stage.stageAll.confirmCancel` = "取消",`variant="text"`
- `persistent`:`true`(与 restore 一致;不允许点遮罩跳过)
- 状态:`confirmStageAllOpen: ref<boolean>` + `pendingStageAllCount: ref<number>`

弹窗草图见 §6.6。

### 6.4 Commit 弹窗(新增)

#### 6.4.1 布局

```
┌─ 提交 ──────────────────────────────────────────┐
│                                                 │
│  Commit message:                                │
│  ┌───────────────────────────────────────────┐  │
│  │ feat: add git-stage endpoint              │  │
│  │                                           │  │
│  │ 支持 files / all 互斥模式                  │  │
│  │                                           │  │
│  └───────────────────────────────────────────┘  │
│  字符数: 47 / 8192                              │  ← 实时 counter
│                                                 │
│  已暂存 3 个文件:                                │
│   • src/main.py                                 │
│   • tests/test_foo.py                           │
│   • README.md                                   │
│                                                 │
│  ⚠ stderr (若 hook_rejected / git_error):       │  ← 失败后显示
│  ┌───────────────────────────────────────────┐  │
│  │ ruff format --check ........... 3 errors  │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│              [取消]              [提交]          │
└─────────────────────────────────────────────────┘
```

#### 6.4.2 行为

- `message` 双向绑定 `<textarea>`,min-height 120px
- 字符数 counter(P1-6 修复:警告色用 Vuetify token):
  - `<span :class="['commit-char-counter', { 'is-warning': message.length > 7000, 'is-error': message.length > 8192 }]">`
  - `{{ tm("commit.dialog.charCounter", { count: message.length }) }}`
  - CSS:
    ```css
    .commit-char-counter { color: rgba(var(--v-theme-on-surface), 0.55); font-size: 12px; }
    .commit-char-counter.is-warning { color: rgb(var(--v-theme-warning)); font-weight: 500; }
    .commit-char-counter.is-error { color: rgb(var(--v-theme-error)); font-weight: 600; }
    ```
- "提交" 按钮:`disabled` 当 `message.trim().length === 0 || message.length > 8192 || isCommitting`
- "取消" 按钮:关闭 dialog,清空 `message` 与 `lastError`
- 提交中:提交按钮显示 `v-progress-circular`,disabled,textarea disabled
- 失败时:不关闭 dialog,在 footer 上方显示 stderr 块(`<pre>`);同时全局 snackbar 提示
- 关闭方式:`persistent: true` + Esc 关闭等同取消(由 `<v-dialog>` 默认行为提供)

#### 6.4.3 props / events

```ts
defineProps<{
  modelValue: boolean;
  stagedFiles: string[];
  isCommitting: boolean;
  lastError?: { reason: string; stderr: string };
}>();

defineEmits<{
  (e: 'update:modelValue', v: boolean): void;
  (e: 'confirm', payload: { message: string }): void;
  (e: 'cancel'): void;
}>();
```

### 6.5 History 视图(新增第 3 个 viewMode)

#### 6.5.1 过滤栏(顶部)

```
┌────────────────────────────────────────────────────┐
│ Ref: [HEAD]  Author: [____]  Path: [____]         │
│ Since: [2026-06-01]  N: [20]    [应用] [重置]      │
└────────────────────────────────────────────────────┘
```

- 控件:Vuetify `v-text-field` (density="compact", variant="outlined", hide-details),placeholder 提供示例
- "应用" 按钮:触发 `useSpcodeGitLog.refresh({ ...filter })`
- "重置" 按钮:重置所有 filter 为默认值,触发 refresh

> **P0-4 修复说明**:`useSpcodeGitLog` 内部 ETag Map 的 key 维度是 `umo + worktree + ref + path + author + since + until + n`(决策 #25)。filter 变化时 key 自动变化,旧 ETag **天然不会复用**(`Map.get()` miss)。`etagMap.clear()` 只在切 worktree / 切 umo 时调用(决策 #24),不在每次应用 filter 时调用。

#### 6.5.2 commit 列表

紧凑型单行:

```
● 418bb36  feat: add git-stage endpoint
  elecvoid243 · 2 小时前 · +142 −27  3 files
─────────────────────────────────────────────────────
● 0a3f2e1  fix: handle scope drift
  elecvoid243 · 昨天 · +18 −4      1 file
─────────────────────────────────────────────────────
```

- 左侧图标:Vuetify 默认 commit 图标 `mdi-source-commit`
- SHA-7:等宽字体,monospace
- subject:主标题(粗体),`text-truncate` 截断
- 元信息行:author · 相对时间(派生自 `date`)· shortstat
- 相对时间格式(P0-5 修复:见下方 `formatRelativeTime` 函数)
- 点击行 → 展开 body(若有)
- `truncated === true` 时显示顶部黄色 banner(同 diff 截断处理)

**`formatRelativeTime(isoDate: string, now: number = Date.now()): string` 实现规则**:

```ts
function formatRelativeTime(isoDate: string, now: number = Date.now()): string {
  const t = new Date(isoDate).getTime();
  if (Number.isNaN(t)) return isoDate;  // fallback:原样返回
  const diff = now - t;
  const min = Math.floor(diff / 60_000);
  if (min < 1) return tm("history.relativeTime.now");
  if (min < 60) return tm("history.relativeTime.minutesAgo", { n: min });
  const h = Math.floor(min / 60);
  if (h < 24) return tm("history.relativeTime.hoursAgo", { n: h });
  const d = Math.floor(h / 24);
  if (d < 7) return tm("history.relativeTime.daysAgo", { n: d });
  // > 7 天:显示完整日期(本地时区,YYYY-MM-DD)
  const yyyy = t.getFullYear?.() ?? new Date(t).getFullYear();
  const mm = String((t.getMonth?.() ?? new Date(t).getMonth()) + 1).padStart(2, "0");
  const dd = String(t.getDate?.() ?? new Date(t).getDate()).padStart(2, "0");
  return tm("history.relativeTime.exactDate", { date: `${yyyy}-${mm}-${dd}` });
}
```

**边界条件**:
- 未来时间(`diff < 0`):`min < 1` 走"刚刚"(i18n `now` key 兼作"无显著间隔"标记)
- 解析失败(`Number.isNaN`):返回原 ISO 字符串,UI 可肉眼识别
- 同一天多次 commit:第一次显示 "{n} 分钟前",跨小时后切到 "{n} 小时前"

#### 6.5.3 分页

- 列表底部"加载更多"按钮(仅 `has_more === true` 时显示)
- 点击 → `useSpcodeGitLog.loadMore()`,将 `n` 翻倍(20 → 40 → 80 → 200 上限)

### 6.6 全部暂存确认弹窗草图

```
┌─ 全部暂存 ────────────────────────────────────────┐
│                                                    │
│  将暂存所有未暂存的改动。                           │
│  当前有 12 个文件尚未暂存。                        │
│                                                    │
│  此操作可随时通过"取消暂存"撤销。                  │
│                                                    │
│              [取消]              [全部暂存]        │
└────────────────────────────────────────────────────┘
```

### 6.7 粘性 commit bar

```
┌─ commit-bar ──────────────────────────────────────┐
│  ⓘ 已暂存 3 个文件          [全部暂存]  [提交 →]  │
└────────────────────────────────────────────────────┘
```

- 位置:`git-diff-sidebar-body` 之后(在 `body` 的 `flex: 1` 之外,作为 `flex-shrink: 0` 的 sibling)
- 背景:`rgb(var(--v-theme-surface))` + 顶部 1px border(与 sidebar header 对称)
- 文字:`stagedFiles.size > 0 ? "已暂存 {count} 个文件" : "暂存文件后可提交"(muted color)`
- "全部暂存" 按钮:仅在 `unstagedCount > 0` 时 enabled;否则 disabled + muted
- "提交" 按钮:仅在 `stagedFiles.size > 0` 时 enabled;否则 disabled + muted
- 移动端(≤ 760px):保持原尺寸,只是内部按钮可能缩窄

#### 6.7.1 `unstagedCount` 派生(P1-5 修复:分 scope 列出语义)

**关键事实**:`useSpcodeGitDiff` 的 `snapshot.files` 内容**取决于 `selectedScope`**。三语种下含义不同:

| `selectedScope` | `snapshot.files` 包含 | `stagedFiles.size` 含义 | `unstagedCount` 公式 | 期望值 |
|------------------|------------------------|--------------------------|-----------------------|--------|
| `unstaged` | 仅未暂存文件(已 `git add` 的不出现) | 跨终端/跨 session 的"已 stage"集合(可能 > 0) | `snapshot.files.length` | 总是 ≥ 0 |
| `staged` | 仅已暂存文件 | 当前 session 的 staged 集合 | `0`(没有未暂存) | 总是 0 |
| `all` | staged + unstaged + untracked | 当前 session 的 staged 集合 | `snapshot.files.length - stagedFiles.size` | ≥ 0 |

```ts
const unstagedCount = computed(() => {
  // Reads from diffBodyState (not composable.state) so the splice
  // of untracked/intent_to_add paths from /spcode/git-status is
  // reflected in the count. Same code serves both the "unstaged"
  // and "all" views; "staged" view skips the splice (untracked is
  // by definition not staged).
  const s = diffBodyState.value;
  if (s.kind !== "ok") return 0;
  const total = s.snapshot.files.length;
  // 简化处理:untracked 算作 unstaged(后端 untracked 也在 files_changed 列表里)
  if (selectedScope.value === "staged") return 0;
  if (selectedScope.value === "unstaged") return total;  // snapshot 已仅含未暂存
  return Math.max(0, total - stagedFiles.value.size);  // all(含 spliced untracked)
});
```

> **Q5 决策依据**:scope=staged 时 `unstagedCount=0`,`"全部暂存"` 按钮 disabled,与"暂存"操作不适用此 scope 的语义一致。
> 
> **P2-5 同步**:此公式与 §10 风险 #5(行内按钮密度)无关,后者讨论的是视觉密度,不是数据语义。
> 
> **P3-1 新增**:`newFilePaths` 与 `diffBodyState` 的 splice gate 改为 `selectedScope !== "staged"`(原为 `=== "unstaged"`),让 "all (vs HEAD)" 视图同样显示 untracked/intent_to_add 文件,语义与"未暂存"一致。`!existing.has` 守卫保证 `git diff HEAD` 已含的 `intent_to_add` 不会被重复插入。

### 6.8 Snackbar(扩展)

现有 restore 用的 snackbar 扩展:支持 `withStderr` 渲染(P0-6 修复 —— 模板明确分两种情况)。

`SnackbarState` 类型已在 §5.3 给出。`withStderr: true` 的 reason 当前字典里只有 `git_error` 与 `hook_rejected`(详见 §5.1 注释 + §7 i18n 标注)。

```vue
<v-snackbar
  v-model="snackbar.show"
  :color="snackbar.color"
  :timeout="snackbar.color === 'success' ? 4000 : 6000"
  location="bottom right"
>
  <!-- 携带 stderr 的 reason:消息正文 + <pre> 块 -->
  <div v-if="snackbar.stderr" class="spcode-snackbar-stderr">
    <div class="spcode-snackbar-message">{{ snackbar.message }}</div>
    <pre class="spcode-snackbar-pre">{{ snackbar.stderr }}</pre>
  </div>
  <!-- 普通消息 -->
  <div v-else>{{ snackbar.message }}</div>
</v-snackbar>
```

```css
.spcode-snackbar-message {
  font-weight: 500;
  margin-bottom: 6px;
}
.spcode-snackbar-pre {
  background: rgba(0, 0, 0, 0.2);
  color: inherit;
  padding: 6px 8px;
  border-radius: 4px;
  font-size: 11px;
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
```

### 6.9 键盘可达性

- 行内 ↑ / ↓ 按钮:Tab 聚焦,Enter / Space 触发
- 全部暂存确认 dialog:Tab 在按钮间循环,Esc 关闭等同取消
- commit dialog:Tab 跳到 textarea、提交、取消;Cmd/Ctrl+Enter 提交
- Snackbar:Vuetify 默认 Esc 关闭

---

## 7. i18n 键结构

> 三语同步,缺一会导致 `useModuleI18n` 静默回退到 key 字面值(已知 footgun)。

### 7.1 zh-CN

```jsonc
"diffSidebar": {
  "...": "...",
  "gitWorkflow": {
    "stage": {
      "buttonAria": "暂存 {path}",
      "unstageButtonAria": "取消暂存 {path}",
      "success": "已暂存 {path}",
      "successAll": "已暂存全部 {count} 个文件",
      "stageAll": {
        "button": "全部暂存",
        "buttonAria": "暂存所有未暂存文件",
        "confirmTitle": "全部暂存?",
        "confirmMessage": "当前有 {count} 个文件尚未暂存。\n\n此操作可随时通过\"取消暂存\"撤销。",
        "confirmAction": "全部暂存",
        "confirmCancel": "取消"
      }
    },
    "unstage": {
      "buttonAria": "取消暂存 {path}",
      "success": "已取消暂存 {path}"
    },
    "commit": {
      "bar": {
        "stagedCount": "已暂存 {count} 个文件",
        "stagedCountZero": "暂存文件后可提交",
        "stageAll": "全部暂存",
        "stageAllAria": "暂存所有未暂存文件",
        "commit": "提交",
        "commitDisabledHint": "暂存文件后才能提交"
      },
      "dialog": {
        "title": "提交",
        "messageLabel": "Commit message",
        "messagePlaceholder": "feat: 简要描述本次改动...",
        "charCounter": "{count} / 8192",
        "stagedFilesTitle": "已暂存 {count} 个文件:",
        "stagedFilesEmpty": "(无)",
        "stderrTitle": "⚠ 错误输出",
        "cancel": "取消",
        "confirm": "提交",
        "submitShortcutHint": "Ctrl+Enter 提交"
      },
      "success": "已提交 {sha}",
      "failureHint": "提交失败,请修改 message 或修复错误后重试"
    },
    "history": {
      "tab": "历史",
      "tabAria": "切换到历史视图",
      "filter": {
        "ref": "Ref",
        "refPlaceholder": "HEAD / 分支名 / SHA",
        "author": "作者",
        "authorPlaceholder": "作者名或邮箱",
        "path": "路径",
        "pathPlaceholder": "仓库相对路径",
        "since": "起始时间",
        "sincePlaceholder": "2026-06-01",
        "n": "数量",
        "nPlaceholder": "20",
        "apply": "应用",
        "reset": "重置"
      },
      "empty": "暂无提交记录",
      "emptyRepository": "仓库还没有任何提交",
      "loadMore": "加载更多",
      "loading": "加载中…",
      "truncated": "⚠ 输出已截断(可能不完整),请缩小过滤范围",
      "relativeTime": {
        "now": "刚刚",
        "minutesAgo": "{n} 分钟前",
        "hoursAgo": "{n} 小时前",
        "daysAgo": "{n} 天前",
        "exactDate": "{date}"
      },
      "filesStat": "{files} 个文件, +{add} −{del}",
      "expandCommit": "展开 commit 详情",
      "collapseCommit": "折叠 commit 详情"
    },
    "error": {
      "reason": {
        "network": "网络连接失败",
        "unknown": "操作失败({reason})",
        "feature_disabled": "功能未启用",
        "no_project_loaded": "项目未载入",
        "worktree_invalid": "目标 worktree 无效",
        "directory_missing": "已加载的目录不存在",
        "not_a_git_repo": "当前目录不是 Git 仓库",
        "git_unavailable": "未检测到 git 可执行文件",
        "git_error": "Git 执行失败",
        "invalid_body": "请求格式错误",
        "invalid_files": "files / all 参数错误(同时传、都不传、格式不对或数量超限)",
        "invalid_all": "all 参数必须是 bool",
        "invalid_message": "commit message 校验失败(非 str / 空 / 超过 8192 字符)",
        "invalid_param": "query 参数解析失败",
        "path_unsafe": "文件路径不安全(已拒绝)",
        "nothing_to_commit": "没有可提交的暂存改动",
        "hook_rejected": "pre-commit / commit-msg 钩子拒绝",
        "identity_not_set": "请先 `git config --global user.email ...`",
        "empty_repository": "仓库还没有任何提交"
      }
    }
  }
}
```

### 7.2 en-US

```jsonc
"gitWorkflow": {
  "stage": {
    "buttonAria": "Stage {path}",
    "unstageButtonAria": "Unstage {path}",
    "success": "Staged {path}",
    "successAll": "Staged all {count} files",
    "stageAll": {
      "button": "Stage all",
      "buttonAria": "Stage all unstaged files",
      "confirmTitle": "Stage all?",
      "confirmMessage": "{count} files are currently unstaged.\n\nThis can be undone via \"Unstage\".",
      "confirmAction": "Stage all",
      "confirmCancel": "Cancel"
    }
  },
  "unstage": {
    "buttonAria": "Unstage {path}",
    "success": "Unstaged {path}"
  },
  "commit": {
    "bar": {
      "stagedCount": "{count} files staged",
      "stagedCountZero": "Stage files to commit",
      "stageAll": "Stage all",
      "stageAllAria": "Stage all unstaged files",
      "commit": "Commit",
      "commitDisabledHint": "Stage files before committing"
    },
    "dialog": {
      "title": "Commit",
      "messageLabel": "Commit message",
      "messagePlaceholder": "feat: short description of changes...",
      "charCounter": "{count} / 8192",
      "stagedFilesTitle": "{count} files staged:",
      "stagedFilesEmpty": "(empty)",
      "stderrTitle": "⚠ Error output",
      "cancel": "Cancel",
      "confirm": "Commit",
      "submitShortcutHint": "Ctrl+Enter to commit"
    },
    "success": "Committed {sha}",
    "failureHint": "Commit failed. Please fix the message or errors and retry."
  },
  "history": {
    "tab": "History",
    "tabAria": "Switch to history view",
    "filter": {
      "ref": "Ref",
      "refPlaceholder": "HEAD / branch / SHA",
      "author": "Author",
      "authorPlaceholder": "name or email",
      "path": "Path",
      "pathPlaceholder": "repo-relative path",
      "since": "Since",
      "sincePlaceholder": "2026-06-01",
      "n": "Count",
      "nPlaceholder": "20",
      "apply": "Apply",
      "reset": "Reset"
    },
    "empty": "No commits",
    "emptyRepository": "Repository has no commits yet",
    "loadMore": "Load more",
    "loading": "Loading…",
    "truncated": "⚠ Output truncated (may be incomplete). Narrow your filter.",
    "relativeTime": {
      "now": "just now",
      "minutesAgo": "{n} min ago",
      "hoursAgo": "{n}h ago",
      "daysAgo": "{n}d ago",
      "exactDate": "{date}"
    },
    "filesStat": "{files} files, +{add} −{del}",
    "expandCommit": "Expand commit details",
    "collapseCommit": "Collapse commit details"
  },
  "error": {
    "reason": {
      "network": "Network error",
      "unknown": "Operation failed ({reason})",
      "feature_disabled": "Feature disabled",
      "no_project_loaded": "No project loaded",
      "worktree_invalid": "Target worktree invalid",
      "directory_missing": "Loaded directory no longer exists",
      "not_a_git_repo": "Current directory is not a Git repository",
      "git_unavailable": "Git executable not found",
      "git_error": "Git execution failed",
      "invalid_body": "Malformed request",
      "invalid_files": "files / all parameter invalid (mutually exclusive, both missing, wrong format, or over limit)",
      "invalid_all": "all must be a boolean",
      "invalid_message": "commit message invalid (non-string / empty / over 8192 chars)",
      "invalid_param": "query parameter parse error",
      "path_unsafe": "File path unsafe (rejected)",
      "nothing_to_commit": "No staged changes to commit",
      "hook_rejected": "pre-commit / commit-msg hook rejected",
      "identity_not_set": "Run `git config --global user.email ...` first",
      "empty_repository": "Repository has no commits yet"
    }
  }
}
```

### 7.3 ru-RU

```jsonc
"gitWorkflow": {
  "stage": {
    "buttonAria": "Подготовить {path}",
    "unstageButtonAria": "Отменить подготовку {path}",
    "success": "Подготовлено: {path}",
    "successAll": "Подготовлено файлов: {count}",
    "stageAll": {
      "button": "Подготовить всё",
      "buttonAria": "Подготовить все неподготовленные файлы",
      "confirmTitle": "Подготовить всё?",
      "confirmMessage": "Сейчас {count} неподготовленных файлов.\n\nЭто можно отменить через \"Отменить подготовку\".",
      "confirmAction": "Подготовить всё",
      "confirmCancel": "Отмена"
    }
  },
  "unstage": {
    "buttonAria": "Отменить подготовку {path}",
    "success": "Подготовка отменена: {path}"
  },
  "commit": {
    "bar": {
      "stagedCount": "Подготовлено файлов: {count}",
      "stagedCountZero": "Подготовьте файлы для коммита",
      "stageAll": "Подготовить всё",
      "stageAllAria": "Подготовить все неподготовленные файлы",
      "commit": "Закоммитить",
      "commitDisabledHint": "Сначала подготовьте файлы"
    },
    "dialog": {
      "title": "Коммит",
      "messageLabel": "Сообщение коммита",
      "messagePlaceholder": "feat: краткое описание изменений...",
      "charCounter": "{count} / 8192",
      "stagedFilesTitle": "Подготовлено файлов: {count}:",
      "stagedFilesEmpty": "(пусто)",
      "stderrTitle": "⚠ Вывод ошибки",
      "cancel": "Отмена",
      "confirm": "Закоммитить",
      "submitShortcutHint": "Ctrl+Enter — закоммитить"
    },
    "success": "Закоммичено: {sha}",
    "failureHint": "Коммит не удался. Исправьте сообщение или ошибки и повторите."
  },
  "history": {
    "tab": "История",
    "tabAria": "Переключиться на историю",
    "filter": {
      "ref": "Ref",
      "refPlaceholder": "HEAD / ветка / SHA",
      "author": "Автор",
      "authorPlaceholder": "имя или email",
      "path": "Путь",
      "pathPlaceholder": "путь относительно репозитория",
      "since": "С даты",
      "sincePlaceholder": "2026-06-01",
      "n": "Кол-во",
      "nPlaceholder": "20",
      "apply": "Применить",
      "reset": "Сброс"
    },
    "empty": "Нет коммитов",
    "emptyRepository": "В репозитории ещё нет коммитов",
    "loadMore": "Загрузить ещё",
    "loading": "Загрузка…",
    "truncated": "⚠ Вывод обрезан (может быть неполным). Сузьте фильтр.",
    "relativeTime": {
      "now": "только что",
      "minutesAgo": "{n} мин назад",
      "hoursAgo": "{n} ч назад",
      "daysAgo": "{n} дн назад",
      "exactDate": "{date}"
    },
    "filesStat": "{files} файлов, +{add} −{del}",
    "expandCommit": "Развернуть детали коммита",
    "collapseCommit": "Свернуть детали коммита"
  },
  "error": {
    "reason": {
      "network": "Ошибка сети",
      "unknown": "Операция не удалась ({reason})",
      "feature_disabled": "Функция отключена",
      "no_project_loaded": "Проект не загружен",
      "worktree_invalid": "Целевое worktree недопустимо",
      "directory_missing": "Загруженный каталог больше не существует",
      "not_a_git_repo": "Текущий каталог не является репозиторием Git",
      "git_unavailable": "Исполняемый файл git не найден",
      "git_error": "Ошибка выполнения Git",
      "invalid_body": "Некорректный запрос",
      "invalid_files": "параметр files / all недопустим (взаимоисключающие, оба отсутствуют, неверный формат или превышен лимит)",
      "invalid_all": "all должен быть boolean",
      "invalid_message": "сообщение коммита недопустимо (не строка / пусто / более 8192 символов)",
      "invalid_param": "ошибка разбора параметра query",
      "path_unsafe": "Путь к файлу небезопасен (отклонено)",
      "nothing_to_commit": "Нет подготовленных изменений",
      "hook_rejected": "pre-commit / commit-msg хук отклонил",
      "identity_not_set": "Сначала выполните `git config --global user.email ...`",
      "empty_repository": "В репозитории ещё нет коммитов"
    }
  }
}
```

---

## 8. 文件清单

| 文件 | 类型 | 行数预估 | 职责 |
|------|------|---------|------|
| `dashboard/src/composables/parseSpcodeGitWorkflow.ts` | 新增 | +180 | 4 端点 envelope parser;`StagedSnapshot` / `CommitSnapshot` / `LogSnapshot` / `LogCommit` 类型;`GIT_WORKFLOW_REASON_CODES` 字典;`classifyReason(reason, endpoint)` |
| `dashboard/src/composables/useSpcodeGitStage.ts` | 新增 | +110 | POST 包装;`stage({files?, all?, worktree?, umo?})`;`isStaging: Set<string>`;AbortController |
| `dashboard/src/composables/useSpcodeGitUnstage.ts` | 新增 | +110 | POST 包装;对称 stage |
| `dashboard/src/composables/useSpcodeGitCommit.ts` | 新增 | +120 | POST 包装;`commit({message, worktree?, umo?})`;`isCommitting` |
| `dashboard/src/composables/useSpcodeGitLog.ts` | 新增 | +180 | GET 包装;`state: LogFetchState`;ETag Map 内部维护;`refresh(filter?)` / `loadMore()`;10s polling |
| `dashboard/tests/parseSpcodeGitWorkflow.test.mjs` | 新增 | +120 | 4 端点 envelope + reason 分类单测 |
| `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue` | 修改 | +75 / -5 | 新增 `onStage` / `onUnstage` / `isStaging` / `isUnstaging` props;↑ / ↓ 行内按钮;CSS 块 |
| `dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue` | 修改 | +20 | 下传 `onStage` / `onUnstage` 回调;re-emit |
| `dashboard/src/components/chat/message_list_comps/GitCommitDialog.vue` | 新增 | +160 | message textarea + staged 预览 + stderr 块 |
| `dashboard/src/components/chat/message_list_comps/GitLogView.vue` | 新增 | +200 | commit 列表 + 过滤栏 + 分页 |
| `dashboard/src/components/chat/message_list_comps/GitCommitBar.vue` | 新增 | +60 | 粘性底部栏 |
| `dashboard/src/components/chat/GitDiffSidebar.vue` | 修改 | +180 / -10 | 集成 4 个 composable;commit bar;History tab;confirmStageAll dialog;扩展 snackbar;扩展 RESTORE → GIT_WORKFLOW reason map |
| `dashboard/src/i18n/locales/zh-CN/features/chat.json` | 修改 | +95 | `diffSidebar.gitWorkflow.*` 命名空间 |
| `dashboard/src/i18n/locales/en-US/features/chat.json` | 修改 | +95 | `diffSidebar.gitWorkflow.*` 命名空间 |
| `dashboard/src/i18n/locales/ru-RU/features/chat.json` | 修改 | +95 | `diffSidebar.gitWorkflow.*` 命名空间 |
| `docs/superpowers/specs/2026-06-24-chatui-git-workflow-controls-design.md` | 新增 | — | 本文档 |

**总计**:新增 ~1230 行,修改 ~190 行(净增),3 个 i18n 文件各 +95 行。

**关于 `parseSpcodeGitWorkflow.ts` 单文件拆分的 AGENTS.md 合规说明**:

`AGENTS.md` "No Unnecessary Helpers" 规则要求"3 处以上复用"或"极高复杂度"才可抽 helper。本 spec 的解析器虽然只被 4 个 composable 使用,**但**:
- 4 个端点共享大量 envelope 字段(`umo`、`worktree`、`directory`、`elapsed_ms`、`reason`、`stderr`、`files`、`staged_count`)
- 4 个端点共享 reason 字典,`classifyReason(reason, endpoint)` 是 4 处复用
- 单元测试 `parseSpcodeGitWorkflow.test.mjs` 必须独立导入纯函数模块(在 Node `node --test` 环境下,Vue composable 难以 mock,而纯函数解析器零依赖可测)
- 既有 `parseSpcodeFileRestore.ts` + `useSpcodeFileRestore.ts` / `parseSpcodeGitDiff.ts` + `useSpcodeGitDiff.ts` 同构拆分

故 2 文件拆分(共享 parser + 4 个独立 composable)合理。

---

## 9. 测试策略

### 9.1 后端测试

**不修改**。`astrbot_plugin_spcode_toolkit/tests/test_git_workflow.py`(v3.7 release 时已写)覆盖 4 端点所有 reason 与边界。

### 9.2 前端单元测试(`parseSpcodeGitWorkflow.test.mjs`)

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  parseSpcodeGitStage,
  parseSpcodeGitUnstage,
  parseSpcodeGitCommit,
  parseSpcodeGitLog,
  classifyReason,
} from '../dashboard/src/composables/parseSpcodeGitWorkflow.js';

test('parseSpcodeGitStage: success envelope', () => {
  const r = parseSpcodeGitStage({
    status: 'ok',
    data: {
      success: true, reason: null, stderr: '',
      elapsed_ms: 8, umo: 'webchat-1', worktree: 'C:/repo', directory: 'C:/repo',
      staged: true, files: ['src/main.py'], staged_count: 1,
    },
  });
  assert.equal(r.kind, 'ok');
  assert.equal(r.snapshot.staged, true);
  assert.deepEqual(r.snapshot.files, ['src/main.py']);
});

test('parseSpcodeGitStage: failure (path_unsafe)', () => {
  const r = parseSpcodeGitStage({
    status: 'ok',
    data: {
      success: false, reason: 'path_unsafe', stderr: 'fatal: ...',
      elapsed_ms: 4, umo: 'x', worktree: 'C:/repo', directory: 'C:/repo',
      staged: false, files: [], staged_count: 0,
    },
  });
  assert.equal(r.kind, 'ok');  // 业务失败仍 parse 成功
  assert.equal(r.snapshot.success, false);
  assert.equal(r.snapshot.reason, 'path_unsafe');
});

test('parseSpcodeGitCommit: success returns 40-char SHA', () => {
  const r = parseSpcodeGitCommit({
    status: 'ok',
    data: {
      success: true, reason: null, stderr: '',
      elapsed_ms: 47, umo: 'x', worktree: 'C:/repo', directory: 'C:/repo',
      committed: true, sha: '418bb365a7c8a1b7c5b1b2d2e7b3a4f5a6b7c8d9',
      files: ['src/main.py'], committed_count: 1, staged_count: 0,
    },
  });
  assert.equal(r.kind, 'ok');
  assert.equal(r.snapshot.sha.length, 40);
  assert.equal(r.snapshot.stagedCount, 0);
});

test('parseSpcodeGitCommit: hook_rejected (failure keeps staged)', () => {
  const r = parseSpcodeGitCommit({
    status: 'ok',
    data: {
      success: false, reason: 'hook_rejected', stderr: 'ruff ...',
      elapsed_ms: 1200, umo: 'x', worktree: 'C:/repo', directory: 'C:/repo',
      committed: false, sha: '',
      files: ['src/main.py', 'tests/foo.py'], committed_count: 0, staged_count: 2,
    },
  });
  assert.equal(r.snapshot.stagedCount, 2);  // 关键:失败后 staged 不丢
});

test('parseSpcodeGitLog: empty repository', () => {
  const r = parseSpcodeGitLog({
    status: 'ok',
    data: {
      success: false, reason: 'empty_repository', loaded: false,
      elapsed_ms: 5, umo: 'x', worktree: 'C:/repo', directory: 'C:/repo',
      ref: 'HEAD', count: 0, has_more: false, truncated: false, max_bytes: 1048576,
      commits: [],
    },
  });
  assert.equal(r.snapshot.commits.length, 0);
  assert.equal(r.snapshot.reason, 'empty_repository');
});

test('classifyReason: known reason for stage endpoint', () => {
  assert.equal(classifyReason('path_unsafe', 'stage'), 'path_unsafe');
  assert.equal(classifyReason('invalid_files', 'unstage'), 'invalid_files');
});

test('classifyReason: endpoint mismatch (hook_rejected is commit-only)', () => {
  assert.equal(classifyReason('hook_rejected', 'stage'), 'unknown');
  assert.equal(classifyReason('hook_rejected', 'commit'), 'hook_rejected');
});

test('classifyReason: unknown reason always returns unknown', () => {
  assert.equal(classifyReason('foo_bar_baz', 'stage'), 'unknown');
  assert.equal(classifyReason(null, 'stage'), 'unknown');
});

test('parseSpcodeGitLog: throws on missing data field', () => {
  assert.throws(() => parseSpcodeGitLog({ status: 'ok' }));
});

test('parseSpcodeGitLog: parses commits array', () => {
  const r = parseSpcodeGitLog({
    status: 'ok',
    data: {
      success: true, reason: null, loaded: true,
      elapsed_ms: 23, umo: 'x', worktree: 'C:/repo', directory: 'C:/repo',
      ref: 'HEAD', count: 1, has_more: false, truncated: false, max_bytes: 1048576,
      commits: [{
        sha: '418bb365a7c8a1b7c5b1b2d2e7b3a4f5a6b7c8d9',
        sha_short: '418bb36',
        author: { name: 'elecvoid243', email: 'elecvoid243@example.com' },
        committer: { name: 'elecvoid243', email: 'elecvoid243@example.com' },
        date: '2026-06-24T10:15:32+08:00',
        subject: 'feat: add git-stage endpoint',
        body: 'long description',
        parents: ['abc1234'],
        shortstat: { files: 3, additions: 142, deletions: 27 },
      }],
    },
  });
  assert.equal(r.snapshot.commits.length, 1);
  assert.equal(r.snapshot.commits[0].shaShort, '418bb36');
  assert.equal(r.snapshot.commits[0].author.name, 'elecvoid243');
});

// ── P1-8 追加:边界与向后兼容 ──────────────────────────

test('parseSpcodeGitLog: root commit (empty parents array)', () => {
  const r = parseSpcodeGitLog({
    status: 'ok',
    data: {
      success: true, reason: null, loaded: true,
      elapsed_ms: 5, umo: 'x', worktree: 'C:/repo', directory: 'C:/repo',
      ref: 'HEAD', count: 1, has_more: false, truncated: false, max_bytes: 1048576,
      commits: [{
        sha: '0000000000000000000000000000000000000000',
        sha_short: '0000000',
        author: { name: 'root', email: 'root@example.com' },
        committer: { name: 'root', email: 'root@example.com' },
        date: '2026-01-01T00:00:00+00:00',
        subject: 'Initial commit',
        body: null,
        parents: [],                              // 根 commit,无父
        shortstat: { files: 1, additions: 1, deletions: 0 },
      }],
    },
  });
  assert.equal(r.snapshot.commits[0].parents.length, 0);
});

test('parseSpcodeGitCommit: failure returns empty SHA', () => {
  const r = parseSpcodeGitCommit({
    status: 'ok',
    data: {
      success: false, reason: 'nothing_to_commit', stderr: '',
      elapsed_ms: 5, umo: 'x', worktree: 'C:/repo', directory: 'C:/repo',
      committed: false, sha: '',                 // 失败时 sha 必为空
      files: [], committed_count: 0, staged_count: 0,
    },
  });
  assert.equal(r.snapshot.sha, '');
  assert.equal(r.snapshot.committed, false);
});

test('parseSpcodeGitStage: missing staged field defaults to false (backward compat)', () => {
  // v3.7 之前的 plugin 可能不返回 staged 字段;parser 应宽容
  const r = parseSpcodeGitStage({
    status: 'ok',
    data: {
      success: true, reason: null, stderr: '',
      elapsed_ms: 5, umo: 'x', worktree: 'C:/repo', directory: 'C:/repo',
      // 故意不传 staged
      files: ['src/main.py'], staged_count: 1,
    },
  });
  assert.equal(r.snapshot.staged, false);  // 缺省 false
  assert.equal(r.snapshot.stagedCount, 1);
});

test('parseSpcodeGitLog: truncated output flagged', () => {
  const r = parseSpcodeGitLog({
    status: 'ok',
    data: {
      success: true, reason: null, loaded: true,
      elapsed_ms: 50, umo: 'x', worktree: 'C:/repo', directory: 'C:/repo',
      ref: 'HEAD', count: 200, has_more: true, truncated: true, max_bytes: 1048576,
      commits: [],                              // 截断时 commits 可能为空
    },
  });
  assert.equal(r.snapshot.truncated, true);
  assert.equal(r.snapshot.hasMore, true);
});

test('parseSpcodeGitLog: empty commits array (success, not empty_repository)', () => {
  // 区分:success=true + commits=[] (无 commit 但仓库存在) vs success=false + reason=empty_repository
  const r = parseSpcodeGitLog({
    status: 'ok',
    data: {
      success: true, reason: null, loaded: true,
      elapsed_ms: 5, umo: 'x', worktree: 'C:/repo', directory: 'C:/repo',
      ref: 'HEAD', count: 0, has_more: false, truncated: false, max_bytes: 1048576,
      commits: [],
    },
  });
  assert.equal(r.snapshot.commits.length, 0);
  assert.equal(r.snapshot.reason, null);
});
```

### 9.3 手动冒烟(无 Vue Test Utils,与既有约定一致)

| 场景 | 操作 | 预期 |
|------|------|------|
| 单文件暂存 | 切到 unstaged scope → 点击 ↑ | 行变 staged(切到 staged 视图可见) |
| 全部暂存(有未暂存) | 点击 commit bar "全部暂存" → 确认弹窗 → 确认 | 所有未暂存变 staged |
| 全部暂存(无未暂存) | 按钮 disabled | hover 显示 commitDisabledHint |
| 取消单文件暂存 | 切到 staged scope → 点击 ↓ | 行变 unstaged |
| 提交成功 | 输 message → 提交 | dialog 关闭、toast、staged 清空、log 增加(若在 history 视图) |
| 提交失败(hook) | 触发 pre-commit 错误 | dialog 内显示 stderr、可修改 message 重试;staged 保留 |
| 提交失败(nothing_to_commit) | 极端情况(已暂存但 race) | toast warning;dialog 关闭;staged 不变 |
| 提交 message > 8192 | 粘贴超长文本 | char counter 变 warning 色;提交按钮 disabled |
| 切 worktree | 切换 worktree tab | commit bar 仍显示;stagedFiles 保留(决策 #22) |
| 切 project | `/project unload` | stagedFiles 清空(决策 #23);commit bar 隐藏 |
| History 加载 | 切到 History tab | 显示 commit 列表 |
| History 过滤 | 修改 ref/author/path → 应用 | 列表重渲;ETag Map 清掉旧 key |
| History 304 | 1.5s 内重复刷新 | 网络显示 304;UI 不显示 loading |
| History 分页 | has_more=true 时加载更多 | 追加 commit;`n` 翻倍 |
| all scope 行内按钮 | 切到 all scope | ↑ / ↓ **不显示**(决策 #6) |
| 移动端 | ≤ 760px 宽度 | commit bar 仍可见,按钮缩窄但可点 |

### 9.4 ETag 测试(专项)

```
1. 打开 History tab,首次 GET /spcode/git-log → 200 + ETag-A
2. 1.5s 内再次触发 refresh → 携带 If-None-Match: ETag-A → 304
3. UI 不显示 loading,沿用旧 snapshot
4. 1.5s 后再次 refresh → 后端生成新 ETag-B(若 worktree_mtime 或 index_mtime 变了)
5. 切 worktree → etagMap.clear() → 下次请求不带 If-None-Match
6. 改 filter → key 变化 → 旧 ETag 不复用
```

### 9.5 浏览器 DevTools 验证

- Network 面板:确认 4 端点请求 URL、method、payload、response shape
- Application → Local Storage:不写入新 key(本方案不持久化)
- Vue DevTools:确认 `stagedFiles` Set 在 stage/unstage/commit 后正确更新
- Console:无 `[pluginExtensionApi]` 错误

---

## 10. 风险与缓解

| # | 风险 | 缓解 |
|---|------|------|
| 1 | all scope 下无行内 stage/unstage,用户需切 scope | commit bar "全部暂存" 按钮兜底;Help tooltip 写明 |
| 2 | commit message 8192 字符上限被绕过 | commit dialog 加 char counter;> 7000 时 warning 色;提交按钮 disabled 当 length === 0 或 > 8192 |
| 3 | 多人/多终端并发操作导致 staged_files 与 dashboard 不同步 | 10s 轮询自然收敛;写操作后立即 refresh;接受"最终一致"语义 |
| 4 | ETag 1.5s 太短,实际命中率低 | 接受;网络开销可忽略;不优化 |
| 5 | History 视图在大仓库(1MB 截断)的处理 | 后端 `data.truncated=true` 时显示顶部黄色 banner(同 diff 截断处理) |
| 6 | 行内按钮密集(stage + unstage + restore + chevron 共 4-5 个) | hover 行时才显示 stage/unstage(与 restore 同 opacity 0.5/1 模式) |
| 7 | 中文文件名 / 路径 | 沿用现有 `git-diff` 编码处理,本方案不引入新逻辑 |
| 8 | "全部暂存"确认对话框与 restore 对话框状态空间重叠 | 两个 dialog 状态独立 ref(`confirmDialogOpen` for restore / `confirmStageAllOpen` for stage-all),互不干扰 |
| 9 | commit 后 refresh log 仅在 history 视图触发,其他视图不感知新 commit | 10s 轮询兜底;切到 history 视图时也会拉新 |
| 10 | 行内按钮 4 个(↑ ↓ ↩ ⌄)在小宽度(< 400px)侧边栏溢出 | 移动端 CSS:`@media (max-width: 760px)` 时进一步降低 font-size + padding;GitDiffFileItem 改用 `min-width: 0` + flex 收缩 |
| 11 | 写端点 failure 的 `data.stderr` 长度 | API 文档 ≤ 1 KB / 4 KB 已截断;snackbar `<pre>` 设 `max-height: 200px; overflow: auto` |
| 12 | 用户在 stage-all 确认弹窗打开时切 worktree | dispose 流程:`onBeforeUnmount` 中 `confirmStageAllOpen = false`;`selectedWorktree` watcher 检测弹窗状态,如打开则先关弹窗再切 |
| 13 | History 视图与 diff 视图的 selectedScope 概念冲突 | History 视图不显示 scope bar(scope 仅对 git-diff 有意义);scope 选择在切到 history 时保留但不渲染 |
| 14 | useSpcodeGitLog 的 ETag Map 内存泄漏 | `dispose()` 中 `etagMap.clear()`;切 worktree 时 clear;最大 64 个 key(后端限制,前端 Map 无强约束) |

---

## 11. 验收标准

### 11.1 功能验收

- [ ] 4 端点全部接入,UI 入口覆盖暂存/取消暂存/全部暂存/提交/历史
- [ ] 行内 stage/unstage 按钮按 scope 自动显隐(unstaged→↑, staged→↓, all→不显示)
- [ ] commit bar 显示 staged 数量,可"全部暂存" + "提交"
- [ ] "全部暂存"按钮点击后弹出二次确认对话框(决策 #16)
- [ ] 确认对话框显示未暂存文件数量(pendingStageAllCount)
- [ ] 确认后调用 `git-stage { all: true }`,失败走 toast
- [ ] commit dialog 支持 message 输入 + staged 文件预览 + stderr 显示(失败时)
- [ ] commit 失败可保留 staged 修改 message 重试
- [ ] commit message 字符数实时 counter(超 7000 警告)
- [ ] History tab 渲染 commit 列表,支持 ref/author/path/since/n 过滤 + load more
- [ ] ETag 缓存 1.5s 内复用(Network 面板可见 304)
- [ ] 切 worktree 后 ETag Map 清空(下个请求不带 If-None-Match)
- [ ] 切 worktree 时 stagedFiles 保留;切 project 时清空
- [ ] 3 语 i18n 同步,无 key 字面值回退
- [ ] 错误 reason 走 snackbar,`withStderr` 的展示 `<pre>` 块
- [ ] 移动端(≤ 760px)commit bar 仍可见可用

### 11.2 非功能验收

- [ ] 单元测试覆盖 4 端点 parser + reason 分类,覆盖率 ≥ 80%
- [ ] 写操作后立即 refresh(不依赖 10s 轮询)
- [ ] 行内按钮防双击(同文件 stage+unstage 互斥;不同文件可并发)
- [ ] 组件卸载时 AbortController 触发,isMounted guard 生效
- [ ] 切 worktree 时 ETag 不复用
- [ ] `ruff format .` + `ruff check .` 通过
- [ ] 无 `console.log` / `console.error` 残留(允许 `console.warn` 用于 drift / 304 等异常路径)

### 11.3 设计一致性

- [ ] 与 restore spec 共享 dialog / snackbar 模式
- [ ] 与 useSpcodeGitDiff / useSpcodeFileRestore 共享 state 模式
- [ ] 与现有 useModuleI18n / pluginExtensionApi 模式同构
- [ ] 与 2026-06-20 scope switcher 共享 scope pill 样式
- [ ] 注释用英文,关键逻辑附中文说明(项目 AGENTS.md 约定)

---

## 12. 实施步骤

| Step | 内容 | 依赖 | 估时 |
|------|------|------|------|
| 1 | `parseSpcodeGitWorkflow.ts` + 单元测试 | 无 | 2h |
| 2 | `useSpcodeGitStage.ts` + `useSpcodeGitUnstage.ts` | 1 | 1.5h |
| 3 | `useSpcodeGitCommit.ts` | 1 | 1.5h |
| 4 | `useSpcodeGitLog.ts`(含 ETag Map) | 1 | 2.5h |
| 5 | `GitDiffFileItem.vue` 行内 stage/unstage 按钮 | 2 | 1h |
| 6 | `GitDiffBodyContent.vue` 下传回调 | 2, 5 | 0.5h |
| 7 | `GitCommitDialog.vue` | 3 | 2h |
| 8 | `GitCommitBar.vue` | 3, 7 | 1h |
| 9 | `GitLogView.vue` | 4 | 2.5h |
| 10 | `GitDiffSidebar.vue` 集成 4 composable + commit bar + History tab + confirmStageAll dialog + snackbar 扩展 | 5, 6, 7, 8, 9 | 3h |
| 11 | 3 个 i18n locale 文件同步 | 10 | 1h |
| 12 | 手动冒烟测试(分 4 端点 × 多 reason 矩阵 + 移动端) | 11 | 2h |
| 13 | 修复冒烟发现的问题 + ruff format/check | 12 | 1h |
| 14 | 提交 PR,标题 `feat(dashboard): add git workflow controls to GitDiff sidebar` | 13 | — |

**总估时**:约 18.5h(2-3 个工作日)

### 12.1 拆分 PR 策略(可选)(P1-9 修复:明确依赖图与串/并行)

**依赖图**(DAG):

```
PR #1 (stage/unstage) ─┐
                       ├─→ PR #2 (commit) ─┐
                       │                    ├─→ PR #3 (history,可与 #2 并行,因都基于已合并的 #1)
                       └──────────────────┘
```

**合并顺序(强制)**:

1. **PR #1 必须先合**:`stagedFiles` ref 的写入者只有 stage/unstage 写端点;PR #2 (commit) 读 `stagedFiles` 渲染预览、读 `stagedFiles.size` 控制"提交"按钮 enabled —— 无 PR #1 则 PR #2 编译/运行失败。
2. **PR #2 与 PR #3 可并行**:两者都假设 PR #1 已合并(共享 `stagedFiles`),但 commit 与 history 互不读写对方的 composable,无功能耦合。**可由 2 个 reviewer 并行 review。**
3. **PR #2 与 PR #3 之间也互不阻塞**:PR #3 只读 `stagedFiles` 不写;PR #2 写 `stagedFiles` 但不读 history state。

**禁止的合并动作**:

- ❌ PR #1 合并前开 PR #2 / #3(CI 必失败)
- ❌ PR #2 / #3 合并前对 PR #1 做进一步修改(避免 force-push 引发 rebase 链)
- ❌ 三个 PR 任意一个 reviewer 在另一个 PR 合并前 approve 后者(避免后续 PR #1 改动导致 PR #2/3 冲突无人察觉)

**各 PR 内容细化**:

| PR | Steps | 文件改动 | 评审重点 |
|----|-------|---------|---------|
| **PR #1** | 1, 2, 5, 6, 10(部分:stage/unstage 处理), 11(部分:stage/unstage i18n) | `parseSpcodeGitWorkflow.ts`(part), `useSpcodeGitStage.ts`, `useSpcodeGitUnstage.ts`, `GitDiffFileItem.vue`, `GitDiffBodyContent.vue`, `GitDiffSidebar.vue`(partial), 3 个 i18n(partial) | 行内按钮 UX / 乐观语义 / 防双击 |
| **PR #2** | 3, 7, 8, 10(部分:commit bar + dialog), 11(部分:commit i18n) | `parseSpcodeGitWorkflow.ts`(part), `useSpcodeGitCommit.ts`, `GitCommitDialog.vue`, `GitCommitBar.vue`, `GitDiffSidebar.vue`(partial), 3 个 i18n(partial) | commit dialog UX / hook 失败 stderr / char counter |
| **PR #3** | 4, 9, 10(部分:history view), 11(部分:history i18n) | `parseSpcodeGitWorkflow.ts`(part), `useSpcodeGitLog.ts`, `GitLogView.vue`, `GitDiffSidebar.vue`(partial), 3 个 i18n(partial) | ETag 协议 / 空仓库分支 / 分页策略 |

**单 PR 合并时长估算**:
- PR #1: ~1.5 天(2 composable + 2 组件)
- PR #2: ~1.5 天(1 composable + 2 组件 + 弹窗)
- PR #3: ~1.5 天(1 composable + 1 组件 + 状态机最复杂)
- 合计: ~4.5 天(比单 PR 3 天长 50%,因 PR 间需要串行合并 + 各自 rebase base 分支)

### 12.2 回滚策略

本方案不修改 spcode 后端契约,不修改 `useSpcodeGitDiff` 等既有 composable,纯增量添加:

- 若 PR 整体回滚:删除 4 个新 composable + 2 个新 view 组件 + 1 个 dialog 组件,还原 `GitDiffSidebar.vue` 模板变更
- 单端点回滚:删除对应 composable + UI 入口,其他功能保留

---

## 附录 A:相关参考

### A.1 既有 spec 链接

- `docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md` — GitDiff 侧边栏 v1
- `docs/superpowers/specs/2026-06-18-git-worktree-switcher-design.md` — worktree 切换
- `docs/superpowers/specs/2026-06-20-git-diff-scope-switcher-design.md` — scope 切换
- `docs/superpowers/specs/2026-06-22-chatui-git-diff-file-restore-design.md` — restore 按钮(dialog / snackbar 模式)
- `astrbot_plugin_spcode_toolkit/docs/webapi-git-workflow-api.md` — 后端契约 v3.7

### A.2 关键文件位置

| 文件 | 路径 |
|------|------|
| GitDiff 侧边栏 | `dashboard/src/components/chat/GitDiffSidebar.vue` |
| 文件行 | `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue` |
| 列表容器 | `dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue` |
| git-diff composable | `dashboard/src/composables/useSpcodeGitDiff.ts` |
| file-restore composable | `dashboard/src/composables/useSpcodeFileRestore.ts`(参考模式) |
| project status | `dashboard/src/composables/useSpcodeProjectStatus.ts` |
| plugin API 客户端 | `dashboard/src/api/v1.ts:1299-1316` |
| i18n chat 模块 | `dashboard/src/i18n/locales/{zh-CN,en-US,ru-RU}/features/chat.json` |
| 解析器单测模板 | `dashboard/tests/parseSpcodeFileRestore.test.mjs` |

### A.3 词汇表

| 术语 | 定义 |
|------|------|
| umo | Unique Message Origin,会话唯一标识符,spcode 用它索引 `_loaded_projects` |
| worktree | git worktree,同一仓库的多个工作区;primary 是主工作区 |
| scope | diff 范围,3 个值:unstaged / staged / all |
| staged | 已 `git add` 加入暂存区(index) |
| unstaged | 工作区相对 index 的修改(未 `git add`) |
| ETag | HTTP 缓存协商标识,`W/"<sha>-<mtime>-<imtime>"` |
| ReasonCode | 业务失败 reason 字符串,前端直接当 i18n key |

---

**作者**:elecvoid243 | **最后更新**:2026-06-24 | **版本**:v1.2 (Approved)

---

## 修订记录

### v1.2 (2026-06-24) — Critical Review 修复

**Critical review 报告**:`chat-message 中 critical review 报告`(`P0=6 / P1=10 / P2=7`)。

**P0 必修(6 项全部修复)**:

| # | 问题 | 修复位置 |
|---|------|---------|
| P0-1 | `LogFetchState` 类型定义缺失 | §3.3.5 — 补充完整联合类型 + `prevSnapshot` 变量说明 |
| P0-2 | Snackbar stderr 字段双重定义矛盾 | §5.3 + §6.8 — 统一为 `SnackbarState.stderr?: string` 字段,不再拼字符串 |
| P0-3 | `empty_repository` 语义错误(被当 error) | §5.1 + §5.2 — 从 reason 字典移除,改为 GitLogView 模板分支 |
| P0-4 | §6.5.1 "清空旧 ETag" 冗余 | §6.5.1 — 删除冗余语句,改为 note 说明 ETag key 维度自动失效 |
| P0-5 | `formatRelativeTime` 函数实现规则缺失 | §6.5.2 — 补充完整实现 + 边界条件 |
| P0-6 | `git_error` i18n 与 stderr 关系不清 | §5.1 注释 + §6.8 模板 + §7 — 明确 `withStderr` 范围,模板分两情况 |

**P1 建议(10 项全部修复)**:

| # | 问题 | 修复位置 |
|---|------|---------|
| P1-1 | `GitDiffFileItem` 怎么拿 `selectedScope` | §3.2 + §6.2.4 — 改用 `showStage` / `showUnstage` 布尔 props,父级派生 |
| P1-2 | 状态机未显式标注不变量 | §3.3 全部子节 — 每条状态转换显式列出 `stagedFiles` / dialog 状态变化 |
| P1-3 | `pendingStageAllCount` 填充时机不明确 | §3.3.3 — 进入 `CONFIRMING` 时同步计算 |
| P1-4 | `isStaging` props 是 boolean 还是 Set | §3.2 + §6.2.4 — 补充完整派生链 Sidebar → BodyContent → FileItem |
| P1-5 | `unstagedCount` 在不同 scope 下含义 | §6.7.1 — 分 scope 列出公式与含义 |
| P1-6 | 字符数 counter 7000 警告色未定义 | §6.4.2 — 明确 Vuetify token + 3 段颜色阈值 |
| P1-7 | `GitLogView` props 模糊 | §3.2 — 完整 props/emits/内部状态/派生 |
| P1-8 | 单测覆盖度不足 | §9.2 — 追加 5 个边界 test(根 commit / 失败 sha / 缺字段 / truncated / 空 commits) |
| P1-9 | PR 拆分依赖关系不明确 | §12.1 — 补充 DAG + 合并顺序 + 禁止动作 + 评审重点 |
| P1-10 | `classifyReason` 返回值不明确 | §5.1 — 统一为 `ReasonMeta` 类型,与单测一致 |

**P2 可推迟(7 项暂不修,记录在此供未来改进)**:

| # | 位置 | 问题 | 影响 |
|---|------|------|------|
| P2-1 | §7 `relativeTime.exactDate` | `{date}` 格式未定义 | 实施时补一行 `date: 'YYYY-MM-DD'` |
| P2-2 | §7 `commit.bar` | `stagedCountZero` 与 `commitDisabledHint` 区别 | 实施时 inline 注释即可 |
| P2-3 | §3.2 | `GitCommitDialog` 缺 `v-model` 双向绑定说明 | 已在 v1.2 修复时同步补上 |
| P2-4 | §8 | `GitCommitBar.vue` 估时 1h 偏多 | 调为 0.5h(可推迟) |
| P2-5 | §10 风险 #6 | 行内按钮密度 | 实施时如出现溢出,补 hover 才显示机制 |
| P2-6 | §6.4.1 草图 | 字符对齐 | 在 CSS 章节补 flexbox 说明 |
| P2-7 | §2 决策 #16 vs #20 | 表面矛盾 | 已加交叉引用注释 |

---

**作者**:elecvoid243 | **最后更新**:2026-06-24 | **版本**:v1.2 (Approved)
