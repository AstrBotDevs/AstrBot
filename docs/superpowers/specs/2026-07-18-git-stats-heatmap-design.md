# GitDiffSidebar: Change Heatmap & Stats Panel Design

**Date:** 2026-07-18
**Status:** Draft (pending user review)
**Author:** elecvoid243
**Related:** `docs/superpowers/specs/2026-07-18-git-stats-endpoint-design.md` (plugin repo, endpoint contract), `docs/superpowers/specs/2026-06-24-chatui-git-workflow-controls-design.md` (git workflow / GitLogView), `docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md` (sidebar shell)

## Goal

The History sub-tab of `GitDiffSidebar` must gain a **collapsible stats panel** at its top (above the filter bar) that visualizes repository activity:

1. a **GitHub-style calendar heatmap** (26 weeks × 7 days) of commit activity;
2. a **Top-10 hot-files bar list** ranked by commit touch count;
3. a **totals row** (commits / additions / deletions / files changed).

Clicking a heatmap day applies a `since`/`until` filter to the commit list below; clicking a hot file applies a `path` filter. The panel is therefore both a visualization and a **navigation entry** into git history.

Data comes from a **new backend endpoint** `GET /spcode/git-stats` (server-side aggregation over `git log --numstat`), so the full history (not just the 500-commit client window) with line-level stats is covered.

## Background

### Current History tab

- `GitDiffSidebar.vue` mounts one `useSpcodeGitLog` instance and passes it (plus `useSpcodeGitShow`) into `GitLogView.vue` (`viewMode === "history"`).
- `GitLogView` owns a local filter form `localFilter: LogFilter = {ref: "HEAD", n: 20}` and emits `apply(filter)` / `reset(filter)` / `loadMore` / `refresh` / `revert`. The sidebar's `onLogApply` runs `gitLog.refresh(filter)` (ETag-keyed per filter tuple).
- `LogFilter` already supports `ref`, `path`, `author`, `since`, `until`, `n` — the backend `/spcode/git-log` passes `since`/`until`/`path` straight through to `git log`. **No backend change is needed for the filter linkage.**
- Fetch/parse patterns: every spcode endpoint has a `useSpcode*.ts` composable (state machine `idle/loading/ok/error` with `previousSnapshot` retention, AbortController, ETag/304) plus a `parseSpcode*.ts` pure parser returning a discriminated `ParseResult<T>`.
- Persisted UI state lives in `GitDiffSidebar.vue`'s `STORAGE_KEYS` under `astrbot.spcode.gitDiffSidebar.*` (viewMode, currentPath, selectedWorktree, selectedScope, searchOpen).

### Why a new endpoint (decision Q1)

Frontend aggregation over `useSpcodeGitLog` data would cap the heatmap at ~500 commits (the `MAX_N` ceiling of `/spcode/git-log`) and would have **no per-file line stats** (git-log returns per-commit shortstat totals only). The user chose option **B**: a dedicated `GET /spcode/git-stats` endpoint that aggregates `git log --numstat` server-side. Contract authority lives in the plugin-repo spec; a summary is reproduced in §3.

### Why inside GitLogView (decision Q2)

Two placements were considered: (1) collapsible panel at the top of the History tab — chosen; (2) a separate fifth sidebar tab. Option 1 keeps the stats next to the commit list and makes the click-to-filter linkage almost free, because `GitLogView` already owns `localFilter` and the `apply` emit; `GitDiffSidebar` needs **zero** new plumbing.

## Decisions (confirmed with user)

| # | Question | Decision |
|---|----------|----------|
| Q1 | Stats data source | **B** — new `GET /spcode/git-stats` endpoint, server-side aggregation of full history with line-level stats |
| Q2 | Panel placement | **方案一** — collapsible panel embedded at the top of `GitLogView`, above the filter bar |
| Q3 | Visualization tech | No chart library — heatmap is a pure CSS grid of divs; bars are percentage-width divs; tooltips via native `title` |
| Q4 | Aggregation location | Backend aggregates (`days`, `hot_files`, `totals` ready to render); frontend parser stays thin |

## Scope

The feature must:

- add `GET /spcode/git-stats` to the spcode toolkit plugin (contract: §3; full details in the plugin spec);
- add a parser `dashboard/src/composables/parseSpcodeGitStats.ts` and a composable `dashboard/src/composables/useSpcodeGitStats.ts`, mirroring `parseSpcodeGitShow.ts` / `useSpcodeGitShow.ts` structure (state machine, ETag/304, abort, `previousSnapshot` on error);
- add `dashboard/src/components/chat/message_list_comps/GitStatsPanel.vue` and render it inside `GitLogView.vue`, above the filter bar;
- mount the composable in `GitDiffSidebar.vue` with the same lifecycle as `gitShow` (owned by the sidebar, disposed/recreated on worktree switch) and pass it into `GitLogView` as a prop;
- fetch lazily: only when the panel is expanded; the sidebar header refresh button also refreshes stats when the panel is expanded;
- persist the collapsed/expanded state to localStorage key `astrbot.spcode.gitDiffSidebar.statsOpen`;
- on heatmap-day click, apply `{ref: "HEAD", n: 20, since: "YYYY-MM-DDT00:00:00", until: "YYYY-MM-DDT23:59:59"}` via the existing `apply` emit (local timezone; explicit times avoid git parsing a date-only `--until` as midnight and producing an empty range);
- on hot-file click, apply `{ref: "HEAD", n: 20, path: "<repo-relative path>"}` via the existing `apply` emit;
- cover loading / error (inline retry) / `empty_repository` / `truncated` (badge "only last N commits counted") states;
- add i18n keys under `spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.*` for all shipped locales (en, zh-CN, ru — matching the locale set touched by the immediately preceding gitignore commit).

The feature must **not**:

- draw author-distribution charts, weekly bar charts, or any visualization beyond heatmap + hot-files + totals;
- add a `path` parameter to the stats endpoint request (stats are always whole-repo for the active worktree in v1);
- add export/share functionality;
- introduce a charting dependency (e.g. ECharts, D3);
- change any existing behavior of `GitLogView`'s filter bar, commit list, expand/fetch flows, or the other three sidebar tabs;
- require new ReasonCodes on the frontend beyond the existing `spcodeProjectLoad.diffSidebar.gitWorkflow.error.reason.*` mapping (the endpoint reuses existing codes).

## Endpoint contract summary (authority: plugin spec)

`GET /spcode/git-stats?ref=HEAD&since=&until=&max_commits=5000&top_files=10` (+ standard `umo`, `worktree`).

Standard envelope; success indicator `reason === null`. Data fields consumed by the frontend:

```jsonc
{
  "loaded": true, "umo": "...", "worktree": null, "directory": "...",
  "ref": "HEAD", "resolved_sha": "abc123...",
  "days": [ {"date": "2026-07-18", "commits": 5, "additions": 320, "deletions": 41} ],  // sparse, ascending
  "hot_files": [ {"path": "astrbot/core/pipeline.py", "commits": 12, "additions": 800, "deletions": 120} ],
  "totals": {"commits": 132, "additions": 9200, "deletions": 3100, "files_changed": 47},
  "range": {"first": "2026-05-01", "last": "2026-07-18"},
  "truncated": false, "max_commits": 5000,
  "reason": null, "stderr": "", "elapsed_ms": 230
}
```

Failure reasons reused from `ReasonCode`: `feature_disabled`, `no_project_loaded`, `worktree_invalid`, `directory_missing`, `not_a_git_repo`, `git_unavailable`, `git_error`, `empty_repository`, `invalid_param`. The panel surfaces them through the existing `...error.reason.*` i18n mapping.

## Component design

### Layout

```
┌ 📊 Stats   132 commits · +9.2k −3.1k · 47 files        [↻] [▾] ┐ ← collapsed: one-line summary
├──────────────────────────────────────────────────────────┤
│ [calendar heatmap: 26 week-columns × 7 rows]                   │ ← expanded body
│ Hot files (Top 10):                                            │
│ ████████████ astrbot/core/pipeline.py   12 (+800 −120)         │
│ ██████       astrbot/core/provider.py    6 (+210 −80)          │
│ Totals: 132 commits · +9,200 −3,100 · 47 files · 2026-05-01 → 2026-07-18 │
└──────────────────────────────────────────────────────────┘
```

- The header row is always visible and carries a compact summary (`totals.commits`, signed +/- shorthand, `totals.files_changed`), a refresh button, and the expand/collapse chevron.
- Expanded body scrolls independently if the sidebar is short; commit list below keeps its own scroll region.

### Calendar heatmap

- Window: **last 26 weeks ending today** (182 cells), computed in local time from the `days` array; missing days render as level 0.
- Level buckets by `commits` per day: `0` / `1–2` / `3–5` / `6–9` / `10+` — five fixed thresholds, no dynamic scaling (predictable colors across repos).
- Colors: five theme-aware greens via scoped CSS custom properties with an `isDark` variant (read from the customizer store, same as `FilePatchPanel`).
- Each cell: `title="2026-07-18 · 5 commits (+320 −41)"`; click emits the date-filter event. Level-0 cells are not clickable.
- Month labels on top of the grid at each month boundary (computed from the first cell of each month).

### Hot files

- Rows sorted as received (backend guarantees `commits` desc, `(additions+deletions)` desc, `path` asc).
- Bar width = `commits / max(commits)` as a percentage; label is the path with middle truncation (`title` holds the full path); value reads `N commits (+A −D)`.
- Row click emits the path-filter event.

### States

| State | Rendering |
|---|---|
| collapsed | Header summary only; no fetch |
| `idle`/`loading` (expanded) | Skeleton rows in the body |
| `error` | Inline error line + retry button; `previousSnapshot` keeps the last good body visible behind it (mirrors GitLogView's error overlay convention) |
| `empty_repository` | Friendly empty text (repo has no commits yet) |
| `truncated === true` | Badge on the summary line: "last 5000 commits only" |

## Data flow

```
GitStatsPanel expand (first time)
  → useSpcodeGitStats.refresh({ref: "HEAD"})
  → GET /spcode/git-stats (umo, worktree from spcodeStatus + selectedWorktree)
  → parseSpcodeGitStats → state ok
  → render heatmap + bars + totals
click day cell   → GitLogView: localFilter = {ref:"HEAD", n:20, since, until} → emit("apply") → sidebar onLogApply (existing)
click file row   → GitLogView: localFilter = {ref:"HEAD", n:20, path}         → emit("apply") → sidebar onLogApply (existing)
sidebar refresh button (viewMode==="history" && panel expanded) → gitStats.refresh()
worktree switch  → sidebar recreates the composable (same lifecycle as gitShow)
```

## Files

**New (dashboard):**

- `src/composables/parseSpcodeGitStats.ts`
- `src/composables/parseSpcodeGitStats.spec.ts`
- `src/composables/useSpcodeGitStats.ts`
- `src/components/chat/message_list_comps/GitStatsPanel.vue`

**Modified (dashboard):**

- `src/components/chat/GitDiffSidebar.vue` — mount `useSpcodeGitStats`, pass prop, extend `onManualRefresh`, add `statsOpen` storage key
- `src/components/chat/message_list_comps/GitLogView.vue` — render `GitStatsPanel` above the filter bar, wire the two filter events into `onApply`
- i18n locale modules for `features/chat` (en, zh-CN, ru)

**Plugin (separate repo/worktree, per plugin spec):** `tools/webapi/git_stats.py` (new), `tools/webapi/__init__.py` (route registration), `tests/test_git_stats.py` (new), `tests/test_webapi_end_to_end.py` (route count 35 → 36).

## Testing

- **Parser unit tests** (`parseSpcodeGitStats.spec.ts`, vitest): happy-path parse, missing-field fallbacks, malformed envelope rejection, `deriveSuccess` semantics (`reason === null`), sparse `days` preserved as-is.
- **Composable**: manual verification through the panel (no new test harness — consistent with the untested sibling composables like `useSpcodeGitShow`).
- **Backend**: `tests/test_git_stats.py` in the plugin — aggregation correctness on a fixture repo with a known commit sequence, merge-commit zero-stats, binary `- -` rows, rename-as-delete+add, `max_commits`+1 truncation detection, `since`/`until` passthrough, invalid params → `invalid_param`, preflight reason paths, ETag 304 short-circuit.
- **Route count**: `test_webapi_end_to_end.py` updated 35 → 36.
- **Manual acceptance**: expand panel → heatmap renders; click a day → commit list filters to that day; click a file → commit list filters to that file; collapse persists across reload; worktree switch refreshes stats.

## Risks / edge cases

- **Large repos**: `max_commits=5000` default + `truncated` badge bounds latency; the endpoint has an 8 MB stdout cap (plugin spec §5).
- **Date-only `--until` pitfall**: git parses a bare date as midnight; the day-click filter always sends explicit `T00:00:00` / `T23:59:59` local times.
- **Timezone**: `days` dates are author-local (`%aI` truncated to the date portion); the heatmap groups by that string verbatim — no re-bucketing in JS.
- **Panel inside `v-if="viewMode === 'history'"`**: state survives tab switches because the composable lives in the sidebar, not in `GitLogView`.
- **i18n parity**: all three shipped locales must receive the new keys in the same commit (lesson from the immediately preceding gitignore-key fix).
