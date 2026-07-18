# GitDiffSidebar 变更热力图与统计面板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 GitDiffSidebar 的 History 子页顶部新增可折叠「变更统计」面板（26 周日历热力图 + 热点文件 Top10 + 汇总行），点击天/文件可联动下方 commit 列表过滤器。

**Architecture:** 三件套新文件（parser / composable / 面板组件）复刻 `useSpcodeGitShow` 模式；`GitLogView` 内嵌面板并复用其 `localFilter` + `apply` emit 实现联动，`GitDiffSidebar` 仅做挂载/传参/懒加载/持久化。数据源为插件新端点 `GET /spcode/git-stats`（契约见关联 spec）。

**Tech Stack:** Vue 3 `<script setup>` + TypeScript、Vuetify 3、vitest、`useModuleI18n("features/chat")`。

**工作区:** `F:\github\Astrbot\.worktrees\feat-git-stats-heatmap`（branch `feat/git-stats-heatmap`）。dashboard 命令均在 `<worktree>\dashboard` 下执行。

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-18-git-stats-heatmap-design.md`（本仓库同分支）
- 端点契约（插件侧已实现/并行实现）：`GET /spcode/git-stats?umo&worktree`，data 字段：`days[{date,commits,additions,deletions}]`（稀疏升序）、`hot_files[{path,commits,additions,deletions}]`、`totals{commits,additions,deletions,files_changed}`、`range{first,last}`、`truncated`、`max_commits`、`resolved_sha`、`loaded`、`reason`（成功为 null）、`stderr`、`elapsed_ms`
- **零图表库**：热力图 = CSS grid divs；条形图 = 百分比宽度 div；tooltip 用原生 `title`
- 热力图固定 26 周窗口，commits 分桶 `0 / 1–2 / 3–5 / 6–9 / 10+`
- localStorage key：`astrbot.spcode.gitDiffSidebar.statsOpen`（沿用 `GitDiffSidebar.vue` 的 `STORAGE_KEYS` + `safeGetItem`/`safeSetItem`）
- i18n 三语言（en-US / zh-CN / ru-RU）同 commit 补齐，key 前缀 `spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.*`
- 不改 GitLogView 既有过滤器/commit 列表/展开逻辑与其他三个 tab 的任何行为
- 注释用英文（AGENTS.md 约定）
- 完成后 `cd dashboard && pnpm test`（vitest run）通过

---

### Task 1: `parseSpcodeGitStats.ts` + 单元测试

**Files:**
- Create: `dashboard/src/composables/parseSpcodeGitStats.ts`
- Test: `dashboard/src/composables/parseSpcodeGitStats.spec.ts`

**Interfaces:**
- Produces（Task 2/3 依赖）:
  - `parseSpcodeGitStats(raw: unknown): ParseResult<GitStatsData>`
  - `interface GitStatsDay { date: string; commits: number; additions: number; deletions: number }`
  - `interface GitStatsHotFile { path: string; commits: number; additions: number; deletions: number }`
  - `interface GitStatsData { success, reason, loaded, stderr, elapsedMs, umo, worktree, directory, ref, resolvedSha, days, hotFiles, totals, range, truncated, maxCommits }`
  - `type ParseResult<T> = { kind: "ok"; snapshot: T } | { kind: "error"; reason: string }`

- [ ] **Step 1: 写失败测试**

创建 `dashboard/src/composables/parseSpcodeGitStats.spec.ts`：

```typescript
// Author: elecvoid243, 2026-07-18
// Spec: docs/superpowers/specs/2026-07-18-git-stats-heatmap-design.md
// Tests exercise the parser with the actual wire shape produced by the
// plugin's GET /spcode/git-stats endpoint (envelope: {status, data}).

import { describe, expect, it } from "vitest";
import { parseSpcodeGitStats } from "./parseSpcodeGitStats";

function envelope(data: Record<string, unknown>) {
  return { status: "ok", data };
}

function fullData(overrides: Record<string, unknown> = {}) {
  return {
    loaded: true,
    umo: "webchat:FriendMessage:x",
    worktree: null,
    directory: "F:/repo",
    ref: "HEAD",
    resolved_sha: "abc123",
    days: [
      { date: "2026-07-10", commits: 2, additions: 8, deletions: 2 },
      { date: "2026-07-12", commits: 1, additions: 3, deletions: 3 },
    ],
    hot_files: [
      { path: "a.py", commits: 3, additions: 9, deletions: 5 },
      { path: "b.py", commits: 1, additions: 2, deletions: 0 },
    ],
    totals: { commits: 3, additions: 11, deletions: 5, files_changed: 2 },
    range: { first: "2026-07-10", last: "2026-07-12" },
    truncated: false,
    max_commits: 5000,
    reason: null,
    stderr: "",
    elapsed_ms: 230,
    ...overrides,
  };
}

describe("parseSpcodeGitStats", () => {
  it("parses a full success envelope", () => {
    const r = parseSpcodeGitStats(envelope(fullData()));
    expect(r.kind).toBe("ok");
    if (r.kind !== "ok") return;
    const s = r.snapshot;
    expect(s.success).toBe(true);
    expect(s.reason).toBeNull();
    expect(s.days).toEqual([
      { date: "2026-07-10", commits: 2, additions: 8, deletions: 2 },
      { date: "2026-07-12", commits: 1, additions: 3, deletions: 3 },
    ]);
    expect(s.hotFiles).toEqual([
      { path: "a.py", commits: 3, additions: 9, deletions: 5 },
      { path: "b.py", commits: 1, additions: 2, deletions: 0 },
    ]);
    expect(s.totals).toEqual({
      commits: 3,
      additions: 11,
      deletions: 5,
      filesChanged: 2,
    });
    expect(s.range).toEqual({ first: "2026-07-10", last: "2026-07-12" });
    expect(s.truncated).toBe(false);
    expect(s.maxCommits).toBe(5000);
    expect(s.resolvedSha).toBe("abc123");
    expect(s.elapsedMs).toBe(230);
  });

  it("derives success=false from a non-null reason (deriveSuccess)", () => {
    const r = parseSpcodeGitStats(
      envelope(fullData({ reason: "git_error", loaded: false })),
    );
    expect(r.kind).toBe("ok");
    if (r.kind !== "ok") return;
    expect(r.snapshot.success).toBe(false);
    expect(r.snapshot.reason).toBe("git_error");
  });

  it("preserves an explicit success field when present", () => {
    const r = parseSpcodeGitStats(
      envelope(fullData({ success: true, reason: "weird" })),
    );
    expect(r.kind).toBe("ok");
    if (r.kind !== "ok") return;
    expect(r.snapshot.success).toBe(true);
  });

  it("falls back to defaults for missing optional fields", () => {
    const r = parseSpcodeGitStats(envelope({ reason: null }));
    expect(r.kind).toBe("ok");
    if (r.kind !== "ok") return;
    const s = r.snapshot;
    expect(s.days).toEqual([]);
    expect(s.hotFiles).toEqual([]);
    expect(s.totals).toEqual({
      commits: 0,
      additions: 0,
      deletions: 0,
      filesChanged: 0,
    });
    expect(s.range).toEqual({ first: null, last: null });
    expect(s.ref).toBe("HEAD");
    expect(s.truncated).toBe(false);
    expect(s.maxCommits).toBe(5000);
    expect(s.umo).toBeNull();
  });

  it("coerces non-array days / hot_files to empty arrays", () => {
    const r = parseSpcodeGitStats(
      envelope(fullData({ days: "oops", hot_files: 42 })),
    );
    expect(r.kind).toBe("ok");
    if (r.kind !== "ok") return;
    expect(r.snapshot.days).toEqual([]);
    expect(r.snapshot.hotFiles).toEqual([]);
  });

  it("returns error on a malformed envelope (missing data)", () => {
    const r = parseSpcodeGitStats({ status: "ok" });
    expect(r.kind).toBe("error");
  });

  it("returns error on a non-ok status envelope", () => {
    const r = parseSpcodeGitStats({ status: "error", data: {} });
    expect(r.kind).toBe("error");
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd dashboard && npx vitest run src/composables/parseSpcodeGitStats.spec.ts`
Expected: FAIL — `Failed to resolve import "./parseSpcodeGitStats"`

- [ ] **Step 3: 实现 parser**

创建 `dashboard/src/composables/parseSpcodeGitStats.ts`：

```typescript
// Author: elecvoid243
// Date: 2026-07-18
// Spec: docs/superpowers/specs/2026-07-18-git-stats-heatmap-design.md
//
// Parser for GET /spcode/git-stats. Mirrors parseSpcodeGitShow.ts:
// envelope unwrap + field normalization into a discriminated result.

export interface GitStatsDay {
  /** "YYYY-MM-DD" author-local date. */
  date: string;
  commits: number;
  additions: number;
  deletions: number;
}

export interface GitStatsHotFile {
  path: string;
  commits: number;
  additions: number;
  deletions: number;
}

export interface GitStatsData {
  // Envelope fields
  success: boolean;
  reason: string | null;
  loaded: boolean;
  stderr: string;
  elapsedMs: number;
  umo: string | null;
  worktree: string | null;
  directory: string | null;

  // Stats payload
  ref: string;
  resolvedSha: string;
  days: GitStatsDay[];
  hotFiles: GitStatsHotFile[];
  totals: {
    commits: number;
    additions: number;
    deletions: number;
    filesChanged: number;
  };
  range: { first: string | null; last: string | null };
  truncated: boolean;
  maxCommits: number;
}

export type ParseResult<T> =
  | { kind: "ok"; snapshot: T }
  | { kind: "error"; reason: string };

// ─── Helpers ───────────────────────────────────────────────────────

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}
function asNumber(v: unknown, fallback = 0): number {
  return typeof v === "number" ? v : fallback;
}
function asBoolean(v: unknown, fallback = false): boolean {
  return typeof v === "boolean" ? v : fallback;
}
function asStringOrNull(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}

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

/** Mirror parseSpcodeGitShow.deriveSuccess: backend never writes
 *  `success`; the canonical indicator is `reason === null`. */
function deriveSuccess(d: { success?: unknown; reason?: unknown }): boolean {
  if (d.success !== undefined) return asBoolean(d.success);
  return d.reason === null;
}

// ─── Public parser ─────────────────────────────────────────────────

/** Parse the envelope from GET /spcode/git-stats. */
export function parseSpcodeGitStats(raw: unknown): ParseResult<GitStatsData> {
  try {
    const d = unwrapEnvelope(raw) as Record<string, unknown>;

    const rawDays = Array.isArray(d.days) ? d.days : [];
    const days: GitStatsDay[] = rawDays.map((x) => {
      const d0 = x as Record<string, unknown>;
      return {
        date: asString(d0.date),
        commits: asNumber(d0.commits),
        additions: asNumber(d0.additions),
        deletions: asNumber(d0.deletions),
      };
    });

    const rawHot = Array.isArray(d.hot_files) ? d.hot_files : [];
    const hotFiles: GitStatsHotFile[] = rawHot.map((x) => {
      const f0 = x as Record<string, unknown>;
      return {
        path: asString(f0.path),
        commits: asNumber(f0.commits),
        additions: asNumber(f0.additions),
        deletions: asNumber(f0.deletions),
      };
    });

    const t = (d.totals ?? {}) as Record<string, unknown>;
    const rg = (d.range ?? {}) as Record<string, unknown>;

    return {
      kind: "ok",
      snapshot: {
        success: deriveSuccess(d),
        reason: asStringOrNull(d.reason),
        loaded: asBoolean(d.loaded),
        stderr: asString(d.stderr),
        elapsedMs: asNumber(d.elapsed_ms),
        umo: asStringOrNull(d.umo),
        worktree: asStringOrNull(d.worktree),
        directory: asStringOrNull(d.directory),
        ref: asString(d.ref, "HEAD"),
        resolvedSha: asString(d.resolved_sha),
        days,
        hotFiles,
        totals: {
          commits: asNumber(t.commits),
          additions: asNumber(t.additions),
          deletions: asNumber(t.deletions),
          filesChanged: asNumber(t.files_changed),
        },
        range: {
          first: asStringOrNull(rg.first),
          last: asStringOrNull(rg.last),
        },
        truncated: asBoolean(d.truncated),
        maxCommits: asNumber(d.max_commits, 5000),
      },
    };
  } catch (e) {
    return {
      kind: "error",
      reason: e instanceof Error ? e.message : "parse_error",
    };
  }
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd dashboard && npx vitest run src/composables/parseSpcodeGitStats.spec.ts`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/composables/parseSpcodeGitStats.ts dashboard/src/composables/parseSpcodeGitStats.spec.ts
git commit -m "feat(dashboard): add git-stats response parser"
```

---

### Task 2: `useSpcodeGitStats.ts` composable

**Files:**
- Create: `dashboard/src/composables/useSpcodeGitStats.ts`

**Interfaces:**
- Consumes: Task 1 的 `parseSpcodeGitStats` / `GitStatsData`
- Produces（Task 3/4/5 依赖）:
  - `type GitStatsFetchState = { kind: "idle" } | { kind: "loading" } | { kind: "ok"; snapshot: GitStatsData; notModified?: boolean } | { kind: "error"; reason: string; previousSnapshot?: GitStatsData }`
  - `interface UseSpcodeGitStats { state: Ref<GitStatsFetchState>; refresh(options?: { forceLoading?: boolean }): Promise<void>; invalidateEtag(): void; dispose(): void }`
  - `function useSpcodeGitStats(worktreeRef: MaybeRef<string | null>): UseSpcodeGitStats`

无独立自动化测试（与 `useSpcodeGitShow` 等兄弟 composable 的现状一致）；由 Task 4/5 集成验证 + vitest 全量回归兜底。

- [ ] **Step 1: 实现 composable**

创建 `dashboard/src/composables/useSpcodeGitStats.ts`：

```typescript
// Author: elecvoid243
// Date: 2026-07-18
// Spec: docs/superpowers/specs/2026-07-18-git-stats-heatmap-design.md
//
// Vue composable wrapping GET /spcode/git-stats. Single-snapshot
// (whole-repo stats for the active worktree) mirroring the
// useSpcodeGitLog state machine, minus polling / loadMore / filters:
// the stats request has no varying query dimensions in v1 (always
// ref=HEAD, whole repo), so the ETag key is umo|worktree only.

import { ref, toValue, type MaybeRef, type Ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import {
  parseSpcodeGitStats,
  type GitStatsData,
} from "./parseSpcodeGitStats";

export type GitStatsFetchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; snapshot: GitStatsData; notModified?: boolean }
  | { kind: "error"; reason: string; previousSnapshot?: GitStatsData };

export interface UseSpcodeGitStats {
  state: Ref<GitStatsFetchState>;
  refresh: (options?: { forceLoading?: boolean }) => Promise<void>;
  /** Clear the ETag map (worktree / umo switch). */
  invalidateEtag: () => void;
  dispose: () => void;
}

export function useSpcodeGitStats(
  worktreeRef: MaybeRef<string | null> = null,
): UseSpcodeGitStats {
  const state = ref<GitStatsFetchState>({ kind: "idle" });
  const spcodeStatus = useSpcodeProjectStatus();
  // ETag + previous snapshot keyed by umo|worktree so a worktree
  // switch never replays another worktree's stats on a 304 replay.
  const etagMap = new Map<string, string>();
  const prevSnapshotMap = new Map<string, GitStatsData>();
  let abortController: AbortController | null = null;
  let isMounted = true;

  function etagKey(umo: string, worktree: string | null): string {
    return [umo, worktree ?? ""].join("|");
  }

  async function refresh(options?: { forceLoading?: boolean }): Promise<void> {
    if (!isMounted) return;
    const umo = spcodeStatus.status.value.umo;
    if (!umo) {
      state.value = { kind: "error", reason: "no_project_loaded" };
      return;
    }
    abortController?.abort();
    abortController = new AbortController();
    // loading only on the first fetch (or when the caller explicitly
    // wants visual feedback); 304 short-circuits never enter loading.
    if (state.value.kind !== "ok" || options?.forceLoading) {
      state.value = { kind: "loading" };
    }
    const worktree = toValue(worktreeRef);
    const key = etagKey(umo, worktree);
    const etag = etagMap.get(key);
    try {
      const resp = await pluginExtensionApi.get<unknown>("spcode/git-stats", {
        params: {
          umo,
          ...(worktree ? { worktree } : {}),
        },
        headers: etag ? { "If-None-Match": etag } : {},
        // Surface 304 as a valid response (default axios would throw).
        validateStatus: (s) => (s >= 200 && s < 300) || s === 304,
        signal: abortController.signal,
      });
      if (!isMounted) return;

      if (resp.status === 304) {
        const cached = prevSnapshotMap.get(key);
        if (cached) {
          state.value = { kind: "ok", snapshot: cached, notModified: true };
        }
        return;
      }

      const parsed = parseSpcodeGitStats(resp.data);
      if (parsed.kind !== "ok") {
        state.value = {
          kind: "error",
          reason: parsed.reason,
          previousSnapshot: prevSnapshotMap.get(key) ?? undefined,
        };
        return;
      }
      const snap = parsed.snapshot;
      // Business failure (git_error / not_a_git_repo / empty_repository
      // / ...) rides a 200 envelope with success=false — route to the
      // error state with the raw ReasonCode (mirrors useSpcodeGitLog).
      if (!snap.success) {
        state.value = {
          kind: "error",
          reason: snap.reason ?? "unknown",
          previousSnapshot: prevSnapshotMap.get(key) ?? undefined,
        };
        return;
      }
      prevSnapshotMap.set(key, snap);
      const newEtag =
        (resp.headers as Record<string, string> | undefined)?.["etag"] ??
        (resp.headers as Record<string, string> | undefined)?.["ETag"];
      if (newEtag) etagMap.set(key, newEtag);
      state.value = { kind: "ok", snapshot: snap, notModified: false };
    } catch (err) {
      if (!isMounted) return;
      if ((err as { name?: string })?.name === "CanceledError") return;
      const anyErr = err as { code?: string; message?: string };
      state.value = {
        kind: "error",
        reason:
          anyErr.code === "ERR_NETWORK" ||
          /network/i.test(anyErr.message ?? "")
            ? "network"
            : "unknown",
        previousSnapshot: prevSnapshotMap.get(key) ?? undefined,
      };
    }
  }

  function invalidateEtag(): void {
    etagMap.clear();
  }

  function dispose(): void {
    isMounted = false;
    abortController?.abort();
    abortController = null;
    etagMap.clear();
    prevSnapshotMap.clear();
  }

  return { state, refresh, invalidateEtag, dispose };
}
```

- [ ] **Step 2: 类型与全量回归**

Run: `cd dashboard && pnpm test`
Expected: 全部通过（既有 spec 无回归；本 Task 无新测试）

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/composables/useSpcodeGitStats.ts
git commit -m "feat(dashboard): add useSpcodeGitStats composable"
```

---

### Task 3: `GitStatsPanel.vue` 面板组件

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/GitStatsPanel.vue`

**Interfaces:**
- Consumes: Task 2 的 `GitStatsFetchState`；Task 1 的 `GitStatsDay`
- Produces（Task 4 依赖）:
  - Props: `{ state: GitStatsFetchState; open: boolean; isDark?: boolean }`
  - Emits: `(e: "update:open", v: boolean)`、`(e: "refresh")`、`(e: "filter-date", p: { since: string; until: string })`、`(e: "filter-path", path: string)`

i18n key 清单见 Task 6（本 Task 的模板直接引用这些 key）。

- [ ] **Step 1: 实现组件**

创建 `dashboard/src/components/chat/message_list_comps/GitStatsPanel.vue`：

```vue
<!--
  Author: elecvoid243, 2026-07-18
  Spec: docs/superpowers/specs/2026-07-18-git-stats-heatmap-design.md

  GitStatsPanel — collapsible change-stats panel embedded at the top of
  GitLogView: 26-week calendar heatmap + Top-N hot files + totals row.
  Clicking a day / file emits filter events that GitLogView turns into
  its standard `apply` flow.
-->
<script setup lang="ts">
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { GitStatsFetchState } from "@/composables/useSpcodeGitStats";
import type { GitStatsDay } from "@/composables/parseSpcodeGitStats";

const props = defineProps<{
  state: GitStatsFetchState;
  /** Collapsed/expanded state (persisted by the sidebar). */
  open: boolean;
  isDark?: boolean;
}>();
const emit = defineEmits<{
  (e: "update:open", v: boolean): void;
  (e: "refresh"): void;
  (e: "filter-date", p: { since: string; until: string }): void;
  (e: "filter-path", path: string): void;
}>();

const { tm } = useModuleI18n("features/chat");

// ── Snapshot access (ok, or stale snapshot behind an error) ────────
const snapshot = computed(() => {
  const s = props.state;
  if (s.kind === "ok") return s.snapshot;
  if (s.kind === "error") return s.previousSnapshot ?? null;
  return null;
});
const isLoading = computed(() => props.state.kind === "loading");
const errorReason = computed(() =>
  props.state.kind === "error" ? props.state.reason : null,
);
const isEmptyRepo = computed(() => errorReason.value === "empty_repository");
const totals = computed(() => snapshot.value?.totals ?? null);
const truncated = computed(() => snapshot.value?.truncated ?? false);
const maxCommits = computed(() => snapshot.value?.maxCommits ?? 0);

// ── Heatmap grid (26 week-columns × 7 rows, local time) ────────────
const WEEKS = 26;

interface DayCell {
  date: string;
  commits: number;
  additions: number;
  deletions: number;
  level: number;
  /** Cells after today in the current week: dimmed + not clickable. */
  future: boolean;
}

function levelOf(commits: number): number {
  if (commits <= 0) return 0;
  if (commits <= 2) return 1;
  if (commits <= 5) return 2;
  if (commits <= 9) return 3;
  return 4;
}

function fmtDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

const grid = computed<DayCell[][]>(() => {
  const byDate = new Map<string, GitStatsDay>();
  for (const d of snapshot.value?.days ?? []) byDate.set(d.date, d);
  const today = new Date();
  const todayStart = new Date(
    today.getFullYear(),
    today.getMonth(),
    today.getDate(),
  );
  // Sunday of the current week anchors the LAST column.
  const endSunday = new Date(todayStart);
  endSunday.setDate(endSunday.getDate() - endSunday.getDay());
  const cols: DayCell[][] = [];
  for (let w = WEEKS - 1; w >= 0; w--) {
    const col: DayCell[] = [];
    for (let dow = 0; dow < 7; dow++) {
      const d = new Date(endSunday);
      d.setDate(d.getDate() - w * 7 + dow);
      const key = fmtDate(d);
      const stat = byDate.get(key);
      const commits = stat?.commits ?? 0;
      col.push({
        date: key,
        commits,
        additions: stat?.additions ?? 0,
        deletions: stat?.deletions ?? 0,
        level: levelOf(commits),
        future: d.getTime() > todayStart.getTime(),
      });
    }
    cols.push(col);
  }
  return cols;
});

/** Month labels above the grid, emitted at each month boundary. Uses
 *  the browser locale via toLocaleDateString (zero i18n keys). */
const monthLabels = computed(() => {
  const labels: { col: number; label: string }[] = [];
  let prevMonth = -1;
  grid.value.forEach((col, i) => {
    const first = new Date(col[0].date + "T00:00:00");
    const m = first.getMonth();
    if (m !== prevMonth) {
      labels.push({
        col: i,
        label: first.toLocaleDateString(undefined, { month: "short" }),
      });
      prevMonth = m;
    }
  });
  return labels;
});

// ── Hot files ──────────────────────────────────────────────────────
const hotFiles = computed(() => snapshot.value?.hotFiles ?? []);
const maxHotCommits = computed(() =>
  Math.max(1, ...hotFiles.value.map((f) => f.commits)),
);
function barWidth(commits: number): string {
  return `${Math.round((commits / maxHotCommits.value) * 100)}%`;
}

// ── Events ─────────────────────────────────────────────────────────
function onToggle(): void {
  emit("update:open", !props.open);
}
function onDayClick(cell: DayCell): void {
  if (cell.level === 0 || cell.future) return;
  // Explicit local times: a date-only --until parses as midnight in
  // git, which would yield an empty range for same-day filters.
  emit("filter-date", {
    since: `${cell.date}T00:00:00`,
    until: `${cell.date}T23:59:59`,
  });
}
function onFileClick(path: string): void {
  emit("filter-path", path);
}
function cellTitle(cell: DayCell): string {
  if (cell.commits === 0) {
    return tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.zeroTooltip", {
      date: cell.date,
    });
  }
  return tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.cellTooltip", {
    date: cell.date,
    commits: cell.commits,
    additions: cell.additions,
    deletions: cell.deletions,
  });
}
</script>

<template>
  <div class="git-stats-panel" :class="{ 'is-dark': !!isDark }">
    <!-- Header: always visible; collapsed shows only this row -->
    <div class="git-stats-header">
      <v-icon size="14" class="git-stats-header-icon">mdi-chart-box-outline</v-icon>
      <span class="git-stats-title">
        {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.title") }}
      </span>
      <span v-if="totals" class="git-stats-summary">
        {{
          tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.summary", {
            commits: totals.commits,
            additions: totals.additions,
            deletions: totals.deletions,
            files: totals.filesChanged,
          })
        }}
      </span>
      <span v-if="truncated" class="git-stats-truncated-badge">
        {{
          tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.truncatedBadge", {
            n: maxCommits,
          })
        }}
      </span>
      <span class="git-stats-header-spacer" />
      <v-btn
        icon
        size="x-small"
        variant="text"
        :loading="isLoading && open"
        :title="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.refresh')"
        @click="emit('refresh')"
      >
        <v-icon size="14">mdi-restart</v-icon>
      </v-btn>
      <v-btn
        icon
        size="x-small"
        variant="text"
        :title="
          tm(
            open
              ? 'spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.collapse'
              : 'spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.expand',
          )
        "
        @click="onToggle"
      >
        <v-icon size="14">{{ open ? "mdi-chevron-up" : "mdi-chevron-down" }}</v-icon>
      </v-btn>
    </div>

    <!-- Body: only while expanded -->
    <div v-if="open" class="git-stats-body">
      <!-- loading skeleton -->
      <div v-if="isLoading" class="git-stats-loading">
        {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.loading") }}
      </div>

      <!-- error (non-empty-repo) -->
      <div v-else-if="errorReason && !isEmptyRepo" class="git-stats-error">
        <span>
          {{
            tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.error") +
            ": " +
            tm(`spcodeProjectLoad.diffSidebar.gitWorkflow.error.reason.${errorReason}`, { reason: errorReason })
          }}
        </span>
        <button type="button" class="git-stats-retry" @click="emit('refresh')">
          {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.retry") }}
        </button>
      </div>

      <!-- empty repository -->
      <div v-else-if="isEmptyRepo" class="git-stats-empty">
        {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.emptyRepo") }}
      </div>

      <template v-else-if="snapshot">
        <!-- month labels + heatmap -->
        <div class="git-stats-heatmap-wrap">
          <div class="git-stats-months" :style="{ gridTemplateColumns: `repeat(${WEEKS}, 1fr)` }">
            <span
              v-for="ml in monthLabels"
              :key="ml.col"
              class="git-stats-month-label"
              :style="{ gridColumnStart: ml.col + 1 }"
            >
              {{ ml.label }}
            </span>
          </div>
          <div class="git-stats-grid" role="grid" aria-label="commit activity heatmap">
            <template v-for="(col, ci) in grid" :key="ci">
              <button
                v-for="cell in col"
                :key="cell.date"
                type="button"
                class="git-stats-cell"
                :class="[`lv-${cell.level}`, { 'is-future': cell.future }]"
                :title="cellTitle(cell)"
                :disabled="cell.level === 0 || cell.future"
                @click="onDayClick(cell)"
              />
            </template>
          </div>
        </div>

        <!-- hot files -->
        <div v-if="hotFiles.length > 0" class="git-stats-hot">
          <div class="git-stats-hot-title">
            {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFiles") }}
          </div>
          <button
            v-for="f in hotFiles"
            :key="f.path"
            type="button"
            class="git-stats-hot-row"
            :title="f.path"
            @click="onFileClick(f.path)"
          >
            <span class="git-stats-hot-bar-wrap">
              <span class="git-stats-hot-bar" :style="{ width: barWidth(f.commits) }" />
            </span>
            <span class="git-stats-hot-path">{{ f.path }}</span>
            <span class="git-stats-hot-value">
              {{
                tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFileValue", {
                  commits: f.commits,
                  additions: f.additions,
                  deletions: f.deletions,
                })
              }}
            </span>
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.git-stats-panel {
  --gs-l0: rgb(127 127 127 / 15%);
  --gs-l1: #9be9a8;
  --gs-l2: #40c463;
  --gs-l3: #30a14e;
  --gs-l4: #216e39;
  --gs-bar: rgb(var(--v-theme-primary));
  border: 1px solid rgb(var(--v-theme-on-surface), 0.08);
  border-radius: 8px;
  margin-bottom: 8px;
  font-size: 12px;
}
.git-stats-panel.is-dark {
  --gs-l0: rgb(255 255 255 / 8%);
  --gs-l1: #0e4429;
  --gs-l2: #006d32;
  --gs-l3: #26a641;
  --gs-l4: #39d353;
}
.git-stats-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
}
.git-stats-header-icon {
  opacity: 0.7;
}
.git-stats-title {
  font-weight: 600;
}
.git-stats-summary {
  opacity: 0.75;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.git-stats-truncated-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: rgb(var(--v-theme-warning), 0.18);
  color: rgb(var(--v-theme-warning));
  white-space: nowrap;
}
.git-stats-header-spacer {
  flex: 1;
}
.git-stats-body {
  padding: 4px 8px 8px;
}
.git-stats-loading,
.git-stats-empty {
  padding: 12px 4px;
  text-align: center;
  opacity: 0.65;
}
.git-stats-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 4px;
  color: rgb(var(--v-theme-error));
}
.git-stats-retry {
  text-decoration: underline;
  cursor: pointer;
}
.git-stats-months {
  display: grid;
  margin-bottom: 2px;
}
.git-stats-month-label {
  font-size: 10px;
  opacity: 0.6;
  grid-row: 1;
}
.git-stats-grid {
  display: grid;
  grid-template-rows: repeat(7, 1fr);
  grid-auto-flow: column;
  gap: 2px;
}
.git-stats-cell {
  width: 100%;
  aspect-ratio: 1;
  min-width: 8px;
  border: 0;
  border-radius: 2px;
  background: var(--gs-l0);
  cursor: pointer;
  padding: 0;
}
.git-stats-cell:disabled {
  cursor: default;
}
.git-stats-cell.lv-1 { background: var(--gs-l1); }
.git-stats-cell.lv-2 { background: var(--gs-l2); }
.git-stats-cell.lv-3 { background: var(--gs-l3); }
.git-stats-cell.lv-4 { background: var(--gs-l4); }
.git-stats-cell.is-future {
  opacity: 0.35;
}
.git-stats-cell:not(:disabled):hover {
  outline: 1px solid rgb(var(--v-theme-primary));
}
.git-stats-hot {
  margin-top: 8px;
}
.git-stats-hot-title {
  font-weight: 600;
  margin-bottom: 4px;
  opacity: 0.8;
}
.git-stats-hot-row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 2px 0;
  border: 0;
  background: none;
  cursor: pointer;
  text-align: left;
  font-size: 12px;
  color: inherit;
}
.git-stats-hot-row:hover .git-stats-hot-path {
  color: rgb(var(--v-theme-primary));
}
.git-stats-hot-bar-wrap {
  flex: 0 0 80px;
  height: 8px;
  border-radius: 4px;
  background: rgb(127 127 127 / 15%);
  overflow: hidden;
}
.git-stats-hot-bar {
  display: block;
  height: 100%;
  background: var(--gs-bar);
  border-radius: 4px;
}
.git-stats-hot-path {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  direction: rtl; /* left-truncate long paths */
}
.git-stats-hot-value {
  flex: 0 0 auto;
  opacity: 0.7;
  font-variant-numeric: tabular-nums;
}
</style>
```

注：`<style>` 顶部 `.git-stats-grid` 用 `grid-auto-flow: column` + `grid-template-rows: repeat(7, 1fr)` 实现「列 = 周」的列主序布局，模板中按列优先 v-for 输出 182 个 cell。

- [ ] **Step 2: 验证（类型层面）**

Run: `cd dashboard && pnpm test`
Expected: 全量通过（新组件无 spec，验证点 = 编译不破坏既有测试）

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/components/chat/message_list_comps/GitStatsPanel.vue
git commit -m "feat(dashboard): add GitStatsPanel component"
```

---

### Task 4: `GitLogView.vue` 接线（嵌入面板 + 过滤器联动）

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/GitLogView.vue`

**Interfaces:**
- Consumes: Task 2 的 `UseSpcodeGitStats`、Task 3 的 `GitStatsPanel`
- Produces（Task 5 依赖）: `GitLogView` 新 props `gitStats: UseSpcodeGitStats`、`statsOpen: boolean`；新 emit `(e: "update:statsOpen", v: boolean)`

- [ ] **Step 1: script 部分修改**

`GitLogView.vue` 的 `<script setup>` 中：

1. import 区追加：

```typescript
import GitStatsPanel from "./GitStatsPanel.vue";
import type { UseSpcodeGitStats } from "@/composables/useSpcodeGitStats";
```

2. props 定义中（`focusedCommitSha` 之后）追加两个 prop：

```typescript
  /**
   * 2026-07-18 git-stats: the sidebar's `useSpcodeGitStats` instance.
   * Received as a handle (not a snapshot) so the panel's refresh
   * button can re-fetch through the composable the sidebar owns.
   */
  gitStats: UseSpcodeGitStats;
  /** 2026-07-18 git-stats: collapse state of the stats panel.
   *  Owned (and persisted) by the sidebar; mirrored via
   *  `update:statsOpen`. */
  statsOpen: boolean;
```

3. emits 定义中追加：

```typescript
  // 2026-07-18 git-stats: v-model passthrough for the panel's
  // collapse state (the sidebar persists it to localStorage).
  (e: "update:statsOpen", v: boolean): void;
```

4. `onReset` 函数之后追加两个联动 handler：

```typescript
// ── Stats panel filter linkage (2026-07-18 git-stats) ─────────────
// Both handlers route through the SAME apply path as the filter bar:
// they replace localFilter wholesale (ref=HEAD, n=20) so a previous
// author/path filter never silently narrows a stats-driven query.
function onStatsFilterDate(p: { since: string; until: string }): void {
  localFilter.value = { ref: "HEAD", n: 20, since: p.since, until: p.until };
  emit("apply", { ...localFilter.value });
}

function onStatsFilterPath(path: string): void {
  localFilter.value = { ref: "HEAD", n: 20, path };
  emit("apply", { ...localFilter.value });
}
```

- [ ] **Step 2: template 部分修改**

`GitLogView.vue` 模板根节点 `<div class="git-log-view">` 内、truncation banner **之前**插入：

```html
  <div class="git-log-view">
    <!-- 2026-07-18 git-stats: collapsible stats panel above the
         filter bar. Sits inside GitLogView so its filter events can
         reuse the local `apply` flow with zero sidebar plumbing. -->
    <GitStatsPanel
      :state="gitStats.state.value"
      :open="statsOpen"
      :is-dark="isDark"
      @update:open="emit('update:statsOpen', $event)"
      @refresh="() => gitStats.refresh({ forceLoading: true })"
      @filter-date="onStatsFilterDate"
      @filter-path="onStatsFilterPath"
    />

    <!-- Truncation banner (spec §6.5.2) -->
```

isDark 处理说明：`GitLogView` 当前**没有** `isDark` prop（FilePatchPanel 自读 customizer store）。若 `GitLogView` script 中无现成 isDark，则在 `GitLogView.vue` import 区追加 `import { useCustomizerStore } from "@/stores/customizer";`，script 内追加：

```typescript
// 2026-07-18 git-stats: dark-mode flag for the stats panel's color
// scale. Mirrors FilePatchPanel's approach of reading the customizer
// store directly (GitLogView has no isDark prop of its own).
const customizer = useCustomizerStore();
const isDark = computed(() => customizer.uiTheme === "dark");
```

并确认 `computed` 已在 vue import 中（已有）。实现前先 `grep -n "useCustomizerStore" dashboard/src/components/chat/message_list_comps/FilePatchPanel.vue` 核对主题字段名（若字段不是 `uiTheme`，以 FilePatchPanel 的实际读取为准）。

- [ ] **Step 3: 回归**

Run: `cd dashboard && pnpm test`
Expected: 全量通过

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/components/chat/message_list_comps/GitLogView.vue
git commit -m "feat(dashboard): embed GitStatsPanel in GitLogView with filter linkage"
```

---

### Task 5: `GitDiffSidebar.vue` 接线（挂载 / 持久化 / 懒加载 / 刷新）

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue`

**Interfaces:**
- Consumes: Task 2 `useSpcodeGitStats`；Task 4 的 `GitLogView` 新 props
- Produces: `gitStats` 实例（GitLogView prop）、`statsOpen` ref（localStorage 持久化）

- [ ] **Step 1: script 修改**

1. import 区（`useSpcodeGitShow` import 附近）追加：

```typescript
import { useSpcodeGitStats } from "@/composables/useSpcodeGitStats";
```

2. `STORAGE_KEYS` 常量（第 83-91 行）追加一个 key：

```typescript
  // 2026-07-18 git-stats: stats-panel expanded state.
  statsOpen: "astrbot.spcode.gitDiffSidebar.statsOpen",
```

3. `const gitShow = useSpcodeGitShow(selectedWorktree);`（约 623 行）之后追加：

```typescript
// 2026-07-18 git-stats: single-snapshot stats for the active
// worktree. Lifecycle mirrors gitShow (sidebar-owned, disposed on
// unmount; the ETag key embeds umo|worktree so a worktree switch
// never replays stale stats).
const gitStats = useSpcodeGitStats(selectedWorktree);

// 2026-07-18 git-stats: collapse state, persisted (mirrors searchOpen).
const statsOpen = ref<boolean>(
  safeGetItem(STORAGE_KEYS.statsOpen) === "true",
);
watch(statsOpen, (v) => safeSetItem(STORAGE_KEYS.statsOpen, String(v)), {
  flush: "post",
});

// 2026-07-18 git-stats: lazy fetch — only while the panel is expanded
// AND the History view is active. Covers both the toggle-on path and
// entering History with a persisted-open panel. Repeat refreshes are
// cheap (backend ETag short-circuit).
watch([statsOpen, viewMode], ([open, mode]) => {
  if (open && mode === "history") void gitStats.refresh();
});
```

4. `onManualRefresh` 的 else 分支（约 1242-1244 行）由：

```typescript
    } else {
      await Promise.all([composable.refresh(), worktreeRefresh]);
    }
```

改为：

```typescript
    } else {
      const tasks: Promise<void>[] = [composable.refresh(), worktreeRefresh];
      // 2026-07-18 git-stats: in History view with the stats panel
      // expanded, the header refresh also reloads stats.
      if (viewMode.value === "history" && statsOpen.value) {
        tasks.push(gitStats.refresh());
      }
      await Promise.all(tasks);
    }
```

5. 在 composable 集中 dispose 的位置（onBeforeUnmount 内，`gitShow.dispose()` 同处）追加 `gitStats.dispose();`。

- [ ] **Step 2: template 修改**

`<GitLogView>` 挂载点（约 3375-3390 行）追加三个绑定：

```html
          <GitLogView
            v-else-if="viewMode === 'history'"
            :state="gitLog.state.value"
            :has-more="logHasMore"
            :is-loading="logIsLoading"
            :git-show="gitShow"
            :git-stats="gitStats"
            :stats-open="statsOpen"
            :focused-commit-sha="focusedCommitSha"
            @update:stats-open="statsOpen = $event"
            @apply="onLogApply"
            @reset="onLogReset"
            @load-more="onLogLoadMore"
            @refresh="() => gitLog.refresh()"
            @revert="onLogRevertRequest"
          />
```

- [ ] **Step 3: 回归**

Run: `cd dashboard && pnpm test`
Expected: 全量通过

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/components/chat/GitDiffSidebar.vue
git commit -m "feat(dashboard): wire git-stats panel into GitDiffSidebar"
```

---

### Task 6: i18n 三语言 + 端到端验收

**Files:**
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json`
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json`
- Modify: `dashboard/src/i18n/locales/ru-RU/features/chat.json`

**Interfaces:**
- Consumes: Task 3 模板引用的全部 key（前缀 `spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.`）

- [ ] **Step 1: 定位插入锚点**

Run: `grep -n "\"history\"" dashboard/src/i18n/locales/en-US/features/chat.json | head -5`
在 `spcodeProjectLoad.diffSidebar.gitWorkflow.history` 对象内（与 `filter`、`relativeTime` 同级）追加 `stats` 子对象。三语言同位置。

- [ ] **Step 2: en-US 追加**

```json
      "stats": {
        "title": "Change stats",
        "summary": "{commits} commits · +{additions} −{deletions} · {files} files",
        "truncatedBadge": "last {n} commits only",
        "refresh": "Refresh stats",
        "expand": "Expand stats",
        "collapse": "Collapse stats",
        "loading": "Loading stats…",
        "error": "Failed to load stats",
        "retry": "Retry",
        "emptyRepo": "No commits yet — stats will appear after the first commit.",
        "hotFiles": "Hot files (Top 10)",
        "hotFileValue": "{commits} commits (+{additions} −{deletions})",
        "cellTooltip": "{date} · {commits} commits (+{additions} −{deletions})",
        "zeroTooltip": "{date} · no commits"
      },
```

- [ ] **Step 3: zh-CN 追加**

```json
      "stats": {
        "title": "变更统计",
        "summary": "{commits} commits · +{additions} −{deletions} · {files} 个文件",
        "truncatedBadge": "仅最近 {n} 条",
        "refresh": "刷新统计",
        "expand": "展开统计",
        "collapse": "收起统计",
        "loading": "统计加载中…",
        "error": "统计加载失败",
        "retry": "重试",
        "emptyRepo": "暂无提交 — 首次 commit 后将显示统计。",
        "hotFiles": "热点文件 (Top 10)",
        "hotFileValue": "{commits} commits (+{additions} −{deletions})",
        "cellTooltip": "{date} · {commits} commits (+{additions} −{deletions})",
        "zeroTooltip": "{date} · 无提交"
      },
```

- [ ] **Step 4: ru-RU 追加**

```json
      "stats": {
        "title": "Статистика изменений",
        "summary": "{commits} коммитов · +{additions} −{deletions} · {files} файлов",
        "truncatedBadge": "только последние {n}",
        "refresh": "Обновить статистику",
        "expand": "Развернуть статистику",
        "collapse": "Свернуть статистику",
        "loading": "Загрузка статистики…",
        "error": "Не удалось загрузить статистику",
        "retry": "Повторить",
        "emptyRepo": "Коммитов пока нет — статистика появится после первого коммита.",
        "hotFiles": "Горячие файлы (Топ 10)",
        "hotFileValue": "{commits} коммитов (+{additions} −{deletions})",
        "cellTooltip": "{date} · {commits} коммитов (+{additions} −{deletions})",
        "zeroTooltip": "{date} · нет коммитов"
      },
```

- [ ] **Step 5: JSON 合法性 + 全量测试**

Run: `cd dashboard && pnpm test`
Expected: 全量通过（i18n validator 若纳入测试则 key 三语对齐）

- [ ] **Step 6: 手动验收清单（实现者逐项执行并勾选）**

前置：AstrBot 后端运行（插件含 git-stats 端点）、dashboard dev 运行、会话已加载 spcode 项目且有 ≥20 条 commit。

1. History tab → 面板折叠态显示一行摘要（commits/+/−/files）
2. 展开 → loading → 热力图（26 周）+ 热点文件 Top10 + 汇总行渲染
3. 点击有 commit 的某天 → 下方 commit 列表过滤为该天（filter bar 的 since/until 同步显示）
4. 点击热点文件 → commit 列表过滤为该文件（path 输入框同步）
5. 点击 level-0 天 / 未来天 → 无反应
6. 折叠 → 刷新页面 → 重新进入 → 面板保持折叠（localStorage 持久化）；展开同理
7. 面板内 refresh 按钮 → 数据重拉（loading 态可见）
8. 侧栏头部 refresh 按钮（history + 展开）→ 统计与 diff 同步刷新
9. 切换 worktree → 统计数据随之变化（无陈旧 304 回放）
10. 空仓库 / 非 git 目录 → 对应空态或错误行 + 重试按钮
11. 深色模式 → 热力图色阶切换（l1-l4 变暗色组）

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/i18n/locales/en-US/features/chat.json dashboard/src/i18n/locales/zh-CN/features/chat.json dashboard/src/i18n/locales/ru-RU/features/chat.json
git commit -m "feat(dashboard): add i18n keys for git-stats panel"
```

---

## Self-Review 记录

- **Spec 覆盖**：三件套（T1/T2/T3）、面板 UI 与状态（T3）、联动（T4）、挂载/懒加载/持久化/刷新（T5）、i18n 三语（T6）、localStorage key（T5 Step 1.2）、测试（T1 spec 7 例 + T6 验收清单）✅
- **占位符**：无 TBD；唯一不确定点（customizer store 主题字段名）已在 T4 Step 2 给出 grep 核对指令与默认实现 ✅
- **类型一致**：`GitStatsFetchState`（T2）= T3 prop 类型；`filter-date` payload `{since, until}`（T3 emit ↔ T4 handler 签名一致）；`update:open`（T3）↔ `update:statsOpen`（T4）↔ `statsOpen` ref（T5）链路一致 ✅
- **依赖说明**：本计划依赖插件端点（另一仓库计划 `2026-07-18-git-stats-endpoint.md`）；T1–T5 可在端点就绪前完成（parser 测试基于契约 wire shape），T6 Step 6 验收需端点已部署 ✅
