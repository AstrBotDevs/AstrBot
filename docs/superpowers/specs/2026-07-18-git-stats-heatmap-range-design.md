# GitStatsPanel: Adjustable Heatmap Time Range

**Date:** 2026-07-18
**Status:** Draft (pending user review)
**Author:** elecvoid243
**Related:**
- `docs/superpowers/specs/2026-07-18-git-stats-heatmap-design.md` — the panel itself, backend endpoint contract, current 26-week default
- `docs/superpowers/specs/2026-06-24-chatui-git-workflow-controls-design.md` — git workflow / GitLogView
- `docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md` — sidebar shell, `STORAGE_KEYS`

## Goal

The Git-stats heatmap (top of the History sub-tab in `GitDiffSidebar`) must let the user **adjust the time window** that is rendered, from a control placed **inside** the `GitStatsPanel` itself (so the panel stays self-contained and no plumbing changes are needed in `GitDiffSidebar` beyond what already exists for `statsOpen`).

Two control surfaces, both reachable from one header button:

1. **Five preset chips**: 最近一周 / 一个月 / 三个月 / 六个月 / 一年 (rolling windows anchored at today, integer-week multiples).
2. **A custom date range** (two `YYYY-MM-DD` inputs) for "I want a specific window".

Every change **re-fetches** `GET /spcode/git-stats` with new `since`/`until` query parameters (the endpoint already supports them — see backend spec). This avoids the silent data-loss trap of a frontend-only range expansion that walks past what the backend returned.

The choice persists across reloads via localStorage, defaulting to "六个月" so existing users see no change.

## Background

The current panel hard-codes `const WEEKS = 26` in `GitStatsPanel.vue:92`. The grid is computed by walking back 26 weeks from today's Sunday and bucketing each day into a 5-level color. The endpoint `GET /spcode/git-stats` already accepts `since`/`until`/`max_commits=5000` (see heatmap spec §3), but the frontend does not pass `since`/`until` today — it gets the whole truncated history and discards everything outside the last 26 weeks client-side.

That is fine while `WEEKS` is fixed. Once the user can ask for a wider window, **the frontend-only approach would silently lose data**: e.g. on a 8000-commit repo, asking for "1 year" with a 5000-commit backend cap would render dozens of empty cells on the left with no way to tell "no activity" from "we didn't fetch this far back".

The fix is to push the window into the backend query. The truncated badge already exists and re-uses its meaning cleanly: it now reads as "this range exceeds the 5000-commit window; the oldest commits are not represented".

## Decisions (confirmed with user)

| # | Question | Decision |
|---|----------|----------|
| Q1 | Control UI | **Preset chips + custom date inputs**, both reachable from one `v-menu` triggered by a header button. NOT a chip row above the heatmap (sidebar is too narrow). |
| Q2 | Data fetch strategy | **Re-fetch** with `since`/`until` on every range change. NOT frontend-only crop. 304 replay still works because ETag keys by `umo\|worktree\|since\|until`. |
| Q3 | Preset list | 最近一周 / 一个月 / 三个月 / 六个月 / 一年 (rolling windows, integer weeks, anchored at today) |
| Q4 | "最近一周" semantics | Rolling **7 days** from today, rendered as **1 column** (current calendar week). NOT calendar-week-of-today (which would shift on weekdays). |
| Q5 | Persistence | localStorage, key under existing `astrbot.spcode.gitDiffSidebar.*` namespace, default `"6mo"`. |
| Q6 | Custom range anchor | For presets, anchor grid at today's Sunday. For custom range, anchor grid at `until`'s Sunday. |
| Q7 | Couple with commit-log filter? | No. Heatmap range and `GitLogView` `localFilter` are orthogonal. A day click still applies a single-day filter to the commit list, independent of the heatmap window. |

## Scope

The feature must:

- Add a `GitStatsRange` discriminated-union type (preset | custom) co-located with the existing parser;
- Add a header `v-menu` button in `GitStatsPanel.vue` showing the current range label (e.g. "最近 6 个月") with a chevron;
- Inside the menu: a `v-list` of 5 presets (highlight the active one), a divider, then a custom-range section with two `v-text-field type="date"` inputs and an "应用" button;
- Convert `GitStatsPanel`'s `grid` computed from a hard-coded `WEEKS` constant into a parameterized computation that derives both the number of week-columns and the anchor Sunday from the `range` prop;
- Plumb `range` as a prop and `update:range` as an emit, following the same prop-emit convention the panel already uses for `open` / `update:open`;
- `GitLogView` becomes a transparent pass-through for the new prop/emit (no logic);
- `GitDiffSidebar` owns the range state (consistent with where `statsOpen` and `gitStats` composable already live), persists it via the existing `safeGetItem`/`safeSetItem` pattern with a new `STORAGE_KEYS.gitStatsRange` entry, and triggers `gitStats.refresh({ since, until })` on range change (and on worktree/UMO switch — same lifecycle that already invalidates stats);
- Extend `useSpcodeGitStats.refresh({ since?, until? })` to pass `since`/`until` as query params, and extend the ETag key from `umo|worktree` to `umo|worktree|since|until` so 304 replay still works when switching back to a previous range;
- Add i18n keys under `spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.range.*` for all three shipped locales (en-US, zh-CN, ru-RU) covering: 5 preset labels, custom-range section title, "起始" / "结束" labels, "应用" button (no `range.fallback` key — corrupted localStorage falls back to `"6mo"` silently per the Edge-cases table);
- Update the `truncated` badge copy from `"最近 N 次提交"` to `"仅显示最近 N 次提交"` (all 3 locales) so its meaning matches the new context ("range was capped" rather than "history was capped"). Same i18n key, same params — a string-content change only.
- Add a vitest spec for `useSpcodeGitStats` covering: since/until forwarded to axios `params`, ETag key change on range change, 304 replay within an ETag bucket, refresh-on-range-change, abort-on-pending-then-new-range.

The feature must **not**:

- Couple the heatmap range with `GitLogView`'s `localFilter` (they remain orthogonal);
- Add new ReasonCodes (reuse existing `spcodeProjectLoad.diffSidebar.gitWorkflow.error.reason.*`);
- Add any chart library;
- Add a "全历史" / "all time" preset (would require raising `max_commits` on the backend, out of scope);
- Add validation messages toasts on every minor invalid input — only fire a toast for parse-fail fallback to default ("6mo");
- Add per-UMO persistence (range is global, like `viewMode`);
- Change the heatmap's color thresholds (`levelOf`) or its visual layout beyond the grid width;
- Change the hot-files list (Top-N remains "since the heatmap window" — wait, see open issue below).

### Open issue (to resolve during implementation)

The hot-files list is currently scoped to "all of HEAD", not "since the heatmap window". The backend spec does not mention a `top_files` time filter. Two options:

- **A. Leave hot files as "all time"** — simplest. Heatmap window narrows the activity graph but hot files stays the global Top-10. May be confusing if user thinks "1 year heatmap = 1 year hot files".
- **B. Push the heatmap's `since` to hot files too** — requires backend support (`top_files_since` parameter, or filter post-hoc in the parser). Hot files then reflect the same window as the heatmap.

For v1, **go with A**: leave hot files alone. Note in the spec's Risks section. If we want B later, it's a parser-only change plus a backend param.

## Architecture

### Range state location

`GitDiffSidebar.vue` is the owner. It already owns:

- the `useSpcodeGitStats` composable instance;
- the `statsOpen` ref + persistence;
- the manual refresh wiring (`onManualRefresh`).

Adding `statsRange` here costs zero new plumbing: a new `ref<GitStatsRange>(loadGitStatsRange())`, a new `STORAGE_KEYS` entry, and a `watch` that persists + calls `gitStats.refresh({ since, until })`. `GitLogView` and `GitStatsPanel` become pure renderers of the prop.

### Component tree

```
GitDiffSidebar
  └─ GitLogView
       └─ GitStatsPanel
            ├─ props: state, open, isDark, range          ← range added
            └─ emits: update:open, refresh, filter-date, filter-path, update:range  ← update:range added
```

### `GitStatsRange` type

Co-locate in `parseSpcodeGitStats.ts` (alongside `GitStatsData`, `GitStatsDay`, etc.) so consumers that already import from this module need no new import line:

```ts
export type GitStatsRangePreset = "1w" | "1mo" | "3mo" | "6mo" | "1y";

export type GitStatsRange =
  | { kind: "preset"; preset: GitStatsRangePreset }
  | { kind: "custom"; since: string; until: string };  // YYYY-MM-DD
```

### Preset → backend query mapping

Implemented as a pure function in `parseSpcodeGitStats.ts` (so both UI and any future server-side validation can reuse it):

```ts
export const STATS_PRESETS: ReadonlyArray<{
  key: GitStatsRangePreset;
  weeks: number;
  days: number;
}> = [
  { key: "1w",  weeks: 1,  days: 7   },
  { key: "1mo", weeks: 5,  days: 35  },
  { key: "3mo", weeks: 13, days: 91  },
  { key: "6mo", weeks: 26, days: 182 },  // current default
  { key: "1y",  weeks: 52, days: 364 },
];

/** Convert a preset into {since, until} for the backend query. */
export function rangeForPreset(p: GitStatsRangePreset, today = new Date()): { since: string; until: string } {
  const cfg = STATS_PRESETS.find((x) => x.key === p)!;
  const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const endSunday = new Date(todayStart);
  endSunday.setDate(endSunday.getDate() - endSunday.getDay());
  const sinceDate = new Date(endSunday);
  sinceDate.setDate(sinceDate.getDate() - (cfg.weeks - 1) * 7);
  return { since: fmtYmd(sinceDate), until: fmtYmd(todayStart) };
}
```

`fmtYmd` matches the existing `fmtDate` in `GitStatsPanel.vue` (`YYYY-MM-DD`).

The grid computation (below) also calls `parseYmd(s: string): Date | null`, which is a tiny inverse helper to add in `GitStatsPanel.vue` next to `fmtDate`:

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

### Composable changes (`useSpcodeGitStats.ts`)

```ts
async function refresh(options?: {
  forceLoading?: boolean;
  since?: string;
  until?: string;
}): Promise<void> { ... }

function etagKey(umo: string, worktree: string | null, since: string, until: string): string {
  return [umo, worktree ?? "", since, until].join("|");
}
```

Inside `refresh`, `params` becomes:
```ts
params: { umo, ...(worktree ? { worktree } : {}), ...(since ? { since } : {}), ...(until ? { until } : {}) }
```

The `prevSnapshotMap` and `etagMap` continue to use the same composite key, so switching range = new ETag bucket. This is intentional: a 304 on a different range is impossible because the response payload changes.

Worktree switch already calls `invalidateEtag()` (drops all buckets). The new range's bucket is created on the next refresh. ✓

### Grid computation (`GitStatsPanel.vue`)

Replace `const WEEKS = 26;` and the `grid` computed body:

```ts
const grid = computed<DayCell[][]>(() => {
  const byDate = new Map<string, GitStatsDay>();
  for (const d of snapshot.value?.days ?? []) byDate.set(d.date, d);

  const today = new Date();
  const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate());

  // Anchor and column count depend on the range kind.
  let weeks: number;
  let anchor: Date;
  if (props.range.kind === "preset") {
    const cfg = STATS_PRESETS.find((p) => p.key === props.range.preset)!;
    weeks = cfg.weeks;
    anchor = new Date(todayStart);
    anchor.setDate(anchor.getDate() - anchor.getDay());  // today's Sunday
  } else {
    const sinceDate = parseYmd(props.range.since);
    const untilDate = parseYmd(props.range.until);
    if (!sinceDate || !untilDate) return [];  // invalid → empty grid; backend will reject anyway
    weeks = Math.max(1, Math.ceil((untilDate.getTime() - sinceDate.getTime()) / 86400000 / 7) + 1);
    anchor = new Date(untilDate);
    anchor.setDate(anchor.getDate() - anchor.getDay());  // until's Sunday
  }

  const cols: DayCell[][] = [];
  for (let w = weeks - 1; w >= 0; w--) {
    const col: DayCell[] = [];
    for (let dow = 0; dow < 7; dow++) {
      const d = new Date(anchor);
      d.setDate(d.getDate() - w * 7 + dow);
      const key = fmtDate(d);
      const stat = byDate.get(key);
      col.push({
        date: key,
        commits: stat?.commits ?? 0,
        additions: stat?.additions ?? 0,
        deletions: stat?.deletions ?? 0,
        level: levelOf(stat?.commits ?? 0),
        future: d.getTime() > todayStart.getTime(),
      });
    }
    cols.push(col);
  }
  return cols;
});
```

`monthLabels` continues to walk the first cell of each column, so it adapts to the new column count automatically.

## Component design

### Header button (`GitStatsPanel.vue` template)

Insert between the truncated badge and the refresh button:

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
        <v-list-item-title>{{ tm(`...stats.range.${p.key}`) }}</v-list-item-title>
        <template #append>
          <span class="git-stats-range-days">{{ p.days }}d</span>
        </template>
      </v-list-item>
    </v-list>
    <v-divider />
    <div class="git-stats-range-custom">
      <div class="git-stats-range-custom-title">
        {{ tm("...stats.range.custom") }}
      </div>
      <v-text-field
        v-model="customSince"
        :label="tm('...stats.range.since')"
        type="date"
        density="compact"
        variant="outlined"
        hide-details
        :max="customUntil || undefined"
      />
      <v-text-field
        v-model="customUntil"
        :label="tm('...stats.range.until')"
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
        {{ tm("...stats.range.apply") }}
      </v-btn>
    </div>
  </v-card>
</v-menu>
```

### Local state inside the panel

```ts
const customSince = ref("");
const customUntil = ref("");
const todayYmd = computed(() => fmtDate(new Date()));
const isCustomValid = computed(() => {
  if (!customSince.value || !customUntil.value) return false;
  if (customSince.value > customUntil.value) return false;  // string compare is correct for YYYY-MM-DD
  return true;
});
const rangeLabel = computed(() => {
  if (props.range.kind === "preset") {
    return tm(`...stats.range.${props.range.preset}`);
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

When the popover opens, pre-fill `customSince` / `customUntil` from the active range (so a user editing "6mo" sees the current window in the date inputs as a starting point). Implemented by listening to `update:open` on the `v-menu` — or simpler, a `watchEffect` that sets them when `props.range` changes.

## Data flow

```
[user clicks preset in popover]
  ↓
GitStatsPanel emits update:range({kind:"preset", preset:"1mo"})
  ↓ (transparent pass-through)
GitLogView emits update:range(...)
  ↓
GitDiffSidebar:
  1. statsRange.value = newRange
  2. safeSetItem(STORAGE_KEYS.gitStatsRange, JSON.stringify(newRange))    // immediate
  3. const {since, until} = computeBackendRange(newRange)
  4. gitStats.refresh({ since, until })
       ↓
     useSpcodeGitStats:
       - abort previous AbortController (if pending)
       - composite ETag key now includes since/until → new bucket
       - GET /spcode/git-stats?umo=...&since=...&until=...
       - 304 → prevSnapshot replay (likely empty for new bucket) → ok state
       - 200 → parse → ok state → panel re-renders
  ↓
GitStatsPanel: range prop changed → grid computed re-runs
  - new weeks count → grid-template-columns changes
  - new anchor Sunday → cells shift
  - levelOf unchanged
  - monthLabels re-derives automatically
```

### Worktree switch behavior

`onSelectedWorktreeChange` (the existing sidebar watcher) already calls `invalidateEtag()` then `gitStats.refresh()`. Add `since`/`until` from the current `statsRange` to that refresh call. ETag is wiped so the first fetch is a 200; subsequent range switches within the new worktree use 304 replay if returning to a prior range.

### Persistence details

- key: `"astrbot.spcode.gitDiffSidebar.statsRange"`
- value: `JSON.stringify(range)` where range is `{kind:"preset", preset:"6mo"}` or `{kind:"custom", since:"2025-01-01", until:"2025-12-31"}`
- reader `loadGitStatsRange()`, defined in `GitDiffSidebar.vue` next to the existing `loadViewMode` / `loadFileBrowserCurrentPath` / `loadSelectedScope` / `loadGitStatsOpen` helpers (so it shares the same `safeGetItem` shim and the same module-load timing):
  ```ts
  function loadGitStatsRange(): GitStatsRange {
    const raw = safeGetItem(STORAGE_KEYS.gitStatsRange);
    if (!raw) return { kind: "preset", preset: "6mo" };
    try {
      const v = JSON.parse(raw);
      if (v?.kind === "preset" && STATS_PRESETS.some((p) => p.key === v.preset)) {
        return v;
      }
      if (v?.kind === "custom" && /^\d{4}-\d{2}-\d{2}$/.test(v.since) && /^\d{4}-\d{2}-\d{2}$/.test(v.until) && v.since <= v.until) {
        return v;
      }
    } catch { /* fallthrough */ }
    return { kind: "preset", preset: "6mo" };
  }
  ```
- Persist on every change (immediate, no debounce — clicks are rare and JSON is small).

## Edge cases

| Scenario | Behavior |
|---|---|
| `since > until` (custom inputs) | "应用" button `disabled` (bound to `isCustomValid`) |
| `since > today` (custom) | Allowed; backend returns 0 commits → empty grid. No toast — silent. |
| `since` in distant past, beyond backend `max_commits=5000` cap | Backend sets `truncated: true`. Badge appears with "仅显示最近 5000 次提交". |
| `since` before `range.first` | Heatmap shows empty cells for the gap. No banner (out of scope). |
| Switch preset, then switch back | ETag bucket for the previous preset still in map → 304 replay → instant re-render. |
| Worktree switch | `invalidateEtag()` drops all buckets. Range state preserved. Next refresh re-fetches. |
| localStorage corrupted (non-JSON / unknown preset / invalid date) | `loadGitStatsRange` falls back to `"6mo"`. **No** toast on first load (would be noisy on every corrupted-state user). |
| Rapid preset clicks (5 in 1 sec) | AbortController cancels the in-flight request; only the final one lands. The `loading` flicker is acceptable. |
| Custom range parse error (e.g. "2025-13-99" after browser coercion) | The browser's `type="date"` picker returns empty string for invalid input (the text-input path can produce garbage); `isCustomValid` regex check (`/^\d{4}-\d{2}-\d{2}$/` + `since <= until`) is the real gate; `:min`/`:max` attrs prevent the picker from offering out-of-range dates in the first place. |
| `until > today` (custom) | Capped via `:max="todayYmd"` on the `until` input. Defense in depth in `isCustomValid`. |
| Preset chip selected while menu open | Menu stays open until user clicks outside (standard `v-menu` behavior with `close-on-content-click="false"`). No re-trigger of refresh loop. |

## i18n keys

Add under `spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.range.*`:

| key | en-US | zh-CN | ru-RU |
|---|---|---|---|
| `range.1w` | "Last week" | "最近一周" | "Последняя неделя" |
| `range.1mo` | "Last month" | "一个月" | "Последний месяц" |
| `range.3mo` | "Last 3 months" | "三个月" | "Последние 3 месяца" |
| `range.6mo` | "Last 6 months" | "六个月" | "Последние 6 месяцев" |
| `range.1y` | "Last year" | "一年" | "Последний год" |
| `range.custom` | "Custom range" | "自定义范围" | "Произвольный диапазон" |
| `range.since` | "From" | "起始" | "С" |
| `range.until` | "To" | "结束" | "По" |
| `range.apply` | "Apply" | "应用" | "Применить" |

Existing `stats.truncatedBadge` value: change from "最近 {n} 次提交" → "仅显示最近 {n} 次提交" across all 3 locales.

## Testing

### Unit tests (vitest)

**New file**: `dashboard/src/composables/useSpcodeGitStats.spec.ts`

Mock `pluginExtensionApi.get` with axios-style response. Assertions:

1. `refresh()` without `since`/`until` → params do NOT contain them (backward compat).
2. `refresh({ since: "2025-01-01", until: "2025-12-31" })` → params contain both.
3. ETag key for `{since:"2025-01-01"}` differs from `{since:"2025-02-01"}` (different buckets).
4. Two sequential calls with same `since`/`until` → second one sends `If-None-Match`, on 304 the previous snapshot is replayed (no parse call).
5. Range switch while a previous `refresh()` is pending → AbortController aborts the first; only the second lands.
6. `loadGitStatsRange` (extract from sidebar or test via a tiny exported helper) handles: missing key → `"6mo"`; valid preset → round-trip; valid custom → round-trip; garbage JSON → `"6mo"`; `since > until` → `"6mo"`; unknown preset key → `"6mo"`.

**New file**: `dashboard/src/composables/parseSpcodeGitStats.range.spec.ts` (or extend existing `parseSpcodeGitStats.spec.ts`)

- `rangeForPreset("6mo")` returns the expected `since`/`until` for a fixed `today` parameter (deterministic).
- `rangeForPreset("1w")` on a Wednesday returns `since = this Sunday`.
- All 5 presets produce `since <= until`.

### Manual acceptance

1. Default range on a fresh load = "六个月" → 26 columns rendered.
2. Switch to "最近一周" → 1 column appears immediately. Header label updates to "最近一周".
3. Reload the page → header still says "最近一周".
4. Switch to "一年" → 52 columns. If repo has >5000 commits in the past year, the truncated badge appears with new copy.
5. Custom range: pick 2024-01-01 to 2024-12-31 → ~73 columns. Grid anchors at the Sunday of 2024-12-31. Heatmap renders.
6. Custom range with `since > until` → Apply button disabled.
7. Worktree switch: range persists; data reloads.
8. Corrupt localStorage (DevTools edit to `{"kind":"preset","preset":"bogus"}`) → reload → falls back to "六个月" silently.
9. DevTools network: confirm `since`/`until` query params appear on `GET /spcode/git-stats` after a range change.
10. Click a day in a custom range → emits `filter-date` with that day's `00:00:00`/`23:59:59` (existing behavior, unaffected by range).

## Files

**New (dashboard):**

- `src/composables/parseSpcodeGitStats.range.spec.ts` (or extend the existing spec)
- `src/composables/useSpcodeGitStats.spec.ts`

**Modified (dashboard):**

- `src/composables/parseSpcodeGitStats.ts` — add `GitStatsRange` types + `STATS_PRESETS` + `rangeForPreset`
- `src/composables/useSpcodeGitStats.ts` — `refresh({ since?, until? })` + ETag key extension
- `src/components/chat/message_list_comps/GitStatsPanel.vue` — popover, parameterized grid
- `src/components/chat/message_list_comps/GitLogView.vue` — pass-through `range` / `update:range`
- `src/components/chat/GitDiffSidebar.vue` — `statsRange` state + persistence + refresh wiring
- 3× locale files: `src/locales/{en-US,zh-CN,ru-RU}/features/chat.ts` — add range keys, update `truncatedBadge` copy

**Plugin (separate repo / worktree, per plugin spec):** No changes. Endpoint already supports `since`/`until`. If behavior diverges in practice, file a separate spec.

## Risks

- **Hot-files list stays "all time"** (open issue above): a user selecting "1 month" sees a 1-month heatmap but a global Top-10 hot files. May confuse. Acceptable for v1; address in a follow-up.
- **Custom range past `range.first` of the repo**: silent empty cells. No banner. Acceptable for v1.
- **localStorage growth from frequent switches**: each entry is ~50 bytes JSON; no concern.
- **Date input UX on non-Chrome browsers**: `<input type="date">` rendering varies (Safari shows a native picker, Firefox shows text fields with mask). Spec does not standardize. Acceptable.
- **Timezone semantics**: `since`/`until` are sent as date-only strings (`YYYY-MM-DD`). Backend interprets per its own convention (likely local or UTC — see plugin spec). Frontend does not transform. The grid anchor (today's Sunday, local time) is decoupled from the backend's interpretation, so a user looking at "今天" in the heatmap may see data attributed to "yesterday" by the backend if their TZ is unusual. Same as today's behavior — out of scope to change.
- **CSS grid template**: the existing `.git-stats-grid` uses `grid-template-rows: repeat(7, 1fr); grid-auto-flow: column;`. Switching from 26 to 1 to 52 columns re-flows via `grid-template-columns: repeat(${WEEKS}, 1fr)` on the months row only — the day grid uses `grid-auto-flow`, so it reflows automatically. ✓