# GitDiff 侧边栏 ↩ 文件恢复按钮 — 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 dashboard 的 `GitDiffFileItem` 文件路径右侧新增"恢复"按钮,点击后弹确认框 → 确认后调用既有 `POST /spcode/file-restore` 端点 → 成功 toast + 列表立即刷新;失败 toast 显示具体 reason。

**Architecture:**
- 新增 2 个 composable (`parseSpcodeFileRestore` + `useSpcodeFileRestore`) 镜像既有 `parseSpcodeGitDiff` + `useSpcodeGitDiff` 同构模式
- composable 实例在 `GitDiffSidebar` 顶层持有(因需要 `selectedWorktree` + 触发顶层 snackbar + 调用既有 `composable.refresh()`)
- `GitDiffFileItem` 接收 `onRestore` / `isRestoring` props,触发 emit 由父级处理
- 二次确认用本地内联 `<v-dialog persistent>`,**不**复用 `useConfirmDialog()`(见 spec §2 决策 #6)
- i18n 三语(zh-CN / en-US / ru-RU)同步加 `diffSidebar.restore.*` 嵌套命名空间

**Tech Stack:** Vue 3.3.4 + Vuetify 3.7.11 + TypeScript + axios 1.13.5 + vue-i18n 11 + Node.js 内建 `node --test` 框架

**前置 spec:** `docs/superpowers/specs/2026-06-22-chatui-git-diff-file-restore-design.md`(已通过 2 轮 review loop,APPROVED)

**后端契约(只读):** `astrbot_plugin_spcode_toolkit` v3.5 `POST /spcode/file-restore`(已实现)

---

## File Structure

### 新增文件

| 文件 | 职责 |
|------|------|
| `dashboard/src/composables/parseSpcodeFileRestore.ts` | 纯函数:解析后端响应;导出 `SpcodeFileRestoreSnapshot`、`RestoreReason`、`classifyReason` |
| `dashboard/src/composables/useSpcodeFileRestore.ts` | Vue composable:POST 包装;`restore({file, worktree?, umo})` → `RestoreResult`;AbortController;classifyError |
| `dashboard/tests/parseSpcodeFileRestore.test.mjs` | Node `node --test` 单元测试:success / failure envelope、reason 分类、缺 `data` 抛错 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue` | 外层 row `<button>` → `<div role="button" tabindex=0>` + 键盘事件;新增 ↩ `<button>` + `@click.stop`;新增 `.git-diff-file-restore` CSS;接收 `onRestore` / `isRestoring` props |
| `dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue` | 接收 `onRestore` callback;re-emit `'restore'` 事件给 `GitDiffFileItem` |
| `dashboard/src/components/chat/GitDiffSidebar.vue` | 实例化 `useSpcodeFileRestore`;实现 `onFileRestore(path)`;v-snackbar 挂载;本地内联 `<v-dialog persistent>` 确认框;`RESTORE_REASON_I18N_KEYS` 映射;将 `onRestore` 回调下传 |
| `dashboard/src/i18n/locales/zh-CN/features/chat.json` | `diffSidebar.restore.*` 命名空间 |
| `dashboard/src/i18n/locales/en-US/features/chat.json` | `diffSidebar.restore.*` 命名空间 |
| `dashboard/src/i18n/locales/ru-RU/features/chat.json` | `diffSidebar.restore.*` 命名空间 |

---

## Chunk 1: Setup + 解析层(TDD)

### Task 1: 准备工作(worktree + 分支)

**Files:**
- (无文件改动,仅 git 操作)

- [ ] **Step 1: 确认 `all` 分支 HEAD 包含 spec commits**

```bash
cd /d F:\github\Astrbot
git log --oneline -5
```

Expected: 顶部包含 `ca236382b docs(spec): fix N1/N2 trivial wording in state machine diagram` 及其上 2 条 spec commits。

- [ ] **Step 2: 创建 worktree**

```bash
cd /d F:\github\Astrbot
git worktree add .worktrees/feat-gitdiff-file-restore -b feat/gitdiff-file-restore all
```

Expected: worktree 创建在 `.worktrees/feat-gitdiff-file-restore/`,基于 `all` 分支。

- [ ] **Step 3: 在 worktree 中确认状态**

```bash
cd .worktrees/feat-gitdiff-file-restore
git status
git branch --show-current
```

Expected: `On branch feat/gitdiff-file-restore`,working tree clean。

> **后续所有命令**都假定你在 `.worktrees/feat-gitdiff-file-restore/` 目录下执行,使用 `@test-driven-development` 技能。

---

### Task 2: TDD 解析层 — 写测试

**Files:**
- Create: `dashboard/tests/parseSpcodeFileRestore.test.mjs`

- [ ] **Step 1: 写失败的测试**

完整内容写入 `dashboard/tests/parseSpcodeFileRestore.test.mjs`:

```javascript
// Author: elecvoid243
// Date: 2026-06-22
// Spec: docs/superpowers/specs/2026-06-22-chatui-git-diff-file-restore-design.md §4-5
import assert from "node:assert/strict";
import test from "node:test";

import {
  parseSpcodeFileRestore,
  classifyReason,
  RESTORE_REASON_CODES,
  type SpcodeFileRestoreRawResponse,
  type RestoreReason,
} from "../src/composables/parseSpcodeFileRestore.ts";

const baseData: SpcodeFileRestoreRawResponse = {
  restored: true,
  reason: null,
  file: "main.py",
  umo: "qq:1",
  worktree: "F:\\repo",
  directory: "F:\\repo",
  scope: "unstaged",
  elapsed_ms: 23,
  stderr: "",
};

test("parses success envelope", () => {
  const r = parseSpcodeFileRestore({ status: "ok", data: { ...baseData } });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.restored, true);
  assert.equal(r.snapshot.reason, null);
  assert.equal(r.snapshot.file, "main.py");
  assert.equal(r.snapshot.elapsedMs, 23);
});

test("parses failure envelope with reason", () => {
  const r = parseSpcodeFileRestore({
    status: "ok",
    data: { ...baseData, restored: false, reason: "untracked_file", stderr: "?? new.py" },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.restored, false);
  assert.equal(r.snapshot.reason, "untracked_file");
  assert.equal(r.snapshot.stderr, "?? new.py");
});

test("parses git_error with stderr", () => {
  const r = parseSpcodeFileRestore({
    status: "ok",
    data: { ...baseData, restored: false, reason: "git_error", stderr: "fatal: ..." },
  });
  assert.equal(r.snapshot.reason, "git_error");
  assert.equal(r.snapshot.stderr, "fatal: ...");
});

test("throws on missing data field", () => {
  assert.throws(
    () => parseSpcodeFileRestore({ status: "ok" }),
    /missing data/i,
  );
});

test("throws on wrong status", () => {
  assert.throws(
    () => parseSpcodeFileRestore({ status: "error" }),
    /status/i,
  );
});

test("classifyReason returns known reason unchanged", () => {
  for (const code of RESTORE_REASON_CODES) {
    assert.equal(classifyReason(code), code);
  }
});

test("classifyReason maps unknown to 'unknown'", () => {
  assert.equal(classifyReason("not_a_real_code"), "unknown");
});

test("classifyReason maps null/undefined to 'unknown'", () => {
  assert.equal(classifyReason(null), "unknown");
  assert.equal(classifyReason(undefined), "unknown");
});
```

- [ ] **Step 2: 运行测试,确认失败**

```bash
cd dashboard
node --test tests/parseSpcodeFileRestore.test.mjs
```

Expected: FAIL with `Cannot find module '../src/composables/parseSpcodeFileRestore.ts'`(模块未实现)

- [ ] **Step 3: 提交失败的测试**

```bash
git add tests/parseSpcodeFileRestore.test.mjs
git commit -m "test(file-restore): add parseSpcodeFileRestore unit tests (TDD red)"
```

---

### Task 3: TDD 解析层 — 实现

**Files:**
- Create: `dashboard/src/composables/parseSpcodeFileRestore.ts`

- [ ] **Step 1: 写最小实现**

完整内容写入 `dashboard/src/composables/parseSpcodeFileRestore.ts`:

```typescript
// Author: elecvoid243
// Date: 2026-06-22
// Spec: docs/superpowers/specs/2026-06-22-chatui-git-diff-file-restore-design.md §4-5
//
// Pure parser for POST /spcode/file-restore responses. No Vue / no axios —
// importable by node --test (see tests/parseSpcodeFileRestore.test.mjs).

/** All reason codes the spcode plugin can return (excluding `null` = success). */
export const RESTORE_REASON_CODES = [
  "invalid_body",
  "missing_file",
  "feature_disabled",
  "no_project_loaded",
  "directory_missing",
  "not_a_git_repo",
  "worktree_invalid",
  "git_unavailable",
  "path_unsafe",
  "file_not_found",
  "not_modified",
  "untracked_file",
  "git_error",
] as const;

export type RestoreReason = (typeof RESTORE_REASON_CODES)[number] | "network" | "unknown";

/** Raw response shape from POST /spcode/file-restore. */
export interface SpcodeFileRestoreRawResponse {
  restored: boolean;
  reason: string | null;
  file: string;
  umo: string | null;
  worktree: string;
  directory: string | null;
  scope: "unstaged";
  elapsed_ms: number;
  stderr: string;
}

export interface SpcodeFileRestoreSnapshot {
  restored: boolean;
  reason: string | null;
  file: string;
  umo: string | null;
  worktree: string;
  directory: string | null;
  elapsedMs: number;
  stderr: string;
}

export type ParseResult =
  | { kind: "ok"; snapshot: SpcodeFileRestoreSnapshot }
  | { kind: "error"; reason: string };

/**
 * Parse the envelope returned by POST /spcode/file-restore.
 *
 * Throws if the envelope is malformed (caller catches and shows generic
 * error toast). Business-level failures (restored=false with a reason
 * code) are NOT thrown — they're returned as `kind: "ok"` with the
 * reason captured in the snapshot, matching the existing
 * parseSpcodeGitDiff convention.
 */
export function parseSpcodeFileRestore(
  raw: unknown,
): ParseResult {
  if (typeof raw !== "object" || raw === null) {
    throw new Error("missing status envelope");
  }
  const env = raw as { status?: unknown; data?: unknown };
  if (env.status !== "ok") {
    throw new Error("unexpected status envelope");
  }
  if (typeof env.data !== "object" || env.data === null) {
    throw new Error("missing data in response");
  }
  const d = env.data as Partial<SpcodeFileRestoreRawResponse>;
  return {
    kind: "ok",
    snapshot: {
      restored: Boolean(d.restored),
      reason: d.reason ?? null,
      file: typeof d.file === "string" ? d.file : "",
      umo: typeof d.umo === "string" ? d.umo : null,
      worktree: typeof d.worktree === "string" ? d.worktree : "",
      directory: typeof d.directory === "string" ? d.directory : null,
      elapsedMs: typeof d.elapsed_ms === "number" ? d.elapsed_ms : 0,
      stderr: typeof d.stderr === "string" ? d.stderr : "",
    },
  };
}

/**
 * Classify a reason string to a known RestoreReason.
 * Returns the input unchanged if it's a known code; otherwise "unknown".
 * "network" is returned only when the caller passes it explicitly (used
 * by useSpcodeFileRestore to flag axios ERR_NETWORK before the parser
 * ever runs).
 */
export function classifyReason(raw: string | null | undefined): RestoreReason {
  if (raw === null || raw === undefined) return "unknown";
  if (raw === "network") return "network";
  if ((RESTORE_REASON_CODES as readonly string[]).includes(raw)) {
    return raw as RestoreReason;
  }
  return "unknown";
}
```

- [ ] **Step 2: 运行测试,确认通过**

```bash
cd dashboard
node --test tests/parseSpcodeFileRestore.test.mjs
```

Expected: PASS(8 tests, 0 failures)

- [ ] **Step 3: 提交实现**

```bash
git add src/composables/parseSpcodeFileRestore.ts
git commit -m "feat(file-restore): add parseSpcodeFileRestore (TDD green)"
```

---

## Chunk 2: Composable + i18n

### Task 4: TDD Composable — 写测试(可选)

**Files:**
- Create: `dashboard/tests/useSpcodeFileRestore.test.mjs`(可选 — 详见说明)

> **说明**:项目 dashboard **无 Vue 组件 / composable 测试框架**(见 spec §12 "关于 pnpm test 脚本的缺位")。本 Task 是**可选的**;若你希望严格 TDD,需要先在 `dashboard/package.json` 增加 `"test:unit": "node --test tests/*.test.mjs"` 并安装 vitest(超出本 spec 范围)。**推荐做法**:跳过本 Task,直接进入 Task 5(写最小实现),用 Task 7 的手测冒烟覆盖 composable 行为。

- [ ] **Step 1(推荐跳过):仅当你接受引入 vitest 时执行**

如跳过,直接进入 Task 5。

---

### Task 5: Composable 实现

**Files:**
- Create: `dashboard/src/composables/useSpcodeFileRestore.ts`

- [ ] **Step 1: 写 composable**

完整内容写入 `dashboard/src/composables/useSpcodeFileRestore.ts`:

```typescript
// Author: elecvoid243
// Date: 2026-06-22
// Spec: docs/superpowers/specs/2026-06-22-chatui-git-diff-file-restore-design.md §4, §6.5
//
// Vue composable wrapping POST /spcode/file-restore. Mirrors the lifecycle
// pattern of useSpcodeGitDiff.ts (single instance per consumer, AbortController
// for cancellation, isMounted guard).

import { ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import {
  parseSpcodeFileRestore,
  classifyReason,
  type SpcodeFileRestoreSnapshot,
} from "./parseSpcodeFileRestore";

export interface UseSpcodeFileRestore {
  isRestoring: import("vue").Ref<boolean>;
  restore: (params: RestoreParams) => Promise<RestoreResult>;
  dispose: () => void;
}

export interface RestoreParams {
  file: string;
  worktree?: string | null;
  umo?: string | null;
}

export type RestoreResult =
  | { ok: true; snapshot: SpcodeFileRestoreSnapshot }
  | { ok: false; reason: string; stderr?: string };

export function useSpcodeFileRestore(): UseSpcodeFileRestore {
  const isRestoring = ref(false);
  let abortController: AbortController | null = null;
  let isMounted = true;

  async function restore(params: RestoreParams): Promise<RestoreResult> {
    if (!isMounted) {
      return { ok: false, reason: "aborted" };
    }
    abortController?.abort();
    abortController = new AbortController();
    isRestoring.value = true;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/file-restore",
        {
          file: params.file,
          ...(params.worktree ? { worktree: params.worktree } : {}),
          ...(params.umo ? { umo: params.umo } : {}),
        },
        { signal: abortController.signal },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      const parsed = parseSpcodeFileRestore(resp.data);
      if (parsed.kind !== "ok") {
        return { ok: false, reason: "unknown" };
      }
      const snap = parsed.snapshot;
      if (snap.restored) {
        return { ok: true, snapshot: snap };
      }
      return {
        ok: false,
        reason: classifyReason(snap.reason),
        stderr: snap.stderr || undefined,
      };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      if ((err as { name?: string })?.name === "CanceledError") {
        return { ok: false, reason: "aborted" };
      }
      const anyErr = err as { code?: string; message?: string };
      if (anyErr.code === "ERR_NETWORK" || /network/i.test(anyErr.message ?? "")) {
        return { ok: false, reason: "network" };
      }
      return { ok: false, reason: "unknown" };
    } finally {
      if (isMounted) isRestoring.value = false;
    }
  }

  function dispose(): void {
    isMounted = false;
    abortController?.abort();
    abortController = null;
  }

  return { isRestoring, restore, dispose };
}
```

- [ ] **Step 2: 类型检查通过**

```bash
cd dashboard
pnpm typecheck
```

Expected: 0 errors(可能需要先 `pnpm install` 如果 `node_modules` 缺失)

- [ ] **Step 3: 提交**

```bash
git add src/composables/useSpcodeFileRestore.ts
git commit -m "feat(file-restore): add useSpcodeFileRestore composable"
```

---

### Task 6: i18n 三语同步加键

**Files:**
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json`(在 `diffSidebar` 对象下加 `restore` 子对象)
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json`
- Modify: `dashboard/src/i18n/locales/ru-RU/features/chat.json`

- [ ] **Step 1: 修改 zh-CN**

打开 `dashboard/src/i18n/locales/zh-CN/features/chat.json`,在 `diffSidebar` 对象的最后(在 `error` 之后,`}` 闭合前)插入:

```json
,
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
```

- [ ] **Step 2: 修改 en-US**

打开 `dashboard/src/i18n/locales/en-US/features/chat.json`,在 `diffSidebar` 对象的最后插入:

```json
,
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

- [ ] **Step 3: 修改 ru-RU**

打开 `dashboard/src/i18n/locales/ru-RU/features/chat.json`,在 `diffSidebar` 对象的最后插入:

```json
,
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

- [ ] **Step 4: JSON 语法校验**

```bash
cd dashboard
for f in src/i18n/locales/zh-CN/features/chat.json src/i18n/locales/en-US/features/chat.json src/i18n/locales/ru-RU/features/chat.json; do
  node -e "JSON.parse(require('fs').readFileSync('$f', 'utf8'))" && echo "OK: $f"
done
```

Expected: 3 行 `OK: ...`(JSON 全部合法)

- [ ] **Step 5: 提交**

```bash
git add src/i18n/locales/
git commit -m "feat(i18n): add diffSidebar.restore namespace to 3 locales"
```

---

## Chunk 3: 组件层

### Task 7: GitDiffFileItem.vue — 重构 row + 加 ↩ 按钮

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue`

- [ ] **Step 1: 备份当前文件**

```bash
cp dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue.bak
```

- [ ] **Step 2: 完整重写文件**

完整内容写入 `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue`(替换 `.bak` 文件):

```vue
<!-- Author: elecvoid243, 2026-06-22
     Spec: docs/superpowers/specs/2026-06-22-chatui-git-diff-file-restore-design.md §4, §6.1-§6.2
     Refactored: outer row <button> -> <div role="button" tabindex=0> to allow
     nesting a real <button> for the restore action (HTML5 forbids
     button-in-button nesting; see spec §2 decision #4). -->
<script setup lang="ts">
import { computed } from 'vue'
import type { SpcodeGitDiffFile, FileStatus } from '@/composables/parseSpcodeGitDiff'
import { useModuleI18n } from '@/i18n/composables'
import { useSpcodeProjectStatus } from '@/composables/useSpcodeProjectStatus'
import DiffPreview from '@/components/chat/message_list_comps/DiffPreview.vue'

const { tm } = useModuleI18n('features/chat')

const props = defineProps<{
  file: SpcodeGitDiffFile
  expanded: boolean
  isDark: boolean
  /** When provided, renders the restore button and emits 'restore' on click. */
  onRestore?: (path: string) => void
  /** True while a restore request is in flight for THIS row. */
  isRestoring?: boolean
}>()
const emit = defineEmits<{
  (e: 'toggle'): void
  (e: 'restore', path: string): void
}>()

const ICON_MAP: Record<FileStatus, { icon: string; color: string }> = {
  M: { icon: 'mdi-pencil', color: 'primary' },
  A: { icon: 'mdi-plus-circle', color: 'success' },
  D: { icon: 'mdi-minus-circle', color: 'error' },
  R: { icon: 'mdi-rename-box', color: 'warning' },
  C: { icon: 'mdi-content-copy', color: 'info' },
  T: { icon: 'mdi-swap-horizontal', color: 'info' },
  unknown: { icon: 'mdi-file-document-edit-outline', color: 'grey' },
}
const iconInfo = computed(() => ICON_MAP[props.file.status])

const spcodeStatus = useSpcodeProjectStatus()
/** Spec §6.2: button visible only when project is loaded + umo present. */
const showRestoreButton = computed(() => {
  return Boolean(
    props.onRestore &&
      spcodeStatus.status.value.loaded &&
      spcodeStatus.status.value.umo,
  )
})

function onRowKeydown(e: KeyboardEvent): void {
  // Spec §6.5: Enter / Space toggles the row.
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    emit('toggle')
  }
}

function onRestoreClick(e: MouseEvent): void {
  // Spec §6.1: @click.stop prevents the click from bubbling to the row's
  // toggle handler.
  e.stopPropagation()
  if (props.isRestoring) return
  emit('restore', props.file.path)
}
</script>

<template>
  <div class="git-diff-file-item" :class="{ expanded: expanded }">
    <div
      class="git-diff-file-row"
      role="button"
      tabindex="0"
      :aria-expanded="expanded"
      @click="emit('toggle')"
      @keydown="onRowKeydown"
    >
      <v-icon :size="16" :color="iconInfo.color">{{ iconInfo.icon }}</v-icon>
      <span class="git-diff-file-path">{{ file.path }}</span>
      <span class="git-diff-file-stats">
        <span class="git-diff-add">+{{ file.additions }}</span>
        <span class="git-diff-del">−{{ file.deletions }}</span>
      </span>
      <button
        v-if="showRestoreButton"
        type="button"
        class="git-diff-file-restore"
        :class="{ 'is-loading': isRestoring }"
        :disabled="isRestoring"
        :aria-label="tm('spcodeProjectLoad.diffSidebar.restore.buttonAria', { path: file.path })"
        :aria-busy="isRestoring ? 'true' : 'false'"
        :title="tm('spcodeProjectLoad.diffSidebar.restore.buttonAria', { path: file.path })"
        @click="onRestoreClick"
      >
        <v-progress-circular
          v-if="isRestoring"
          indeterminate
          :size="14"
          :width="2"
        />
        <v-icon v-else :size="16">mdi-restore</v-icon>
      </button>
      <v-icon
        :size="16"
        class="git-diff-file-chevron"
        :class="{ expanded: expanded }"
      >mdi-chevron-down</v-icon>
    </div>
    <div v-if="expanded" class="git-diff-file-body">
      <v-alert
        v-if="file.isBinary"
        type="info"
        density="compact"
        variant="tonal"
        class="git-diff-binary-alert"
      >
        {{ tm('spcodeProjectLoad.diffSidebar.binaryFile') }}
      </v-alert>
      <DiffPreview
        v-else-if="file.slice"
        :content="file.slice"
        :file-path="file.path"
        :collapsible="false"
        :is-dark="isDark"
      />
      <div v-else class="git-diff-file-no-content">
        {{ tm('spcodeProjectLoad.diffSidebar.noContent') }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.git-diff-file-item {
  /* Dark mode flips to a translucent white so the divider remains
     visible against the dark surface. Tied to the `isDark` prop that
     Chat.vue already passes down. */
  border-bottom: 1px solid v-bind('isDark ? "rgba(255, 255, 255, 0.18)" : "rgba(0, 0, 0, 0.08)"');
}
.git-diff-file-row {
  display: flex; align-items: center; gap: 8px;
  width: 100%; padding: 8px 12px;
  background: transparent; border: none; cursor: pointer; text-align: left;
}
.git-diff-file-row:hover { background: rgba(0, 0, 0, 0.04); }
.git-diff-file-row:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.git-diff-file-path {
  flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-family: monospace; font-size: 13px;
}
.git-diff-file-stats { display: flex; gap: 6px; font-family: monospace; font-size: 12px; }
.git-diff-add { color: rgb(46, 160, 67); }
.git-diff-del { color: rgb(248, 81, 73); }
.git-diff-file-restore {
  /* Spec §6.1: muted by default, full opacity on row hover. Real <button>
     so it can be focused, disabled, and announced by screen readers. */
  display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 24px;
  padding: 0;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
  opacity: 0.5;
  transition: opacity 0.12s ease, background 0.12s ease, border-color 0.12s ease;
  flex-shrink: 0;
}
.git-diff-file-row:hover .git-diff-file-restore { opacity: 1; }
.git-diff-file-restore:hover { background: rgba(var(--v-theme-primary), 0.1); }
.git-diff-file-restore:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
  opacity: 1;
}
.git-diff-file-restore:disabled { cursor: not-allowed; opacity: 0.3; }
.git-diff-file-restore.is-loading { opacity: 1; }
.git-diff-file-chevron { transition: transform 0.15s; }
.git-diff-file-chevron.expanded { transform: rotate(180deg); }
.git-diff-file-body { padding: 0 12px 12px; }
.git-diff-file-no-content {
  /* Themed muted text — stays readable in both light and dark modes. */
  padding: 12px; text-align: center; color: rgba(var(--v-theme-on-surface), 0.45); font-size: 12px;
}
.git-diff-binary-alert { font-size: 13px; }
</style>
```

- [ ] **Step 3: 删除备份**

```bash
rm dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue.bak
```

> 注:用 `astrbot_file_remove` 删除(项目规范)

- [ ] **Step 4: 类型检查通过**

```bash
cd dashboard
pnpm typecheck
```

Expected: 0 errors

- [ ] **Step 5: 提交**

```bash
git add src/components/chat/message_list_comps/GitDiffFileItem.vue
git commit -m "refactor(file-item): convert row to <div role=button> + add restore button"
```

---

### Task 8: GitDiffBodyContent.vue — 加 re-emit

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue`

- [ ] **Step 1: 编辑 props / emits**

打开 `dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue`,做 3 处微改:

**改动 1** — props 加 `onRestore`:

找到:
```ts
const props = defineProps<{
  state: GitDiffFetchState
  expanded: Set<string>
  isDark: boolean
}>()
```

替换为:
```ts
const props = defineProps<{
  state: GitDiffFetchState
  expanded: Set<string>
  isDark: boolean
  onRestore?: (path: string) => void
}>()
```

**改动 2** — emits 加 `restore`:

找到:
```ts
const emit = defineEmits<{
  (e: 'toggle', path: string): void
  (e: 'retry'): void
}>()
```

替换为:
```ts
const emit = defineEmits<{
  (e: 'toggle', path: string): void
  (e: 'retry'): void
  (e: 'restore', path: string): void
}>()
```

**改动 3** — template 给 `GitDiffFileItem` 传 prop + 监听事件:

找到:
```vue
<GitDiffFileItem
  v-for="f in files"
  :key="f.path + ':' + f.status"
  :file="f"
  :expanded="expanded.has(f.path)"
  :is-dark="isDark"
  @toggle="emit('toggle', f.path)"
/>
```

替换为:
```vue
<GitDiffFileItem
  v-for="f in files"
  :key="f.path + ':' + f.status"
  :file="f"
  :expanded="expanded.has(f.path)"
  :is-dark="isDark"
  :on-restore="onRestore"
  @toggle="emit('toggle', f.path)"
  @restore="emit('restore', $event)"
/>
```

- [ ] **Step 2: 类型检查**

```bash
cd dashboard
pnpm typecheck
```

Expected: 0 errors

- [ ] **Step 3: 提交**

```bash
git add src/components/chat/message_list_comps/GitDiffBodyContent.vue
git commit -m "feat(file-item): thread onRestore prop and 'restore' event"
```

---

### Task 9: GitDiffSidebar.vue — 组合 composable + dialog + snackbar

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue`

- [ ] **Step 1: 在 `<script setup>` 顶部加 import**

找到 `import { ref, watch, onBeforeUnmount, computed, onMounted } from "vue";` 这行附近,在合适位置插入:

```ts
import { useSpcodeFileRestore } from "@/composables/useSpcodeFileRestore";
import type { RestoreResult } from "@/composables/useSpcodeFileRestore";
```

- [ ] **Step 2: 实例化 composable + 状态**

在 `const composable = useSpcodeGitDiff(...)` 之后插入:

```ts
// ── file-restore (spec §3.2) ──────────────────────────────────────────
// Composable instance lives at sidebar level so it can call
// composable.refresh() and reach the snackbar / dialog state.
const fileRestore = useSpcodeFileRestore();
const restoringFile = ref<string | null>(null);

// Confirm dialog state.
const confirmDialogOpen = ref(false);
const confirmTargetPath = ref<string | null>(null);

// Snackbar state (success / warning / error).
interface SnackbarState {
  show: boolean;
  message: string;
  color: "success" | "warning" | "error";
}
const snackbar = ref<SnackbarState>({ show: false, message: "", color: "success" });

// Maps a restore reason code to a snackbar message + color.
const RESTORE_REASON_I18N_KEYS: Record<string, { key: string; color: "warning" | "error" }> = {
  invalid_body: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.invalid_body", color: "error" },
  missing_file: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.missing_file", color: "error" },
  feature_disabled: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.feature_disabled", color: "error" },
  no_project_loaded: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.no_project_loaded", color: "error" },
  directory_missing: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.directory_missing", color: "error" },
  not_a_git_repo: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.not_a_git_repo", color: "error" },
  worktree_invalid: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.worktree_invalid", color: "error" },
  git_unavailable: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.git_unavailable", color: "error" },
  path_unsafe: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.path_unsafe", color: "error" },
  file_not_found: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.file_not_found", color: "error" },
  not_modified: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.not_modified", color: "warning" },
  untracked_file: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.untracked_file", color: "warning" },
  git_error: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.git_error", color: "error" },
  network: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.network", color: "error" },
  unknown: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.unknown", color: "error" },
};
```

- [ ] **Step 3: 实现 `onFileRestore` + `onConfirmRestore` + `onCancelRestore`**

在 `function onFileBrowserNavigate(...)` 之后插入:

```ts
// Spec §3.2 data flow: GitDiffFileItem -> GitDiffBodyContent -> here.
function onFileRestore(path: string): void {
  confirmTargetPath.value = path;
  confirmDialogOpen.value = true;
}

function onCancelRestore(): void {
  confirmDialogOpen.value = false;
  confirmTargetPath.value = null;
}

async function onConfirmRestore(): Promise<void> {
  const path = confirmTargetPath.value;
  if (!path) return;
  confirmDialogOpen.value = false;
  confirmTargetPath.value = null;
  restoringFile.value = path;
  const umo = spcodeStatus.status.value.umo;
  const worktree = selectedWorktree.value;
  const result: RestoreResult = await fileRestore.restore({ file: path, worktree, umo });
  restoringFile.value = null;
  if (result.ok) {
    snackbar.value = {
      show: true,
      message: tm("spcodeProjectLoad.diffSidebar.restore.success", { path }),
      color: "success",
    };
    // Spec §3.2: success -> immediate refresh so the row disappears.
    await composable.refresh();
  } else {
    const mapping = RESTORE_REASON_I18N_KEYS[result.reason] ?? RESTORE_REASON_I18N_KEYS.unknown;
    const message = mapping.key === "spcodeProjectLoad.diffSidebar.restore.error.reason.git_error"
      ? tm(mapping.key, { stderr: result.stderr ?? "" })
      : tm(mapping.key);
    snackbar.value = { show: true, message, color: mapping.color };
  }
}
```

- [ ] **Step 4: 在 `onBeforeUnmount` 中 dispose composable**

找到:
```ts
onBeforeUnmount(() => {
  onMouseUp();
  composable.dispose();
  worktreesComposable.dispose();
  if (persistCurrentPathTimer) {
    clearTimeout(persistCurrentPathTimer);
    persistCurrentPathTimer = null;
  }
});
```

替换为:
```ts
onBeforeUnmount(() => {
  onMouseUp();
  composable.dispose();
  worktreesComposable.dispose();
  fileRestore.dispose();
  if (persistCurrentPathTimer) {
    clearTimeout(persistCurrentPathTimer);
    persistCurrentPathTimer = null;
  }
});
```

- [ ] **Step 5: 在 template 中加 dialog + snackbar + 传递回调**

找到 `<GitDiffBodyContent ...>` 调用,改为:

```vue
<GitDiffBodyContent
  v-else
  :state="composable.state.value"
  :expanded="expandedSet"
  :is-dark="!!isDark"
  :on-restore="onFileRestore"
  @toggle="toggleFile"
  @retry="onManualRefresh"
  @restore="onFileRestore"
/>
```

- [ ] **Step 6: 在 template 末尾(`</aside>` 之前)加 dialog + snackbar**

```vue
      <!-- Spec §6.3: inline <v-dialog persistent> confirmation. -->
      <v-dialog
        v-model="confirmDialogOpen"
        persistent
        max-width="440"
      >
        <v-card>
          <v-card-title class="text-h6">
            {{ tm("spcodeProjectLoad.diffSidebar.restore.confirmTitle") }}
          </v-card-title>
          <v-card-text>
            {{ tm("spcodeProjectLoad.diffSidebar.restore.confirmMessage", { path: confirmTargetPath ?? "" }) }}
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn
              variant="text"
              @click="onCancelRestore"
            >{{ tm("spcodeProjectLoad.diffSidebar.restore.confirmCancel") }}</v-btn>
            <v-btn
              variant="flat"
              color="warning"
              :loading="restoringFile !== null"
              @click="onConfirmRestore"
            >{{ tm("spcodeProjectLoad.diffSidebar.restore.confirmAction") }}</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Spec §6.4: result snackbar. -->
      <v-snackbar
        v-model="snackbar.show"
        :color="snackbar.color"
        :timeout="snackbar.color === 'success' ? 4000 : 6000"
        location="bottom right"
      >
        {{ snackbar.message }}
      </v-snackbar>
```

- [ ] **Step 7: 类型检查**

```bash
cd dashboard
pnpm typecheck
```

Expected: 0 errors

- [ ] **Step 8: 提交**

```bash
git add src/components/chat/GitDiffSidebar.vue
git commit -m "feat(gitdiff-sidebar): wire file-restore composable + dialog + snackbar"
```

---

## Chunk 4: 验证 + 收尾

### Task 10: 运行所有检查

- [ ] **Step 1: 类型检查**

```bash
cd dashboard
pnpm typecheck
```

Expected: 0 errors

- [ ] **Step 2: Lint**

```bash
pnpm lint
```

Expected: 0 errors(可自动修复)

- [ ] **Step 3: 单元测试**

```bash
node --test tests/parseSpcodeFileRestore.test.mjs
```

Expected: 8 tests pass

---

### Task 11: 手动冒烟测试(9 个场景)

> dashboard 无 Vue 组件测试框架,这些场景通过浏览器手测(spec §9.3)。

- [ ] **场景 1**:加载项目 + 修改一个文件 → diff 列表出现该行

- [ ] **场景 2**:点 ↩ → 弹出 confirm → 取消 → 列表不变,无 toast

- [ ] **场景 3**:点 ↩ → 弹出 confirm → 确认 → spinner → success toast → 该行从列表消失

- [ ] **场景 4**:新建一个未 `git add` 的文件 → diff 列表出现 → 点 ↩ → spinner → warning toast 显示"未跟踪的文件无法恢复"

- [ ] **场景 5**:Tab 聚焦 ↩ → Enter 触发 confirm 弹窗

- [ ] **场景 6**:切换 worktree(多 worktree 场景)→ 验证 POST body 包含新 worktree

- [ ] **场景 7**:卸载项目 → ↩ 按钮消失

- [ ] **场景 8**:DevTools Network 面板检查:POST 请求路径 = `/plugins/extensions/spcode/file-restore`,body 含 `file` 字段

- [ ] **场景 9**:三语切换(zh-CN / en-US / ru-RU)→ 按钮文字与 toast 文字正确切换

> 若任一场景失败,记录问题并修复;不进入 Task 12 直到全部通过。

---

### Task 12: 提交 + 推分支

- [ ] **Step 1: 确认 worktree 状态干净**

```bash
git status
```

Expected: `nothing to commit, working tree clean`(若未干净,按 `git diff` 排查)

- [ ] **Step 2: 查看 commits 列表**

```bash
git log --oneline all..HEAD
```

Expected: 4-5 个 commits(spec 已 3 个 + 本次 4-5 个)

- [ ] **Step 3: 推分支**

```bash
git push -u origin feat/gitdiff-file-restore
```

Expected: 远端创建分支

- [ ] **Step 4: 创建 PR**

用 `gh pr create`(或浏览器):
- 标题:`feat: add file-restore button to GitDiff sidebar`
- 描述:粘贴 spec 与 plan 的链接,概述测试覆盖

---

## Plan Review Self-Check (完成时)

- [ ] 所有 9 个手动冒烟场景通过
- [ ] `pnpm typecheck` 0 errors
- [ ] `pnpm lint` 0 errors
- [ ] `node --test tests/parseSpcodeFileRestore.test.mjs` 8 pass
- [ ] 4-5 个新 commits,conventional commit 格式
- [ ] PR 创建,链接已发给用户审阅
