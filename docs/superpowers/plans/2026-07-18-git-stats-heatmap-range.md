# GitStatsPanel Heatmap Range Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Git-stats heatmap's time window user-adjustable from a control inside `GitStatsPanel` itself (5 rolling-week presets + a custom `YYYY-MM-DD` range), with every change re-fetching `GET /spcode/git-stats` with `since`/`until` query params and persisting the choice to localStorage.

**Architecture:** A new `GitStatsRange` discriminated union (preset | custom) lives next to the existing parser. The panel becomes a pure renderer of `range` prop; the sidebar (`GitDiffSidebar`) owns the range state and persistence (mirroring the existing `statsOpen` pattern), and triggers `gitStats.refresh({ since, until })` on every change. The composable's ETag key extends to `umo|worktree|since|until` so 304 replay still works when the user switches back to a previous range.

**Tech Stack:** Vue 3 (`<script setup>`, computed refs), Vuetify 3 (`v-menu`, `v-list`, `v-text-field`), TypeScript, vitest, axios (via `pluginExtensionApi`), localStorage.

**Spec:** `docs/superpowers/specs/2026-07-18-git-stats-heatmap-range-design.md`

## Global Constraints

- Project uses `uv` + `pnpm`. Dashboard tests run via `pnpm vitest run <path>`; lint via `pnpm lint` (or `ruff` on Python; this plan touches dashboard only).
- Code style: `code_format` for `.py`; for dashboard, follow existing patterns (script-setup, scoped CSS via `.git-stats-*` class names, scoped custom properties for colors).
- i18n keys must be added in **all three shipped locales** (en-US, zh-CN, ru-RU) in the same commit as the consumer; otherwise lint or runtime falls back to raw key strings.
- Commit messages follow conventional-commit format.
- All Vue props/emits use `defineProps<{...}>()` / `defineEmits<{...}>()` syntax (not runtime declarations).
- All async work uses the existing AbortController pattern; never `await` without cancellation awareness.
- Persistence uses the existing `safeGetItem` / `safeSetItem` shim in `GitDiffSidebar.vue` (NOT raw `localStorage`).
- Working directory: this worktree is `feat/git-log-filter-redesign`. Stay on it; do NOT switch branches.

---

## Task 1: Range types + helpers in the parser

**Files:**
- Modify: `dashboard/src/composables/parseSpcodeGitStats.ts`
- Create or modify: `dashboard/src/composables/parseSpcodeGitStats.spec.ts` (existing file — append; do not rewrite)

**Interfaces:**
- Produces (consumed by all later tasks):
  - `type GitStatsRangePreset = "1w" | "1mo" | "3mo" | "6mo" | "1y"`
  - `type GitStatsRange = { kind: "preset"; preset: GitStatsRangePreset } | { kind: "custom"; since: string; until: string }`
  - `const STATS_PRESETS: ReadonlyArray<{ key: GitStatsRangePreset; weeks: number; days: number }>`
  - `function rangeForPreset(p: GitStatsRangePreset, today?: Date): { since: string; until: string }`

- [ ] **Step 1: Append failing tests to `parseSpcodeGitStats.spec.ts`**

Open the existing spec file. Append a `describe("GitStatsRange helpers", ...)` block at the end with these four tests (do NOT rewrite existing tests):

```ts
import { rangeForPreset, STATS_PRESETS } from "./parseSpcodeGitStats";

describe("GitStatsRange helpers", () => {
  it("STATS_PRESETS contains exactly the 5 documented presets in order", () => {
    expect(STATS_PRESETS.map((p) => p.key)).toEqual([
      "1w",
      "1mo",
      "3mo",
      "6mo",
      "1y",
    ]);
  });

  it("rangeForPreset('6mo') produces 26-week since anchored at today's Sunday", () => {
    // Fixed today = Wed 2026-07-15 (getDay() === 3)
    const today = new Date(2026, 6, 15);
    const { since, until } = rangeForPreset("6mo", today);
    expect(until).toBe("2026-07-15");
    // 26 weeks -> since = today.Sunday - 25 weeks
    // today.Sunday = 2026-07-12, minus 25*7 days = 2026-01-18
    expect(since).toBe("2026-01-18");
  });

  it("rangeForPreset('1w') produces since === until's Sunday (1-column)", () => {
    const today = new Date(2026, 1, 18); // Wed Feb 18
    const { since, until } = rangeForPreset("1w", today);
    expect(until).toBe("2026-02-18");
    expect(since).toBe("2026-02-15"); // the preceding Sunday
  });

  it("rangeForPreset always yields since <= until", () => {
    for (const p of STATS_PRESETS) {
      const { since, until } = rangeForPreset(p.key, new Date(2026, 6, 15));
      expect(since <= until).toBe(true);
    }
  });
});
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd dashboard && pnpm vitest run src/composables/parseSpcodeGitStats.spec.ts`
Expected: 4 failures with "rangeForPreset is not a function" / "STATS_PRESETS is not defined".

- [ ] **Step 3: Add types and helpers to `parseSpcodeGitStats.ts`**

At the top of the file, after the existing interface declarations but BEFORE the helpers section, add:

```ts
// ── Range types (2026-07-18: spec §"GitStatsRange type") ────────
export type GitStatsRangePreset = "1w" | "1mo" | "3mo" | "6mo" | "1y";

export type GitStatsRange =
  | { kind: "preset"; preset: GitStatsRangePreset }
  | { kind: "custom"; since: string; until: string };

export const STATS_PRESETS: ReadonlyArray<{
  key: GitStatsRangePreset;
  weeks: number;
  days: number;
}> = [
  { key: "1w",  weeks: 1,  days: 7   },
  { key: "1mo", weeks: 5,  days: 35  },
  { key: "3mo", weeks: 13, days: 91  },
  { key: "6mo", weeks: 26, days: 182 },
  { key: "1y",  weeks: 52, days: 364 },
];

function fmtYmd(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

export function rangeForPreset(
  p: GitStatsRangePreset,
  today: Date = new Date(),
): { since: string; until: string } {
  const cfg = STATS_PRESETS.find((x) => x.key === p);
  if (!cfg) throw new Error(`unknown preset: ${p}`);
  const todayStart = new Date(
    today.getFullYear(),
    today.getMonth(),
    today.getDate(),
  );
  const endSunday = new Date(todayStart);
  endSunday.setDate(endSunday.getDate() - endSunday.getDay());
  const sinceDate = new Date(endSunday);
  sinceDate.setDate(sinceDate.getDate() - (cfg.weeks - 1) * 7);
  return { since: fmtYmd(sinceDate), until: fmtYmd(todayStart) };
}
```

- [ ] **Step 4: Re-run tests to verify they pass**

Run: `cd dashboard && pnpm vitest run src/composables/parseSpcodeGitStats.spec.ts`
Expected: all tests in the file pass (existing + new).

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/composables/parseSpcodeGitStats.ts dashboard/src/composables/parseSpcodeGitStats.spec.ts
git commit -m "feat(dashboard): add GitStatsRange types and preset helper"
```

---

## Task 2: Extend `useSpcodeGitStats.refresh` with `since`/`until`

**Files:**
- Modify: `dashboard/src/composables/useSpcodeGitStats.ts`
- Create: `dashboard/src/composables/useSpcodeGitStats.spec.ts`

**Interfaces:**
- Consumes: `rangeForPreset` from Task 1 (only needed in tests, not in the composable itself).
- Produces:
  - `refresh({ forceLoading?, since?, until? })` — when `since`/`until` are passed, they go into axios `params`.
  - ETag key signature changes to `etagKey(umo, worktree, since, until)` — internal to the composable.

- [ ] **Step 1: Write the failing test file**

Create `dashboard/src/composables/useSpcodeGitStats.spec.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ref } from "vue";
import { useSpcodeGitStats } from "./useSpcodeGitStats";
import { useSpcodeProjectStatus } from "./useSpcodeProjectStatus";
import { pluginExtensionApi } from "@/api/v1";

vi.mock("@/api/v1", () => ({
  pluginExtensionApi: { get: vi.fn() },
}));
vi.mock("./useSpcodeProjectStatus", () => ({
  useSpcodeProjectStatus: () => ({
    status: ref({ umo: "umo-1" }),
  }),
}));

function makeAxiosResponse(status: number, data: unknown, etag?: string) {
  return {
    status,
    data,
    headers: etag ? { etag } : {},
  };
}

function okEnvelope(days: unknown[] = []) {
  return {
    status: "ok",
    data: {
      success: true,
      reason: null,
      loaded: true,
      stderr: "",
      elapsed_ms: 10,
      umo: "umo-1",
      worktree: null,
      directory: "/x",
      ref: "HEAD",
      resolved_sha: "deadbeef",
      days,
      hot_files: [],
      totals: { commits: 0, additions: 0, deletions: 0, files_changed: 0 },
      range: { first: null, last: null },
      truncated: false,
      max_commits: 5000,
    },
  };
}

describe("useSpcodeGitStats refresh params and ETag", () => {
  beforeEach(() => {
    vi.mocked(pluginExtensionApi.get).mockReset();
  });

  it("refresh() without since/until does NOT pass them in params", async () => {
    vi.mocked(pluginExtensionApi.get).mockResolvedValueOnce(
      makeAxiosResponse(200, okEnvelope()),
    );
    const { refresh } = useSpcodeGitStats();
    await refresh();
    const call = vi.mocked(pluginExtensionApi.get).mock.calls[0];
    expect(call[1]?.params).toEqual({ umo: "umo-1" });
  });

  it("refresh({since,until}) forwards them in params", async () => {
    vi.mocked(pluginExtensionApi.get).mockResolvedValueOnce(
      makeAxiosResponse(200, okEnvelope()),
    );
    const { refresh } = useSpcodeGitStats();
    await refresh({ since: "2025-01-01", until: "2025-12-31" });
    const call = vi.mocked(pluginExtensionApi.get).mock.calls[0];
    expect(call[1]?.params).toEqual({
      umo: "umo-1",
      since: "2025-01-01",
      until: "2025-12-31",
    });
  });

  it("different since/until produces a new ETag bucket (separate 304 cache)", async () => {
    // First range: 200 + etag
    vi.mocked(pluginExtensionApi.get).mockResolvedValueOnce(
      makeAxiosResponse(200, okEnvelope(), "etag-A"),
    );
    // Second range (different since): should NOT send If-None-Match
    vi.mocked(pluginExtensionApi.get).mockResolvedValueOnce(
      makeAxiosResponse(200, okEnvelope(), "etag-B"),
    );

    const { refresh } = useSpcodeGitStats();
    await refresh({ since: "2025-01-01", until: "2025-06-30" });
    await refresh({ since: "2025-07-01", until: "2025-12-31" });

    const secondCall = vi.mocked(pluginExtensionApi.get).mock.calls[1];
    expect(secondCall[1]?.headers).toEqual({});
  });

  it("same since/until on second call sends If-None-Match and replays cache on 304", async () => {
    vi.mocked(pluginExtensionApi.get)
      .mockResolvedValueOnce(makeAxiosResponse(200, okEnvelope(), "etag-X"))
      .mockResolvedValueOnce(makeAxiosResponse(304, null));

    const { refresh, state } = useSpcodeGitStats();
    await refresh({ since: "2025-01-01", until: "2025-12-31" });
    const firstSnapshot = (state.value as { kind: "ok"; snapshot: unknown })
      .snapshot;

    await refresh({ since: "2025-01-01", until: "2025-12-31" });
    expect(state.value.kind).toBe("ok");
    if (state.value.kind === "ok") {
      expect(state.value.snapshot).toBe(firstSnapshot);
      expect(state.value.notModified).toBe(true);
    }
    const secondCall = vi.mocked(pluginExtensionApi.get).mock.calls[1];
    expect(secondCall[1]?.headers).toEqual({ "If-None-Match": "etag-X" });
  });

  it("second refresh aborts the first when called while first is pending", async () => {
    let resolveFirst!: (v: unknown) => void;
    const first = new Promise((r) => {
      resolveFirst = r;
    });
    vi.mocked(pluginExtensionApi.get)
      .mockReturnValueOnce(first as never)
      .mockResolvedValueOnce(makeAxiosResponse(200, okEnvelope(), "etag-Z"));

    const { refresh } = useSpcodeGitStats();
    const p1 = refresh({ since: "2025-01-01", until: "2025-06-30" });
    const p2 = refresh({ since: "2025-07-01", until: "2025-12-31" });

    const firstCallSig = vi.mocked(pluginExtensionApi.get).mock.calls[0][1];
    resolveFirst(makeAxiosResponse(200, okEnvelope()));
    await p1;
    await p2;

    expect(firstCallSig?.signal?.aborted).toBe(true);
  });
});
```

- [ ] **Step 2: Run the new spec to verify all 5 fail**

Run: `cd dashboard && pnpm vitest run src/composables/useSpcodeGitStats.spec.ts`
Expected: 5 failures, mostly around `since`/`until` not being forwarded.

- [ ] **Step 3: Modify the composable**

In `dashboard/src/composables/useSpcodeGitStats.ts`, change two things.

**Change A — `etagKey` signature and call sites.** Replace:

```ts
function etagKey(umo: string, worktree: string | null): string {
  return [umo, worktree ?? ""].join("|");
}
```

with:

```ts
function etagKey(
  umo: string,
  worktree: string | null,
  since: string,
  until: string,
): string {
  return [umo, worktree ?? "", since, until].join("|");
}
```

**Change B — `refresh` signature and body.** Replace:

```ts
async function refresh(options?: { forceLoading?: boolean }): Promise<void> {
  if (!isMounted) return;
  const umo = spcodeStatus.status.value.umo;
  if (!umo) {
    state.value = { kind: "error", reason: "no_project_loaded" };
    return;
  }
  abortController?.abort();
  abortController = new AbortController();
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
      ...
```

with:

```ts
async function refresh(options?: {
  forceLoading?: boolean;
  since?: string;
  until?: string;
}): Promise<void> {
  if (!isMounted) return;
  const umo = spcodeStatus.status.value.umo;
  if (!umo) {
    state.value = { kind: "error", reason: "no_project_loaded" };
    return;
  }
  abortController?.abort();
  abortController = new AbortController();
  if (state.value.kind !== "ok" || options?.forceLoading) {
    state.value = { kind: "loading" };
  }
  const worktree = toValue(worktreeRef);
  const since = options?.since ?? "";
  const until = options?.until ?? "";
  const key = etagKey(umo, worktree, since, until);
  const etag = etagMap.get(key);
  try {
    const resp = await pluginExtensionApi.get<unknown>("spcode/git-stats", {
      params: {
        umo,
        ...(worktree ? { worktree } : {}),
        ...(since ? { since } : {}),
        ...(until ? { until } : {}),
      },
      ...
```

(No other lines in the file change.)

- [ ] **Step 4: Re-run the spec to verify all 5 pass**

Run: `cd dashboard && pnpm vitest run src/composables/useSpcodeGitStats.spec.ts`
Expected: 5 passing, 0 failing.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/composables/useSpcodeGitStats.ts dashboard/src/composables/useSpcodeGitStats.spec.ts
git commit -m "feat(dashboard): support since/until in useSpcodeGitStats"
```

---

## Task 3: i18n keys for the range UI

**Files:**
- Modify: `dashboard/src/locales/en-US/features/chat.ts`
- Modify: `dashboard/src/locales/zh-CN/features/chat.ts`
- Modify: `dashboard/src/locales/ru-RU/features/chat.ts`
- Possibly modify the type-only module under `dashboard/src/locales/` that declares the i18n key tree (search for `spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats` to find the right insertion point)

**Interfaces:**
- Produces (consumed by Task 4):
  - `stats.range.1w`, `stats.range.1mo`, `stats.range.3mo`, `stats.range.6mo`, `stats.range.1y`
  - `stats.range.custom`, `stats.range.since`, `stats.range.until`, `stats.range.apply`
- Also: `stats.truncatedBadge` value updated in all 3 locales.

- [ ] **Step 1: Locate the i18n type declaration**

Run: `grep -rn "truncatedBadge" dashboard/src/locales/`

The output points to (a) the type/declaration file with the key tree, and (b) three locale value files. Open the type file and find where the `stats` block ends. Add the 9 new keys there (under `stats.range.*`).

- [ ] **Step 2: Update `en-US/features/chat.ts`**

Find `stats: { ... truncatedBadge: "...{n} 次提交" }` (English equivalent; the value will be `"Last {n} commits"` or similar — confirm by reading).

Replace the `truncatedBadge` value with `"Only the last {n} commits are shown"`.

Add inside the `stats` block:

```ts
range: {
  "1w":   "Last week",
  "1mo":  "Last month",
  "3mo":  "Last 3 months",
  "6mo":  "Last 6 months",
  "1y":   "Last year",
  custom: "Custom range",
  since:  "From",
  until:  "To",
  apply:  "Apply",
},
```

- [ ] **Step 3: Update `zh-CN/features/chat.ts`**

Replace `truncatedBadge` with `"仅显示最近 {n} 次提交"`.

Add:

```ts
range: {
  "1w":   "最近一周",
  "1mo":  "一个月",
  "3mo":  "三个月",
  "6mo":  "六个月",
  "1y":   "一年",
  custom: "自定义范围",
  since:  "起始",
  until:  "结束",
  apply:  "应用",
},
```

- [ ] **Step 4: Update `ru-RU/features/chat.ts`**

Replace `truncatedBadge` with `"Показаны только последние {n} коммитов"`.

Add:

```ts
range: {
  "1w":   "Последняя неделя",
  "1mo":  "Последний месяц",
  "3mo":  "Последние 3 месяца",
  "6mo":  "Последние 6 месяцев",
  "1y":   "Последний год",
  custom: "Произвольный диапазон",
  since:  "С",
  until:  "По",
  apply:  "Применить",
},
```

- [ ] **Step 5: Run the linter / type-check to verify key-tree consistency**

Run: `cd dashboard && pnpm lint` (or `pnpm tsc --noEmit` if lint is too slow).
Expected: no errors related to `stats.range.*` keys. If the i18n type-checker complains about missing keys, re-open the type declaration file and add the 9 keys there.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/locales/
git commit -m "feat(dashboard): i18n for git-stats heatmap range UI"
```

---

## Task 4: Add popover UI + range prop to `GitStatsPanel.vue`

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/GitStatsPanel.vue`

**Interfaces:**
- Consumes:
  - `GitStatsRange`, `STATS_PRESETS` from `parseSpcodeGitStats` (Task 1)
  - i18n keys `stats.range.*` from Task 3
- Produces:
  - New prop: `range: GitStatsRange`
  - New emit: `(e: "update:range", v: GitStatsRange): void`
  - Local refs `customSince`, `customUntil`, computed `todayYmd`, `isCustomValid`, `rangeLabel`
  - Methods `selectPreset(p)`, `applyCustom()`
  - Header `<v-menu>` block (between the truncated badge and the refresh button)

- [ ] **Step 1: Add the `range` prop + `update:range` emit**

In `<script setup>`, find:

```ts
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
```

Add the `range` prop and the `update:range` emit:

```ts
import type {
  GitStatsRange,
  GitStatsRangePreset,
} from "@/composables/parseSpcodeGitStats";
import { STATS_PRESETS } from "@/composables/parseSpcodeGitStats";

const props = defineProps<{
  state: GitStatsFetchState;
  open: boolean;
  isDark?: boolean;
  range: GitStatsRange;
}>();
const emit = defineEmits<{
  (e: "update:open", v: boolean): void;
  (e: "update:range", v: GitStatsRange): void;
  (e: "refresh"): void;
  (e: "filter-date", p: { since: string; until: string }): void;
  (e: "filter-path", path: string): void;
}>();
```

- [ ] **Step 2: Add local state + helpers (above the `grid` computed)**

```ts
const customSince = ref<string>("");
const customUntil = ref<string>("");
const todayYmd = computed(() => fmtDate(new Date()));
const isCustomValid = computed(() => {
  if (!customSince.value || !customUntil.value) return false;
  return customSince.value <= customUntil.value;
});
const rangeLabel = computed(() => {
  if (props.range.kind === "preset") {
    return tm(
      `spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.range.${props.range.preset}`,
    );
  }
  return `${props.range.since} → ${props.range.until}`;
});
function isPresetActive(p: GitStatsRangePreset): boolean {
  return props.range.kind === "preset" && props.range.preset === p;
}
function selectPreset(p: GitStatsRangePreset): void {
  emit("update:range", { kind: "preset", preset: p });
}
function applyCustom(): void {
  if (!isCustomValid.value) return;
  emit("update:range", {
    kind: "custom",
    since: customSince.value,
    until: customUntil.value,
  });
}
```

- [ ] **Step 3: Add a watch to pre-fill custom inputs when the popover opens**

Below the helpers, add:

```ts
watch(
  () => props.range,
  (r) => {
    if (r.kind === "custom") {
      customSince.value = r.since;
      customUntil.value = r.until;
    } else {
      // For presets, clear the inputs so user starts fresh
      customSince.value = "";
      customUntil.value = "";
    }
  },
  { immediate: true },
);
```

- [ ] **Step 4: Insert the header `<v-menu>` button**

In the template, locate the existing refresh button:

```vue
<v-btn
  icon
  size="x-small"
  variant="text"
  :loading="isLoading && open"
  :title="..."
  @click="emit('refresh')"
>
  <v-icon size="14">mdi-restart</v-icon>
</v-btn>
```

Insert this block IMMEDIATELY BEFORE the refresh button:

```vue
<v-menu :close-on-content-click="false" location="bottom end">
  <template #activator="{ props: tipProps }">
    <v-btn
      variant="text"
      size="x-small"
      class="git-stats-range-trigger"
      v-bind="tipProps"
    >
      <v-icon size="13" start>mdi-calendar-range</v-icon>
      <span class="git-stats-range-trigger-label">{{ rangeLabel }}</span>
      <v-icon size="13" end>mdi-chevron-down</v-icon>
    </v-btn>
  </template>
  <v-card class="git-stats-range-menu" min-width="240">
    <v-list density="compact" class="git-stats-range-presets">
      <v-list-item
        v-for="p in STATS_PRESETS"
        :key="p.key"
        :active="isPresetActive(p.key)"
        @click="selectPreset(p.key)"
      >
        <v-list-item-title>{{
          tm(
            `spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.range.${p.key}`,
          )
        }}</v-list-item-title>
        <template #append>
          <span class="git-stats-range-days">{{ p.days }}d</span>
        </template>
      </v-list-item>
    </v-list>
    <v-divider />
    <div class="git-stats-range-custom">
      <div class="git-stats-range-custom-title">
        {{
          tm(
            "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.range.custom",
          )
        }}
      </div>
      <v-text-field
        v-model="customSince"
        :label="
          tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.range.since')
        "
        type="date"
        density="compact"
        variant="outlined"
        hide-details
        :max="customUntil || undefined"
      />
      <v-text-field
        v-model="customUntil"
        :label="
          tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.range.until')
        "
        type="date"
        density="compact"
        variant="outlined"
        hide-details
        :min="customSince || undefined"
        :max="todayYmd"
      />
      <v-btn
        size="small"
        variant="tonal"
        :disabled="!isCustomValid"
        block
        @click="applyCustom"
      >
        {{
          tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.range.apply")
        }}
      </v-btn>
    </div>
  </v-card>
</v-menu>
```

- [ ] **Step 5: Add scoped CSS**

Append to the `<style scoped>` block:

```css
.git-stats-range-trigger {
  text-transform: none;
  letter-spacing: normal;
  font-size: 12px;
  padding: 0 6px;
  min-height: 24px;
}
.git-stats-range-trigger-label {
  max-width: 110px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.git-stats-range-menu {
  padding: 4px 0;
}
.git-stats-range-presets .v-list-item__append {
  font-size: 11px;
  opacity: 0.6;
  font-variant-numeric: tabular-nums;
}
.git-stats-range-custom {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px 12px;
}
.git-stats-range-custom-title {
  font-size: 11px;
  font-weight: 600;
  opacity: 0.7;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
```

- [ ] **Step 6: Type-check the component**

Run: `cd dashboard && pnpm tsc --noEmit` (or whatever the project's check is; try `pnpm lint` too).
Expected: no errors. If `pnpm tsc` flags missing types (e.g. `range` not destructured from `props`), re-check Step 1.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/components/chat/message_list_comps/GitStatsPanel.vue
git commit -m "feat(dashboard): add heatmap range popover to GitStatsPanel"
```

---

## Task 5: Parameterize the `grid` computed + add `parseYmd`

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/GitStatsPanel.vue` (same file as Task 4)

**Interfaces:**
- Consumes: `range` prop from Task 4.
- Produces: the `grid` computed reads `props.range` (no longer the `WEEKS` constant).

- [ ] **Step 1: Add the `parseYmd` helper next to `fmtDate`**

After the existing `fmtDate` function, add:

```ts
function parseYmd(s: string): Date | null {
  // Strict YYYY-MM-DD, anchored at local midnight (NOT UTC) so the
  // weekday math in the grid (anchor.getDay()) matches the user's
  // calendar. `new Date("2025-01-01")` alone would parse as UTC and
  // shift by the local TZ offset.
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]) - 1;
  const d = Number(m[3]);
  if (mo < 0 || mo > 11) return null;
  return new Date(y, mo, d);
}
```

- [ ] **Step 2: Replace `const WEEKS = 26;` and the `grid` computed body**

Find:

```ts
// ── Heatmap grid (26 week-columns × 7 rows, local time) ────────────
const WEEKS = 26;

interface DayCell {
  ...
}

function levelOf(commits: number): number {
  ...
}

function fmtDate(d: Date): string {
  ...
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
```

Replace with:

```ts
// ── Heatmap grid (N week-columns × 7 rows, range-driven) ──────────
// Number of columns + anchor derive from props.range:
//   preset   → STATS_PRESETS.weeks, anchored at today's Sunday
//   custom   → ceil((until - since) / 7d) + 1, anchored at until's Sunday
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

  let weeks: number;
  let anchor: Date;
  if (props.range.kind === "preset") {
    const cfg = STATS_PRESETS.find((p) => p.key === props.range.preset);
    if (!cfg) return [];
    weeks = cfg.weeks;
    anchor = new Date(todayStart);
    anchor.setDate(anchor.getDate() - anchor.getDay()); // today's Sunday
  } else {
    const sinceDate = parseYmd(props.range.since);
    const untilDate = parseYmd(props.range.until);
    if (!sinceDate || !untilDate) return [];
    weeks = Math.max(
      1,
      Math.ceil(
        (untilDate.getTime() - sinceDate.getTime()) / 86400000 / 7,
      ) + 1,
    );
    anchor = new Date(untilDate);
    anchor.setDate(anchor.getDate() - anchor.getDay()); // until's Sunday
  }

  const cols: DayCell[][] = [];
  for (let w = weeks - 1; w >= 0; w--) {
    const col: DayCell[] = [];
    for (let dow = 0; dow < 7; dow++) {
      const d = new Date(anchor);
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
```

- [ ] **Step 3: Replace `WEEKS` references in the template**

Find these in the template:

```vue
<div
  class="git-stats-months"
  :style="{ gridTemplateColumns: `repeat(${WEEKS}, 1fr)` }"
>
```

Replace `WEEKS` with `grid.length` (the grid computed's column count). This makes the months row align with the actual rendered columns without needing a separate `weeks` ref:

```vue
<div
  class="git-stats-months"
  :style="{ gridTemplateColumns: `repeat(${grid.length}, 1fr)` }"
>
```

(No other `WEEKS` references should remain; search the file to confirm.)

- [ ] **Step 4: Run type-check + tests**

Run: `cd dashboard && pnpm tsc --noEmit && pnpm vitest run src/composables/parseSpcodeGitStats.spec.ts`
Expected: no type errors; the 4 range tests still pass.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/chat/message_list_comps/GitStatsPanel.vue
git commit -m "feat(dashboard): drive heatmap grid width from range prop"
```

---

## Task 6: Plumb `range` through `GitLogView.vue`

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/GitLogView.vue`

**Interfaces:**
- Consumes: `GitStatsRange` from `parseSpcodeGitStats` (re-exported by the panel file is fine; otherwise import directly).
- Produces:
  - New prop on the `<GitStatsPanel>` child: `:range="range"`
  - New event listener: `@update:range="emit('update:range', $event)"`
  - New prop on `GitLogView` itself: `range: GitStatsRange`
  - New emit on `GitLogView`: `(e: "update:range", v: GitStatsRange): void`

- [ ] **Step 1: Inspect the existing `GitLogView` props/emits block**

Open `dashboard/src/components/chat/message_list_comps/GitLogView.vue`. Find:

```ts
const props = defineProps<{...}>();
const emit = defineEmits<{...}>();
```

Find the `<GitStatsPanel ... />` JSX/template usage. Note what props it currently passes.

- [ ] **Step 2: Add `range` prop + `update:range` emit to `GitLogView`**

In the `defineProps<{...}>()` block, add `range: GitStatsRange;`. In the `defineEmits<{...}>()` block, add `(e: "update:range", v: GitStatsRange): void;`.

At the top of `<script setup>`, add the import:

```ts
import type { GitStatsRange } from "@/composables/parseSpcodeGitStats";
```

- [ ] **Step 3: Forward the prop and emit on the `<GitStatsPanel>` element**

Find the `<GitStatsPanel ... />` tag. Add two attributes:

```vue
<GitStatsPanel
  ...
  :range="props.range"
  @update:range="(v) => emit('update:range', v)"
/>
```

(No other behavior changes in `GitLogView`.)

- [ ] **Step 4: Type-check**

Run: `cd dashboard && pnpm tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/chat/message_list_comps/GitLogView.vue
git commit -m "refactor(dashboard): pass range prop through GitLogView"
```

---

## Task 7: `GitDiffSidebar.vue` owns range state, persistence, refresh wiring

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue`

**Interfaces:**
- Consumes: `GitStatsRange`, `rangeForPreset` from Task 1; `useSpcodeGitStats.refresh({since, until})` from Task 2.
- Produces:
  - New `STORAGE_KEYS.gitStatsRange: "astrbot.spcode.gitDiffSidebar.statsRange"`
  - New helper `loadGitStatsRange(): GitStatsRange`
  - New ref `statsRange = ref<GitStatsRange>(loadGitStatsRange())`
  - New `watch(statsRange, ...)` that: persists to localStorage + computes `since`/`until` + calls `gitStats.refresh({ since, until })`
  - The existing `onManualRefresh` / worktree-switch handler also forwards `{ since, until }` based on the current `statsRange`
  - `<GitLogView ... :range="statsRange" @update:range="onStatsRangeUpdate" />`

- [ ] **Step 1: Add the storage key**

In the `STORAGE_KEYS` constant, add a new entry alongside `gitStatsOpen`:

```ts
gitStatsRange: "astrbot.spcode.gitDiffSidebar.statsRange",
```

- [ ] **Step 2: Add the loader**

Next to the existing `loadGitStatsOpen()` function (around line 130), add:

```ts
function loadGitStatsRange(): GitStatsRange {
  const raw = safeGetItem(STORAGE_KEYS.gitStatsRange);
  if (!raw) return { kind: "preset", preset: "6mo" };
  try {
    const v = JSON.parse(raw);
    if (
      v?.kind === "preset" &&
      STATS_PRESETS.some((p) => p.key === v.preset)
    ) {
      return v;
    }
    if (
      v?.kind === "custom" &&
      /^\d{4}-\d{2}-\d{2}$/.test(v.since) &&
      /^\d{4}-\d{2}-\d{2}$/.test(v.until) &&
      v.since <= v.until
    ) {
      return v;
    }
  } catch {
    /* fall through */
  }
  return { kind: "preset", preset: "6mo" };
}
```

Add to the imports at the top of `<script setup>`:

```ts
import {
  STATS_PRESETS,
  rangeForPreset,
  type GitStatsRange,
} from "@/composables/parseSpcodeGitStats";
```

- [ ] **Step 3: Add the state ref + update handler**

Next to the existing `statsOpen` ref (around line 261), add:

```ts
const statsRange = ref<GitStatsRange>(loadGitStatsRange());
```

Add an update handler near the other emit-bound handlers:

```ts
function onStatsRangeUpdate(v: GitStatsRange): void {
  statsRange.value = v;
}
```

- [ ] **Step 4: Add a watcher that persists + re-fetches on range change**

Below the existing `watch(statsOpen, ...)` block, add:

```ts
watch(
  statsRange,
  (v) => {
    safeSetItem(STORAGE_KEYS.gitStatsRange, JSON.stringify(v));
    const { since, until } =
      v.kind === "preset" ? rangeForPreset(v.preset) : { since: v.since, until: v.until };
    void gitStats.refresh({ since, until });
  },
  { flush: "post" },
);
```

- [ ] **Step 5: Update the existing `gitStats.refresh()` call sites to pass `since`/`until`**

The sidebar already calls `gitStats.refresh()` in two places: `onManualRefresh` and the worktree-switch watcher. Find each, and replace with:

```ts
const { since, until } =
  statsRange.value.kind === "preset"
    ? rangeForPreset(statsRange.value.preset)
    : { since: statsRange.value.since, until: statsRange.value.until };
void gitStats.refresh({ since, until });
```

(Use the inline ternary above. Do NOT extract a helper — the two call sites plus the watcher in Step 4 make 3; that's already the threshold but extracting a 3-liner violates KISS. Leave inline.)

- [ ] **Step 6: Pass the prop on `<GitLogView>`**

Find the `<GitLogView ... />` JSX/template usage in the sidebar. Add `:range="statsRange" @update:range="onStatsRangeUpdate"`.

- [ ] **Step 7: Type-check**

Run: `cd dashboard && pnpm tsc --noEmit`
Expected: no errors. If `pnpm tsc` complains about `STATS_PRESETS` / `rangeForPreset` not being exported, re-check the import from Step 2.

- [ ] **Step 8: Run all dashboard tests to confirm no regression**

Run: `cd dashboard && pnpm vitest run`
Expected: all tests pass (existing + Task 1 + Task 2).

- [ ] **Step 9: Commit**

```bash
git add dashboard/src/components/chat/GitDiffSidebar.vue
git commit -m "feat(dashboard): own statsRange state in sidebar with persistence"
```

---

## Self-Review

**1. Spec coverage:**

| Spec section | Implementing task |
|---|---|
| §"Goal" — presets + custom + re-fetch | Tasks 3 (i18n), 4 (UI), 5 (grid), 7 (sidebar) |
| §"Decisions" Q1 (popover UI) | Task 4 |
| §"Decisions" Q2 (re-fetch) | Tasks 2, 7 |
| §"Decisions" Q3 (5 presets) | Tasks 1 (STATS_PRESETS), 4 (UI list) |
| §"Decisions" Q4 (1w = 1 col, current calendar week) | Task 1 (`rangeForPreset`) |
| §"Decisions" Q5 (localStorage default "6mo") | Task 7 (`loadGitStatsRange`) |
| §"Decisions" Q6 (anchor differs by kind) | Task 5 (grid computed) |
| §"Decisions" Q7 (decoupled from commit-log filter) | No task needed (already true) |
| §"Scope" must — types | Task 1 |
| §"Scope" must — popover button | Task 4 |
| §"Scope" must — list + divider + 2 date inputs + apply | Task 4 |
| §"Scope" must — parameterized grid | Task 5 |
| §"Scope" must — prop / emit convention | Tasks 4, 6 |
| §"Scope" must — pass-through in GitLogView | Task 6 |
| §"Scope" must — sidebar state + watcher + new STORAGE_KEY | Task 7 |
| §"Scope" must — composable refresh signature + ETag key | Task 2 |
| §"Scope" must — 9 i18n keys × 3 locales + truncatedBadge update | Task 3 |
| §"Scope" must — vitest for composable | Task 2 |
| §"Scope" must-not — coupled to localFilter, new ReasonCodes, all-time preset, hot-files time filter | No tasks (deliberately excluded) |
| §"Open issue" — hot files stays "all time" | Tasks 4-7 leave hot-files untouched |
| §"Files" — modify parseSpcodeGitStats | Task 1 |
| §"Files" — modify useSpcodeGitStats | Task 2 |
| §"Files" — modify GitStatsPanel | Tasks 4, 5 |
| §"Files" — modify GitLogView | Task 6 |
| §"Files" — modify GitDiffSidebar | Task 7 |
| §"Files" — modify 3 locale files | Task 3 |
| §"Testing" — composable unit tests | Task 2 |
| §"Testing" — parser range helper tests | Task 1 |
| §"Testing" — manual acceptance (10 items) | Final acceptance step below |

**2. Placeholder scan:** No "TBD", no "implement later", no "similar to" references — every step has the actual code.

**3. Type consistency:**
- `GitStatsRange`, `GitStatsRangePreset` defined once in Task 1, imported everywhere.
- `rangeForPreset` signature: `(p: GitStatsRangePreset, today?: Date) => { since, until }` — used identically in Tasks 1 (test), 7 (sidebar).
- `STATS_PRESETS` element shape `{ key, weeks, days }` — used in Tasks 1 (test), 4 (template `v-for`), 7 (validation in loader).
- `useSpcodeGitStats.refresh({ forceLoading?, since?, until? })` — used in Tasks 2 (test), 7 (sidebar).
- `loadGitStatsRange(): GitStatsRange` — defined once in Task 7, no other caller.

No naming inconsistencies found.

---

## Final Acceptance

After all 7 tasks commit cleanly on top of `feat/git-log-filter-redesign`:

- [ ] **Manual: default = "六个月" on first load**

Run: `pnpm dev`, open a repo with the heatmap panel, verify the grid is 26 columns and the header trigger reads "六个月".

- [ ] **Manual: preset switch**

Click the header trigger, pick "最近一周". Grid collapses to 1 column. Network panel shows `GET /spcode/git-stats?since=...&until=...`.

- [ ] **Manual: custom range**

Open the menu, scroll to the custom section, pick `2024-01-01` and `2024-12-31`, click "应用". Grid renders ~73 columns anchored at the Sunday of 2024-12-31.

- [ ] **Manual: persistence**

Set range to "一年". Reload the page. Header still reads "一年" and grid stays 52 columns.

- [ ] **Manual: 304 replay**

Open Network panel. Pick "一年" (200 OK with ETag). Pick "六个月" (200 OK with new ETag). Pick "一年" again → expect `304 Not Modified` with `If-None-Match` header.

- [ ] **Manual: truncated badge**

On a repo with >5000 commits in the past year, pick "一年". Verify the badge appears with text "仅显示最近 5000 次提交" (or locale equivalent).

- [ ] **Manual: worktree switch preserves range**

Switch to a different worktree. Range state stays; data reloads.

- [ ] **Manual: corrupted localStorage**

In DevTools, run `localStorage.setItem("astrbot.spcode.gitDiffSidebar.statsRange", "{not json")`. Reload. Range falls back to "六个月" silently.

- [ ] **Manual: commit-log filter remains orthogonal**

After setting the heatmap to "一年", click a day in the grid. Verify the commit list below filters to that single day (existing behavior unchanged) and the heatmap range stays "一年".

- [ ] **Run full dashboard test suite one more time**

Run: `cd dashboard && pnpm vitest run`
Expected: all tests pass; no regressions in existing specs.