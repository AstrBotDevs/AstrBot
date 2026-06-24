<!-- Author: elecvoid243
     Date: 2026-06-24
     Spec: docs/superpowers/specs/2026-06-24-chatui-git-workflow-controls-design.md §3.2, §6.5
     Pure presentation: takes a LogFetchState and exposes
     'apply' / 'loadMore' / 'refresh' events back to the parent
     (which owns the useSpcodeGitLog composable instance). -->
<script setup lang="ts">
import { computed, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { LogFetchState, LogFilter } from "@/composables/useSpcodeGitLog";

const { tm } = useModuleI18n("features/chat");

const props = defineProps<{
  state: LogFetchState;
  hasMore: boolean;
  isLoading: boolean;
}>();

const emit = defineEmits<{
  (e: "apply", filter: LogFilter): void;
  (e: "loadMore"): void;
  (e: "refresh"): void;
}>();

// Local filter form state. Emitted on Apply; reset on Reset.
const localFilter = ref<LogFilter>({ ref: "HEAD", n: 20 });

const commits = computed(() => {
  if (props.state.kind === "ok") return props.state.snapshot.commits;
  if (props.state.kind === "error") {
    // On error, keep showing the last successful snapshot's commits (if any)
    // so the user does not lose context during transient failures. For the
    // empty-repository case (reason === "empty_repository") the fallback
    // returns [] so the empty-illustration branch in the template fires.
    return props.state.previousSnapshot?.commits ?? [];
  }
  return [];
});

const isEmptyRepository = computed(() => {
  return (
    props.state.kind === "error" && props.state.reason === "empty_repository"
  );
});

const isTruncated = computed(() => {
  if (props.state.kind === "ok") return props.state.snapshot.truncated;
  if (props.state.kind === "error" && props.state.previousSnapshot) {
    return props.state.previousSnapshot.truncated;
  }
  return false;
});

const errorReason = computed(() => {
  if (props.state.kind !== "error") return null;
  return props.state.reason;
});

const expanded = ref<Set<string>>(new Set<string>());

function toggleCommit(sha: string): void {
  const next = new Set(expanded.value);
  if (next.has(sha)) next.delete(sha);
  else next.add(sha);
  expanded.value = next;
}

/** Spec §6.5.2: relative time formatter (P0-5 fix). */
function formatRelativeTime(isoDate: string, now: number = Date.now()): string {
  const t = new Date(isoDate).getTime();
  if (Number.isNaN(t)) return isoDate;
  const diff = now - t;
  const min = Math.floor(diff / 60_000);
  if (min < 1) return tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.relativeTime.now");
  if (min < 60) return tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.relativeTime.minutesAgo", { n: min });
  const h = Math.floor(min / 60);
  if (h < 24) return tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.relativeTime.hoursAgo", { n: h });
  const d = Math.floor(h / 24);
  if (d < 7) return tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.relativeTime.daysAgo", { n: d });
  const dt = new Date(t);
  const yyyy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  return tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.relativeTime.exactDate", {
    date: `${yyyy}-${mm}-${dd}`,
  });
}

function onApply(): void {
  emit("apply", { ...localFilter.value });
}

function onReset(): void {
  localFilter.value = { ref: "HEAD", n: 20 };
  emit("apply", { ...localFilter.value });
}
</script>

<template>
  <div class="git-log-view">
    <!-- Truncation banner (spec §6.5.2) -->
    <div v-if="isTruncated" class="git-log-truncated">
      {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.truncated") }}
    </div>

    <!-- Filter bar (spec §6.5.1) -->
    <div class="git-log-filter">
      <v-text-field
        v-model="localFilter.ref"
        :label="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.ref')"
        :placeholder="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.refPlaceholder')"
        density="compact"
        variant="outlined"
        hide-details
        class="git-log-filter-field"
      />
      <v-text-field
        v-model="localFilter.author"
        :label="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.author')"
        :placeholder="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.authorPlaceholder')"
        density="compact"
        variant="outlined"
        hide-details
        class="git-log-filter-field"
      />
      <v-text-field
        v-model="localFilter.path"
        :label="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.path')"
        :placeholder="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.pathPlaceholder')"
        density="compact"
        variant="outlined"
        hide-details
        class="git-log-filter-field"
      />
      <v-text-field
        v-model="localFilter.since"
        :label="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.since')"
        :placeholder="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.sincePlaceholder')"
        density="compact"
        variant="outlined"
        hide-details
        class="git-log-filter-field"
      />
      <v-text-field
        v-model.number="localFilter.n"
        :label="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.n')"
        :placeholder="tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.nPlaceholder')"
        density="compact"
        variant="outlined"
        hide-details
        type="number"
        min="1"
        max="200"
        class="git-log-filter-field git-log-filter-n"
      />
      <div class="git-log-filter-actions">
        <v-btn
          size="x-small"
          variant="flat"
          color="primary"
          :loading="isLoading"
          @click="onApply"
        >
          {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.apply") }}
        </v-btn>
        <v-btn
          size="x-small"
          variant="text"
          :disabled="isLoading"
          @click="onReset"
        >
          {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.reset") }}
        </v-btn>
      </div>
    </div>

    <!-- Body: loading / empty repo / no commits / commit list / error -->
    <div v-if="state.kind === 'loading'" class="git-log-center">
      <v-progress-circular indeterminate :size="28" />
      <span class="git-log-center-text">
        {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.loading") }}
      </span>
    </div>

    <div v-else-if="isEmptyRepository" class="git-log-center">
      <v-icon size="32" color="grey">mdi-source-branch</v-icon>
      <span class="git-log-center-text">
        {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.emptyRepository") }}
      </span>
    </div>

    <div v-else-if="commits.length === 0" class="git-log-center">
      <v-icon size="32" color="grey">mdi-source-commit-off</v-icon>
      <span class="git-log-center-text">
        {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.empty") }}
      </span>
    </div>

    <div v-else class="git-log-list">
      <div
        v-for="c in commits"
        :key="c.sha"
        class="git-log-item"
        :class="{ expanded: expanded.has(c.sha) }"
      >
        <button
          type="button"
          class="git-log-item-header"
          :aria-expanded="expanded.has(c.sha)"
          :aria-label="
            expanded.has(c.sha)
              ? tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.collapseCommit')
              : tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.expandCommit')
          "
          @click="toggleCommit(c.sha)"
        >
          <v-icon size="14" class="git-log-item-icon">mdi-source-commit</v-icon>
          <span class="git-log-item-sha">{{ c.shaShort || c.sha.slice(0, 7) }}</span>
          <span class="git-log-item-subject">{{ c.subject }}</span>
        </button>
        <div class="git-log-item-meta">
          <span class="git-log-item-author">{{ c.author.name }}</span>
          <span class="git-log-item-sep">·</span>
          <span class="git-log-item-time">{{ formatRelativeTime(c.date) }}</span>
          <span class="git-log-item-sep">·</span>
          <span class="git-log-item-stat">
            {{
              tm(
                "spcodeProjectLoad.diffSidebar.gitWorkflow.history.filesStat",
                {
                  files: c.shortstat.files,
                  add: c.shortstat.additions,
                  del: c.shortstat.deletions,
                },
              )
            }}
          </span>
        </div>
        <div v-if="expanded.has(c.sha) && c.body" class="git-log-item-body">
          <pre class="git-log-item-body-pre">{{ c.body }}</pre>
        </div>
      </div>

      <div v-if="hasMore" class="git-log-load-more">
        <v-btn
          size="small"
          variant="text"
          color="primary"
          :loading="isLoading"
          :disabled="isLoading"
          @click="emit('loadMore')"
        >
          {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.loadMore") }}
        </v-btn>
      </div>
    </div>

    <!-- Generic error banner with retry (above any cached commits). -->
    <div v-if="errorReason && !isEmptyRepository" class="git-log-banner-error">
      <span>
        {{
          tm(
            `spcodeProjectLoad.diffSidebar.gitWorkflow.error.reason.${errorReason}`,
            { reason: errorReason },
          )
        }}
      </span>
      <button class="git-log-banner-retry" @click="emit('refresh')">
        {{ tm("spcodeProjectLoad.diffSidebar.error.retry") }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.git-log-view {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0;
}

.git-log-truncated {
  padding: 6px 12px;
  margin: 0 12px;
  background: rgba(255, 193, 7, 0.12);
  color: rgb(255, 152, 0);
  font-size: 12px;
  border-radius: 4px;
}

.git-log-filter {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 8px;
  padding: 4px 12px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  padding-bottom: 8px;
}
.git-log-filter-field {
  font-size: 12px;
}
.git-log-filter-n {
  max-width: 80px;
}
.git-log-filter-actions {
  grid-column: 1 / -1;
  display: flex;
  justify-content: flex-end;
  gap: 4px;
}

.git-log-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px 16px;
  min-height: 140px;
}
.git-log-center-text {
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 13px;
}

.git-log-list {
  display: flex;
  flex-direction: column;
}
.git-log-item {
  padding: 8px 12px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.git-log-item-header {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 0;
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  color: inherit;
}
.git-log-item-header:hover .git-log-item-subject {
  color: rgb(var(--v-theme-primary));
}
.git-log-item-icon {
  color: rgb(var(--v-theme-primary));
  flex-shrink: 0;
}
.git-log-item-sha {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  flex-shrink: 0;
}
.git-log-item-subject {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.git-log-item-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  margin-top: 2px;
  padding-left: 20px;
}
.git-log-item-author {
  color: rgba(var(--v-theme-on-surface), 0.8);
}
.git-log-item-sep {
  color: rgba(var(--v-theme-on-surface), 0.35);
}
.git-log-item-stat {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
}
.git-log-item-body {
  margin-top: 6px;
  padding-left: 20px;
}
.git-log-item-body-pre {
  margin: 0;
  padding: 6px 8px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-radius: 4px;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre-wrap;
  word-break: break-word;
  color: rgba(var(--v-theme-on-surface), 0.85);
}

.git-log-load-more {
  display: flex;
  justify-content: center;
  padding: 8px 0;
}

.git-log-banner-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 12px;
  margin: 8px 12px 0;
  background: rgba(248, 81, 73, 0.1);
  border-radius: 4px;
  font-size: 12px;
  color: rgb(248, 81, 73);
}
.git-log-banner-retry {
  background: transparent;
  border: 1px solid currentColor;
  border-radius: 4px;
  padding: 2px 8px;
  cursor: pointer;
  color: inherit;
}

@media (max-width: 760px) {
  .git-log-filter {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
