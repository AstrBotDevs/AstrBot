<!--
  Author: elecvoid243, 2026-07-18
  Spec: docs/superpowers/specs/2026-07-18-git-stats-heatmap-design.md

  GitStatsPanel — collapsible change-stats panel embedded at the top of
  GitLogView: 26-week calendar heatmap + Top-N hot files + totals row.
  Clicking a day / file emits filter events that GitLogView turns into
  its standard `apply` flow.
-->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { GitStatsFetchState } from "@/composables/useSpcodeGitStats";
import type { GitStatsDay, GitStatsHotFile } from "@/composables/parseSpcodeGitStats";
import {
  STATS_PRESETS,
  type GitStatsRange,
  type GitStatsRangePreset,
} from "@/composables/parseSpcodeGitStats";

/** UI-facing cap for the user-controllable "Top N" hot-files picker.
 *  Mirrors the backend's accepted range (1..50). The slider here
 *  exposes 5..50 so the user can drive every value the API accepts;
 *  the composable's defensive clamp catches any stray caller. */
const HOT_FILES_MIN = 5;
const HOT_FILES_MAX = 50;
const HOT_FILES_DEFAULT = 10;

/** localStorage key for the persisted user exclude-pattern list. The
 *  limit (topFilesLimit) is owned by the parent so it can be re-fetched,
 *  but the filter string is purely a client-side post-processing knob
 *  so we keep it local to the panel. */
const EXCLUDE_PATTERNS_STORAGE_KEY = "astrbot.spcode.gitDiffSidebar.hotFilesExclude";

const props = defineProps<{
  state: GitStatsFetchState;
  /** Collapsed/expanded state (persisted by the sidebar). */
  open: boolean;
  isDark?: boolean;
  /** Time-range window (preset or custom). Owned by GitDiffSidebar. */
  range: GitStatsRange;
  /** Server-side hot-files cap (5..50). Owned by the parent so a
   *  change re-fetches with a new ETag bucket. */
  topFilesLimit?: number;
}>();
const emit = defineEmits<{
  (e: "update:open", v: boolean): void;
  (e: "update:range", v: GitStatsRange): void;
  (e: "update:topFilesLimit", v: number): void;
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

// ── Colored +/− helpers (2026-07-18) ───────────────────────────────
// The summary and hotFileValue locale strings embed the numeric
// counters; we need to render additions in green and deletions in
// red. Since the project uses a custom i18n (no <i18n-t> slots), we
// call tm() with sentinel substitutions for the two numbers, then
// split the result so the static text (e.g. "commits · … / … · files")
// stays locale-aware while the +/- numbers are rendered as colored
// spans with an explicit sign.
interface DeltaParts {
  prefix: string;
  mid: string;
  suffix: string;
}
const DELTA_A = "§A§";
const DELTA_D = "§D§";
function splitDelta(
  key: string,
  params: Record<string, string | number>,
): DeltaParts {
  const s = tm(key, { ...params, additions: DELTA_A, deletions: DELTA_D });
  const [prefix, rest] = s.split(DELTA_A);
  const [mid, suffix] = rest.split(DELTA_D);
  return { prefix, mid, suffix };
}
const summaryParts = computed<DeltaParts>(() => {
  if (!totals.value) return { prefix: "", mid: "", suffix: "" };
  return splitDelta(
    "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.summary",
    {
      commits: totals.value.commits,
      additions: 0,
      deletions: 0,
      files: totals.value.filesChanged,
    },
  );
});
function hotFileParts(f: {
  commits: number;
  additions: number;
  deletions: number;
}): DeltaParts {
  return splitDelta(
    "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFileValue",
    { commits: f.commits, additions: 0, deletions: 0 },
  );
}

// ── Range control (popover) ────────────────────────────────────────
const customSince = ref<string>("");
const customUntil = ref<string>("");
const todayYmd = computed(() => fmtDate(new Date()));
const isCustomValid = computed(() => {
  if (!customSince.value || !customUntil.value) return false;
  // YYYY-MM-DD is lexically comparable, so this is correct.
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
// Pre-fill the date inputs whenever the active range changes so the
// popover opens with reasonable defaults instead of empty boxes.
watch(
  () => props.range,
  (r) => {
    if (r.kind === "custom") {
      customSince.value = r.since;
      customUntil.value = r.until;
    } else {
      customSince.value = "";
      customUntil.value = "";
    }
  },
  { immediate: true },
);

// ── Heatmap grid is fully range-driven (see grid computed below). ─
// (WEEKS is gone: the grid width comes from `props.range` via the
// `weeksForRange` computed below, and the visual density floor is
// COMPACT_HEATMAP_WEEKS_THRESHOLD further down.)

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

/** Parse a strict YYYY-MM-DD string into a local-midnight Date.
 *  We deliberately use the (year, month-1, day) constructor instead of
 *  `new Date(s)` so the resulting date is anchored at the user's local
 *  midnight — `new Date("2025-01-01")` alone would parse as UTC and
 *  shift by the local TZ offset, throwing off `getDay()` math. */
function parseYmd(s: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]) - 1;
  const d = Number(m[3]);
  if (mo < 0 || mo > 11) return null;
  return new Date(y, mo, d);
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

  // Width + anchor derive from props.range:
  //   preset  → STATS_PRESETS.weeks, anchor at today's Sunday
  //   custom  → ceil((until - since) / 7) + 1, anchor at until's Sunday
  let weeks: number;
  let anchor: Date;
  // Capture into a local so TypeScript narrows the discriminated union
  // in both branches (a callback that re-reads `props.range` would not).
  const range = props.range;
  if (range.kind === "preset") {
    const cfg = STATS_PRESETS.find((p) => p.key === range.preset);
    if (!cfg) return [];
    weeks = cfg.weeks;
    if (range.preset === "1w") {
      // 2026-07-19 last-7-days fix: a Sunday-anchored 1w collapses to
      // a 1-day column on Sunday (1 actual cell + 6 future-dimmed).
      // Mirror rangeForPreset's "last 7 days" semantics by anchoring
      // 6 days back so the column always spans the last 7 actual days.
      anchor = new Date(todayStart);
      anchor.setDate(anchor.getDate() - 6);
    } else {
      // 1mo/3mo/6mo/1y keep Sun–Sat columns anchored at today's Sunday
      // so the rightmost week snaps to today's weekday (matches the
      // GitHub contribution-graph visual and the 6mo spec).
      anchor = new Date(todayStart);
      anchor.setDate(anchor.getDate() - anchor.getDay());
    }
  } else {
    const sinceDate = parseYmd(range.since);
    const untilDate = parseYmd(range.until);
    if (!sinceDate || !untilDate) return [];
    weeks = Math.max(
      1,
      Math.ceil((untilDate.getTime() - sinceDate.getTime()) / 86400000 / 7) + 1,
    );
    anchor = new Date(untilDate);
    anchor.setDate(anchor.getDate() - anchor.getDay());
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

/** 2026-07-18 heatmap-cell-size: ranges that span more than 26
 *  weeks (≈ 6 months) collapse each cell below ~20px on a typical
 *  ~600px sidebar, which is too cramped to read. Anything 26 weeks
 *  or under uses the original "fill-the-column" cells (variable
 *  size: a 1w / 1mo cell is large, a 6mo cell is the
 *  not-too-big / not-too-small sweet spot the user approved);
 *  anything strictly larger switches to the fixed 12px squares so
 *  each cell stays legible and the strip stays a single
 *  ~100px-tall band regardless of how many years are in view. The
 *  threshold is the same as the `6mo` preset (26 weeks), so the
 *  preset boundary and the layout boundary line up exactly. */
const COMPACT_HEATMAP_WEEKS_THRESHOLD = 26;
const isCompactHeatmap = computed<boolean>(
  () => grid.value.length > COMPACT_HEATMAP_WEEKS_THRESHOLD,
);

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
/** Raw hot-files list as received from the backend (up to topFilesLimit). */
const rawHotFiles = computed<GitStatsHotFile[]>(
  () => snapshot.value?.hotFiles ?? [],
);

/** Comma-separated exclude patterns the user can edit in the settings
 *  popover. Each entry is a case-insensitive glob (supports `*` and
 *  `?`); an entry that does not contain a glob wildcard is treated as
 *  a literal substring so simple filenames like `pyproject.toml` Just
 *  Work. Persisted to localStorage so the user's noise-floor
 *  preferences survive a reload. */
const excludePatternsRaw = ref<string>("");
function loadExcludePatterns(): string {
  try {
    return localStorage.getItem(EXCLUDE_PATTERNS_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}
function saveExcludePatterns(value: string): void {
  try {
    localStorage.setItem(EXCLUDE_PATTERNS_STORAGE_KEY, value);
  } catch {
    /* localStorage disabled / quota — silently ignore */
  }
}
excludePatternsRaw.value = loadExcludePatterns();
watch(excludePatternsRaw, (v) => saveExcludePatterns(v));

/** Parse "*.json, pyproject.toml, *.lock" → ["*.json", "pyproject.toml", "*.lock"].
 *  Whitespace trimmed, empties dropped, case-folded for matching. */
const excludePatterns = computed<string[]>(() =>
  excludePatternsRaw.value
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
    .map((s) => s.toLowerCase()),
);

/** Convert a single pattern to a RegExp with .gitignore semantics:
 *  wildcard syntax (`*`/`?`) on top of plain text. The two anchor
 *  flavors below let a single helper cover both "match this filename
 *  anywhere" and "match this exact path" without forcing the user to
 *  pick between two different filter UIs.
 *
 *  - Pattern WITHOUT `/` (filename-style): anchored only at the end
 *    with `(?:^|/)<re>$`. So `pyproject.toml`,
 *    `tool_loop_agent_runner.py`, and `*.json` all match the file's
 *    basename at any depth. `*`/`?` still match a single path
 *    segment (`*` is `[^/]*`, `?` is `[^/]`), so the trailing `$`
 *    cleanly rejects `a.json.txt` and `*.json` will not bleed into
 *    an unrelated `.json` parent.
 *  - Pattern WITH `/` (path-shaped): fully anchored `^<re>$`. So
 *    `dashboard/*.json` matches direct children of `dashboard/` and
 *    does NOT match `dashboard/sub/foo.json`. Path-shape is the
 *    "I want exactly this path" escape hatch.
 *
 *  Regex metacharacters in the user input are escaped — `*` and `?`
 *  are the only wildcard operators. A user typing `a.json/b.json`
 *  in the input means the literal file `a.json/b.json`, not a regex.
 *
 *  Examples:
 *  - `*.json`              matches `chat.json` and
 *                          `dashboard/src/foo.json`; NOT `a.json.txt`.
 *  - `pyproject.toml`      matches `pyproject.toml` at any depth.
 *  - `tool_loop_agent_runner.py`
 *                          matches `…/tool_loop_agent_runner.py`.
 *  - `dashboard/*.json`    matches `dashboard/chat.json`; NOT
 *                          `dashboard/sub/chat.json` and NOT
 *                          `foo/dashboard/chat.json`.
 *  - `dashboard/**`        matches anything under `dashboard/`. */
function patternToRegex(pattern: string): RegExp {
  let re = "";
  for (const ch of pattern) {
    if (ch === "*") re += "[^/]*";
    else if (ch === "?") re += "[^/]";
    else if (/[.+^${}()|[\]\\]/.test(ch)) re += "\\" + ch;
    else re += ch;
  }
  // Filename-style (no `/`): match the basename anywhere in the path.
  // Path-shape (`/` present): match the full path exactly.
  const anchored = pattern.includes("/") ? `^${re}$` : `(?:^|/)${re}$`;
  return new RegExp(anchored);
}
const excludeRegexes = computed<RegExp[]>(() =>
  excludePatterns.value.map(patternToRegex),
);
function isExcluded(path: string): boolean {
  const lowered = path.toLowerCase();
  for (const re of excludeRegexes.value) {
    if (re.test(lowered)) return true;
  }
  return false;
}

/** The user-facing cap mirrored to a clamped number; an out-of-range
 *  prop (defensive: parent could push a stale localStorage value) is
 *  coerced so the slider / numeric input never shows a value the
 *  backend would reject. */
const topFilesLimit = computed<number>(() => {
  const raw = props.topFilesLimit ?? HOT_FILES_DEFAULT;
  return Math.min(HOT_FILES_MAX, Math.max(HOT_FILES_MIN, Math.floor(raw)));
});

/** Hot-files list after the client-side exclude filter. Order is
 *  preserved (backend already sorts) and the bar's max is recomputed
 *  against the filtered set so the surviving rows still fill the
 *  available width. */
const hotFiles = computed<GitStatsHotFile[]>(() =>
  rawHotFiles.value.filter((f) => !isExcluded(f.path)),
);
const excludedCount = computed<number>(
  () => rawHotFiles.value.length - hotFiles.value.length,
);
const maxHotCommits = computed(() =>
  Math.max(1, ...hotFiles.value.map((f) => f.commits)),
);
function barWidth(commits: number): string {
  return `${Math.round((commits / maxHotCommits.value) * 100)}%`;
}

/** Two-way binding for the slider/input — clamp + emit so the parent
 *  re-fetches with the new top_files and the local input always
 *  displays a valid integer. */
const limitDraft = ref<number>(topFilesLimit.value);
watch(
  () => topFilesLimit.value,
  (v) => {
    limitDraft.value = v;
  },
);
function commitLimitDraft(): void {
  const next = Math.min(
    HOT_FILES_MAX,
    Math.max(HOT_FILES_MIN, Math.floor(Number(limitDraft.value) || HOT_FILES_DEFAULT)),
  );
  limitDraft.value = next;
  if (next !== topFilesLimit.value) {
    emit("update:topFilesLimit", next);
  }
}
function bumpLimit(delta: number): void {
  limitDraft.value = Math.min(
    HOT_FILES_MAX,
    Math.max(HOT_FILES_MIN, limitDraft.value + delta),
  );
  commitLimitDraft();
}

/** Settings popover open state. Lives in the panel because the only
 *  thing inside the popover is the panel's own knobs. */
const settingsOpen = ref(false);
function closeSettings(): void {
  settingsOpen.value = false;
}

/** Stable id for the exclude-pattern input so the <label for=...> in
 *  the popover can target it without us having to register a
 *  click-outside listener manually. */
const hotFilesExcludeInputId = "git-stats-hot-exclude";

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
    return tm(
      "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.zeroTooltip",
      { date: cell.date },
    );
  }
  return tm(
    "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.cellTooltip",
    {
      date: cell.date,
      commits: cell.commits,
      additions: cell.additions,
      deletions: cell.deletions,
    },
  );
}
</script>

<template>
  <div class="git-stats-panel" :class="{ 'is-dark': !!isDark }">
    <!-- Header: always visible; collapsed shows only this row -->
    <div class="git-stats-header">
      <v-icon size="14" class="git-stats-header-icon"
        >mdi-chart-box-outline</v-icon
      >
      <span class="git-stats-title">
        {{
          tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.title")
        }}
      </span>
      <!--
        The pieces from summaryParts already carry the surrounding
        spaces from the locale string ("5000 次提交 · ", " / ",
        " · 2637 个文件"), so the colored +/- spans are spliced in
        with no whitespace between them and the interpolations.
        Any newline between `}}` and `<span>` would inject an extra
        space under Vue's default whitespace condensation, so the
        dynamic part is kept on a single line.
      -->
      <span v-if="totals" class="git-stats-summary"
        >{{ summaryParts.prefix
        }}<span class="gs-add">+{{ totals.additions }}</span
        >{{ summaryParts.mid
        }}<span class="gs-del">−{{ totals.deletions }}</span
        >{{ summaryParts.suffix }}</span
      >
      <span v-if="truncated" class="git-stats-truncated-badge">
        {{
          tm(
            "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.truncatedBadge",
            { n: maxCommits },
          )
        }}
      </span>
      <span class="git-stats-header-spacer" />
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
                tm(
                  'spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.range.since',
                )
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
                tm(
                  'spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.range.until',
                )
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
                tm(
                  "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.range.apply",
                )
              }}
            </v-btn>
          </div>
        </v-card>
      </v-menu>
      <v-btn
        icon
        size="x-small"
        variant="text"
        :loading="isLoading && open"
        :title="
          tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.refresh')
        "
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
        <v-icon size="14">{{
          open ? "mdi-chevron-up" : "mdi-chevron-down"
        }}</v-icon>
      </v-btn>
    </div>

    <!-- Body: only while expanded -->
    <div v-if="open" class="git-stats-body">
      <!-- loading skeleton -->
      <div v-if="isLoading" class="git-stats-loading">
        {{
          tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.loading")
        }}
      </div>

      <!-- error (non-empty-repo) -->
      <div v-else-if="errorReason && !isEmptyRepo" class="git-stats-error">
        <span>
          {{
            tm(
              "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.error",
            ) +
            ": " +
            tm(
              `spcodeProjectLoad.diffSidebar.gitWorkflow.error.reason.${errorReason}`,
              { reason: errorReason },
            )
          }}
        </span>
        <button type="button" class="git-stats-retry" @click="emit('refresh')">
          {{
            tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.retry")
          }}
        </button>
      </div>

      <!-- empty repository -->
      <div v-else-if="isEmptyRepo" class="git-stats-empty">
        {{
          tm(
            "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.emptyRepo",
          )
        }}
      </div>

      <template v-else-if="snapshot">
        <!-- month labels + heatmap -->
        <div class="git-stats-heatmap-wrap">
          <div
            class="git-stats-months"
            :class="{ 'is-compact': isCompactHeatmap }"
            :style="
              isCompactHeatmap
                ? { gridTemplateColumns: `repeat(${grid.length}, 14px)` }
                : { gridTemplateColumns: `repeat(26, 1fr)` }
            "
          >
            <span
              v-for="ml in monthLabels"
              :key="ml.col"
              class="git-stats-month-label"
              :style="{ gridColumnStart: ml.col + 1 }"
            >
              {{ ml.label }}
            </span>
          </div>
          <div
            class="git-stats-grid"
            :class="{ 'is-compact': isCompactHeatmap }"
            role="grid"
            aria-label="commit activity heatmap"
          >
            <template v-for="(col, ci) in grid" :key="ci">
              <button
                v-for="cell in col"
                :key="cell.date"
                type="button"
                class="git-stats-cell"
                :class="[
                  `lv-${cell.level}`,
                  { 'is-future': cell.future, 'is-compact': isCompactHeatmap },
                ]"
                :title="cellTitle(cell)"
                :disabled="cell.level === 0 || cell.future"
                @click="onDayClick(cell)"
              />
            </template>
          </div>
        </div>

        <!-- hot files -->
        <div v-if="rawHotFiles.length > 0" class="git-stats-hot">
          <div class="git-stats-hot-title-row">
            <div class="git-stats-hot-title">
              {{
                tm(
                  "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFiles",
                )
              }}
              <span class="git-stats-hot-limit-pill">{{
                tm(
                  "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFilesLimit",
                  { n: topFilesLimit },
                )
              }}</span>
              <span
                v-if="excludedCount > 0"
                class="git-stats-hot-excluded-pill"
                :title="
                  tm(
                    'spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFilesExcludedHint',
                    { n: excludedCount },
                  )
                "
                >−{{ excludedCount }}</span
              >
            </div>
            <v-menu
              v-model="settingsOpen"
              :close-on-content-click="false"
              location="bottom end"
            >
              <template #activator="{ props: tipProps }">
                <v-btn
                  icon
                  size="x-small"
                  variant="text"
                  class="git-stats-hot-settings"
                  :title="
                    tm(
                      'spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFilesSettings',
                    )
                  "
                  v-bind="tipProps"
                  @click.stop
                >
                  <v-icon size="14">mdi-tune-variant</v-icon>
                </v-btn>
              </template>
              <v-card class="git-stats-hot-settings-card" min-width="260">
                <div class="git-stats-hot-settings-row">
                  <label class="git-stats-hot-settings-label">
                    {{
                      tm(
                        "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFilesLimitLabel",
                      )
                    }}
                  </label>
                  <div class="git-stats-hot-limit-input">
                    <v-btn
                      icon
                      size="x-small"
                      variant="text"
                      :disabled="limitDraft <= HOT_FILES_MIN"
                      @click="bumpLimit(-5)"
                    >
                      <v-icon size="14">mdi-minus</v-icon>
                    </v-btn>
                    <input
                      type="number"
                      class="git-stats-hot-limit-number"
                      :min="HOT_FILES_MIN"
                      :max="HOT_FILES_MAX"
                      v-model.number="limitDraft"
                      @change="commitLimitDraft"
                      @blur="commitLimitDraft"
                    />
                    <v-btn
                      icon
                      size="x-small"
                      variant="text"
                      :disabled="limitDraft >= HOT_FILES_MAX"
                      @click="bumpLimit(5)"
                    >
                      <v-icon size="14">mdi-plus</v-icon>
                    </v-btn>
                  </div>
                  <div class="git-stats-hot-settings-hint">
                    {{
                      tm(
                        "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFilesLimitHint",
                        { min: HOT_FILES_MIN, max: HOT_FILES_MAX },
                      )
                    }}
                  </div>
                </div>
                <v-divider class="git-stats-hot-settings-divider" />
                <div class="git-stats-hot-settings-row">
                  <label
                    class="git-stats-hot-settings-label"
                    :for="hotFilesExcludeInputId"
                  >
                    {{
                      tm(
                        "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFilesExcludeLabel",
                      )
                    }}
                  </label>
                  <input
                    :id="hotFilesExcludeInputId"
                    v-model="excludePatternsRaw"
                    type="text"
                    class="git-stats-hot-exclude-input"
                    :placeholder="
                      tm(
                        'spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFilesExcludePlaceholder',
                      )
                    "
                    spellcheck="false"
                  />
                  <div class="git-stats-hot-settings-hint">
                    {{
                      tm(
                        "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFilesExcludeHint",
                      )
                    }}
                  </div>
                </div>
                <div class="git-stats-hot-settings-actions">
                  <v-btn
                    size="small"
                    variant="text"
                    :disabled="excludePatternsRaw.length === 0"
                    @click="excludePatternsRaw = ''"
                    >{{
                      tm(
                        "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFilesExcludeClear",
                      )
                    }}</v-btn
                  >
                  <v-btn
                    size="small"
                    variant="tonal"
                    @click="closeSettings"
                    >{{
                      tm(
                        "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFilesExcludeDone",
                      )
                    }}</v-btn
                  >
                </div>
              </v-card>
            </v-menu>
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
              <span
                class="git-stats-hot-bar"
                :style="{ width: barWidth(f.commits) }"
              />
            </span>
            <span class="git-stats-hot-path">{{ f.path }}</span>
            <!-- Same locale-split + colored-spans composition as the
                 summary row; pieces carry the surrounding spaces. -->
            <span class="git-stats-hot-value"
              >{{ hotFileParts(f).prefix
              }}<span class="gs-add">+{{ f.additions }}</span
              >{{ hotFileParts(f).mid
              }}<span class="gs-del">−{{ f.deletions }}</span
              >{{ hotFileParts(f).suffix }}</span
            >
          </button>
          <div
            v-if="hotFiles.length === 0 && excludedCount > 0"
            class="git-stats-hot-all-excluded"
          >
            {{
              tm(
                "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFilesAllExcluded",
              )
            }}
          </div>
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
  /* 2026-07-18: additions/deletions tinting (GitHub diff convention).
     Light mode = #1a7f37 / #cf222e, dark mode overridden below. */
  --gs-add: #1a7f37;
  --gs-del: #cf222e;
  border: 1px solid rgb(var(--v-theme-on-surface), 0.08);
  border-radius: 8px;
  margin-bottom: 8px;
  font-size: 12px;
  /* Align digit widths across the +/- counters so the numbers read
     as a tidy column rather than a wobbly row. */
  font-variant-numeric: tabular-nums;
}
.git-stats-panel.is-dark {
  --gs-l0: rgb(255 255 255 / 8%);
  --gs-l1: #0e4429;
  --gs-l2: #006d32;
  --gs-l3: #26a641;
  --gs-l4: #39d353;
  --gs-add: #3fb950;
  --gs-del: #f85149;
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
  /* 2026-07-18: switched from `opacity: 0.75` to a muted color so the
     child .gs-add / .gs-del spans render at full color saturation
     (opacity on the parent would wash out the green/red too). */
  color: rgba(var(--v-theme-on-surface), 0.7);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gs-add {
  color: var(--gs-add);
}
.gs-del {
  color: var(--gs-del);
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
/* 2026-07-18 heatmap-cell-size: parent for both the month-labels
   row and the heatmap grid. `overflow-x: auto` shows a
   horizontal scrollbar when the sidebar is resized below the
   grid's natural width (e.g. 26 weeks × 14px ≈ 362px on a
   200px-wide panel) so the cells stay at their design size
   instead of being squashed into illegible slivers. The
   children below use `width: max-content` so the wrap shrinks
   to the content when the panel is wider than the grid,
   leaving the unused horizontal space empty. */
.git-stats-heatmap-wrap {
  overflow-x: auto;
}
/* 2026-07-18 heatmap-cell-size: two layout modes, picked by the
   `is-compact` class that GitStatsPanel toggles on the grids and
   each cell once `grid.length > 26` (the 6-month preset).

   DEFAULT (no is-compact) — "big" cells for ≤ 6 months:
   `width: 100%` + `aspect-ratio: 1` makes every cell a square
   that fills its column, and `grid-template-rows: repeat(7,
   1fr)` lets the rows size to that square. With ≤ 26 columns
   the column width = (wrap-width - gaps) / N, so a 1w / 1mo
   cell is generous and a 6mo cell lands around 18-22px on a
   typical ~600px sidebar — the size the user described as
   "just right, not too big or too small." The month-labels row
   uses `repeat(N, 1fr)` so its columns line up with the
   heatmap's auto-sized tracks. The grid itself fills the wrap
   (no `width: max-content`), so the wrap never needs a
   horizontal scrollbar in this mode.

   COMPACT (is-compact) — "small" cells for > 6 months:
   `width: 12px; height: 12px` and `grid-template-rows: repeat(7,
   12px)` make every cell a fixed 12px square. The grid uses
   `width: max-content` and the month row switches to
   `repeat(N, 14px)` (12px cell + 2px gap), so both rows shrink
   to their content and stay pixel-aligned. The wrap keeps its
   `overflow-x: auto` so a narrow sidebar shows a horizontal
   scrollbar instead of squashing the cells. */
.git-stats-months {
  display: grid;
  margin-bottom: 2px;
}
.git-stats-months.is-compact {
  width: max-content;
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
  /* 2026-07-19 heatmap-cell-size: pin the cell width to 1/26 of the
     panel so every range from 1w up to 6mo renders at the same
     "6mo" cell size. Shorter ranges leave the right side of the
     grid empty; longer ranges (1y, custom > 26w) flip into the
     `.is-compact` 12px variant below. */
  grid-template-columns: repeat(26, 1fr);
}
.git-stats-grid.is-compact {
  grid-template-rows: repeat(7, 12px);
  grid-template-columns: unset;
  width: max-content;
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
.git-stats-cell.is-compact {
  width: 12px;
  height: 12px;
  min-width: 0;
  aspect-ratio: auto;
}
.git-stats-cell:disabled {
  cursor: default;
}
.git-stats-cell.lv-1 {
  background: var(--gs-l1);
}
.git-stats-cell.lv-2 {
  background: var(--gs-l2);
}
.git-stats-cell.lv-3 {
  background: var(--gs-l3);
}
.git-stats-cell.lv-4 {
  background: var(--gs-l4);
}
.git-stats-cell.is-future {
  opacity: 0.35;
}
.git-stats-cell:not(:disabled):hover {
  outline: 1px solid rgb(var(--v-theme-primary));
}
.git-stats-hot {
  margin-top: 8px;
}
.git-stats-hot-title-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
}
.git-stats-hot-title {
  font-weight: 600;
  opacity: 0.8;
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.git-stats-hot-limit-pill {
  font-weight: 500;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: rgb(var(--v-theme-on-surface), 0.08);
  color: rgb(var(--v-theme-on-surface), 0.7);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.git-stats-hot-excluded-pill {
  font-weight: 500;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: rgb(var(--v-theme-warning), 0.18);
  color: rgb(var(--v-theme-warning));
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  cursor: help;
}
.git-stats-hot-settings {
  flex: 0 0 auto;
  margin: 0;
}
.git-stats-hot-settings-card {
  padding: 10px 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.git-stats-hot-settings-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.git-stats-hot-settings-label {
  font-size: 12px;
  font-weight: 600;
  opacity: 0.7;
}
.git-stats-hot-limit-input {
  display: flex;
  align-items: center;
  gap: 2px;
}
.git-stats-hot-limit-number {
  flex: 1;
  min-width: 0;
  text-align: center;
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  /* Strip native spinner / borders so the input matches the rest of
     the dashboard's 12px surfaces; the +/- buttons handle stepping. */
  -moz-appearance: textfield;
  appearance: textfield;
  padding: 4px 6px;
  border: 1px solid rgb(var(--v-border-color), 0.24);
  border-radius: 4px;
  background: rgb(var(--v-theme-on-surface), 0.03);
  color: inherit;
}
.git-stats-hot-limit-number::-webkit-outer-spin-button,
.git-stats-hot-limit-number::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.git-stats-hot-exclude-input {
  font-size: 12px;
  padding: 4px 6px;
  border: 1px solid rgb(var(--v-border-color), 0.24);
  border-radius: 4px;
  background: rgb(var(--v-theme-on-surface), 0.03);
  color: inherit;
  font-family: ui-monospace, monospace;
}
.git-stats-hot-exclude-input:focus {
  outline: none;
  border-color: rgb(var(--v-theme-primary));
}
.git-stats-hot-settings-hint {
  font-size: 10.5px;
  opacity: 0.6;
  line-height: 1.4;
}
.git-stats-hot-settings-divider {
  margin: 0 -12px;
}
.git-stats-hot-settings-actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
}
.git-stats-hot-all-excluded {
  font-size: 11px;
  font-style: italic;
  opacity: 0.6;
  padding: 4px 2px;
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
/* 2026-07-18 heatmap-popup-font: v-list-item-title inherits Vuetify's
   default 14-16px typography which is much larger than the
   `改动统计` page's 12px body text. Force 12px on every text node
   inside the popover so the dropdown matches the rest of the
   GitStatsPanel header. Vuetify wraps the title in a dedicated
   class, so we target that explicitly rather than the whole list
   item. The append slot (e.g. "30d", "90d" day counters) is also
   re-aligned to 12px for visual consistency. */
.git-stats-range-presets .v-list-item-title {
  font-size: 12px;
  line-height: 1.2;
}
.git-stats-range-presets .v-list-item__append {
  font-size: 12px;
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
  font-size: 12px;
  font-weight: 600;
  opacity: 0.7;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
/* 2026-07-18 heatmap-popup-font: the v-text-field inside the
   popover (since / until date inputs) would also render at 14px
   by default, looking oversized next to the now-12px labels. Use
   the same :deep() override the rest of the dashboard applies
   (see GitLogView's filter field for the canonical pattern). */
.git-stats-range-custom :deep(.v-field__input),
.git-stats-range-custom :deep(.v-label) {
  font-size: 12px;
}
</style>
