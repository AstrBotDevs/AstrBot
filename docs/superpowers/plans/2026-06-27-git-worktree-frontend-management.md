# Git Worktree 前端管理功能 — 实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `GitDiffSidebar.vue` 中提供 git worktree 完整管理能力（ADD / REMOVE / LOCK / UNLOCK），对齐 `astrbot_plugin_spcode_toolkit` v2.14.0 新增的 4 个写端点

**Architecture:** 扩展现有 `useSpcodeWorktrees` composable 加入 4 个 mutation 方法（共享 state / 复用 polling / 复用 watchers）；新增 `parseSpcodeWorktreeManagement.ts` 独立文件承载 4 个 response parser + reason 字典；就地扩展 `GitDiffSidebar.vue` 的 worktree tab 行（`+` 按钮 + 右键菜单 + 4 个独立 dialog）

**Tech Stack:** Vue 3 + Vuetify 3 + TypeScript + `vue-i18n` + Node.js v24 `node:test` + ESLint + Vue TSC

**Spec:** `docs/superpowers/specs/2026-06-27-git-worktree-frontend-management-design.md`

---

## File Structure

### New Files

| 路径 | 用途 | 行数 |
|------|------|------|
| `dashboard/src/composables/parseSpcodeWorktreeManagement.ts` | 4 个 mutation 端点 response parser + reason 字典 | ~200 |
| `dashboard/tests/parseSpcodeWorktreeManagement.test.mjs` | parser / reason 分类单测 | ~250 |
| `dashboard/src/components/chat/message_list_comps/WorktreeCreateDialog.vue` | ADD 表单组件（独立组件，便于单测） | ~280 |

### Modified Files

| 路径 | 改动 | 行数 |
|------|------|------|
| `dashboard/src/composables/useSpcodeWorktrees.ts` | 新增 `add/remove/lock/unlock` 4 个方法 + 类型 | +160 |
| `dashboard/src/components/chat/GitDiffSidebar.vue` | tab 行加 `+` / `contextmenu` / 4 个 dialog / 状态机 / 8 个新 ref | +250 |
| `dashboard/src/i18n/locales/zh-CN/features/chat.json` | `worktreeMgmt` 子树 + `error.reason` 新增键 | +50 |
| `dashboard/src/i18n/locales/en-US/features/chat.json` | 同上 | +50 |
| `dashboard/src/i18n/locales/ru-RU/features/chat.json` | 同上（占位 stub） | +50 |

### Test Strategy

- **Parser**：纯函数，`node:test` + 直接 `.ts` import（与 `parseSpcodeGitWorkflow.test.mjs` 同模式）
- **Composable**：单测覆盖 mutation 状态机 + abort + umo=null 早返（**v2 范围**；本次实施可推迟到后续 PR，本次仅冒烟测试）
- **UI 组件**：手动 + e2e（v3 范围，本次仅 dev server 验证）

---

## Chunk 1: Parser + Reason 字典（基础设施）

> 自包含 chunk：纯 TS、无 Vue 依赖、单测可独立跑通

### Task 1.1: 创建 parser 文件骨架

**Files:**
- Create: `dashboard/src/composables/parseSpcodeWorktreeManagement.ts`

- [ ] **Step 1: 创建文件头 + 类型定义**

```ts
// Author: elecvoid243
// Date: 2026-06-27
// Spec: docs/superpowers/specs/2026-06-27-git-worktree-frontend-management-design.md §1.2
//
// Pure parser for the 4 git worktree management endpoints (git-worktree-add
// / git-worktree-remove / git-worktree-lock / git-worktree-unlock). No Vue /
// no axios. Mirrors parseSpcodeGitWorkflow.ts split.
//
// All 4 endpoints return the SAME envelope shape:
//   { status: "ok", data: { loaded, directory, umo, worktree, [endpoint-specific], worktrees, reason, stderr, elapsed_ms } }
// The `worktrees` field is the **refreshed complete list** of worktrees,
// which the consumer (useSpcodeWorktrees) uses to atomically replace
// its state — no extra GET roundtrip needed.

import type { SpcodeGitWorktreesSnapshot } from "./parseSpcodeWorktrees";

// ── Endpoint id union ──────────────────────────────────────
export type WorktreeMgmtEndpoint = "add" | "remove" | "lock" | "unlock";

// ── Raw envelope shape (shared by all 4 endpoints) ────────
export interface SpcodeWorktreeMgmtRawData {
  loaded: boolean;
  directory: string | null;
  umo: string | null;
  worktree: string;
  // Endpoint-specific (optional in raw shape; present per endpoint).
  branch?: string | null;
  removed_path?: string;
  locked?: boolean;
  lock_reason?: string | null;
  // The refreshed worktree list.
  worktrees: unknown[];
  reason: string | null;
  stderr: string;
  elapsed_ms: number;
}

export interface SpcodeWorktreeMgmtRawResponse {
  loaded?: boolean;
  directory?: string | null;
  umo?: string | null;
  worktree?: string;
  branch?: string | null;
  removed_path?: string;
  locked?: boolean;
  lock_reason?: string | null;
  worktrees?: unknown[];
  reason?: string | null;
  stderr?: string;
  elapsed_ms?: number;
}

export type ParseResult<T> =
  | { kind: "ok"; snapshot: T }
  | { kind: "error"; reason: string };

// ── Snapshot (consumer-facing) ────────────────────────────
//
// We embed the same `meta` shape SpcodeGitWorktreesSnapshot uses, so
// the useSpcodeWorktrees consumer can swap state with the refreshed
// list atomically.
export interface SpcodeWorktreeMgmtSnapshot {
  meta: {
    directory: string | null;
    umo: string | null;
    loaded: boolean;
    reason: string | null;
    stderr: string;
    elapsedMs: number;
    fetchedAt: number;
  };
  worktree: string;
  branch: string | null;
  removedPath: string | null;
  locked: boolean;
  lockReason: string | null;
  worktrees: SpcodeGitWorktreesSnapshot["worktrees"];
}
```

- [ ] **Step 2: 验证文件能解析**

Run: `cd dashboard && pnpm typecheck 2>&1 | head -20`
Expected: 无错误（仅 file 自身的类型定义，不引用未实现函数）

- [ ] **Step 3: 提交**

```bash
git add dashboard/src/composables/parseSpcodeWorktreeManagement.ts
git commit -m "feat(worktree-mgmt): scaffold parser types and snapshot"
```

### Task 1.2: 实现 envelope helpers

**Files:**
- Modify: `dashboard/src/composables/parseSpcodeWorktreeManagement.ts`（在类型定义后追加）

- [ ] **Step 1: 写失败的测试**

Create: `dashboard/tests/parseSpcodeWorktreeManagement.test.mjs`

```mjs
// Author: elecvoid243
// Date: 2026-06-27
// Spec: docs/superpowers/specs/2026-06-27-git-worktree-frontend-management-design.md §8

import assert from "node:assert/strict";
import test from "node:test";

import {
  parseSpcodeWorktreeAdd,
  parseSpcodeWorktreeRemove,
  parseSpcodeWorktreeLock,
  parseSpcodeWorktreeUnlock,
  classifyWorktreeReason,
  WORKTREE_MGMT_REASON_CODES,
  ALLOWED_WORKTREE_REASONS,
} from "../src/composables/parseSpcodeWorktreeManagement.ts";

const baseData = {
  loaded: true,
  directory: "C:/repo",
  umo: "webchat-1",
  worktree: "C:/repo/.worktrees/feat",
  worktrees: [
    {
      path: "C:/repo",
      head_sha: "abc1234",
      branch: "main",
      is_main: true,
      prunable: false,
      locked: null,
    },
  ],
  reason: null,
  stderr: "",
  elapsed_ms: 50,
};

test("parseSpcodeWorktreeAdd: success returns snapshot with branch", () => {
  const r = parseSpcodeWorktreeAdd({
    status: "ok",
    data: { ...baseData, branch: "feat" },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.branch, "feat");
  assert.equal(r.snapshot.worktree, "C:/repo/.worktrees/feat");
  assert.equal(r.snapshot.worktrees.length, 1);
});
```

- [ ] **Step 2: 运行测试，验证失败**

Run: `cd dashboard && node --test tests/parseSpcodeWorktreeManagement.test.mjs 2>&1 | head -30`
Expected: FAIL with "parseSpcodeWorktreeAdd is not a function"

- [ ] **Step 3: 实现 envelope helpers（写入 parser 文件）**

```ts
// ── Envelope helpers (copied & adapted from parseSpcodeGitWorkflow) ─

function unwrapEnvelope(raw: unknown): unknown {
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
  return env.data;
}

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}
function asStringOrNull(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}
function asNumber(v: unknown, fallback = 0): number {
  return typeof v === "number" ? v : fallback;
}
function asBoolean(v: unknown, fallback = false): boolean {
  return typeof v === "boolean" ? v : fallback;
}

/** Build the snapshot's `meta` block + endpoint-specific fields.
 *  Pure function — takes the unwrapped `data` object and the consumer-
 *  facing field overrides. Centralizes the field-name mapping from
 *  snake_case (backend) to camelCase (frontend) so the 4 parsers
 *  share the same implementation. */
function buildSnapshot(
  d: SpcodeWorktreeMgmtRawData,
  overrides: Partial<{
    branch: string | null;
    removedPath: string | null;
    locked: boolean;
    lockReason: string | null;
  }> = {},
): SpcodeWorktreeMgmtSnapshot {
  return {
    meta: {
      directory: d.directory ?? null,
      umo: d.umo ?? null,
      loaded: Boolean(d.loaded),
      reason: d.reason ?? null,
      stderr: asString(d.stderr),
      elapsedMs: asNumber(d.elapsed_ms),
      fetchedAt: Date.now(),
    },
    worktree: asString(d.worktree),
    branch: overrides.branch !== undefined ? overrides.branch : asStringOrNull(d.branch),
    removedPath:
      overrides.removedPath !== undefined
        ? overrides.removedPath
        : (d.removed_path ?? null),
    locked: overrides.locked !== undefined ? overrides.locked : asBoolean(d.locked),
    lockReason:
      overrides.lockReason !== undefined
        ? overrides.lockReason
        : (d.lock_reason ?? null),
    // We reuse the raw worktrees array as-is; useSpcodeWorktrees will
    // re-parse via parseSpcodeGitWorktrees() before swapping state.
    // The double-parse is intentional: it keeps the parser pure (no
    // import of parseSpcodeWorktrees here) and avoids drifting the
    // two parsers' field mappings.
    worktrees: (d.worktrees ?? []) as SpcodeGitWorktreesSnapshot["worktrees"],
  };
}
```

- [ ] **Step 4: 验证类型可解析**

Run: `cd dashboard && pnpm typecheck 2>&1 | head -20`
Expected: 无错误

- [ ] **Step 5: 提交**

```bash
git add dashboard/src/composables/parseSpcodeWorktreeManagement.ts
git commit -m "feat(worktree-mgmt): add envelope helpers and buildSnapshot"
```

### Task 1.3: 实现 4 个 endpoint parser

**Files:**
- Modify: `dashboard/src/composables/parseSpcodeWorktreeManagement.ts`

- [ ] **Step 1: 写失败的测试（追加到 test 文件）**

```mjs
test("parseSpcodeWorktreeRemove: success returns snapshot with removedPath", () => {
  const r = parseSpcodeWorktreeRemove({
    status: "ok",
    data: { ...baseData, removed_path: "C:/repo/.worktrees/feat" },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.removedPath, "C:/repo/.worktrees/feat");
  assert.equal(r.snapshot.worktree, "C:/repo/.worktrees/feat");
});

test("parseSpcodeWorktreeLock: success returns snapshot with locked=true + reason", () => {
  const r = parseSpcodeWorktreeLock({
    status: "ok",
    data: {
      ...baseData,
      locked: true,
      lock_reason: "WIP until PR #123 merged",
    },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.locked, true);
  assert.equal(r.snapshot.lockReason, "WIP until PR #123 merged");
});

test("parseSpcodeWorktreeUnlock: success returns snapshot with locked=false", () => {
  const r = parseSpcodeWorktreeUnlock({
    status: "ok",
    data: { ...baseData, locked: false },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.locked, false);
  assert.equal(r.snapshot.lockReason, null);
});

test("failure envelope (cannot_remove_main) still parses", () => {
  const r = parseSpcodeWorktreeRemove({
    status: "ok",
    data: { ...baseData, reason: "cannot_remove_main", stderr: "fatal: ..." },
  });
  // Business failure still parses (mirrors useSpcodeGitDiff convention).
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.meta.reason, "cannot_remove_main");
  assert.equal(r.snapshot.meta.stderr, "fatal: ...");
});
```

- [ ] **Step 2: 运行测试，验证失败**

Run: `cd dashboard && node --test tests/parseSpcodeWorktreeManagement.test.mjs 2>&1 | tail -20`
Expected: FAIL with "parseSpcodeWorktreeRemove is not a function" 等

- [ ] **Step 3: 实现 4 个 parser**

```ts
// ── Endpoint-specific parsers ─────────────────────────────
//
// All 4 share the same envelope shape; only the endpoint-specific
// field overrides differ. Each parser is 4-6 lines.

/** Parse the envelope from POST /spcode/git-worktree-add. */
export function parseSpcodeWorktreeAdd(
  raw: unknown,
): ParseResult<SpcodeWorktreeMgmtSnapshot> {
  const d = unwrapEnvelope(raw) as SpcodeWorktreeMgmtRawData;
  return {
    kind: "ok",
    snapshot: buildSnapshot(d, { branch: d.branch ?? null }),
  };
}

/** Parse the envelope from POST /spcode/git-worktree-remove. */
export function parseSpcodeWorktreeRemove(
  raw: unknown,
): ParseResult<SpcodeWorktreeMgmtSnapshot> {
  const d = unwrapEnvelope(raw) as SpcodeWorktreeMgmtRawData;
  return {
    kind: "ok",
    snapshot: buildSnapshot(d, { removedPath: d.removed_path ?? d.worktree }),
  };
}

/** Parse the envelope from POST /spcode/git-worktree-lock. */
export function parseSpcodeWorktreeLock(
  raw: unknown,
): ParseResult<SpcodeWorktreeMgmtSnapshot> {
  const d = unwrapEnvelope(raw) as SpcodeWorktreeMgmtRawData;
  return {
    kind: "ok",
    snapshot: buildSnapshot(d, {
      locked: true,
      lockReason: d.lock_reason ?? null,
    }),
  };
}

/** Parse the envelope from POST /spcode/git-worktree-unlock. */
export function parseSpcodeWorktreeUnlock(
  raw: unknown,
): ParseResult<SpcodeWorktreeMgmtSnapshot> {
  const d = unwrapEnvelope(raw) as SpcodeWorktreeMgmtRawData;
  return {
    kind: "ok",
    snapshot: buildSnapshot(d, {
      locked: false,
      lockReason: null,
    }),
  };
}
```

- [ ] **Step 4: 运行测试，验证通过**

Run: `cd dashboard && node --test tests/parseSpcodeWorktreeManagement.test.mjs 2>&1 | tail -20`
Expected: PASS, 4 tests passed

- [ ] **Step 5: 提交**

```bash
git add dashboard/src/composables/parseSpcodeWorktreeManagement.ts dashboard/tests/parseSpcodeWorktreeManagement.test.mjs
git commit -m "feat(worktree-mgmt): implement 4 endpoint parsers + tests"
```

### Task 1.4: 实现 reason 字典 + classifyWorktreeReason

**Files:**
- Modify: `dashboard/src/composables/parseSpcodeWorktreeManagement.ts`

- [ ] **Step 1: 写失败的测试**

```mjs
// 追加到 tests/parseSpcodeWorktreeManagement.test.mjs

test("classifyWorktreeReason: known reason returns meta", () => {
  const meta = classifyWorktreeReason("worktree_locked", "remove");
  assert.equal(meta.i18nKey, "error.reason.worktree_locked");
  assert.equal(meta.color, "warning");
});

test("classifyWorktreeReason: withStderr for git_error", () => {
  const meta = classifyWorktreeReason("git_error", "remove");
  assert.equal(meta.withStderr, true);
  assert.equal(meta.color, "error");
});

test("classifyWorktreeReason: unknown endpoint-mismatched reason returns unknown", () => {
  // hook_rejected is a commit-only reason; classify on 'remove' should be unknown
  const meta = classifyWorktreeReason("hook_rejected", "remove");
  assert.equal(meta.i18nKey, "error.reason.unknown");
});

test("classifyWorktreeReason: null/undefined returns unknown", () => {
  assert.equal(classifyWorktreeReason(null, "add").i18nKey, "error.reason.unknown");
  assert.equal(classifyWorktreeReason(undefined, "lock").i18nKey, "error.reason.unknown");
});

test("classifyWorktreeReason: network always returns network", () => {
  const meta = classifyWorktreeReason("network", "add");
  assert.equal(meta.i18nKey, "error.reason.network");
});

test("ALLOWED_WORKTREE_REASONS covers all 4 endpoints", () => {
  for (const ep of ["add", "remove", "lock", "unlock"]) {
    assert.ok(Array.isArray(ALLOWED_WORKTREE_REASONS[ep]), `${ep} should be array`);
    assert.ok(ALLOWED_WORKTREE_REASONS[ep].length > 0, `${ep} should have reasons`);
  }
});
```

- [ ] **Step 2: 运行测试，验证失败**

Run: `cd dashboard && node --test tests/parseSpcodeWorktreeManagement.test.mjs 2>&1 | tail -15`
Expected: FAIL with "classifyWorktreeReason is not a function"

- [ ] **Step 3: 实现 reason 字典 + 分类器**

```ts
// ── Reason classification (spec §4) ──────────────────────

export interface ReasonMeta {
  i18nKey: string;
  color: "error" | "warning";
  withStderr?: boolean;
  withReason?: boolean;
}

export const WORKTREE_MGMT_REASON_CODES: Record<string, ReasonMeta> = {
  // 前置类
  feature_disabled:        { i18nKey: "error.reason.feature_disabled", color: "error" },
  no_project_loaded:       { i18nKey: "error.reason.no_project_loaded", color: "error" },
  worktree_invalid:        { i18nKey: "error.reason.worktree_invalid", color: "error" },
  directory_missing:       { i18nKey: "error.reason.directory_missing", color: "error" },
  not_a_git_repo:          { i18nKey: "error.reason.not_a_git_repo", color: "error" },
  git_unavailable:         { i18nKey: "error.reason.git_unavailable", color: "error" },
  git_error:               { i18nKey: "error.reason.git_error", color: "error", withStderr: true },
  // body 类
  invalid_body:            { i18nKey: "error.reason.invalid_body", color: "error" },
  invalid_branch:          { i18nKey: "error.reason.invalid_branch", color: "error" },
  invalid_param:           { i18nKey: "error.reason.invalid_param", color: "error" },
  // 路径类
  path_unsafe:             { i18nKey: "error.reason.path_unsafe", color: "error" },
  // 业务类(ADD)
  path_exists_nonempty:    { i18nKey: "error.reason.path_exists_nonempty", color: "warning" },
  cannot_create_existing:  { i18nKey: "error.reason.cannot_create_existing", color: "warning" },
  // 业务类(REMOVE/LOCK/UNLOCK)
  worktree_not_found:      { i18nKey: "error.reason.worktree_not_found", color: "warning" },
  cannot_remove_main:      { i18nKey: "error.reason.cannot_remove_main", color: "error" },
  worktree_locked:         { i18nKey: "error.reason.worktree_locked", color: "warning" },
  worktree_dirty:          { i18nKey: "error.reason.worktree_dirty", color: "warning" },
  already_locked:          { i18nKey: "error.reason.already_locked", color: "warning" },
  not_locked:              { i18nKey: "error.reason.not_locked", color: "warning" },
  // 网络/未知
  network:                 { i18nKey: "error.reason.network", color: "error" },
  unknown:                 { i18nKey: "error.reason.unknown", color: "error", withReason: true },
};

/** Allowed reason codes per endpoint (spec §4.1). */
export const ALLOWED_WORKTREE_REASONS: Record<WorktreeMgmtEndpoint, readonly string[]> = {
  add: [
    "feature_disabled", "no_project_loaded", "worktree_invalid",
    "directory_missing", "not_a_git_repo", "git_unavailable", "git_error",
    "invalid_body", "invalid_branch", "invalid_param", "path_unsafe",
    "path_exists_nonempty", "cannot_create_existing",
  ],
  remove: [
    "feature_disabled", "no_project_loaded", "worktree_invalid",
    "directory_missing", "not_a_git_repo", "git_unavailable", "git_error",
    "invalid_body", "path_unsafe",
    "worktree_not_found", "cannot_remove_main", "worktree_locked", "worktree_dirty",
  ],
  lock: [
    "feature_disabled", "no_project_loaded", "worktree_invalid",
    "directory_missing", "not_a_git_repo", "git_unavailable", "git_error",
    "invalid_body", "path_unsafe",
    "worktree_not_found", "already_locked",
  ],
  unlock: [
    "feature_disabled", "no_project_loaded", "worktree_invalid",
    "directory_missing", "not_a_git_repo", "git_unavailable", "git_error",
    "invalid_body", "path_unsafe",
    "worktree_not_found", "not_locked",
  ],
};

/** Classify a reason string to a ReasonMeta.
 *  Returns `unknown` for null / undefined / unknown / endpoint-mismatched codes. */
export function classifyWorktreeReason(
  reason: string | null | undefined,
  endpoint: WorktreeMgmtEndpoint,
): ReasonMeta {
  if (reason === null || reason === undefined) {
    return WORKTREE_MGMT_REASON_CODES.unknown;
  }
  if (reason === "network") {
    return WORKTREE_MGMT_REASON_CODES.network;
  }
  if (!(ALLOWED_WORKTREE_REASONS[endpoint] as readonly string[]).includes(reason)) {
    return WORKTREE_MGMT_REASON_CODES.unknown;
  }
  return WORKTREE_MGMT_REASON_CODES[reason] ?? WORKTREE_MGMT_REASON_CODES.unknown;
}
```

- [ ] **Step 4: 运行测试，验证通过**

Run: `cd dashboard && node --test tests/parseSpcodeWorktreeManagement.test.mjs 2>&1 | tail -20`
Expected: PASS, 10 tests passed (4 parser + 6 classifier)

- [ ] **Step 5: 提交**

```bash
git add dashboard/src/composables/parseSpcodeWorktreeManagement.ts dashboard/tests/parseSpcodeWorktreeManagement.test.mjs
git commit -m "feat(worktree-mgmt): add reason codes and classifyWorktreeReason"
```

---

## Chunk 2: 扩展 useSpcodeWorktrees Composable

### Task 2.1: 扩展类型接口

**Files:**
- Modify: `dashboard/src/composables/useSpcodeWorktrees.ts`

- [ ] **Step 1: 添加 WorktreeMgmtParams 类型到接口**

在 `UseSpcodeWorktrees` 接口前追加：

```ts
// ── Worktree management (spec 2026-06-27 §1.1) ──────────────

/** Parameters for the 4 mutation methods. All 4 share the same shape
 *  (path + optional context) so the consumer can pattern-match
 *  uniformly; the 4 parsers differ only in endpoint-specific
 *  response field interpretation. */
export interface WorktreeMgmtParams {
  /** Absolute path of the worktree to act on. For `add`, the new
   *  worktree's location; for the rest, the existing target. */
  path: string;
  /** Optional nested worktree context (rare; passed via ?worktree=
   *  query param to the backend). Aligns with §2.5 of the spcode spec. */
  worktree?: string | null;
  /** Session ID. Falls back to the composable's tracked umo if null. */
  umo?: string | null;
}

/** ADD-specific params (extends WorktreeMgmtParams with create/force/detach/base). */
export interface WorktreeAddParams extends WorktreeMgmtParams {
  branch?: string;
  create?: boolean;
  force?: boolean;
  detach?: boolean;
  base?: string;
}

/** REMOVE-specific params (extends with force for dirty bypass). */
export interface WorktreeRemoveParams extends WorktreeMgmtParams {
  force?: boolean;
}

/** LOCK-specific params (extends with reason). */
export interface WorktreeLockParams extends WorktreeMgmtParams {
  reason?: string;
}

/** Discriminated union return type for all 4 mutations. Mirrors the
 *  useSpcodeFileRestore pattern (ok / failure-with-reason+stderr). */
export type WorktreeMgmtResult =
  | { ok: true; snapshot: SpcodeGitWorktreesSnapshot }
  | { ok: false; reason: string; stderr?: string };
```

- [ ] **Step 2: 添加 import**

在文件顶部 imports 后追加：

```ts
import {
  parseSpcodeWorktreeAdd,
  parseSpcodeWorktreeRemove,
  parseSpcodeWorktreeLock,
  parseSpcodeWorktreeUnlock,
} from "@/composables/parseSpcodeWorktreeManagement";
```

- [ ] **Step 3: 扩展 `UseSpcodeWorktrees` 接口**

在 `dispose: () => void` 之前追加：

```ts
  /**
   * Add a new worktree. See `parseSpcodeWorktreeAdd` for the response
   * shape; on success, the returned snapshot's `worktrees` array is
   * the authoritative refreshed list and is swapped into `state` atomically.
   */
  add: (params: WorktreeAddParams) => Promise<WorktreeMgmtResult>;
  /**
   * Remove an existing worktree. Frontend must NOT call this for the
   * main worktree (ui-side disabled); backend will refuse with
   * `cannot_remove_main` regardless. The `force` flag bypasses the
   * dirty check only (locked check is structural and is not bypassed).
   */
  remove: (params: WorktreeRemoveParams) => Promise<WorktreeMgmtResult>;
  /** Lock a worktree. Optional `reason` is stored alongside the lock
   *  (git 2.30+); backend allows locking the main worktree but the
   *  UI hides the entry for it (see spec §11.2). */
  lock: (params: WorktreeLockParams) => Promise<WorktreeMgmtResult>;
  /** Unlock a worktree. Non-idempotent: second unlock returns
   *  `not_locked`. UI should disable when `locked=false`. */
  unlock: (params: WorktreeMgmtParams) => Promise<WorktreeMgmtResult>;
```

- [ ] **Step 4: 验证 typecheck 通过**

Run: `cd dashboard && pnpm typecheck 2>&1 | head -30`
Expected: 错误在 add/remove/lock/unlock **实现缺失**（预期，因为还没实现函数体）

### Task 2.2: 实现 add() 方法

**Files:**
- Modify: `dashboard/src/composables/useSpcodeWorktrees.ts`

- [ ] **Step 1: 在 `useSpcodeWorktrees()` 内部 `dispose` 之前添加 add 实现**

```ts
  // ── Worktree management methods (spec 2026-06-27 §3) ────────
  //
  // All 4 share the same shape: build a new AbortController (cancel
  // any in-flight read), POST to the endpoint, parse the response,
  // atomically swap `state.value` with the refreshed snapshot. The
  // parsers are imported from parseSpcodeWorktreeManagement.ts.
  //
  // **Single-flight policy**: each call aborts the previous
  // AbortController. This means rapid double-click → the first call
  // resolves as `aborted` (handled by the `isMounted` guard), the
  // second runs to completion. The orchestrator (GitDiffSidebar)
  // guards UI buttons with `isXxx` flags to make double-clicks
  // impossible at the UI level too (defense in depth).

  async function add(params: WorktreeAddParams): Promise<WorktreeMgmtResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    const umo = params.umo ?? spcodeStatus.status.value.umo;
    if (!umo) return { ok: false, reason: "no_project_loaded" };
    const ctrl = new AbortController();
    mutationAbort?.abort();
    mutationAbort = ctrl;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/git-worktree-add",
        {
          path: params.path,
          branch: params.branch,
          create: params.create,
          force: params.force,
          detach: params.detach,
          base: params.base,
        },
        {
          signal: ctrl.signal,
          params: { umo, worktree: params.worktree ?? undefined },
        },
      );
      if (!isMounted || ctrl.signal.aborted) return { ok: false, reason: "aborted" };
      const parsed = parseSpcodeWorktreeAdd(resp.data);
      if (parsed.kind !== "ok") return { ok: false, reason: "unknown" };
      // Atomically replace state with the refreshed list.
      const refreshed = parseSpcodeGitWorktrees({
        loaded: parsed.snapshot.meta.loaded,
        directory: parsed.snapshot.meta.directory,
        umo: parsed.snapshot.meta.umo,
        worktrees: parsed.snapshot.worktrees,
        reason: parsed.snapshot.meta.reason,
        stderr: parsed.snapshot.meta.stderr,
        elapsed_ms: parsed.snapshot.meta.elapsedMs,
      });
      state.value = { kind: "ok", snapshot: refreshed };
      return { ok: true, snapshot: refreshed };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      if ((err as { name?: string })?.name === "CanceledError") {
        return { ok: false, reason: "aborted" };
      }
      return { ok: false, reason: classifyMutationError(err) };
    }
  }
```

- [ ] **Step 2: 添加 `mutationAbort` 状态 + `classifyMutationError`**

在 `useSpcodeWorktrees()` 函数顶部 `let abortController` 旁添加：

```ts
  // Single-flight guard for mutation methods (separate from the read
  // path's `abortController` so a read in progress doesn't cancel a
  // pending write or vice versa).
  let mutationAbort: AbortController | null = null;
```

在文件底部（`classifyError` 旁）添加：

```ts
function classifyMutationError(err: unknown): string {
  if (typeof err === "object" && err !== null) {
    const anyErr = err as { code?: string; message?: string };
    if (anyErr.code === "ERR_NETWORK" || /network/i.test(anyErr.message ?? "")) {
      return "network";
    }
  }
  return "unknown";
}
```

- [ ] **Step 3: 验证 typecheck 通过**

Run: `cd dashboard && pnpm typecheck 2>&1 | head -30`
Expected: 错误减少到只剩 remove/lock/unlock 实现缺失

- [ ] **Step 4: 提交**

```bash
git add dashboard/src/composables/useSpcodeWorktrees.ts
git commit -m "feat(worktree-mgmt): add add() method to useSpcodeWorktrees"
```

### Task 2.3: 实现 remove() / lock() / unlock() 方法

**Files:**
- Modify: `dashboard/src/composables/useSpcodeWorktrees.ts`

- [ ] **Step 1: 在 add() 后添加 remove() 实现**

```ts
  async function remove(params: WorktreeRemoveParams): Promise<WorktreeMgmtResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    const umo = params.umo ?? spcodeStatus.status.value.umo;
    if (!umo) return { ok: false, reason: "no_project_loaded" };
    const ctrl = new AbortController();
    mutationAbort?.abort();
    mutationAbort = ctrl;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/git-worktree-remove",
        { path: params.path, force: params.force },
        {
          signal: ctrl.signal,
          params: { umo, worktree: params.worktree ?? undefined },
        },
      );
      if (!isMounted || ctrl.signal.aborted) return { ok: false, reason: "aborted" };
      const parsed = parseSpcodeWorktreeRemove(resp.data);
      if (parsed.kind !== "ok") return { ok: false, reason: "unknown" };
      const refreshed = parseSpcodeGitWorktrees({
        loaded: parsed.snapshot.meta.loaded,
        directory: parsed.snapshot.meta.directory,
        umo: parsed.snapshot.meta.umo,
        worktrees: parsed.snapshot.worktrees,
        reason: parsed.snapshot.meta.reason,
        stderr: parsed.snapshot.meta.stderr,
        elapsed_ms: parsed.snapshot.meta.elapsedMs,
      });
      state.value = { kind: "ok", snapshot: refreshed };
      return { ok: true, snapshot: refreshed };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      if ((err as { name?: string })?.name === "CanceledError") {
        return { ok: false, reason: "aborted" };
      }
      return { ok: false, reason: classifyMutationError(err) };
    }
  }
```

- [ ] **Step 2: 添加 lock() 实现**

```ts
  async function lock(params: WorktreeLockParams): Promise<WorktreeMgmtResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    const umo = params.umo ?? spcodeStatus.status.value.umo;
    if (!umo) return { ok: false, reason: "no_project_loaded" };
    const ctrl = new AbortController();
    mutationAbort?.abort();
    mutationAbort = ctrl;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/git-worktree-lock",
        { path: params.path, reason: params.reason },
        {
          signal: ctrl.signal,
          params: { umo, worktree: params.worktree ?? undefined },
        },
      );
      if (!isMounted || ctrl.signal.aborted) return { ok: false, reason: "aborted" };
      const parsed = parseSpcodeWorktreeLock(resp.data);
      if (parsed.kind !== "ok") return { ok: false, reason: "unknown" };
      const refreshed = parseSpcodeGitWorktrees({
        loaded: parsed.snapshot.meta.loaded,
        directory: parsed.snapshot.meta.directory,
        umo: parsed.snapshot.meta.umo,
        worktrees: parsed.snapshot.worktrees,
        reason: parsed.snapshot.meta.reason,
        stderr: parsed.snapshot.meta.stderr,
        elapsed_ms: parsed.snapshot.meta.elapsedMs,
      });
      state.value = { kind: "ok", snapshot: refreshed };
      return { ok: true, snapshot: refreshed };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      if ((err as { name?: string })?.name === "CanceledError") {
        return { ok: false, reason: "aborted" };
      }
      return { ok: false, reason: classifyMutationError(err) };
    }
  }
```

- [ ] **Step 3: 添加 unlock() 实现**

```ts
  async function unlock(params: WorktreeMgmtParams): Promise<WorktreeMgmtResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    const umo = params.umo ?? spcodeStatus.status.value.umo;
    if (!umo) return { ok: false, reason: "no_project_loaded" };
    const ctrl = new AbortController();
    mutationAbort?.abort();
    mutationAbort = ctrl;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/git-worktree-unlock",
        { path: params.path },
        {
          signal: ctrl.signal,
          params: { umo, worktree: params.worktree ?? undefined },
        },
      );
      if (!isMounted || ctrl.signal.aborted) return { ok: false, reason: "aborted" };
      const parsed = parseSpcodeWorktreeUnlock(resp.data);
      if (parsed.kind !== "ok") return { ok: false, reason: "unknown" };
      const refreshed = parseSpcodeGitWorktrees({
        loaded: parsed.snapshot.meta.loaded,
        directory: parsed.snapshot.meta.directory,
        umo: parsed.snapshot.meta.umo,
        worktrees: parsed.snapshot.worktrees,
        reason: parsed.snapshot.meta.reason,
        stderr: parsed.snapshot.meta.stderr,
        elapsed_ms: parsed.snapshot.meta.elapsedMs,
      });
      state.value = { kind: "ok", snapshot: refreshed };
      return { ok: true, snapshot: refreshed };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      if ((err as { name?: string })?.name === "CanceledError") {
        return { ok: false, reason: "aborted" };
      }
      return { ok: false, reason: classifyMutationError(err) };
    }
  }
```

- [ ] **Step 4: 在 return 语句中添加新方法**

```ts
  return { state, refresh, startPolling, stopPolling, add, remove, lock, unlock, dispose };
```

- [ ] **Step 5: 在 `dispose()` 中 abort mutation**

修改 `dispose` 函数：

```ts
  function dispose(): void {
    isMounted = false
    stopPolling()
    abortController?.abort()
    abortController = null
    mutationAbort?.abort()
    mutationAbort = null
  }
```

- [ ] **Step 6: 验证 typecheck 通过**

Run: `cd dashboard && pnpm typecheck 2>&1 | head -30`
Expected: 无错误

- [ ] **Step 7: 运行 parser 测试（回归）**

Run: `cd dashboard && node --test tests/parseSpcodeWorktreeManagement.test.mjs 2>&1 | tail -5`
Expected: PASS, 10 tests passed

- [ ] **Step 8: 提交**

```bash
git add dashboard/src/composables/useSpcodeWorktrees.ts
git commit -m "feat(worktree-mgmt): add remove/lock/unlock methods"
```

---

## Chunk 3: i18n 键（三语种）

> 自包含 chunk：纯数据修改，无逻辑依赖

### Task 3.1: 添加 zh-CN 键

**Files:**
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json`

- [ ] **Step 1: 定位插入点**

在 `worktreeTabs` 块后（`"detachedBadge": "游离"` 那行）插入 `worktreeMgmt` 子树：

```jsonc
,
"worktreeMgmt": {
  "addButton": "新建 worktree",
  "addButtonAria": "新建一个 git worktree",
  "contextMenu": {
    "ariaLabel": "worktree 管理",
    "lock": "锁定…",
    "unlock": "解锁",
    "remove": "删除…",
    "mainDisabled": "主 worktree 不可锁定/删除"
  },
  "create": {
    "title": "新建 worktree",
    "modeCreate": "创建新分支 (-b)",
    "modeForce": "强制覆盖 (-B)",
    "modeDetach": "分离 HEAD",
    "modeForceWarning": "该操作将覆盖已存在分支",
    "branch": "分支名",
    "branchHint": "detach 模式可省略",
    "branchRequired": "请输入分支名",
    "path": "路径",
    "pathHint": "绝对路径,父目录必须存在",
    "pathRequired": "请输入路径",
    "base": "起始点",
    "baseHint": "仅创建新分支模式生效,默认 main",
    "submit": "创建",
    "cancel": "取消",
    "success": "已创建 worktree {branch}"
  },
  "remove": {
    "confirmTitle": "删除 worktree",
    "confirmMessage": "确认删除 worktree {branch}?",
    "confirmMessageWithPath": "确认删除 {path} ({branch})?",
    "dirtyHint": "该 worktree 有 {count} 个未提交改动。",
    "force": "强制删除(丢弃 {count} 个未提交改动)",
    "confirm": "删除",
    "cancel": "取消",
    "success": "已删除 worktree {branch}"
  },
  "lock": {
    "dialogTitle": "锁定 worktree",
    "targetInfo": "锁定 worktree {branch}",
    "reason": "锁定原因(可选)",
    "reasonHint": "建议 200 字符以内",
    "submit": "锁定",
    "cancel": "取消",
    "success": "已锁定 worktree {branch}",
    "alreadyLocked": "该 worktree 已锁定"
  },
  "unlock": {
    "confirmTitle": "解锁 worktree",
    "confirmMessage": "确认解锁 worktree {branch}?",
    "confirm": "解锁",
    "cancel": "取消",
    "success": "已解锁 worktree {branch}"
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

> **注意**：如果现有 `error` 块已存在，需要把新增 reason 合并进去（**不是覆盖**）。先 `cat` 一下现有文件确认结构。

- [ ] **Step 2: 验证 JSON 合法**

Run: `cd dashboard && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/zh-CN/features/chat.json', 'utf8'))" && echo OK`
Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add dashboard/src/i18n/locales/zh-CN/features/chat.json
git commit -m "feat(i18n): add zh-CN worktree management keys"
```

### Task 3.2: 添加 en-US 键

**Files:**
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json`

- [ ] **Step 1: 插入相同结构的英文键**

```jsonc
"worktreeMgmt": {
  "addButton": "New worktree",
  "addButtonAria": "Create a new git worktree",
  "contextMenu": {
    "ariaLabel": "Worktree management",
    "lock": "Lock…",
    "unlock": "Unlock",
    "remove": "Remove…",
    "mainDisabled": "Main worktree cannot be locked or removed"
  },
  "create": {
    "title": "New worktree",
    "modeCreate": "Create new branch (-b)",
    "modeForce": "Force overwrite (-B)",
    "modeDetach": "Detached HEAD",
    "modeForceWarning": "This will overwrite the existing branch",
    "branch": "Branch name",
    "branchHint": "Optional in detach mode",
    "branchRequired": "Branch name is required",
    "path": "Path",
    "pathHint": "Absolute path; parent directory must exist",
    "pathRequired": "Path is required",
    "base": "Base ref",
    "baseHint": "Only used in create mode; defaults to main",
    "submit": "Create",
    "cancel": "Cancel",
    "success": "Created worktree {branch}"
  },
  "remove": {
    "confirmTitle": "Remove worktree",
    "confirmMessage": "Remove worktree {branch}?",
    "confirmMessageWithPath": "Remove {path} ({branch})?",
    "dirtyHint": "This worktree has {count} uncommitted change(s).",
    "force": "Force remove (discard {count} uncommitted change(s))",
    "confirm": "Remove",
    "cancel": "Cancel",
    "success": "Removed worktree {branch}"
  },
  "lock": {
    "dialogTitle": "Lock worktree",
    "targetInfo": "Lock worktree {branch}",
    "reason": "Lock reason (optional)",
    "reasonHint": "Recommended under 200 characters",
    "submit": "Lock",
    "cancel": "Cancel",
    "success": "Locked worktree {branch}",
    "alreadyLocked": "This worktree is already locked"
  },
  "unlock": {
    "confirmTitle": "Unlock worktree",
    "confirmMessage": "Unlock worktree {branch}?",
    "confirm": "Unlock",
    "cancel": "Cancel",
    "success": "Unlocked worktree {branch}"
  }
},
"error": {
  "reason": {
    "invalid_branch": "Invalid branch name format",
    "invalid_param": "Invalid base ref format",
    "path_exists_nonempty": "Target path is already in use",
    "cannot_create_existing": "Branch already exists; enable force overwrite",
    "worktree_not_found": "Worktree no longer exists",
    "cannot_remove_main": "Main worktree cannot be removed",
    "worktree_locked": "Worktree is locked; unlock first",
    "worktree_dirty": "Worktree has uncommitted changes",
    "already_locked": "Worktree is already locked",
    "not_locked": "Worktree is not locked"
  }
}
```

- [ ] **Step 2: 验证 JSON 合法**

Run: `cd dashboard && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/en-US/features/chat.json', 'utf8'))" && echo OK`
Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add dashboard/src/i18n/locales/en-US/features/chat.json
git commit -m "feat(i18n): add en-US worktree management keys"
```

### Task 3.3: 添加 ru-RU 键（占位 stub）

**Files:**
- Modify: `dashboard/src/i18n/locales/ru-RU/features/chat.json`

- [ ] **Step 1: 复制 en-US 键值作为占位**

> **策略**：用英文值占位，后续由俄语翻译者补齐。这样不影响功能交付，且 i18n 校验不会失败。

```bash
cd dashboard
node -e "
const fs = require('fs');
const en = JSON.parse(fs.readFileSync('src/i18n/locales/en-US/features/chat.json', 'utf8'));
const ru = JSON.parse(fs.readFileSync('src/i18n/locales/ru-RU/features/chat.json', 'utf8'));
// 仅插入 worktreeMgmt 和新增的 error.reason,不覆盖已有键
ru.worktreeMgmt = en.worktreeMgmt;
ru.error = ru.error || {};
ru.error.reason = Object.assign({}, ru.error.reason || {}, en.error.reason);
fs.writeFileSync('src/i18n/locales/ru-RU/features/chat.json', JSON.stringify(ru, null, 2) + '\n');
console.log('OK');
"
```

- [ ] **Step 2: 验证 JSON 合法 + 不破坏现有键**

Run: `cd dashboard && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/ru-RU/features/chat.json', 'utf8'))" && echo OK`
Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add dashboard/src/i18n/locales/ru-RU/features/chat.json
git commit -m "feat(i18n): add ru-RU worktree management keys (en-US placeholder)"
```

---

## Chunk 4: WorktreeCreateDialog 组件

### Task 4.1: 创建组件骨架

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/WorktreeCreateDialog.vue`

- [ ] **Step 1: 创建组件文件头 + 模板骨架**

```vue
<!-- Author: elecvoid243
     Date: 2026-06-27
     Spec: docs/superpowers/specs/2026-06-27-git-worktree-frontend-management-design.md §2.2.A
     Form for POST /spcode/git-worktree-add. Emits 'submit' on success
     with validated params; emits 'cancel' on close. -->
<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import type { WorktreeAddParams } from "@/composables/useSpcodeWorktrees";

const { tm } = useModuleI18n("features/chat");
const spcodeStatus = useSpcodeProjectStatus();

const props = defineProps<{
  modelValue: boolean;
  isSubmitting?: boolean;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
  (e: "submit", params: WorktreeAddParams): void;
  (e: "cancel"): void;
}>();

// ── Form state (spec §2.2.A table) ────────────────────────
type CreateMode = "create" | "force" | "detach";
const createMode = ref<CreateMode>("create");
const branch = ref<string>("");
const path = ref<string>("");
const base = ref<string>("main");

const projectRoot = computed(
  () => spcodeStatus.status.value.directory ?? "",
);

// Branch sanitization for default path suggestion.
function defaultPath(branchName: string, root: string): string {
  if (!root || !branchName) return "";
  const sep = root.includes("\\") ? "\\" : "/";
  return `${root}${sep}.worktrees${sep}${branchName.replace(/\//g, "-")}`;
}

// Re-compute default path when branch changes (only if user hasn't manually edited path).
const userEditedPath = ref(false);
watch(branch, (b) => {
  if (!userEditedPath.value && b) {
    path.value = defaultPath(b, projectRoot.value);
  }
});
watch(path, () => {
  userEditedPath.value = true;
});

// Field-level validation (aligns with backend 5-step preflight).
const errors = computed(() => {
  const errs: { branch?: string; path?: string; base?: string } = {};
  if (createMode.value !== "detach" && !branch.value.trim()) {
    errs.branch = tm(
      "spcodeProjectLoad.diffSidebar.worktreeMgmt.create.branchRequired",
    );
  }
  if (!path.value.trim()) {
    errs.path = tm(
      "spcodeProjectLoad.diffSidebar.worktreeMgmt.create.pathRequired",
    );
  }
  return errs;
});

const canSubmit = computed(
  () => Object.keys(errors.value).length === 0 && !props.isSubmitting,
);

function onCancel(): void {
  if (props.isSubmitting) return;
  emit("update:modelValue", false);
  emit("cancel");
}

function onSubmit(): void {
  if (!canSubmit.value) return;
  const params: WorktreeAddParams = {
    path: path.value.trim(),
    umo: spcodeStatus.status.value.umo,
  };
  if (createMode.value !== "detach") {
    params.branch = branch.value.trim();
  }
  if (createMode.value === "create") {
    params.create = true;
    if (base.value.trim()) params.base = base.value.trim();
  } else if (createMode.value === "force") {
    params.force = true;
  } else if (createMode.value === "detach") {
    params.detach = true;
  }
  emit("submit", params);
}
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    persistent
    max-width="520"
  >
    <v-card>
      <v-card-title class="text-h6">
        {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.create.title") }}
      </v-card-title>
      <v-card-text>
        <!-- Mode radio group (mutually exclusive) -->
        <div class="worktree-create-mode">
          <v-radio-group v-model="createMode" inline density="compact">
            <v-radio
              value="create"
              :label="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.modeCreate')"
            />
            <v-radio
              value="force"
              :label="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.modeForce')"
            />
            <v-radio
              value="detach"
              :label="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.modeDetach')"
            />
          </v-radio-group>
          <v-chip
            v-if="createMode === 'force'"
            size="x-small"
            color="warning"
            variant="tonal"
            class="ml-2"
          >
            <v-icon start size="12">mdi-alert</v-icon>
            {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.create.modeForceWarning") }}
          </v-chip>
        </div>

        <!-- Branch (disabled in detach mode) -->
        <v-text-field
          v-model="branch"
          :label="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.branch')"
          :hint="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.branchHint')"
          :error-messages="errors.branch ? [errors.branch] : []"
          :disabled="createMode === 'detach'"
          density="comfortable"
          variant="outlined"
          class="mt-3"
        />

        <!-- Path (absolute) -->
        <v-text-field
          v-model="path"
          :label="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.path')"
          :hint="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.pathHint')"
          :error-messages="errors.path ? [errors.path] : []"
          density="comfortable"
          variant="outlined"
          class="mt-2"
        />

        <!-- Base (only in create mode) -->
        <v-text-field
          v-if="createMode === 'create'"
          v-model="base"
          :label="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.base')"
          :hint="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.baseHint')"
          density="comfortable"
          variant="outlined"
          class="mt-2"
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="isSubmitting" @click="onCancel">
          {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.create.cancel") }}
        </v-btn>
        <v-btn
          variant="flat"
          color="primary"
          :loading="isSubmitting"
          :disabled="!canSubmit"
          @click="onSubmit"
        >
          {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.create.submit") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.worktree-create-mode {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
```

- [ ] **Step 2: 验证 typecheck 通过**

Run: `cd dashboard && pnpm typecheck 2>&1 | head -30`
Expected: 无错误（i18n 键缺失警告可能存在，但不影响编译）

- [ ] **Step 3: 提交**

```bash
git add dashboard/src/components/chat/message_list_comps/WorktreeCreateDialog.vue
git commit -m "feat(worktree-mgmt): add WorktreeCreateDialog component"
```

---

## Chunk 5: GitDiffSidebar 集成

> 最大的 chunk（约 250 行新增）。**严格按顺序执行**，每步独立 commit。

### Task 5.1: 在 GitDiffSidebar 中 import 新组件 + 新增 ref 状态

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue`

- [ ] **Step 1: 追加 import**

在现有 imports 后追加：

```ts
import { useSpcodeWorktrees, type WorktreeAddParams, type WorktreeLockParams } from "@/composables/useSpcodeWorktrees";
import WorktreeCreateDialog from "@/components/chat/message_list_comps/WorktreeCreateDialog.vue";
```

- [ ] **Step 2: 在 `confirmDialogOpen` ref 旁新增 4 个 ref + 4 个 loading ref**

定位到 `const confirmDialogOpen = ref(false);` 附近，**紧接着**追加：

```ts
// ── Worktree management state (spec 2026-06-27 §2.4) ────────
const createDialogOpen = ref(false);
const removeDialogOpen = ref(false);
const lockDialogOpen = ref(false);
const confirmUnlockOpen = ref(false);
const confirmUnlockPath = ref<string | null>(null);
const lockDialogTarget = ref<{ path: string; branch: string | null } | null>(null);
const removeDialogTarget = ref<{ path: string; branch: string | null } | null>(null);
const dirtyCount = ref<number | null>(null);
const isRemoving = ref(false);
const isLocking = ref(false);
const isUnlocking = ref(false);
const isCreating = ref(false);
const lastCreateError = ref<{ reason: string; stderr: string } | null>(null);
```

- [ ] **Step 3: 验证 typecheck 通过（仅新增 ref，无功能）**

Run: `cd dashboard && pnpm typecheck 2>&1 | head -20`
Expected: 无错误

- [ ] **Step 4: 提交**

```bash
git add dashboard/src/components/chat/GitDiffSidebar.vue
git commit -m "feat(worktree-mgmt): scaffold sidebar state refs"
```

### Task 5.2: 改造 tab 行模板（加 `+` 按钮 + contextmenu）

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue`

- [ ] **Step 1: 定位 worktree tabs 块**

找到 `<div v-if="hasMultipleWorktrees" class="git-diff-sidebar-tabs" ...>` 块（行号约 760 附近）。

- [ ] **Step 2: 修改 v-for tab，加 `@contextmenu.prevent` + `+` 按钮**

将整个 tabs 块替换为：

```vue
      <div
        v-if="hasMultipleWorktrees"
        class="git-diff-sidebar-tabs"
        role="tablist"
        :aria-label="tm('spcodeProjectLoad.diffSidebar.worktreeTabs.ariaLabel')"
      >
        <span class="git-diff-sidebar-tabs-label">
          {{ tm("spcodeProjectLoad.diffSidebar.worktreeTabs.label") }}
        </span>
        <button
          v-for="wt in worktreeList"
          :key="wt.path"
          type="button"
          role="tab"
          :aria-selected="(selectedWorktree ?? mainWorktreePath) === wt.path"
          :class="[
            'git-diff-sidebar-tab',
            {
              'git-diff-sidebar-tab--active':
                (selectedWorktree ?? mainWorktreePath) === wt.path,
            },
          ]"
          :title="wt.path"
          @click="onWorktreeChange(wt.isMain ? null : wt.path)"
          @contextmenu.prevent="(e) => openContextMenu(e, wt)"
        >
          <v-icon v-if="wt.isMain" size="12" class="git-diff-sidebar-tab-icon"
            >mdi-home</v-icon
          >
          <v-icon v-else-if="wt.locked" size="12" class="git-diff-sidebar-tab-icon"
            >mdi-lock</v-icon
          >
          <span class="git-diff-sidebar-tab-label">
            {{
              wt.branch ??
              (wt.isMain
                ? tm("spcodeProjectLoad.diffSidebar.worktreeTabs.mainBadge")
                : wt.headSha.slice(0, 7))
            }}
          </span>
          <span v-if="!wt.branch" class="git-diff-sidebar-tab-badge">{{
            tm("spcodeProjectLoad.diffSidebar.worktreeTabs.detachedBadge")
          }}</span>
        </button>
        <!-- Add button (spec 2026-06-27 §2.1) -->
        <button
          type="button"
          class="git-diff-sidebar-tab-add"
          :aria-label="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.addButtonAria')"
          :title="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.addButton')"
          @click="openCreateDialog"
        >
          <v-icon size="14">mdi-plus</v-icon>
        </button>

        <!-- Context menu (spec 2026-06-27 §2.3) -->
        <v-menu
          v-model="contextMenu.open"
          :location-strategy="'absolute'"
          :position-x="contextMenu.x"
          :position-y="contextMenu.y"
        >
          <v-list density="compact">
            <template v-if="contextMenu.wt && !contextMenu.wt.isMain">
              <v-list-item
                :disabled="contextMenu.wt.locked"
                @click="onLockClick(contextMenu.wt!)"
              >
                <template #prepend>
                  <v-icon>{{
                    contextMenu.wt.locked ? "mdi-lock-open-variant" : "mdi-lock"
                  }}</v-icon>
                </template>
                <v-list-item-title>{{
                  contextMenu.wt.locked
                    ? tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.contextMenu.unlock")
                    : tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.contextMenu.lock")
                }}</v-list-item-title>
              </v-list-item>
              <v-list-item
                :disabled="contextMenu.wt.locked"
                @click="onRemoveClick(contextMenu.wt!)"
              >
                <template #prepend>
                  <v-icon color="error">mdi-trash-can-outline</v-icon>
                </template>
                <v-list-item-title>{{
                  tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.contextMenu.remove")
                }}</v-list-item-title>
              </v-list-item>
            </template>
            <template v-else>
              <v-list-item disabled>
                <v-list-item-title class="text-caption">
                  {{
                    tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.contextMenu.mainDisabled")
                  }}
                </v-list-item-title>
              </v-list-item>
            </template>
          </v-list>
        </v-menu>
      </div>
```

- [ ] **Step 3: 添加 `contextMenu` 状态 ref**

在 `lastCreateError` ref 后追加：

```ts
const contextMenu = ref<{
  open: boolean;
  x: number;
  y: number;
  wt: SpcodeGitWorktree | null;
}>({ open: false, x: 0, y: 0, wt: null });

import { nextTick } from "vue";
async function openContextMenu(e: MouseEvent, wt: SpcodeGitWorktree): Promise<void> {
  contextMenu.value = { open: false, x: e.clientX, y: e.clientY, wt };
  await nextTick();
  contextMenu.value.open = true;
}
```

> **注意**：import 必须放在文件顶部。实际实施时需把 `nextTick` 合并到顶部 import 块。

- [ ] **Step 4: 验证 typecheck 通过**

Run: `cd dashboard && pnpm typecheck 2>&1 | head -30`
Expected: 错误是 `openCreateDialog` / `onLockClick` / `onRemoveClick` 函数缺失（下一步会加）

- [ ] **Step 5: 添加 `.git-diff-sidebar-tab-add` CSS**

在 `<style scoped>` 块的 `.git-diff-sidebar-tab-badge` 之后追加：

```css
.git-diff-sidebar-tab-add {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 11px;
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.3);
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.6);
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.12s ease;
  margin-left: 2px;
}
.git-diff-sidebar-tab-add:hover {
  border-style: solid;
  border-color: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
}
```

- [ ] **Step 6: 提交**

```bash
git add dashboard/src/components/chat/GitDiffSidebar.vue
git commit -m "feat(worktree-mgmt): add + button and right-click context menu to tabs"
```

### Task 5.3: 实现 4 个操作 handler（含错误处理 + 自动切换）

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue`

- [ ] **Step 1: 在 `onWorktreeChange` 函数后追加 4 个新 handler**

```ts
// ── Worktree management handlers (spec 2026-06-27 §3) ────────

function openCreateDialog(): void {
  // 互斥：开 ADD 关其他
  removeDialogOpen.value = false;
  lockDialogOpen.value = false;
  confirmUnlockOpen.value = false;
  lastCreateError.value = null;
  createDialogOpen.value = true;
}

async function onCreateSubmit(params: WorktreeAddParams): Promise<void> {
  isCreating.value = true;
  lastCreateError.value = null;
  const result = await worktreesComposable.add(params);
  isCreating.value = false;
  if (isAborted(result)) {
    createDialogOpen.value = false;
    return;
  }
  if (result.ok) {
    // spec §7.4: 自动切到新 worktree + 切到 Files 视图
    const newWt = result.snapshot.worktrees.find(
      (w) => w.path === result.snapshot.worktrees[0]?.path,
    );
    if (newWt) {
      selectedWorktree.value = newWt.isMain ? null : newWt.path;
      viewMode.value = "files";
      fileBrowserCurrentPath.value = newWt.path;
      fileBrowserPreviewPath.value = null;
    }
    createDialogOpen.value = false;
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.create.success", {
        branch: params.branch ?? newWt?.branch ?? "",
      }),
      "success",
    );
  } else {
    // 用 classifyWorktreeReason 走统一错误处理
    const meta = classifyWorktreeReason(result.reason, "add");
    const key = `spcodeProjectLoad.diffSidebar.${meta.i18nKey}`;
    const message = meta.withReason ? tm(key, { reason: result.reason }) : tm(key);
    lastCreateError.value = { reason: result.reason, stderr: result.stderr ?? "" };
    showSnackbar(message, meta.color, meta.withStderr ? result.stderr : undefined);
  }
}

function onLockClick(wt: SpcodeGitWorktree): void {
  contextMenu.value.open = false;
  if (wt.locked) {
    // 直接进入 unlock 流程
    confirmUnlockPath.value = wt.path;
    removeDialogOpen.value = false;
    createDialogOpen.value = false;
    lockDialogOpen.value = false;
    confirmUnlockOpen.value = true;
    return;
  }
  // Lock 流程：弹窗让用户填 reason
  lockDialogTarget.value = { path: wt.path, branch: wt.branch };
  removeDialogOpen.value = false;
  createDialogOpen.value = false;
  confirmUnlockOpen.value = false;
  lockDialogOpen.value = true;
}

async function onLockSubmit(reason: string | null): Promise<void> {
  const target = lockDialogTarget.value;
  if (!target) return;
  isLocking.value = true;
  const params: WorktreeLockParams = {
    path: target.path,
    umo: spcodeStatus.status.value.umo,
  };
  if (reason) params.reason = reason;
  const result = await worktreesComposable.lock(params);
  isLocking.value = false;
  if (isAborted(result)) {
    lockDialogOpen.value = false;
    return;
  }
  if (result.ok) {
    lockDialogOpen.value = false;
    lockDialogTarget.value = null;
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.lock.success", {
        branch: target.branch ?? "",
      }),
      "success",
    );
  } else {
    const meta = classifyWorktreeReason(result.reason, "lock");
    const key = `spcodeProjectLoad.diffSidebar.${meta.i18nKey}`;
    const message = meta.withReason ? tm(key, { reason: result.reason }) : tm(key);
    showSnackbar(message, meta.color, meta.withStderr ? result.stderr : undefined);
  }
}

function onRemoveClick(wt: SpcodeGitWorktree): void {
  contextMenu.value.open = false;
  if (wt.isMain) return; // 双保险
  if (wt.locked) return; // 双保险
  removeDialogTarget.value = { path: wt.path, branch: wt.branch };
  dirtyCount.value = null;
  // Lazy load dirty count from /spcode/git-status
  void loadDirtyFor(wt);
  lockDialogOpen.value = false;
  createDialogOpen.value = false;
  confirmUnlockOpen.value = false;
  removeDialogOpen.value = true;
}

async function loadDirtyFor(wt: SpcodeGitWorktree): Promise<void> {
  const umo = spcodeStatus.status.value.umo;
  if (!umo) return;
  try {
    const resp = await pluginExtensionApi.get<{ data: { files_changed?: number } }>(
      "spcode/git-status",
      { params: { umo, worktree: wt.path } },
    );
    dirtyCount.value = resp.data?.data?.files_changed ?? 0;
  } catch {
    dirtyCount.value = null; // 不阻塞 UI
  }
}

async function onConfirmRemove(force: boolean): Promise<void> {
  const target = removeDialogTarget.value;
  if (!target) return;
  isRemoving.value = true;
  const result = await worktreesComposable.remove({
    path: target.path,
    force,
    umo: spcodeStatus.status.value.umo,
  });
  isRemoving.value = false;
  if (isAborted(result)) {
    removeDialogOpen.value = false;
    return;
  }
  if (result.ok) {
    // spec §7.5: 若被删的是当前 worktree,回退到主 worktree
    if (selectedWorktree.value === target.path) {
      selectedWorktree.value = null;
      fileBrowserCurrentPath.value = mainWorktreePath.value ?? projectRoot.value;
    }
    removeDialogOpen.value = false;
    removeDialogTarget.value = null;
    dirtyCount.value = null;
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.remove.success", {
        branch: target.branch ?? "",
      }),
      "success",
    );
  } else {
    const meta = classifyWorktreeReason(result.reason, "remove");
    const key = `spcodeProjectLoad.diffSidebar.${meta.i18nKey}`;
    const message = meta.withReason ? tm(key, { reason: result.reason }) : tm(key);
    showSnackbar(message, meta.color, meta.withStderr ? result.stderr : undefined);
  }
}

async function onConfirmUnlock(): Promise<void> {
  const path = confirmUnlockPath.value;
  if (!path) return;
  isUnlocking.value = true;
  const result = await worktreesComposable.unlock({
    path,
    umo: spcodeStatus.status.value.umo,
  });
  isUnlocking.value = false;
  if (isAborted(result)) {
    confirmUnlockOpen.value = false;
    return;
  }
  if (result.ok) {
    confirmUnlockOpen.value = false;
    confirmUnlockPath.value = null;
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.unlock.success"),
      "success",
    );
  } else {
    const meta = classifyWorktreeReason(result.reason, "unlock");
    const key = `spcodeProjectLoad.diffSidebar.${meta.i18nKey}`;
    const message = meta.withReason ? tm(key, { reason: result.reason }) : tm(key);
    showSnackbar(message, meta.color, meta.withStderr ? result.stderr : undefined);
  }
}

function onCancelUnlock(): void {
  if (isUnlocking.value) return;
  confirmUnlockOpen.value = false;
  confirmUnlockPath.value = null;
}
```

- [ ] **Step 2: 添加 `isAborted` 通用辅助（如果尚未在文件其他地方定义）**

定位 `function isAborted(...)`（行号约 410），如果已存在则跳过；否则在 `reasonKey` 函数前添加：

```ts
function isAborted(result: { ok: boolean; reason?: string }): boolean {
  return !result.ok && result.reason === "aborted";
}
```

- [ ] **Step 3: 补充缺失的 imports**

文件顶部 `import` 块追加：

```ts
import { classifyWorktreeReason } from "@/composables/parseSpcodeWorktreeManagement";
import { pluginExtensionApi } from "@/api/v1";
import { nextTick } from "vue";
import type { SpcodeGitWorktree } from "@/composables/parseSpcodeWorktrees";
```

- [ ] **Step 4: 验证 typecheck 通过**

Run: `cd dashboard && pnpm typecheck 2>&1 | head -30`
Expected: 错误是 dialog 组件尚未引入模板（下一步会加）

- [ ] **Step 5: 提交**

```bash
git add dashboard/src/components/chat/GitDiffSidebar.vue
git commit -m "feat(worktree-mgmt): implement 4 mutation handlers with error mapping"
```

### Task 5.4: 添加 4 个 dialog 到模板

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue`

- [ ] **Step 1: 定位 `confirmUnstageAllOpen` dialog 块**

找到 `<v-dialog v-model="confirmUnstageAllOpen" ...>` 紧邻的关闭 `</v-dialog>` 之后。

- [ ] **Step 2: 追加 4 个新 dialog**

```vue
      <!-- Worktree CREATE dialog (spec 2026-06-27 §2.2.A) -->
      <WorktreeCreateDialog
        v-model="createDialogOpen"
        :is-submitting="isCreating"
        @submit="onCreateSubmit"
        @cancel="createDialogOpen = false"
      />

      <!-- Worktree REMOVE confirm dialog (spec 2026-06-27 §2.2.B) -->
      <v-dialog v-model="removeDialogOpen" persistent max-width="480">
        <v-card>
          <v-card-title class="text-h6">
            {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.remove.confirmTitle") }}
          </v-card-title>
          <v-card-text>
            <p class="mb-2">
              {{
                tm(
                  "spcodeProjectLoad.diffSidebar.worktreeMgmt.remove.confirmMessageWithPath",
                  { path: removeDialogTarget?.path ?? "", branch: removeDialogTarget?.branch ?? "" },
                )
              }}
            </p>
            <p
              v-if="dirtyCount !== null && dirtyCount > 0"
              class="text-caption text-warning mb-2"
            >
              {{
                tm(
                  "spcodeProjectLoad.diffSidebar.worktreeMgmt.remove.dirtyHint",
                  { count: dirtyCount },
                )
              }}
            </p>
            <v-checkbox
              v-if="dirtyCount !== null && dirtyCount > 0"
              v-model="removeForceChecked"
              density="compact"
              :label="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.remove.force', { count: dirtyCount })"
              color="warning"
              hide-details
            />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" :disabled="isRemoving" @click="removeDialogOpen = false">
              {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.remove.cancel") }}
            </v-btn>
            <v-btn
              variant="flat"
              color="warning"
              :loading="isRemoving"
              @click="onConfirmRemove(removeForceChecked)"
            >
              {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.remove.confirm") }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Worktree LOCK dialog (spec 2026-06-27 §2.2.C) -->
      <v-dialog v-model="lockDialogOpen" persistent max-width="480">
        <LockReasonDialogBody
          v-if="lockDialogOpen"
          :target-branch="lockDialogTarget?.branch ?? null"
          :is-locking="isLocking"
          @submit="onLockSubmit"
          @cancel="lockDialogOpen = false"
        />
      </v-dialog>

      <!-- Worktree UNLOCK confirm dialog (spec 2026-06-27 §2.2.D) -->
      <v-dialog v-model="confirmUnlockOpen" persistent max-width="440">
        <v-card>
          <v-card-title class="text-h6">
            {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.unlock.confirmTitle") }}
          </v-card-title>
          <v-card-text>
            {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.unlock.confirmMessage") }}
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" :disabled="isUnlocking" @click="onCancelUnlock">
              {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.unlock.cancel") }}
            </v-btn>
            <v-btn
              variant="flat"
              color="primary"
              :loading="isUnlocking"
              @click="onConfirmUnlock"
            >
              {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.unlock.confirm") }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
```

- [ ] **Step 3: 创建 `LockReasonDialogBody.vue`（LOCK 表单内联组件）**

Create: `dashboard/src/components/chat/message_list_comps/LockReasonDialogBody.vue`

```vue
<!-- Author: elecvoid243
     Date: 2026-06-27
     Inline body for the lock dialog. Kept separate from GitDiffSidebar
     to avoid bloating its template; same pattern as GitCommitDialog. -->
<script setup lang="ts">
import { ref, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
const { tm } = useModuleI18n("features/chat");

const props = defineProps<{
  targetBranch: string | null;
  isLocking: boolean;
}>();

const emit = defineEmits<{
  (e: "submit", reason: string | null): void;
  (e: "cancel"): void;
}>();

const reason = ref<string>("");
const reasonTooLong = computed(
  () => reason.value.length > 200,
);

import { computed } from "vue";
const canSubmit = computed(
  () => !reasonTooLong.value && !props.isLocking,
);

function onSubmit(): void {
  if (!canSubmit.value) return;
  emit("submit", reason.value.trim() || null);
}
</script>

<template>
  <v-card>
    <v-card-title class="text-h6">
      {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.lock.dialogTitle") }}
    </v-card-title>
    <v-card-text>
      <p class="mb-3 text-body-2">
        {{
          tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.lock.targetInfo", {
            branch: targetBranch ?? "",
          })
        }}
      </p>
      <v-textarea
        v-model="reason"
        :label="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.lock.reason')"
        :hint="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.lock.reasonHint')"
        :counter="200"
        :error-messages="reasonTooLong ? [tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.lock.reasonHint')] : []"
        rows="3"
        density="comfortable"
        variant="outlined"
        :maxlength="200"
      />
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn variant="text" :disabled="isLocking" @click="emit('cancel')">
        {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.lock.cancel") }}
      </v-btn>
      <v-btn
        variant="flat"
        color="primary"
        :loading="isLocking"
        :disabled="!canSubmit"
        @click="onSubmit"
      >
        {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.lock.submit") }}
      </v-btn>
    </v-card-actions>
  </v-card>
</template>
```

> **修正**：上面代码里 `import { computed } from "vue";` 应该放在 `<script setup>` 顶部，**而不是中间**。实际编写时调整。

- [ ] **Step 4: 添加 `removeForceChecked` ref**

在 `isCreating` ref 旁添加：

```ts
const removeForceChecked = ref(false);
```

- [ ] **Step 5: 在 GitDiffSidebar 顶部 import LockReasonDialogBody**

```ts
import LockReasonDialogBody from "@/components/chat/message_list_comps/LockReasonDialogBody.vue";
```

- [ ] **Step 6: 验证 typecheck 通过**

Run: `cd dashboard && pnpm typecheck 2>&1 | head -30`
Expected: 无错误

- [ ] **Step 7: 提交**

```bash
git add dashboard/src/components/chat/GitDiffSidebar.vue dashboard/src/components/chat/message_list_comps/LockReasonDialogBody.vue
git commit -m "feat(worktree-mgmt): add 4 dialogs to sidebar"
```

### Task 5.5: 集成验证（dev server + 手动测试）

**Files:** 无（验证步骤）

- [ ] **Step 1: 启动 dev server**

Run: `cd dashboard && pnpm dev`
Expected: Vite dev server starts on `http://localhost:3000` without errors

- [ ] **Step 2: 手动验证 4 个流程**

打开 `http://localhost:3000`：
1. 加载一个 git 项目（含至少 1 个 worktree）
2. 打开工作区侧边栏 → 确认 worktree tab 行显示 `+` 按钮
3. 点击 `+` → 填表 → 提交 → 确认自动切到新 worktree + 切到 Files 视图
4. 右键任一非主 worktree tab → 选 "锁定…" → 填 reason → 提交 → tab 上显示锁图标
5. 再次右键同一 tab → 选 "解锁" → 确认 → 锁图标消失
6. 右键非主 worktree → 选 "删除" → 确认（如有 dirty 会显示 force 选项）→ 提交 → tab 消失
7. 右键**主** worktree → 确认菜单只显示"主 worktree 不可锁定/删除"占位项

- [ ] **Step 3: 验证错误处理**

后端返回错误 reason 时：
1. 制造一个 `cannot_remove_main`（用 curl 模拟）→ 确认前端 snackbar 显示对应 i18n
2. 制造一个 `path_exists_nonempty` → 确认 ADD dialog 显示内联错误
3. 制造一个 `git_error` → 确认 snackbar 显示 stderr 块

- [ ] **Step 4: 验证 polling 联动**

1. 在 dev 工具中手动调 `git worktree add`（mock 外部变更）
2. 等待 30s → 确认 tab 自动出现新 worktree（不需手动刷新）

- [ ] **Step 5: 关闭 dev server**

`Ctrl+C` 终止 `pnpm dev`

### Task 5.6: 跑 lint + format

- [ ] **Step 1: 运行 ESLint**

Run: `cd dashboard && pnpm lint 2>&1 | tail -30`
Expected: 无错误（warning 可接受）

- [ ] **Step 2: 手动修复任何错误**

如有 ESLint 错误，按提示修复（`--fix` 已自动处理大部分格式问题）。

- [ ] **Step 3: 跑 typecheck 最终验证**

Run: `cd dashboard && pnpm typecheck 2>&1 | tail -10`
Expected: 无错误

- [ ] **Step 4: 跑所有单测**

Run: `cd dashboard && for f in tests/parse*.test.mjs; do echo "=== $f ==="; node --test "$f" 2>&1 | tail -3; done`
Expected: 所有测试 PASS

- [ ] **Step 5: 提交（如有 lint 修复）**

```bash
git add -u
git diff --cached --stat  # 确认改动合理
git commit -m "style(worktree-mgmt): fix lint issues"
```

---

## Chunk 6: 收尾

### Task 6.1: 更新 spec 文档的实施状态

**Files:**
- Modify: `docs/superpowers/specs/2026-06-27-git-worktree-frontend-management-design.md`

- [ ] **Step 1: 在文件顶部添加 "实施状态" 标记**

在原 spec 头部块下追加：

```markdown
> **实施状态**: ✅ 已完成 (2026-06-27)
> **实施计划**: `docs/superpowers/plans/2026-06-27-git-worktree-frontend-management.md`
> **相关 PR**: <TBD>
```

- [ ] **Step 2: 提交**

```bash
git add docs/superpowers/specs/2026-06-27-git-worktree-frontend-management-design.md
git commit -m "docs: mark spec as implemented"
```

### Task 6.2: 编写 CHANGELOG 条目

**Files:**
- Modify: `changelogs/<next-version>.md`（如不存在则创建）

- [ ] **Step 1: 在 CHANGELOG 顶部添加条目**

```markdown
## [Unreleased]

### Added
- **Dashboard sidebar**: Git worktree management UI
  - Add/remove/lock/unlock worktrees via the workspace sidebar
  - Right-click context menu on worktree tabs
  - `+` button in the tab row to create new worktrees
  - Auto-switch to newly created worktree (file browser view)
  - Frontend-side safety: main worktree entries are hidden; locked worktrees are disabled
  - Aligns with `astrbot_plugin_spcode_toolkit` v2.14.0
```

- [ ] **Step 2: 提交**

```bash
git add changelogs/
git commit -m "docs(changelog): note worktree management UI"
```

### Task 6.3: 创建 PR（最终收尾）

- [ ] **Step 1: 推送分支**

```bash
git push origin feat/worktree-frontend-management
```

- [ ] **Step 2: 创建 PR**

```bash
gh pr create \
  --title "feat(dashboard): git worktree management UI" \
  --body "## Summary
Implements git worktree management in GitDiffSidebar, aligning with astrbot_plugin_spcode_toolkit v2.14.0.

## Changes
- \`useSpcodeWorktrees\` extended with \`add/remove/lock/unlock\` methods
- New \`parseSpcodeWorktreeManagement.ts\` (parsers + reason codes)
- New \`WorktreeCreateDialog.vue\` + \`LockReasonDialogBody.vue\`
- \`GitDiffSidebar.vue\`: right-click context menu on worktree tabs, 4 independent dialogs
- i18n keys for zh-CN, en-US, ru-RU (placeholder)

## Spec
\`docs/superpowers/specs/2026-06-27-git-worktree-frontend-management-design.md\`
\`docs/superpowers/plans/2026-06-27-git-worktree-frontend-management.md\`

## Test plan
- [ ] Create a worktree via \`+\` button → auto-switches to Files view
- [ ] Lock a worktree → tab shows lock icon
- [ ] Unlock a worktree → lock icon disappears
- [ ] Remove a worktree (clean) → tab disappears
- [ ] Remove a worktree (dirty) → force checkbox appears
- [ ] Main worktree context menu shows placeholder only
- [ ] External \`git worktree add\` is reflected in sidebar within 30s"
```

- [ ] **Step 3: 在 PR 描述里链接 spec + plan 文档**

---

## 验收清单 (Definition of Done)

- [ ] 所有 10 个 parser 单测通过
- [ ] `pnpm typecheck` 无错误
- [ ] `pnpm lint` 无错误
- [ ] dev server 启动无控制台错误
- [ ] 4 个流程（ADD / REMOVE / LOCK / UNLOCK）手动验证通过
- [ ] 错误 reason 正确显示（snackbar + stderr 块）
- [ ] 主 worktree 入口完全隐藏
- [ ] 30s 轮询正常联动
- [ ] i18n 三语种键齐
- [ ] CHANGELOG 更新
- [ ] PR 创建并 review 通过

---

**作者**：elecvoid243 · **生成时间**：2026-06-27 19:40 (CST)
**对应 Spec**：`docs/superpowers/specs/2026-06-27-git-worktree-frontend-management-design.md`
