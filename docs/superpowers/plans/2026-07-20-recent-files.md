# Recent Files Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在工作区文件浏览器默认折叠块里展示「最近打开文件」列表，让用户能一键回到上次未看完的文件。

**Architecture:** 新增一个 composable `useRecentFiles` 做数据层（localStorage 按 worktree 分桶、50 条上限、同 path 去重），一个组件 `<RecentFilesBlock>` 做 UI 层（默认折叠、5 条显示 + `+N more`、× 单删、Clear 二次确认）；`GitDiffSidebar` 通过 `watch(fileBrowserPreviewPath, currentRoot)` 写入；在 `FileBrowserView` 左侧 FileTreeList 上方嵌入组件。无后端改动，无新增 npm 依赖。

**Tech Stack:** Vue 3.3 `<script setup lang="ts">`、TypeScript 5.1、FNV-1a 32 位 inline hash（同步，零依赖）、Vitest 1.6 + @vue/test-utils 2 + happy-dom 14、Vuetify 3.7 `v-dialog`。

**Worktree:** 实施开 `F:\github\Astrbot\.worktrees\feat-recent-files`（分支 `feat/recent-files`，基于 `all`）。Plan 路径与全部代码路径相对工作树根目录。

**Spec:** `docs/superpowers/specs/2026-07-20-recent-files-design.md`

---

## Global Constraints

- 所有源码注释用 **English**；组件/spec 头部注释含 `Author: elecvoid243` + 日期。
- 无新增 npm 依赖（spec §11）；桶键计算用 inline FNV-1a ~10 行，零包。
- 「无 worktree」即 `currentRoot === null` → composable 所有读写 no-op，`<RecentFilesBlock v-if>` 不渲染。
- 每桶容量 50，UI 列表默认显示前 5 条，超出显示 `+{n} more`。
- 默认折叠，每次 sidebar mount 不读折叠状态；折叠状态不持久化（spec §5.3）。
- `localStorage` key：`spcode.recentFiles.<fnv1aHex8(worktreeRoot)>`（spec §4.1）。
- 路径分隔符：`worktreeRoot.includes('\\')` → Windows separator `'\\'`，否则 `'/'`。
- recordOpen 早期 return：path 不在 worktree 内 / 不在 root 自身 → 拒绝（spec §4.3）。
- 测试基础设施：vitest 1.6 + happy-dom + @vue/test-utils 2 + sinon（如需）。Vitest include 仅 `src/**/*.spec.ts`（`tests/*.test.mjs` 不跑）。
- i18n 双语：`spcodeProjectLoad.fileBrowser.recentFiles.*` 9 个键，按既有 en-US / zh-CN 既有惯例更新。
- 提交信息用 conventional commits（English）。
- Plan 偏差备忘：spec §3 表格中 `GitDiffSidebar.vue` / `FileBrowserView.vue` 的「增 ~6/10 行」是粗估；实际接线会带 ~25 行（props 透传 + dialog 状态 + handler）。

---

## File Structure

| 文件 | 状态 | 职责 |
|---|---|---|
| `dashboard/src/composables/useRecentFiles.ts` | 新 | 数据层；导出 composable + type |
| `dashboard/src/composables/useRecentFiles.spec.ts` | 新 | composable 单测 |
| `dashboard/src/components/chat/message_list_comps/RecentFilesBlock.vue` | 新 | UI 折叠块 |
| `dashboard/src/components/chat/message_list_comps/RecentFilesBlock.spec.ts` | 新 | 组件单测 |
| `dashboard/src/components/chat/GitDiffSidebar.vue` | 改 | 加 import / composable / watch / props 透传 |
| `dashboard/src/components/chat/message_list_comps/FileBrowserView.vue` | 改 | 加 import / 嵌入块 / 事件接线 / dialog 状态 |
| `dashboard/src/i18n/en-US/...` | 改 | 加 9 个键 |
| `dashboard/src/i18n/zh-CN/...` | 改 | 加 9 个键 |

8 个文件；最大新增文件 ~180 行（composable + 组件合并），其他全为 < 30 行增量。

---

### Task 1: composable 骨架 —— types + safe storage + FNV-1a + loadBucket

**Files:**
- Create: `dashboard/src/composables/useRecentFiles.ts`
- Create: `dashboard/src/composables/useRecentFiles.spec.ts`

**Interfaces:**
- Consumes: 无（仅浏览器 API）
- Produces（后续 Task 2-5 依赖的准确签名）:
  - `export interface RecentEntry { path: string; openedAt: number; }`
  - `export interface UseRecentFiles { entries: Ref<RecentEntry[]>; recordOpen(path: string): void; remove(path: string): void; clear(): void; }`
  - `export function useRecentFiles(worktree: Ref<string | null>): UseRecentFiles`

- [ ] **Step 1: 写失败测试 `dashboard/src/composables/useRecentFiles.spec.ts`**

```ts
// Author: elecvoid243, 2026-07-20
// useRecentFiles unit tests — covers Task 1 (types + storage helpers + loadBucket).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { useRecentFiles } from "@/composables/useRecentFiles";

const WT = "/tmp/worktrees/recent-files-demo";

beforeEach(() => {
  localStorage.clear();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("initial load", () => {
  it("returns an empty list when localStorage has no bucket", () => {
    const wt = ref<string | null>(WT);
    const { entries } = useRecentFiles(wt);
    expect(entries.value).toEqual([]);
  });

  it("returns an empty list when currentRoot is null", () => {
    const wt = ref<string | null>(null);
    const { entries } = useRecentFiles(wt);
    expect(entries.value).toEqual([]);
  });

  it("returns prior entries when the bucket exists and parses correctly", () => {
    const prior = [{ path: `${WT}/src/main.py`, openedAt: 1700000000000 }];
    localStorage.setItem(
      `spcode.recentFiles.${fnv1aHex(WT)}`,
      JSON.stringify({ entries: prior }),
    );
    const wt = ref<string | null>(WT);
    const { entries } = useRecentFiles(wt);
    expect(entries.value).toEqual(prior);
  });

  it("falls back to empty list when the stored JSON is malformed", () => {
    localStorage.setItem(`spcode.recentFiles.${fnv1aHex(WT)}`, "{not json");
    const wt = ref<string | null>(WT);
    const { entries } = useRecentFiles(wt);
    expect(entries.value).toEqual([]);
  });
});

// helper re-exports the FNV-1a function under test so the test file stays
// self-contained. Implementation lives in the composable file.
function fnv1aHex(input: string): string {
  // mirror of the composable internals; recomputed to assert the key
  let h = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16).padStart(8, "0");
}
```

- [ ] **Step 2: 运行测试确认它们因未实现而失败**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm test src/composables/useRecentFiles.spec.ts
```

Expected: FAIL（`Cannot find module '@/composables/useRecentFiles'` 或 `useRecentFiles is not a function`）。

- [ ] **Step 3: 实现 composable 骨架 `dashboard/src/composables/useRecentFiles.ts`**

```ts
// Author: elecvoid243, 2026-07-20
// useRecentFiles: Recent files data layer for the Files view.
//
// Per the 2026-07-20 Recent Files spec (§4): one bucket per worktree,
// 50-entry cap, LIFO + same-path dedupe, no-op when currentRoot is null.
//
// Storage key shape: "spcode.recentFiles.<fnv1aHex(worktreeRoot)>"
//   - FNV-1a 32-bit hex (8 chars) — sync, ~10 lines, zero deps.
//   - Key stays under 64 chars regardless of worktree path length.
//
// Persists via the existing safeGetItem / safeSetItem wrapper so a
// quota / private-mode failure degrades to no-op without throwing.

import { ref, watch, type Ref } from "vue";

const MAX_ENTRIES = 50;

/** One row in the Recent list. LIFO ordered by openedAt desc. */
export interface RecentEntry {
  path: string;
  /** Unix milliseconds. */
  openedAt: number;
}

export interface UseRecentFiles {
  entries: Ref<RecentEntry[]>;
  recordOpen(path: string): void;
  remove(path: string): void;
  clear(): void;
}

interface RecentBucket {
  entries: RecentEntry[];
}

/** FNV-1a 32-bit hash, lowercase hex, zero-padded to 8 chars.
 *  NOT cryptographic — only used to keep localStorage keys short and
 *  free of filesystem separators / unicode quirks. */
export function fnv1aHex(input: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16).padStart(8, "0");
}

/** localStorage wrapper matching the safe-get/safe-set pattern used in
 *  GitDiffSidebar.vue (lines ~103-116). Returns "" / no-ops on any
 *  exception so quota / private-mode never throws up the stack. */
function safeGetItem(key: string): string {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}
function safeSetItem(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* no-op */
  }
}

/** Resolve current bucket key. Returns "" when no worktree is set so
 *  callers can early-out uniformly. */
function bucketKey(worktreeRoot: string | null): string {
  if (!worktreeRoot) return "";
  try {
    return `spcode.recentFiles.${fnv1aHex(worktreeRoot)}`;
  } catch {
    // Extreme fallback: pathological string inputs. Encode and slice.
    const fallback = encodeURIComponent(worktreeRoot).slice(0, 32);
    return `spcode.recentFiles.rt-${fallback}`;
  }
}

/** Read + JSON.parse a bucket; returns empty list on any error. */
function loadBucket(key: string): RecentEntry[] {
  const raw = safeGetItem(key);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as RecentBucket;
    if (!parsed || !Array.isArray(parsed.entries)) return [];
    return parsed.entries;
  } catch {
    return [];
  }
}

/** Persist a bucket. */
function saveBucket(key: string, entries: RecentEntry[]): void {
  safeSetItem(key, JSON.stringify({ entries } satisfies RecentBucket));
}

/** Worktree-separator detection. Mirrors the spec §6.1 logic. */
function sepOf(root: string): string {
  return root.includes("\\") ? "\\" : "/";
}

export function useRecentFiles(worktree: Ref<string | null>): UseRecentFiles {
  const entries = ref<RecentEntry[]>([]);

  function persist(): void {
    if (!worktree.value) return;
    saveBucket(bucketKey(worktree.value), entries.value);
  }

  // Watch is added in Task 5 — initial load here picks the first bucket.
  function loadForCurrent(): void {
    if (!worktree.value) {
      entries.value = [];
      return;
    }
    entries.value = loadBucket(bucketKey(worktree.value));
  }

  function recordOpen(path: string): void {
    // Implemented in Task 2.
  }
  function remove(path: string): void {
    // Implemented in Task 4.
  }
  function clear(): void {
    // Implemented in Task 4.
  }

  // Initial load.
  loadForCurrent();

  // Re-load when worktree switches. Implementation in Task 5; placeholder
  // watcher is one line so Task 1 test can mount the composable without
  // surprises from absent watch wiring.
  watch(worktree, () => loadForCurrent());

  return { entries, recordOpen, remove, clear };
}
```

- [ ] **Step 4: 运行测试确认 Task 1 用例全部 PASS**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm test src/composables/useRecentFiles.spec.ts
```

Expected: PASS — `initial load` 描述下 4 个用例全绿。

- [ ] **Step 5: 格式化 + Commit**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files
pnpm exec prettier --write dashboard/src/composables/useRecentFiles.ts dashboard/src/composables/useRecentFiles.spec.ts
git add dashboard/src/composables/useRecentFiles.ts dashboard/src/composables/useRecentFiles.spec.ts
git commit -m "feat(dashboard): add useRecentFiles composable skeleton with types and storage"
```

---

### Task 2: composable `recordOpen` —— 去重 + LIFO + trim + 路径校验

**Files:**
- Modify: `dashboard/src/composables/useRecentFiles.ts`（仅 `recordOpen` 主体实现）
- Modify: `dashboard/src/composables/useRecentFiles.spec.ts`（追加 `recordOpen` 描述）

- [ ] **Step 1: 追加失败测试覆盖 `recordOpen` 行为**

在 `dashboard/src/composables/useRecentFiles.spec.ts` 末尾追加（不要替换原内容）：

```ts
describe("recordOpen", () => {
  it("appends a new entry to the head", () => {
    const wt = ref<string | null>(WT);
    const { entries, recordOpen } = useRecentFiles(wt);
    recordOpen(`${WT}/src/main.py`);
    expect(entries.value).toHaveLength(1);
    expect(entries.value[0].path).toBe(`${WT}/src/main.py`);
    expect(typeof entries.value[0].openedAt).toBe("number");
  });

  it("treats a repeat open of the same path as no new row, refreshed to head", () => {
    const wt = ref<string | null>(WT);
    const { entries, recordOpen } = useRecentFiles(wt);
    recordOpen(`${WT}/a.py`);
    recordOpen(`${WT}/b.py`);
    recordOpen(`${WT}/a.py`); // duplicate
    expect(entries.value.map((e) => e.path)).toEqual([
      `${WT}/a.py`,
      `${WT}/b.py`,
    ]);
    // head 'a' should have a newer openedAt than the bottom 'b'
    expect(entries.value[0].openedAt).toBeGreaterThanOrEqual(
      entries.value[1].openedAt,
    );
  });

  it("orders latest-open first across three distinct paths", () => {
    const wt = ref<string | null>(WT);
    const { entries, recordOpen } = useRecentFiles(wt);
    recordOpen(`${WT}/a.py`);
    recordOpen(`${WT}/b.py`);
    recordOpen(`${WT}/c.py`);
    expect(entries.value.map((e) => e.path)).toEqual([
      `${WT}/c.py`,
      `${WT}/b.py`,
      `${WT}/a.py`,
    ]);
  });

  it("rejects paths outside the current worktree (no pollution)", () => {
    const wt = ref<string | null>(WT);
    const { entries, recordOpen } = useRecentFiles(wt);
    recordOpen(`/some/other/project/x.py`);
    expect(entries.value).toEqual([]);
  });

  it("rejects when the current worktree root is null", () => {
    const wt = ref<string | null>(null);
    const { entries, recordOpen } = useRecentFiles(wt);
    recordOpen("/anything");
    expect(entries.value).toEqual([]);
  });

  it("trims to MAX_ENTRIES (50), dropping the oldest entry", () => {
    const wt = ref<string | null>(WT);
    const { entries, recordOpen } = useRecentFiles(wt);
    for (let i = 0; i < 55; i++) {
      recordOpen(`${WT}/file-${String(i).padStart(2, "0")}.py`);
    }
    expect(entries.value).toHaveLength(50);
    // The oldest five (file-00 .. file-04) should have been dropped.
    expect(entries.value.at(-1)?.path).toBe(`${WT}/file-54.py`);
  });

  it("persists to localStorage on every recordOpen", () => {
    const wt = ref<string | null>(WT);
    const { recordOpen } = useRecentFiles(wt);
    recordOpen(`${WT}/main.py`);
    const raw = localStorage.getItem(
      `spcode.recentFiles.${fnv1aHex(WT)}`,
    );
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!);
    expect(parsed.entries).toHaveLength(1);
    expect(parsed.entries[0].path).toBe(`${WT}/main.py`);
  });
});
```

- [ ] **Step 2: 运行确认这些新用例失败**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm test src/composables/useRecentFiles.spec.ts
```

Expected: 所有 7 个 `recordOpen` 用例 FAIL（`recordOpen` 当前是 no-op stub）。

- [ ] **Step 3: 实现 `recordOpen` 主体（替换上一版的占位）**

`dashboard/src/composables/useRecentFiles.ts` 内把：

```ts
function recordOpen(path: string): void {
  // Implemented in Task 2.
}
```

替换为：

```ts
function recordOpen(path: string): void {
  const root = worktree.value;
  if (!root) return;
  // Path validation: the file must live strictly inside the worktree
  // (or be the root itself). Prevents arbitrary filesystem paths from
  // polluting the bucket from search jumps or external triggers.
  const sep = sepOf(root);
  if (path !== root && !path.startsWith(root + sep)) return;

  // Dedupe: strip any prior entry pointing at this exact path so the
  // repeat-open re-lands it at the head.
  const filtered = entries.value.filter((e) => e.path !== path);
  filtered.unshift({ path, openedAt: Date.now() });
  // Cap to MAX_ENTRIES. Old entries beyond the cap are discarded
  // (LIFO retention).
  entries.value = filtered.slice(0, MAX_ENTRIES);
  persist();
}
```

- [ ] **Step 4: 运行确认 Task 2 全绿**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm test src/composables/useRecentFiles.spec.ts
```

Expected: PASS — `recordOpen` 7 个新用例全绿，且前 4 个 `initial load` 用例不回归。

- [ ] **Step 5: Commit**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files
git add dashboard/src/composables/useRecentFiles.ts dashboard/src/composables/useRecentFiles.spec.ts
git commit -m "feat(dashboard): useRecentFiles.recordOpen — dedupe, LIFO, trim, path validation"
```

---

### Task 3: composable `remove` + `clear`

**Files:**
- Modify: `dashboard/src/composables/useRecentFiles.ts`
- Modify: `dashboard/src/composables/useRecentFiles.spec.ts`

- [ ] **Step 1: 追加失败测试**

在 `useRecentFiles.spec.ts` 末尾追加：

```ts
describe("remove", () => {
  it("drops the row whose path matches exactly", () => {
    const wt = ref<string | null>(WT);
    const { entries, recordOpen, remove } = useRecentFiles(wt);
    recordOpen(`${WT}/a.py`);
    recordOpen(`${WT}/b.py`);
    remove(`${WT}/a.py`);
    expect(entries.value.map((e) => e.path)).toEqual([`${WT}/b.py`]);
  });

  it("is a no-op when the path is not present", () => {
    const wt = ref<string | null>(WT);
    const { entries, recordOpen, remove } = useRecentFiles(wt);
    recordOpen(`${WT}/a.py`);
    remove(`${WT}/nope.py`);
    expect(entries.value.map((e) => e.path)).toEqual([`${WT}/a.py`]);
  });

  it("persists the trimmed list", () => {
    const wt = ref<string | null>(WT);
    const { recordOpen, remove } = useRecentFiles(wt);
    recordOpen(`${WT}/a.py`);
    recordOpen(`${WT}/b.py`);
    remove(`${WT}/a.py`);
    const raw = JSON.parse(
      localStorage.getItem(`spcode.recentFiles.${fnv1aHex(WT)}`)!,
    );
    expect(raw.entries.map((e: any) => e.path)).toEqual([`${WT}/b.py`]);
  });
});

describe("clear", () => {
  it("empties the current bucket", () => {
    const wt = ref<string | null>(WT);
    const { entries, recordOpen, clear } = useRecentFiles(wt);
    recordOpen(`${WT}/a.py`);
    recordOpen(`${WT}/b.py`);
    clear();
    expect(entries.value).toEqual([]);
  });

  it("persists the empty list", () => {
    const wt = ref<string | null>(WT);
    const { recordOpen, clear } = useRecentFiles(wt);
    recordOpen(`${WT}/a.py`);
    clear();
    const raw = JSON.parse(
      localStorage.getItem(`spcode.recentFiles.${fnv1aHex(WT)}`)!,
    );
    expect(raw.entries).toEqual([]);
  });

  it("does not affect other buckets", () => {
    const wtA = ref<string | null>("/worktrees/A");
    const wtB = ref<string | null>("/worktrees/B");
    const a = useRecentFiles(wtA);
    const b = useRecentFiles(wtB);
    a.recordOpen("/worktrees/A/foo.py");
    b.recordOpen("/worktrees/B/bar.py");

    a.clear();
    expect(a.entries.value).toEqual([]);
    expect(b.entries.value.map((e) => e.path)).toEqual(["/worktrees/B/bar.py"]);
  });
});
```

- [ ] **Step 2: 运行确认 6 个用例失败**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm test src/composables/useRecentFiles.spec.ts
```

Expected: 6 个新 `remove` / `clear` 用例全部 FAIL；既有用例不退步。

- [ ] **Step 3: 实现 `remove` + `clear`**

把 `useRecentFiles.ts` 内的两个 stub：

```ts
function remove(path: string): void {
  // Implemented in Task 4.
}
function clear(): void {
  // Implemented in Task 4.
}
```

替换为：

```ts
function remove(path: string): void {
  entries.value = entries.value.filter((e) => e.path !== path);
  persist();
}

function clear(): void {
  entries.value = [];
  persist();
}
```

- [ ] **Step 4: 运行全部 composable 测试**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm test src/composables/useRecentFiles.spec.ts
```

Expected: PASS — 共 4 + 7 + 6 = 17 个用例全绿。

- [ ] **Step 5: Commit**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files
git add dashboard/src/composables/useRecentFiles.ts dashboard/src/composables/useRecentFiles.spec.ts
git commit -m "feat(dashboard): useRecentFiles.remove and clear — single-row + full-bucket"
```

---

### Task 4: composable 切换 worktree 时自动重读桶

**Files:**
- Modify: `dashboard/src/composables/useRecentFiles.ts`
- Modify: `dashboard/src/composables/useRecentFiles.spec.ts`

注：Task 1 已经为占位目的加上 `watch(worktree, () => loadForCurrent())`——但它没有 `immediate`。本 Task 强化为：
1) 切换时清空 + 重读；2) 不在切换时丢正在编辑的状态（其实是 no-op 因为 entries 是 ref,UI 自己会重渲染)。

- [ ] **Step 1: 追加失败测试覆盖切换行为**

在 `useRecentFiles.spec.ts` 末尾追加：

```ts
describe("worktree switching", () => {
  it("reloads the bucket when worktree ref changes", async () => {
    const wt = ref<string | null>("/worktrees/A");
    const { entries, recordOpen } = useRecentFiles(wt);
    recordOpen("/worktrees/A/a.py");

    // Pre-seed B's bucket so we can confirm we read B and discard A.
    localStorage.setItem(
      `spcode.recentFiles.${fnv1aHex("/worktrees/B")}`,
      JSON.stringify({
        entries: [{ path: "/worktrees/B/b.py", openedAt: 123 }],
      }),
    );

    wt.value = "/worktrees/B";
    await Promise.resolve(); // flush watcher microtask
    expect(entries.value.map((e) => e.path)).toEqual(["/worktrees/B/b.py"]);
  });

  it("shows an empty list when switching to a brand-new worktree", async () => {
    const wt = ref<string | null>("/worktrees/A");
    const { entries, recordOpen } = useRecentFiles(wt);
    recordOpen("/worktrees/A/a.py");

    wt.value = "/worktrees/C"; // never seen
    await Promise.resolve();
    expect(entries.value).toEqual([]);
  });

  it("writing to a new worktree after switching does not touch the old bucket", async () => {
    const wt = ref<string | null>("/worktrees/A");
    const { recordOpen } = useRecentFiles(wt);
    recordOpen("/worktrees/A/a.py");
    const aRawBefore = localStorage.getItem(
      `spcode.recentFiles.${fnv1aHex("/worktrees/A")}`,
    );
    const parsedA = JSON.parse(aRawBefore!);
    expect(parsedA.entries[0].path).toBe("/worktrees/A/a.py");

    wt.value = "/worktrees/B";
    await Promise.resolve();
    const { recordOpen: recB } = useRecentFiles(wt);
    recB("/worktrees/B/b.py");

    const aRawAfter = localStorage.getItem(
      `spcode.recentFiles.${fnv1aHex("/worktrees/A")}`,
    );
    expect(aRawAfter).toBe(aRawBefore);
  });
});
```

- [ ] **Step 2: 运行确认 3 个用例失败（当前 watcher 不会响应 ref 变化）**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm test src/composables/useRecentFiles.spec.ts
```

Expected: 3 个 `worktree switching` 用例全 FAIL。

- [ ] **Step 3: 强化 worktree watcher**

在 `useRecentFiles.ts` 中把现有的：

```ts
watch(worktree, () => loadForCurrent());
```

替换为：

```ts
// Reactive bucket switch: every change to the worktree ref reloads
// from localStorage so entries always reflect the current project.
// `flush: "sync"` is fine — loadBucket is bounded by MAX_ENTRIES and
// a single JSON.parse; no observable cost in the hot path.
watch(worktree, () => loadForCurrent(), { flush: "sync" });
```

- [ ] **Step 4: 跑全量 composable 测试**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm test src/composables/useRecentFiles.spec.ts
```

Expected: PASS — 全部 20 个用例绿（4 + 7 + 6 + 3）。

- [ ] **Step 5: Commit**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files
git add dashboard/src/composables/useRecentFiles.ts dashboard/src/composables/useRecentFiles.spec.ts
git commit -m "feat(dashboard): useRecentFiles reactive worktree switching"
```

---

### Task 5: `<RecentFilesBlock>` 组件骨架 —— 默认折叠 + props/emits 接口

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/RecentFilesBlock.vue`
- Create: `dashboard/src/components/chat/message_list_comps/RecentFilesBlock.spec.ts`

- [ ] **Step 1: 写失败测试 `RecentFilesBlock.spec.ts`**

```ts
// Author: elecvoid243, 2026-07-20
// RecentFilesBlock default-rendered skeleton: collapsed by default, with
// the entry-count in the header. Click-to-toggle and row interactions
// land in Task 6.
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { createVuetifyForTest } from "@/test/vuetify";
import RecentFilesBlock from "./RecentFilesBlock.vue";

function factory(props: Record<string, unknown> = {}) {
  return mount(RecentFilesBlock, {
    props: {
      entries: [],
      currentRoot: "/projects/demo",
      ...props,
    },
    global: { plugins: [createVuetifyForTest()] },
  });
}

describe("RecentFilesBlock — collapsed default", () => {
  it("renders a header with the count and the chevron-up icon when collapsed is exposed", () => {
    const w = factory({ entries: sampleEntries });
    // Default collapsed → no list rows visible.
    expect(w.findAll('[data-test="recent-row"]')).toHaveLength(0);
    // Header present with the count formatted from props.entries.length.
    expect(w.text()).toContain("Recent Files (3)");
  });

  it("does not throw when entries is empty", () => {
    expect(() => factory({ entries: [] })).not.toThrow();
  });
});

const sampleEntries = [
  { path: "/projects/demo/src/main.py", openedAt: 1700000003000 },
  { path: "/projects/demo/README.md", openedAt: 1700000002000 },
  { path: "/projects/demo/x.ts", openedAt: 1700000001000 },
];
```

- [ ] **Step 2: 创建最小的 Vuetify 测试 helper（首次建,后续任务复用）**

`dashboard/src/test/vuetify.ts`:

```ts
// Author: elecvoid243, 2026-07-20
// Minimal Vuetify 3.7 plugin factory for component tests. Avoids the
// heavyweight full-theme install so each test stays < 50ms.
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import * as directives from "vuetify/directives";

export function createVuetifyForTest() {
  return createVuetify({
    components,
    directives,
    theme: { defaultTheme: "light" },
  });
}
```

- [ ] **Step 3: 运行确认组件测试因 `RecentFilesBlock.vue` 缺失而失败**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm test src/components/chat/message_list_comps/RecentFilesBlock.spec.ts
```

Expected: FAIL（`Cannot find module './RecentFilesBlock.vue'`）。

- [ ] **Step 4: 实现组件骨架 `RecentFilesBlock.vue`**

```vue
<!--
  Author: elecvoid243, 2026-07-20
  RecentFilesBlock: collapsed-by-default panel for the Files view.

  Spec: docs/superpowers/specs/2026-07-20-recent-files-design.md §5
-->
<script setup lang="ts">
import { ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { RecentEntry } from "@/composables/useRecentFiles";

const props = withDefaults(
  defineProps<{
    entries: RecentEntry[];
    currentRoot: string;
  }>(),
  { entries: () => [] },
);

// Emits: select (row click), remove (× click), clear (Clear link).
// Row rendering, × button, Clear link, +N more all live in Task 6.
defineEmits<{
  (e: "select", payload: { path: string }): void;
  (e: "remove", payload: { path: string }): void;
  (e: "clear"): void;
}>();

const { tm } = useModuleI18n("features/chat");

// Default: collapsed. Not persisted across sessions (spec §5.3).
const expanded = ref(false);
function toggle(): void {
  expanded.value = !expanded.value;
}

// `entries.length` is the source of truth for the count badge;
// watch not needed because Vue reactivity re-renders the header on
// prop change.
</script>

<template>
  <section class="recent-files-block">
    <button
      type="button"
      class="recent-files-header"
      :aria-expanded="expanded"
      data-test="recent-files-header"
      @click="toggle"
    >
      <v-icon size="16" class="recent-files-header-icon">
        mdi-clock-outline
      </v-icon>
      <span class="recent-files-header-text">
        {{ tm("spcodeProjectLoad.fileBrowser.recentFiles.titleWithCount", {
          count: props.entries.length,
        }) }}
      </span>
      <v-icon size="16" class="recent-files-header-chevron">
        {{ expanded ? "mdi-chevron-up" : "mdi-chevron-down" }}
      </v-icon>
    </button>
    <!-- Task 6 adds the list panel here, gated by v-if="expanded" -->
    <div v-show="expanded" data-test="recent-files-body" />
  </section>
</template>

<style scoped>
.recent-files-block {
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.recent-files-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  background: transparent;
  border: none;
  cursor: pointer;
  font: inherit;
  color: inherit;
  text-align: left;
}
.recent-files-header:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.recent-files-header-text {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
}
.recent-files-header-chevron {
  opacity: 0.6;
}
</style>
```

- [ ] **Step 5: 运行组件测试确认 PASS**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm test src/components/chat/message_list_comps/RecentFilesBlock.spec.ts
```

Expected: PASS — 2 个 `RecentFilesBlock — collapsed default` 用例全绿。

- [ ] **Step 6: Commit**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files
git add dashboard/src/components/chat/message_list_comps/RecentFilesBlock.vue dashboard/src/components/chat/message_list_comps/RecentFilesBlock.spec.ts dashboard/src/test/vuetify.ts
git commit -m "feat(dashboard): add RecentFilesBlock component skeleton (default collapsed)"
```

---

### Task 6: `<RecentFilesBlock>` 展开态 —— 行渲染 / × 不冒泡 / Clear / +N more / empty 占位

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/RecentFilesBlock.vue`
- Modify: `dashboard/src/components/chat/message_list_comps/RecentFilesBlock.spec.ts`

- [ ] **Step 1: 追加失败测试覆盖展开行为**

在 `RecentFilesBlock.spec.ts` 末尾追加：

```ts
describe("RecentFilesBlock — expanded interactions", () => {
  it("shows up to 5 rows when expanded", async () => {
    const entries = Array.from({ length: 8 }, (_, i) => ({
      path: `/projects/demo/file-${i}.py`,
      openedAt: 1_700_000_000_000 + i,
    }));
    const w = factory({ entries });
    await w.find('[data-test="recent-files-header"]').trigger("click");
    expect(w.findAll('[data-test="recent-row"]')).toHaveLength(5);
    expect(w.text()).toContain("+3 more");
  });

  it("emits 'select' with the row's path when a row is clicked", async () => {
    const w = factory({ entries: sampleEntries });
    await w.find('[data-test="recent-files-header"]').trigger("click");
    await w.find('[data-test="recent-row"]').trigger("click");
    const events = w.emitted("select");
    expect(events).toBeTruthy();
    expect(events![0][0]).toEqual({ path: "/projects/demo/src/main.py" });
  });

  it("emits 'remove' when × is clicked, and does NOT bubble to row select", async () => {
    const w = factory({ entries: sampleEntries });
    await w.find('[data-test="recent-files-header"]').trigger("click");
    await w
      .find('[data-test="recent-row"] [data-test="recent-remove"]')
      .trigger("click");
    const removeEvents = w.emitted("remove");
    const selectEvents = w.emitted("select");
    expect(removeEvents).toBeTruthy();
    expect(removeEvents![0][0]).toEqual({
      path: "/projects/demo/src/main.py",
    });
    expect(selectEvents).toBeFalsy();
  });

  it("emits 'clear' when the Clear link is clicked", async () => {
    const w = factory({ entries: sampleEntries });
    await w.find('[data-test="recent-files-header"]').trigger("click");
    await w.find('[data-test="recent-clear"]').trigger("click");
    const events = w.emitted("clear");
    expect(events).toBeTruthy();
    expect(events).toHaveLength(1);
  });

  it("renders the empty placeholder when entries is empty and expanded", async () => {
    const w = factory({ entries: [] });
    await w.find('[data-test="recent-files-header"]').trigger("click");
    expect(w.text()).toContain(
      // resolved at runtime by the i18n helper; pin the key string for stability
      "recentFiles.empty",
    );
  });

  it("does NOT show Clear link when entries is empty", async () => {
    const w = factory({ entries: [] });
    await w.find('[data-test="recent-files-header"]').trigger("click");
    expect(w.find('[data-test="recent-clear"]').exists()).toBe(false);
  });
});
```

- [ ] **Step 2: 运行确认 6 个新增用例 FAIL**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm test src/components/chat/message_list_comps/RecentFilesBlock.spec.ts
```

Expected: 6 个新用例全部 FAIL（折叠态没有行渲染、没有 × / Clear / `+N more`）。

- [ ] **Step 3: 实现展开态模板与逻辑**

把 `RecentFilesBlock.vue` 的 `<template>` 内的：

```vue
<!-- Task 6 adds the list panel here, gated by v-if="expanded" -->
<div v-show="expanded" data-test="recent-files-body" />
```

替换为：

```vue
<div v-show="expanded" class="recent-files-body" data-test="recent-files-body">
  <div
    v-if="props.entries.length > 0"
    class="recent-files-list"
  >
    <!-- Header subline: Clear link is part of the expanded header. -->
    <button
      type="button"
      class="recent-files-clear"
      data-test="recent-clear"
      @click.stop="$emit('clear')"
    >
      {{ tm("spcodeProjectLoad.fileBrowser.recentFiles.clear") }}
    </button>

    <!-- Up to 5 rows. extra count rolls into the "more" link. -->
    <div
      v-for="entry in displayedEntries"
      :key="entry.path"
      class="recent-files-row"
      data-test="recent-row"
      role="button"
      tabindex="0"
      @click="$emit('select', { path: entry.path })"
      @keyup.enter="$emit('select', { path: entry.path })"
    >
      <v-icon size="14" class="recent-files-row-icon">
        mdi-file-outline
      </v-icon>
      <span class="recent-files-row-main" :title="entry.path">
        {{ basename(entry.path) }}
      </span>
      <span class="recent-files-row-sub">
        {{ dirOf(entry.path) }}
      </span>
      <button
        type="button"
        class="recent-files-remove"
        data-test="recent-remove"
        :title="tm('spcodeProjectLoad.fileBrowser.recentFiles.removeTooltip')"
        @click.stop="$emit('remove', { path: entry.path })"
      >
        <v-icon size="14">mdi-close</v-icon>
      </button>
    </div>

    <div
      v-if="overflow > 0"
      class="recent-files-more"
      data-test="recent-files-more"
    >
      +{{ overflow }} more →
    </div>
  </div>

  <div
    v-else
    class="recent-files-empty"
    data-test="recent-files-empty"
  >
    {{ tm("spcodeProjectLoad.fileBrowser.recentFiles.empty") }}
  </div>
</div>
```

- [ ] **Step 4: 在 `<script setup>` 里增加 `displayedEntries` / `overflow` / `basename` / `dirOf` 的纯计算（KISS：inline，不抽 helper）**

在 `RecentFilesBlock.vue` 的 `<script setup>` 里，`expanded` ref 之后增加：

```ts
// "More than 5 → +N more"
const MAX_DISPLAYED = 5;
const displayedEntries = computed<RecentEntry[]>(() =>
  props.entries.slice(0, MAX_DISPLAYED),
);
const overflow = computed<number>(() =>
  Math.max(0, props.entries.length - MAX_DISPLAYED),
);

/** Strip directory prefix → filename. Pure inline; no helper file. */
function basename(p: string): string {
  const sep = p.includes("\\") ? "\\" : "/";
  const idx = p.lastIndexOf(sep);
  return idx === -1 ? p : p.slice(idx + 1);
}

/** Parent dir of a path. Pure inline. */
function dirOf(p: string): string {
  const sep = p.includes("\\") ? "\\" : "/";
  const idx = p.lastIndexOf(sep);
  return idx === -1 ? "" : p.slice(0, idx);
}
```

并在顶部 import 列表里增加：

```ts
import { computed, ref } from "vue";
```

（替换原 `import { ref } from "vue"`。）

- [ ] **Step 5: 增加展开态的样式**

在 `<style scoped>` 块内 `recent-files-header-chevron { ... }` 之后追加：

```css
.recent-files-body {
  padding: 4px 0 8px 12px;
}
.recent-files-list {
  display: flex;
  flex-direction: column;
}
.recent-files-clear {
  align-self: flex-end;
  margin-right: 12px;
  margin-bottom: 4px;
  background: transparent;
  border: none;
  color: rgba(var(--v-theme-primary), 0.85);
  cursor: pointer;
  font-size: 12px;
}
.recent-files-clear:hover {
  text-decoration: underline;
}
.recent-files-row {
  display: grid;
  grid-template-columns: 18px 1fr auto auto;
  align-items: center;
  gap: 6px;
  padding: 4px 12px 4px 0;
  cursor: pointer;
}
.recent-files-row:hover {
  background: rgba(var(--v-theme-on-surface), 0.05);
}
.recent-files-row-icon {
  opacity: 0.6;
}
.recent-files-row-main {
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.recent-files-row-sub {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 90px;
}
.recent-files-remove {
  background: transparent;
  border: none;
  cursor: pointer;
  opacity: 0;
  color: inherit;
}
.recent-files-row:hover .recent-files-remove,
.recent-files-remove:focus {
  opacity: 0.7;
}
.recent-files-remove:hover {
  opacity: 1;
}
.recent-files-more {
  padding: 4px 12px;
  font-size: 12px;
  color: rgba(var(--v-theme-primary), 0.85);
}
.recent-files-empty {
  text-align: center;
  padding: 12px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-size: 12px;
}
```

- [ ] **Step 6: 运行测试**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm test src/components/chat/message_list_comps/RecentFilesBlock.spec.ts
```

Expected: PASS — 全部 8 个组件用例绿（2 旧 + 6 新）。

- [ ] **Step 7: Commit**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files
git add dashboard/src/components/chat/message_list_comps/RecentFilesBlock.vue dashboard/src/components/chat/message_list_comps/RecentFilesBlock.spec.ts
git commit -m "feat(dashboard): RecentFilesBlock expanded list — rows, × button, clear, +N more, empty"
```

---

### Task 7: i18n 双语 9 键

**Files:**
- Modify: `dashboard/src/i18n/en-US/.../chat.ts`（具体子路径以仓库实际为准）
- Modify: `dashboard/src/i18n/zh-CN/.../chat.ts`

注：找到 en-US / zh-CN 中已有的 `spcodeProjectLoad.fileBrowser.*` 键（spec §9 提到），将新增键追加在 `recentFiles` 子树下，保持排序/格式。

- [ ] **Step 1: 找到 i18n 文件并定位 `spcodeProjectLoad.fileBrowser.recentFiles`**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
grep -rn "spcodeProjectLoad.*fileBrowser" src/i18n/en-US/ | findstr /R "title"
```

Expected: 输出形如 `src/i18n/en-US/.../spcodeProjectLoad.json:  "title": ...` 的若干行；记录文件路径。

- [ ] **Step 2: 在 en-US 文件的 `fileBrowser` 子树下追加 `recentFiles` 子对象**

把以下 JSON 子对象合并到 `fileBrowser` 下：

```json
"recentFiles": {
  "title": "Recent Files",
  "titleWithCount": "Recent Files ({count})",
  "empty": "No recent files",
  "more": "+{n} more",
  "clear": "Clear",
  "clearConfirmTitle": "Clear recent files",
  "clearConfirmMessage": "Clear all recent files for this worktree? Other worktrees are not affected.",
  "removeTooltip": "Remove from recent",
  "quickOpenToast": "Press Ctrl+P to jump to any file"
}
```

- [ ] **Step 3: 在 zh-CN 文件同步追加对应的中文**

```json
"recentFiles": {
  "title": "最近文件",
  "titleWithCount": "最近文件（{count}）",
  "empty": "无最近文件",
  "more": "多 {n} 个",
  "clear": "清空",
  "clearConfirmTitle": "清空最近文件",
  "clearConfirmMessage": "确定要清空当前工作区的所有最近打开文件吗？其他工作区不受影响。",
  "removeTooltip": "从最近文件移除",
  "quickOpenToast": "按住 Ctrl+P 快速跳转所有文件"
}
```

- [ ] **Step 4: 跑一遍既有 i18n 单测（如有）确认无 key 冲突**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm test -- --silent
```

Expected: PASS（与 baseline 一致；新增键不会破坏既有解析，因为是新增路径）。

- [ ] **Step 5: Commit**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files
git add dashboard/src/i18n/en-US dashboard/src/i18n/zh-CN
git commit -m "feat(dashboard): i18n keys for Recent Files (en-US, zh-CN)"
```

---

### Task 8: 接线 —— `GitDiffSidebar.vue` `watch(fileBrowserPreviewPath)` 驱动 recordOpen + 透传 props

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue`

- [ ] **Step 1: 在文件顶部 import 区域加一行**

定位现有 `import { useSpcode... }` 块附近；加入：

```ts
import { useRecentFiles } from "@/composables/useRecentFiles";
```

- [ ] **Step 2: 在 `fileBrowserCurrentPath` ref 附近实例化 composable**

定位：`const fileBrowserCurrentPath = ref<string>(loadFileBrowserCurrentPath());` 行附近；其后追加：

```ts
// 2026-07-20 Recent Files: data layer. Reads/writes a per-worktree
// localStorage bucket whenever a file is previewed.
const recentFiles = useRecentFiles(currentRoot);
```

- [ ] **Step 3: 加 `watch` 把 `fileBrowserPreviewPath` 写入 Recent**

定位：已有 `watch(fileBrowserCurrentPath, ...)` 附近；其后追加：

```ts
// Record every previewed file into the per-worktree Recent bucket.
// 2026-07-20 Recent Files §6.1: filter null (closing the preview)
// and any path outside the current worktree (search jumps to external
// files, historically).
watch(
  [fileBrowserPreviewPath, currentRoot],
  ([newPath, root]) => {
    if (!newPath || !root) return;
    const sep = root.includes("\\") ? "\\" : "/";
    if (newPath !== root && !newPath.startsWith(root + sep)) return;
    recentFiles.recordOpen(newPath);
  },
  { immediate: false },
);
```

- [ ] **Step 4: 透传到 `<FileBrowserView>`**

定位 GitDiffSidebar 模板里的 `<FileBrowserView ...>` 调用；保留既有 props，并在其后增加：

```vue
:recent-entries="recentFiles.entries.value"
@recent-select="onRecentSelect"
@recent-remove="onRecentRemove"
@recent-clear="confirmClearRecentOpen = true"
```

并在 `<script setup>` 末尾追加 handler（与既有其他 handler 同一片区域）：

```ts
function onRecentSelect(payload: { path: string }): void {
  // Mirror onFileOpen: set preview path and switch current path to
  // the file's parent directory. The parent's existing watcher will
  // persist currentPath; we just need to navigate.
  fileBrowserPreviewPath.value = payload.path;
  const sep = payload.path.includes("\\") ? "\\" : "/";
  const lastSep = payload.path.lastIndexOf(sep);
  if (lastSep > 0) {
    fileBrowserCurrentPath.value = payload.path.slice(0, lastSep);
  }
}

function onRecentRemove(payload: { path: string }): void {
  recentFiles.remove(payload.path);
}

const confirmClearRecentOpen = ref(false);
function onConfirmClearRecent(): void {
  recentFiles.clear();
  confirmClearRecentOpen.value = false;
}
```

- [ ] **Step 4b: 在 GitDiffSidebar 模板末尾追加 Clear 二次确认 dialog**

spec §6.3 要求 dialog 与 sidebar 既有 delete / restore 二次确认同形态。把它放在 GitDiffSidebar 顶层 `<template>` 内、紧邻既有其他 `v-dialog` 之后：

```vue
<v-dialog v-model="confirmClearRecentOpen" max-width="420">
  <v-card>
    <v-card-title class="text-h3 pa-4 pb-0 pl-6">
      {{ tm("spcodeProjectLoad.fileBrowser.recentFiles.clearConfirmTitle") }}
    </v-card-title>
    <v-card-text class="pt-4">
      {{ tm("spcodeProjectLoad.fileBrowser.recentFiles.clearConfirmMessage") }}
    </v-card-text>
    <v-card-actions class="pa-4 pt-0">
      <v-spacer />
      <v-btn variant="text" @click="confirmClearRecentOpen = false">
        {{ tm("spcodeProjectLoad.fileBrowser.editor.cancel") }}
      </v-btn>
      <v-btn variant="text" color="error" @click="onConfirmClearRecent">
        {{ tm("spcodeProjectLoad.fileBrowser.recentFiles.clear") }}
      </v-btn>
    </v-card-actions>
  </v-card>
</v-dialog>
```

若 sidebar 内已有的 `useModuleI18n("features/chat")` 没有解构 `tm`，需在 `<script setup>` 顶部 import 区域补：

```ts
import { useModuleI18n } from "@/i18n/composables";
const { tm } = useModuleI18n("features/chat");
```

（与 sidebar 已有 useModuleI18n 调用合并；不要重复声明）。

- [ ] **Step 5: 类型检查（不需跑测试，类型就够了）**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm exec vue-tsc --noEmit
```

Expected: 0 错误（侧栏接线后 props 与 emits 名字匹配 Task 9 的 FileBrowserView）。

如果 Task 9 尚未完成，TypeScript 会报「`recentEntries` 不存在」。先跳到 Task 9 完成接线、回来再跑这步。

- [ ] **Step 6: Commit**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files
git add dashboard/src/components/chat/GitDiffSidebar.vue
git commit -m "feat(dashboard): GitDiffSidebar records file openings into useRecentFiles"
```

---

### Task 9: 接线 —— `FileBrowserView.vue` 嵌入块 + dialog 二次确认

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/FileBrowserView.vue`

- [ ] **Step 1: 在文件顶部 import 区域增加一行**

定位既有 `import RecentFilesBlock` 那行（**保证**位于其他 message_list_comps 导入附近）：

```ts
import RecentFilesBlock from "./RecentFilesBlock.vue";
```

- [ ] **Step 2: 在 props 中追加 recentEntries 与 emits 中追加 recentSelect/RecentRemove/RecentClear**

定位 `defineProps<{ ... }>` 块，在末尾追加：

```ts
recentEntries?: { path: string; openedAt: number }[];
```

定位 `defineEmits<{ ... }>` 块，在末尾追加：

```ts
(e: "recent-select", payload: { path: string }): void;
(e: "recent-remove", payload: { path: string }): void;
(e: "recent-clear"): void;
```

- [ ] **Step 3: 模板里把块嵌入**

定位 FileBrowserView 模板中现有的左栏容器与 FileTreeList：

```vue
<!-- 当前大约 line 892-905 处 -->
<div
  v-show="!isLeftPaneCollapsed"
  class="file-browser-pane-left"
  :style="{ width: leftPanePercent + '%' }"
>
  <FileTreeList
    :state="dirComposable.state.value"
    :selected-path="previewPath"
    ...
  />
</div>
```

把 `<RecentFilesBlock>` 紧邻 `<FileTreeList>` **之上**插入（与 FileTreeList 平级，不放在它内部）：

```vue
<div
  v-show="!isLeftPaneCollapsed"
  class="file-browser-pane-left"
  :style="{ width: leftPanePercent + '%' }"
>
  <RecentFilesBlock
    v-if="rootPath"
    :entries="recentEntries ?? []"
    :current-root="rootPath"
    @select="(p) => $emit('recent-select', p)"
    @remove="(p) => $emit('recent-remove', p)"
    @clear="$emit('recent-clear')"
  />
  <FileTreeList
    :state="dirComposable.state.value"
    :selected-path="previewPath"
    ...
  />
</div>
```

注意：
- 使用 `rootPath`（FileBrowserView 已有 prop）而非重新派生，与 sidebar 保持单一真相源。
- RecentFilesBlock 是 inline-block 风格（spec §5 与 Task 5 实现），不需要额外 wrapper 标签。

- [ ] **Step 4: 类型检查**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm exec vue-tsc --noEmit
```

Expected: 0 错误。

- [ ] **Step 5: 运行既有 Component 级测试确认未回归**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm test
```

Expected: PASS——`RecentFilesBlock.spec.ts` 8 个用例绿；`useRecentFiles.spec.ts` 20 个用例绿；其他既有测试不退步。

- [ ] **Step 6: Commit**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files
git add dashboard/src/components/chat/message_list_comps/FileBrowserView.vue
git commit -m "feat(dashboard): FileBrowserView embeds RecentFilesBlock above FileTreeList"
```

---

### Task 10: 端到端验证 —— build + 全测试 + 手测清单

**Files:**
- 仅运行命令，不修改文件。

- [ ] **Step 1: 类型检查**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm exec vue-tsc --noEmit
```

Expected: 0 错误。

- [ ] **Step 2: 完整测试**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm test
```

Expected: PASS——最近 5 个 commit 加起来的 28 个新用例 + 既有所有用例绿。

- [ ] **Step 3: 构建生产 bundle**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm build
```

Expected: 0 错误；`dist/` 体积相对 baseline 无显著增加（Recent Files 全是 Vue + 纯 JS，无新依赖）。

- [ ] **Step 4: dev 手测清单（启动 dev server 后逐项）**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files\dashboard
pnpm dev
```

依次验证：

1. **默认折叠**：侧栏进入 Files view，Recent Files 块显示标题 `Recent Files (0)`、列表不展开。
2. **打开 3 个文件**：依次点击左树 3 个不同文件 → Recent Files 标题计数变成 `(3)`；点标题展开 → 列表显示 3 行（每行 basename + parent dir），hover 显示完整 path。
3. **顺序**：最近打开的在头；同 path 重复打开 → 仍只 1 条，移到头（看计数不变）。
4. **× 单删**：hover 第二行 → 出现 × → 点击 → 行消失且不跳到该文件；emits 顺序应是 `remove` 而非 `select`。
5. **Clear 链接**：点展开态右上 Clear → 二次确认 dialog → 确认 → 列表清空。
6. **+N more**：打开 8 个文件 → 展开 → 只显示 5 行 + `+3 more →`；点 `+N more` 触发 toast「按住 Ctrl+P 快速跳转所有文件」（A1 待实现）。
7. **切换 worktree**：新增一个 worktree → 切过去 → Recent 列表为空；切回原 worktree → 列表恢复。
8. **空 worktree**：`currentRoot` 为 null 时块不渲染（`v-if` 生效）。
9. **跨会话持久化**：操作完 reload 页面 → 折叠态恢复默认折叠；**条目仍在**。
10. **localStorage 不可用**：DevTools → Application → Storage → 勾「Block localStorage」→ Recent 退化为 no-op；主流程不受影响。

- [ ] **Step 5: 最终汇总 commit（若有累积改动）**

如果上一步手测发现任何小修补，提交：

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files
git status --short
# 若有改动：
git add -A
git commit -m "chore(dashboard): post-implementation polish for recent files"
```

- [ ] **Step 6: 推送分支并发起 PR**

```cmd
cd /d F:\github\Astrbot\.worktrees\feat-recent-files
git push -u origin feat/recent-files
gh pr create --title "feat(dashboard): recent files list in Files view" --body "Implements docs/superpowers/specs/2026-07-20-recent-files-design.md. New <RecentFilesBlock> (default-collapsed) above FileTreeList. Per-worktree 50-entry localStorage bucket; recordOpen on fileBrowserPreviewPath changes; row click mirrors onFileOpen; × button per row; Clear link with secondary-confirm dialog. No new deps. 28 new unit tests."
```

Expected: PR created with checks enqueued.
