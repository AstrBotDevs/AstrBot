# GitDiff 侧边栏 ↩ 文件恢复按钮

| 项目 | 内容 |
|------|------|
| 主题 | 在 dashboard 的 GitDiff 侧边栏中,每个文件行右侧新增"恢复"按钮,调用 `spcode_toolkit` 插件的 `POST /spcode/file-restore` 端点实现 `git checkout -- <file>` 语义 |
| 日期 | 2026-06-22 |
| 作者 | elecvoid243 |
| 状态 | Draft — 待用户审阅 |
| 关联代码(前端) | `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue`、`dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue`、`dashboard/src/components/chat/GitDiffSidebar.vue` |
| 关联代码(后端) | `astrbot_plugin_spcode_toolkit` v3.5:`POST /spcode/file-restore`(已实现,本 spec 不修改) |
| 前置 spec | `docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md`(GitDiff 侧边栏 v1)<br>`docs/superpowers/specs/2026-06-18-git-worktree-switcher-design.md`(worktree 切换)<br>`docs/superpowers/specs/2026-06-20-git-diff-scope-switcher-design.md`(scope 切换)<br>`astrbot_plugin_spcode_toolkit/docs/superpowers/specs/2026-06-22-file-restore-endpoint-design.md`(后端契约) |

---

## 1. 背景与目标

### 1.1 现状

- `astrbot_plugin_spcode_toolkit` v3.5 已上线 `POST /spcode/file-restore` 端点,提供 `git checkout -- <file>` 写操作能力(详见后端 spec §1–§9)
- `dashboard` 的 `GitDiffFileItem.vue` 渲染 `git diff` 文件列表中的每一行,结构为:状态图标 + 文件路径 span + 添加/删除统计 + 展开箭头
- 当前**没有任何 UI 入口**可以从 dashboard 触发恢复操作:用户必须切到 terminal 手敲 `git checkout -- path/to/file`

### 1.2 目标

在每个 `GitDiffFileItem` 的文件路径右侧增加一个"恢复"按钮,点击后:

1. 弹出二次确认对话框(避免误触)
2. 用户确认后调用 `POST /spcode/file-restore`
3. 成功:toast 提示 + 立即刷新当前 diff 列表(让该行消失)
4. 失败:toast 提示具体 reason,不动列表

### 1.3 非目标(显式不做)

- ❌ **不**做客户端预检(直接用后端做权威)
- ❌ **不**做批量恢复(后端 v1 不支持)
- ❌ **不**支持 staged / HEAD 恢复(scope 默认 `unstaged`,不传递)
- ❌ **不**做撤销栈/快捷键(如 Ctrl+Z)
- ❌ **不**改后端契约(只消费既有端点)
- ❌ **不**改 `useSpcodeGitDiff` 的轮询节奏(只在成功后**追加**一次手动 refresh)

---

## 2. 设计决策(已与用户确认)

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 客户端预检 | **不做**;所有 reason 走 toast | 后端是权威;预检与真实状态可能不一致(用户在另一终端已恢复);轮询已 10s,过期自然收敛 |
| 2 | 成功后的列表刷新 | **立即调用 `composable.refresh()`** | UI 立即收敛,所见即所恢复;toast 已能定位 |
| 3 | 失败时的错误反馈 | **全局 `v-snackbar`**,reason → i18n 映射 | 与 `GitDiffBodyContent` 既有 REASON_I18N_KEYS 风格一致;不破坏列表布局;统一样式 |
| 4 | HTML 嵌套按钮问题 | **重构外层 row 为 `<div role="button" tabindex=0>` + 键盘事件,内层 ↩ 用真 `<button>`** | 当前 `GitDiffFileItem.vue:24` 是 `<button>`;HTML5 规范禁止 button-in-button 嵌套(交互模型冲突 + 可访问性树混乱),必须重构外层;`@click.stop` 阻断冒泡;`role="button"` + `tabindex=0` 保留键盘可达 |
| 5 | 架构模式 | **composable 在 `GitDiffSidebar` 持有,回调下传** | 顶层有 `selectedWorktree` / `composable.refresh` / snackbar 挂载点;数据流单向;与既有 `useSpcodeGitDiff` 模式同构 |
| 6 | 确认对话框组件 | **本地内联 `<v-dialog persistent>`** in `GitDiffSidebar.vue`,**不**复用 `useConfirmDialog()` | 验证 `dashboard/src/components/ConfirmDialog.vue:8-9` 按钮文本与颜色**硬编码**,不接受 `confirmText`/`color`;`ConfirmDialogOptions`(`utils/confirmDialog.ts:3-6`) 只支持 `title`+`message`;且 `ConfirmDialog.vue` 缺少 `persistent` 属性,点击遮罩关闭会悬挂 Promise(已存在 bug,不在本 spec 范围)。本地 v-dialog 完全控制标题/正文/按钮文本/按钮颜色/遮罩行为,与 `FileBrowserFilePreview.vue:41-112` 既有 dialog 模式一致 |
| 7 | 同时点击多个文件 | **限制单文件**(单一 `restoringFile` ref) | 后续点击的按钮 disabled + spinner;简单可预测 |
| 8 | i18n 命名空间 | **3 个 locale 都加 `diffSidebar.restore.*` 键** | 与既有 diffSidebar 结构对齐(已有 4 个嵌套 namespace);新功能必须全语言 |
| 9 | 键盘可达性 | **Tab 到 ↩,Enter 触发;Esc 关闭 snackbar(Vuetify 默认)** | 默认免费,显式写出来避免未来改坏 |

---

## 3. 数据流与状态

### 3.1 现有数据流(节选)

```
GitDiffSidebar (持有 useSpcodeGitDiff)
  └─> GitDiffBodyContent (state: GitDiffFetchState, expanded: Set<string>)
        └─> GitDiffFileItem[] (file: SpcodeGitDiffFile, expanded: boolean)
              ├─ <span class="git-diff-file-path">{{ file.path }}</span>
              ├─ <span class="git-diff-file-stats">+{{ add }} −{{ del }}</span>
              └─ <v-icon> chevron </v-icon>
```

### 3.2 改造后数据流

```
GitDiffSidebar
  ├─ useSpcodeGitDiff (existing) → 已有 refresh()
  ├─ useSpcodeFileRestore (NEW)  → restore({file, worktree?, umo}) → RestoreResult
  ├─ useSpcodeProjectStatus (existing) → 取 umo
  ├─ selectedWorktree (existing) → 取 worktree
  ├─ restoringFile: ref<string|null> (NEW, 顶层)
  ├─ snackbar: ref<{show, message, color}> (NEW, 顶层)
  └─ onFileRestore(path: string) (NEW)
        ↓ callback
GitDiffBodyContent
  └─ onRestore 事件 (NEW)  ← re-emit
        ↓ callback
GitDiffFileItem
  └─ isRestoring: boolean prop (NEW)
  └─ onRestore: (path) => void prop (NEW)
        ├─ ↩ <button> @click.stop → emit('restore', file.path)
        └─ 加载态:isRestoring=true → v-progress-circular, disabled
```

**关键不变量**:

- `restoringFile` 同一时刻最多一个值(`null` 表示无请求)
- `isRestoring` 由父级 `restoringFile === file.path` 派生(避免双向状态)
- 失败时**不**刷新列表(只 toast 错误)
- 成功时**立即**调用 `composable.refresh()`(覆盖 10s 轮询)
- 重复点击防护: ↩ 按钮 `disabled` 当 `isRestoring` 为 true

### 3.3 状态机

```
GitDiffFileItem 按钮:
  IDLE ─click→ CONFIRMING(等待 useConfirmDialog 结果)
  CONFIRMING ─cancel→ IDLE
  CONFIRMING ─ok→ RESTORING(restoreFile = file.path)
  RESTORING ─success→ IDLE(父级调用 refresh,本行从列表消失 → 组件卸载)
  RESTORING ─failure→ IDLE(toast 错误)
  RESTORING ─network err→ IDLE(toast network)
  RESTORING ─aborted→ IDLE(切换 worktree / 卸载项目)
```

`restoringFile` 是**全 sidebar 单值**,所以 `RESTORING` 状态在 UI 上一目了然(只有一行的 ↩ 在转圈)。

---

## 4. URL 契约(消费既有后端)

```
POST /plugins/extensions/spcode/file-restore
Content-Type: application/json
Body: { umo?: string, worktree?: string, file: string }

Response 200:
{
  "status": "ok",
  "data": {
    "restored": boolean,
    "reason": string | null,
    "file": string,
    "umo": string | null,
    "worktree": string,
    "directory": string | null,
    "scope": "unstaged",
    "elapsed_ms": number,
    "stderr": string
  }
}
```

**前端组装**:
- `file` = `GitDiffFileItem.file.path`(已为仓库相对路径,与 `files_changed[].path` 零摩擦)
- `umo` = `spcodeStatus.status.value.umo`(项目未载入时不渲染按钮 — 见 §6.2)
- `worktree` = `selectedWorktree.value`(为 null 时不传,后端走主 worktree)

**前端不解析**:`scope`、`elapsed_ms`、`stderr`(成功路径完全不展示;失败路径仅 `git_error` 时展示 stderr,见 §5)

> 跨引用:URL 路径由 `dashboard/src/api/v1.ts:1299-1316` 的 `pluginExtensionApi.post('spcode/file-restore', body)` 生成,后端注册于 `astrbot_plugin_spcode_toolkit/main.py:2044`(`route="/spcode/file-restore"`)。如果未来要改路由,需同步两处。

---

## 5. 错误处理矩阵

新建 `RESTORE_REASON_I18N_KEYS`(放 `GitDiffSidebar.vue` 模块顶部,**与 `GitDiffBodyContent`/`FileBrowserFilePreview` 既有 `error.reason.{code}` 嵌套结构同构**):

| 后端 `data.reason` | i18n key | toast color | 备注 |
|--------------------|----------|-------------|------|
| `null`(成功) | `restore.success({path})` | `success` | 列表立即 refresh |
| `invalid_body` | `restore.error.reason.invalid_body` | `error` | 前端不会主动构造这种 body |
| `missing_file` | `restore.error.reason.missing_file` | `error` | 理论不可达(按钮必带 file) |
| `feature_disabled` | `restore.error.reason.feature_disabled` | `error` | 提示检查 spcode 配置 |
| `no_project_loaded` | `restore.error.reason.no_project_loaded` | `error` | 理论不可达(未载入不渲染按钮) |
| `directory_missing` | `restore.error.reason.directory_missing` | `error` | 加载目录被删 |
| `not_a_git_repo` | `restore.error.reason.not_a_git_repo` | `error` | 加载的不是 git 目录 |
| `worktree_invalid` | `restore.error.reason.worktree_invalid` | `error` | worktree 路径异常 |
| `git_unavailable` | `restore.error.reason.git_unavailable` | `error` | 服务端无 git |
| `path_unsafe` | `restore.error.reason.path_unsafe` | `error` | 文件路径被 4 步防御拒绝 |
| `file_not_found` | `restore.error.reason.file_not_found` | `error` | 文件在 disk 上消失 |
| `not_modified` | `restore.error.reason.not_modified` | `warning` | 已与 index 一致(无操作) |
| `untracked_file` | `restore.error.reason.untracked_file` | `warning` | git checkout 拒绝;**stderr 静默**(见 §10 M2 注释) |
| `git_error` | `restore.error.reason.git_error({stderr})` | `error` | 其他 git 错误,带 stderr |
| axios `ERR_NETWORK` | `restore.error.reason.network` | `error` | 前端拦截 |
| 其他 | `restore.error.reason.unknown({reason})` | `error` | 兜底 |

`color` 在 `warning` (amber)与 `error` (red) 之间区分:**`not_modified` / `untracked_file` 是"不危险但失败"**,用 `warning` 提示色(避免误以为"系统出错")。

---

## 6. UI / UX 细节

### 6.1 按钮位置与样式

- 位置:`<span class="git-diff-file-path">` 右侧、`<span class="git-diff-file-stats">` 左侧
- 视觉:Vuetify `v-btn` icon variant,`size="x-small"`,`density="comfortable"`,`variant="text"`,`color="primary"`
- 图标:`mdi-restore`(国际通用"撤销/恢复"图标)
- 默认可见性:`opacity: 0.5`,hover 行时 `opacity: 1`(避免静止状态视觉杂乱)
- 加载态:`v-progress-circular size=14` 替换图标,`aria-busy="true"`
- 焦点环:Vuetify 默认;不可用时 `disabled` + `opacity: 0.3`

### 6.2 按钮可见性条件(派生 computed)

```ts
const showRestoreButton = computed(() => {
  // 1. 项目必须已加载
  if (!spcodeStatus.status.value.loaded) return false;
  // 2. umo 必须存在(后端要据此查找 _loaded_projects)
  if (!spcodeStatus.status.value.umo) return false;
  // 3. 文件状态必须可恢复(M/A/D/R/T/unknown 均可;但 D 在 restore
  //    时 git 会拒绝——交给后端 reason 处理,前端不做过滤)
  return true;
});
```

> 注:Q1 决策"不做客户端预检",但 `loaded` / `umo` 是**前置**而非预检 — 后端会直接 `no_project_loaded`,前端拦下可省一次请求。

### 6.3 二次确认对话框(内联 `<v-dialog>`)

`GitDiffSidebar.vue` 模板中本地内联一个 `<v-dialog v-model="confirmDialogOpen" persistent max-width="440">`,**不**走 `useConfirmDialog()`(见 §2 决策 #6)。理由:本 spec 需要自定义按钮文本/颜色与 persistent 行为,既有 `ConfirmDialog` 不支持。

- 标题:`restore.confirmTitle`
- 正文:`restore.confirmMessage({path})` — **必须包含完整文件路径**(避免误恢复)
- 主按钮:`restore.confirmAction`(`color="warning"`,`variant="flat"`,因为是破坏性操作)
- 取消按钮:`restore.confirmCancel`(`variant="text"`)
- `persistent`:遮罩点击**不**关闭,强制显式选择(避免被误触跳过)
- `Esc` 关闭等同取消(由 `<v-dialog>` 默认行为提供;`persistent` 不影响 Esc)
- 状态:`confirmDialogOpen` (ref<boolean>) + `confirmTargetPath` (ref<string|null>)

### 6.4 Snackbar

- 挂载在 `GitDiffSidebar` 模板底部(`<v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="...">`)
- 成功:`color="success"`,`timeout=4000`
- 失败:`color="error"` 或 `color="warning"`,`timeout=6000`(给用户更多时间阅读 reason)
- 位置:`location="bottom right"`(与 sidebar 同侧,不挡聊天内容)
- 多条排队:Vue ref 单值 → 后续覆盖前一条(本场景低频,接受)

### 6.5 键盘可达性

- 外层 row(已重构为 `<div role="button" tabindex=0>`):Enter / Space 触发 toggle
- ↩ 按钮:Tab 聚焦,Enter 触发 restore,Esc 关闭 confirm
- Snackbar:Vuetify 默认 Esc 关闭

---

## 7. i18n 键结构

### 7.1 zh-CN

```json
"diffSidebar": {
  "...": "...",
  "restore": {
    "button": "恢复",
    "buttonAria": "恢复文件 {path}",
    "confirmTitle": "恢复文件？",
    "confirmMessage": "将丢弃 \"{path}\" 相对于 index 的所有改动，该操作不可撤销。",
    "confirmAction": "恢复",
    "confirmCancel": "取消",
    "success": "已恢复 {path}",
    "error": {
      "reason": {
        "network": "网络连接失败",
        "unknown": "恢复失败（{reason}）",
        "invalid_body": "请求格式错误",
        "missing_file": "未指定文件",
        "feature_disabled": "功能未启用（请检查 spcode 配置 agentsmd_enabled / codegraph_enabled）",
        "no_project_loaded": "项目未载入",
        "directory_missing": "已加载的目录不存在",
        "not_a_git_repo": "当前目录不是 Git 仓库",
        "worktree_invalid": "目标 worktree 无效",
        "git_unavailable": "未检测到 git 可执行文件",
        "path_unsafe": "文件路径不安全（已拒绝）",
        "file_not_found": "文件不存在",
        "not_modified": "文件无未暂存改动",
        "untracked_file": "未跟踪的文件无法恢复（请用 git rm --cached 或 git add）",
        "git_error": "Git 执行失败（{stderr}）"
      }
    }
  }
}
```

### 7.2 en-US

```json
"restore": {
  "button": "Restore",
  "buttonAria": "Restore file {path}",
  "confirmTitle": "Restore file?",
  "confirmMessage": "This will discard all uncommitted changes to \"{path}\". This cannot be undone.",
  "confirmAction": "Restore",
  "confirmCancel": "Cancel",
  "success": "Restored {path}",
  "error": {
    "reason": {
      "network": "Network error",
      "unknown": "Restore failed ({reason})",
      "invalid_body": "Malformed request",
      "missing_file": "File not specified",
      "feature_disabled": "Feature disabled (check spcode config agentsmd_enabled / codegraph_enabled)",
      "no_project_loaded": "No project loaded",
      "directory_missing": "Loaded directory no longer exists",
      "not_a_git_repo": "Current directory is not a Git repository",
      "worktree_invalid": "Target worktree is invalid",
      "git_unavailable": "Git executable not found",
      "path_unsafe": "File path is unsafe (rejected)",
      "file_not_found": "File does not exist",
      "not_modified": "File has no uncommitted changes",
      "untracked_file": "Cannot restore an untracked file (use git rm --cached or git add)",
      "git_error": "Git execution failed ({stderr})"
    }
  }
}
```

### 7.3 ru-RU

```json
"restore": {
  "button": "Восстановить",
  "buttonAria": "Восстановить файл {path}",
  "confirmTitle": "Восстановить файл?",
  "confirmMessage": "Это отменит все незафиксированные изменения в \"{path}\". Действие необратимо.",
  "confirmAction": "Восстановить",
  "confirmCancel": "Отмена",
  "success": "Восстановлено: {path}",
  "error": {
    "reason": {
      "network": "Ошибка сети",
      "unknown": "Не удалось восстановить ({reason})",
      "invalid_body": "Некорректный запрос",
      "missing_file": "Файл не указан",
      "feature_disabled": "Функция отключена (проверьте spcode config agentsmd_enabled / codegraph_enabled)",
      "no_project_loaded": "Проект не загружен",
      "directory_missing": "Загруженный каталог больше не существует",
      "not_a_git_repo": "Текущий каталог не является репозиторием Git",
      "worktree_invalid": "Целевое worktree недопустимо",
      "git_unavailable": "Исполняемый файл git не найден",
      "path_unsafe": "Путь к файлу небезопасен (отклонено)",
      "file_not_found": "Файл не существует",
      "not_modified": "Файл не имеет незафиксированных изменений",
      "untracked_file": "Невозможно восстановить неотслеживаемый файл (используйте git rm --cached или git add)",
      "git_error": "Ошибка выполнения Git ({stderr})"
    }
  }
}
```

> 所有 key 必须三语同步,缺一会导致 `useModuleI18n` 静默回退到 key 字面值(已观察到的 footgun)。

---

## 8. 文件清单

| 文件 | 类型 | 行数预估 | 职责 |
|------|------|---------|------|
| `dashboard/src/composables/parseSpcodeFileRestore.ts` | 新增 | +60 | 解析响应;导出 `SpcodeFileRestoreSnapshot`、`RestoreReason` 联合类型、`classifyReason` |
| `dashboard/src/composables/useSpcodeFileRestore.ts` | 新增 | +120 | POST 包装;`restore({file, worktree?, umo})` → `RestoreResult`;AbortController 防双击;classifyError |
| `dashboard/tests/parseSpcodeFileRestore.test.mjs` | 新增 | +80 | 单元测试:解析 success / failure envelope、reason 分类、缺 `data` 抛错 |
| `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue` | 修改 | +55 / -12 | 重构 row 为 `<div role="button">` + 键盘事件(Enter/Space 触发 toggle);新增 ↩ `<button>` + `@click.stop`;新增 CSS 块(.git-diff-file-restore:focus-ring/opacity/spinner ~15 行);接收 `onRestore` / `isRestoring` props |
| `dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue` | 修改 | +15 | 接收 `onRestore` callback,re-emit 给 `GitDiffFileItem`;增加 `onRestore` 事件 |
| `dashboard/src/components/chat/GitDiffSidebar.vue` | 修改 | +110 | 实例化 `useSpcodeFileRestore()`;实现 `onFileRestore(path)`;v-snackbar 挂载;**本地内联 `<v-dialog persistent>` 确认框**;RESTORE_REASON_I18N_KEYS 映射;将 `onRestore` 回调下传 |
| `dashboard/src/i18n/locales/zh-CN/features/chat.json` | 修改 | +28 | `diffSidebar.restore.*` 命名空间(§7.1) |
| `dashboard/src/i18n/locales/en-US/features/chat.json` | 修改 | +28 | `diffSidebar.restore.*` 命名空间(§7.2) |
| `dashboard/src/i18n/locales/ru-RU/features/chat.json` | 修改 | +28 | `diffSidebar.restore.*` 命名空间(§7.3) |
| `docs/superpowers/specs/2026-06-22-chatui-git-diff-file-restore-design.md` | 新增 | — | 本文档 |

**总计**:新增 ~260 行,修改 ~195 行(净增),3 个 i18n 文件各 +28 行。

**关于 2 文件拆分(`parseSpcodeFileRestore.ts` + `useSpcodeFileRestore.ts`)的 AGENTS.md 合规说明**:

`AGENTS.md` "No Unnecessary Helpers" 规则要求"3 处以上复用"或"极高复杂度"才可抽 helper。本 spec 的解析器(`parseSpcodeFileRestore.ts`)虽然只被 `useSpcodeFileRestore` 一处使用,**但**它必须被 `dashboard/tests/parseSpcodeFileRestore.test.mjs` 单独导入做单元测试(在 Node `node --test` 环境下,Vue 组件 / composable 难以 mock,而纯函数解析器零依赖可测)。**2 文件拆分与既有 `parseSpcodeGitDiff.ts` + `useSpcodeGitDiff.ts` 同构**(参见 `dashboard/src/composables/parseSpcodeGitDiff.ts` vs `useSpcodeGitDiff.ts`)。YAGNI 与代码对称性的取舍在两难之间,本 spec 选择与既有模式对齐。

---

## 9. 测试策略

### 9.1 后端测试

**不修改**。`astrbot_plugin_spcode_toolkit/tests/test_file_restore.py` 26 个用例已覆盖所有 reason 与边界。

### 9.2 前端单元测试(`parseSpcodeFileRestore.test.mjs`)

```ts
test("parses success envelope") {
  const r = parseSpcodeFileRestore({status: "ok", data: {restored: true, reason: null, file: "x.py", ...}});
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.restored, true);
  assert.equal(r.snapshot.reason, null);
}

test("parses failure envelope") {
  const r = parseSpcodeFileRestore({status: "ok", data: {restored: false, reason: "untracked_file", ...}});
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.restored, false);
  assert.equal(r.snapshot.reason, "untracked_file");
}

test("classifies unknown reason as 'unknown'") {
  assert.equal(classifyReason("foo_bar_baz"), "unknown");
}

test("throws on missing data field") {
  assert.throws(() => parseSpcodeFileRestore({status: "ok"}));
}
```

### 9.3 前端手动冒烟(无 Vue 组件测试框架,与既有约定一致)

1. 加载项目 + 修改一个文件 → diff 列表出现该行
2. 点 ↩ → 弹出 confirm → 取消 → 列表不变
3. 点 ↩ → 弹出 confirm → 确认 → spinner → success snackbar → 该行从列表消失
4. 新建一个未 `git add` 的文件 → diff 列表出现(以 untracked 形式)
5. 点 ↩ → spinner → warning snackbar 显示 `未跟踪的文件无法恢复`
6. Tab 聚焦 ↩ → Enter 触发(键盘可达)
7. 切换 worktree 后,正在 RESTORING 的请求被 AbortController 取消(无副作用)
8. 卸载项目 → ↩ 按钮消失(`showRestoreButton` 返回 false)
9. 刷新页面 → 旧 i18n locale 仍能正常显示按钮文本

---

## 10. 风险与缓解

| 风险 | 严重性 | 缓解 |
|------|--------|------|
| 用户误点 ↩ 恢复整个文件改动 | 高 | 强制 confirm 弹窗,正文**必含**完整文件路径 |
| 同时点击多个 ↩ | 中 | 单一 `restoringFile`;后续点击 disabled + spinner |
| 网络慢时按钮一直转圈 | 中 | axios 默认 10s 超时;超时后 toast `network` |
| 后端拒绝(`path_unsafe` 等) | 低 | toast 明确显示 reason;不修改文件;不刷新 |
| 成功后用户的展开内容被清空 | 低 | Q2=B 决策已接受;`composable.refresh` 触发后该行从列表消失(连同展开内容) |
| i18n 漏译 → UI 显示 key 字面值 | 低 | §7 强制 3 语言同步;CI(未来)可加 vue-i18n 校验 |
| `untracked_file` 的 stderr(`git status --porcelain` 输出)被静默不显示 | 低 | UX 取舍:`not_modified` / `untracked_file` 是"不危险但失败",用 `warning` 颜色(非 `error`);它们各自的 reason 文案已能定位问题(`文件无未暂存改动` / `未跟踪的文件无法恢复`);如果未来需要,在 toast 加一个 "details" 链接展开 stderr 是 v2 范畴(见 §13 开放问题) |
| AbortController 取消后用户切回看到 stale spinner | 低 | 取消后立即清 `restoringFile`;`isMounted` 检查在 `useSpcodeFileRestore` 入口 |
| row 重构为 div + role=button 破坏现有可访问性 | 低 | 显式加 `tabindex=0` + `@keydown.enter/space`;与 `GitDiffSidebar.vue` 既有模式一致 |
| 既有 `GitDiffFileItem` 单元快照测试(Vitest 之类)被破坏 | 低 | dashboard 无 Vue 组件测试;但若未来加测试,本次修改需补 |

---

## 11. 迁移 / 兼容性

- **新增功能,无破坏**:既有 `GitDiffFileItem` 的 props / events 不变(只新增 `onRestore` / `isRestoring`);不传新 prop 时按钮不渲染(`v-if="onRestore"` 守卫)
- **既有事件**:`@toggle` 行为不变;新增 `@restore` 事件
- **既有 CSS class**:`.git-diff-file-path` / `.git-diff-file-stats` / `.git-diff-file-chevron` 全部保留;新增 `.git-diff-file-restore` 按钮样式
- **既有 composable**:`useSpcodeGitDiff` / `useSpcodeProjectStatus` / `useSpcodeWorktrees` 完全不动
- **既有 i18n key**:`diffSidebar.*` 下所有既有 key 不动,只新增 `restore.*` 子树

---

## 12. 实施约束

- Vue 3.3.4 + Vuetify 3.7.11 + vue-i18n 11(项目既定)
- axios 1.13.5(项目既定,`pluginExtensionApi.post` 已存在)
- TypeScript 严格模式;新增 `parseSpcodeFileRestore.ts` 必含导出类型
- 不引入新依赖
- 不修改后端代码
- 不修改 `_conf_schema.json` / `metadata.yaml`
- `pnpm dev` / `pnpm typecheck` / `pnpm lint` 必须通过
- 测试: `node --test tests/parseSpcodeFileRestore.test.mjs` 必须全 PASS
- **关于 `pnpm test` 脚本的缺位**:`dashboard/package.json:6-17` **没有** `test` 脚本(只有 `dev` / `build` / `typecheck` / `lint`)。本 spec 单元测试通过 `node --test` 直接调用(项目已有 5 个 `tests/*.test.mjs` 走同一模式,见 `tests/imeInput.test.mjs` 等)。**可选 PR**:在 `package.json` 新增 `"test:unit": "node --test tests/*.test.mjs"`,与 `typecheck` / `lint` 对齐。本 spec 不强制要求(避免范围蔓延) |

---

## 13. 开放问题(留待 PR review)

- 是否需要在 refresh 之前加一个"乐观更新"阶段(立即从列表移除,失败时再回滚)?**不** — 失败概率低,操作可逆(git reflog),增加复杂度不划算
- 是否需要在 v-snackbar 里加一个"撤销"按钮(短期内回退 `git checkout`)?**不** — v1 范围之外,需要后端先支持 inverse 端点
- 是否要把 toast 文案 i18n 中的 `path` 截断(避免长路径撑爆 viewport)?**不截断** — Vuetify snackbar 默认行为是文本溢出截断(用户视觉上看到 "已恢复 F:\github\Astr..."),但**完整路径已在 confirm 对话框显示过**(`restore.confirmMessage({path})`),用户点确认前已看过完整路径,toast 截断不损失关键信息;真要查看可用 `useSpcodeFileBrowser` 跳到该文件验证。**不**引入截断函数(避免增加 ~10 行 helper 又一个 YAGNI 风险点)
