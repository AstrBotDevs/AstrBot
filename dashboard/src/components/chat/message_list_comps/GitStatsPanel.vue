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
        {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.title") }}
      </span>
      <span v-if="totals" class="git-stats-summary">
        {{
          tm(
            "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.summary",
            {
              commits: totals.commits,
              additions: totals.additions,
              deletions: totals.deletions,
              files: totals.filesChanged,
            },
          )
        }}
      </span>
      <span v-if="truncated" class="git-stats-truncated-badge">
        {{
          tm(
            "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.truncatedBadge",
            { n: maxCommits },
          )
        }}
      </span>
      <span class="git-stats-header-spacer" />
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
          {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.retry") }}
        </button>
      </div>

      <!-- empty repository -->
      <div v-else-if="isEmptyRepo" class="git-stats-empty">
        {{
          tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.emptyRepo")
        }}
      </div>

      <template v-else-if="snapshot">
        <!-- month labels + heatmap -->
        <div class="git-stats-heatmap-wrap">
          <div
            class="git-stats-months"
            :style="{ gridTemplateColumns: `repeat(${WEEKS}, 1fr)` }"
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
            role="grid"
            aria-label="commit activity heatmap"
          >
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
            {{
              tm(
                "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFiles",
              )
            }}
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
            <span class="git-stats-hot-value">
              {{
                tm(
                  "spcodeProjectLoad.diffSidebar.gitWorkflow.history.stats.hotFileValue",
                  {
                    commits: f.commits,
                    additions: f.additions,
                    deletions: f.deletions,
                  },
                )
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
