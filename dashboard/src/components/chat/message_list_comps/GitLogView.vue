<!-- Author: elecvoid243
     Date: 2026-06-24
     Spec: docs/superpowers/specs/2026-06-24-chatui-git-workflow-controls-design.md §3.2, §6.5
     Pure presentation: takes a LogFetchState and exposes
     'apply' / 'loadMore' / 'refresh' events back to the parent
     (which owns the useSpcodeGitLog composable instance).

     Updated 2026-06-25 — when a commit row is expanded, also fetch
     the file list via /spcode/git-show (useSpcodeGitShow). The list
     renders inline below the commit body. Each commit's fetch is
     idempotent and per-SHA cached by the composable, so re-expanding
     a previously seen commit is a no-op (ETag 304 short-circuit).
     Spec: docs/superpowers/specs/2026-06-25-git-show-design.md. -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { LogFetchState, LogFilter } from "@/composables/useSpcodeGitLog";
import type {
  UseSpcodeGitShow,
  GitShowFetchState,
  GitShowFileFetchState,
} from "@/composables/useSpcodeGitShow";
import FilePatchPanel from "./FilePatchPanel.vue";
import type {
  GitShowFile,
  GitShowFileStatus,
  GitShowData,
} from "@/composables/parseSpcodeGitShow";
import type { FileStatus } from "@/composables/parseSpcodeGitDiff";

const { tm } = useModuleI18n("features/chat");
// Note (v3.9, 2026-06-25, elecvoid243): FilePatchPanel reads the
// customizer store itself for `isDark`, so we do not derive / forward
// it here. Keeping the source of truth in one place avoids the
// "computed reads the wrong field" trap that bit the earlier
// useTheme().global.name.value attempt.

const props = defineProps<{
  state: LogFetchState;
  hasMore: boolean;
  isLoading: boolean;
  /** Composable handle injected by the sidebar (spec 2026-06-25 §3.1).
   *  GitLogView reads per-SHA state via the helper methods and auto-
   *  fetches on expand; the sidebar owns the lifecycle (worktree +
   *  umo + dispose). */
  gitShow: UseSpcodeGitShow;
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

// v3.9 (2026-06-25): per-file expand/collapse state, keyed by
// `${sha}\u0001${path}`. Mirrors the `expanded` set's contract (idempotent
// toggles, no array mutation — reassign the ref to keep Vue reactivity
// happy with Set internals). The composable's fetchFile is the only
// observer that consumes this set; it dedupes in-flight and cache hits.
const expandedFiles = ref<Set<string>>(new Set<string>());

function fileKey(sha: string, filePath: string): string {
  return `${sha}\u0001${filePath}`;
}

function isFileExpanded(sha: string, filePath: string): boolean {
  return expandedFiles.value.has(fileKey(sha, filePath));
}

function toggleFile(sha: string, filePath: string): void {
  const k = fileKey(sha, filePath);
  const next = new Set(expandedFiles.value);
  if (next.has(k)) next.delete(k);
  else next.add(k);
  expandedFiles.value = next;
}

// Auto-fetch the file list for any newly-expanded commit. The
// composable's `fetch` is idempotent (no-op on cache hit / in flight),
// so calling it for already-cached SHAs is safe and cheap. Using a
// `watch` rather than `watchEffect` keeps the dependency surface
// explicit and avoids re-runs on every composable-internal mutation
// (state map / data map reassignments inside useSpcodeGitShow).
//
// `flush: "post"` defers the fetch until Vue has flushed the DOM
// update for the new `expanded` set, so the "Loading files…" row is
// visible during the first paint. Without this the spinner would not
// appear for sub-100ms responses (response arrives before Vue paints).
watch(
  () => Array.from(expanded.value),
  (newShas, oldShas = []) => {
    for (const sha of newShas) {
      if (!oldShas.includes(sha)) {
        void props.gitShow.fetch(sha);
      }
    }
  },
  { flush: "post" },
);

// v3.9: when a file row is expanded, lazily fetch its patch.
// Reusing the same `flush: "post"` + array-from-Set pattern keeps the
// spinner visible during the first paint and avoids re-runs on
// every composable-internal mutation.
watch(
  () => Array.from(expandedFiles.value),
  (newKeys, oldKeys = []) => {
    for (const k of newKeys) {
      if (oldKeys.includes(k)) continue;
      const sep = k.indexOf("\u0001");
      // Defensive: skip malformed keys (should never happen — fileKey
      // always inserts the NUL). Avoids throwing on corrupted state.
      if (sep < 0) continue;
      const sha = k.slice(0, sep);
      const path = k.slice(sep + 1);
      void props.gitShow.fetchFile(sha, path);
    }
  },
  { flush: "post" },
);

/** Spec §6.5.2: relative time formatter (P0-5 fix). */
function formatRelativeTime(isoDate: string, now: number = Date.now()): string {
  const t = new Date(isoDate).getTime();
  if (Number.isNaN(t)) return isoDate;
  const diff = now - t;
  const min = Math.floor(diff / 60_000);
  if (min < 1)
    return tm(
      "spcodeProjectLoad.diffSidebar.gitWorkflow.history.relativeTime.now",
    );
  if (min < 60)
    return tm(
      "spcodeProjectLoad.diffSidebar.gitWorkflow.history.relativeTime.minutesAgo",
      { n: min },
    );
  const h = Math.floor(min / 60);
  if (h < 24)
    return tm(
      "spcodeProjectLoad.diffSidebar.gitWorkflow.history.relativeTime.hoursAgo",
      { n: h },
    );
  const d = Math.floor(h / 24);
  if (d < 7)
    return tm(
      "spcodeProjectLoad.diffSidebar.gitWorkflow.history.relativeTime.daysAgo",
      { n: d },
    );
  const dt = new Date(t);
  const yyyy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  return tm(
    "spcodeProjectLoad.diffSidebar.gitWorkflow.history.relativeTime.exactDate",
    {
      date: `${yyyy}-${mm}-${dd}`,
    },
  );
}

function onApply(): void {
  emit("apply", { ...localFilter.value });
}

function onReset(): void {
  localFilter.value = { ref: "HEAD", n: 20 };
  emit("apply", { ...localFilter.value });
}

// ── File list helpers (spec 2026-06-25 §3.3) ──────────────────────

/** Map a git-show file status to the same FileStatus union used by
 *  git-diff. The two parsers share a 1-letter alphabet (M/A/D/R/C)
 *  so the cast is a no-op for valid statuses. */
function toFileStatus(s: GitShowFileStatus): FileStatus {
  return s as FileStatus;
}

/** Single source of truth for the per-file row icon (matches
 *  GitDiffFileItem.ICON_MAP so the two views look identical). The
 *  M/A/D/R/C palette is the same; T is folded into M by the parser
 *  per spec. */
const FILE_ICON_MAP: Record<
  GitShowFileStatus,
  { icon: string; color: string }
> = {
  M: { icon: "mdi-pencil", color: "primary" },
  A: { icon: "mdi-plus-circle", color: "success" },
  D: { icon: "mdi-minus-circle", color: "error" },
  R: { icon: "mdi-rename-box", color: "warning" },
  C: { icon: "mdi-content-copy", color: "info" },
  unknown: { icon: "mdi-file-document-edit-outline", color: "grey" },
};

function fileIcon(f: GitShowFile): { icon: string; color: string } {
  return FILE_ICON_MAP[f.status] ?? FILE_ICON_MAP.unknown;
}

function fileStatusLabel(s: GitShowFileStatus): string {
  return tm(
    `spcodeProjectLoad.diffSidebar.gitWorkflow.history.fileStatus.${s}`,
  );
}

/** Convert a rename/copy's `oldPath` + `similarity` into a single
 *  inline label. Returns null for non-rename / non-copy files. */
function renameLabel(f: GitShowFile): string | null {
  if ((f.status !== "R" && f.status !== "C") || !f.oldPath) return null;
  const similarity = f.similarity ?? 0;
  return tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.renameFrom", {
    old: f.oldPath,
    new: f.path,
    similarity,
  });
}

/** Per-commit error reason i18n key. Falls back to the raw reason
 *  string in the unlikely case the backend introduces a code we
 *  haven't localized yet. */
function fileErrorKey(reason: string): string {
  return `spcodeProjectLoad.diffSidebar.gitWorkflow.error.reason.${reason}`;
}

/** Extract a string reason from a `GitShowFetchState` discriminated
 *  union. Returns null for any non-error state. Used by the template
 *  (which can't run TypeScript `as` casts) to build the i18n key for
 *  the per-commit error message. */
function errorReasonOf(state: GitShowFetchState): string | null {
  if (state.kind === "error") return state.reason;
  return null;
}

/** Compose the user-facing error message for a per-commit file-load
 *  failure. Combines the "failed" prefix with the localized reason
 *  text. Returns null when the state is not an error. */
function fileErrorMessage(state: GitShowFetchState): string | null {
  const reason = errorReasonOf(state);
  if (reason === null) return null;
  return (
    tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.errorFiles") +
    ": " +
    tm(fileErrorKey(reason), { reason })
  );
}
</script>

<template>
  <div class="git-log-view">
    <!-- Truncation banner (spec §6.5.2) -->
    <div v-if="isTruncated" class="git-log-truncated">
      {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.truncated") }}
    </div>

        <!-- Filter bar (spec §6.5.1; search boxes → 12px, buttons → small) -->
    <div class="git-log-filter">
      <v-text-field
        v-model="localFilter.ref"
        :label="
          tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.ref')
        "
        :placeholder="
          tm(
            'spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.refPlaceholder',
          )
        "
        density="compact"
        variant="outlined"
        hide-details
        class="git-log-filter-field"
      />
      <v-text-field
        v-model="localFilter.author"
        :label="
          tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.author')
        "
        :placeholder="
          tm(
            'spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.authorPlaceholder',
          )
        "
        density="compact"
        variant="outlined"
        hide-details
        class="git-log-filter-field"
      />
      <v-text-field
        v-model="localFilter.path"
        :label="
          tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.path')
        "
        :placeholder="
          tm(
            'spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.pathPlaceholder',
          )
        "
        density="compact"
        variant="outlined"
        hide-details
        class="git-log-filter-field"
      />
      <v-text-field
        v-model="localFilter.since"
        :label="
          tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.since')
        "
        :placeholder="
          tm(
            'spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.sincePlaceholder',
          )
        "
        density="compact"
        variant="outlined"
        hide-details
        class="git-log-filter-field"
      />
      <v-text-field
        v-model.number="localFilter.n"
        :label="
          tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.n')
        "
        :placeholder="
          tm(
            'spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.nPlaceholder',
          )
        "
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
          size="small"
          variant="flat"
          color="primary"
          :loading="isLoading"
          @click="onApply"
        >
          {{
            tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.apply")
          }}
        </v-btn>
        <v-btn
          size="small"
          variant="text"
          :disabled="isLoading"
          @click="onReset"
        >
          {{
            tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.filter.reset")
          }}
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
        {{
          tm(
            "spcodeProjectLoad.diffSidebar.gitWorkflow.history.emptyRepository",
          )
        }}
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
              ? tm(
                  'spcodeProjectLoad.diffSidebar.gitWorkflow.history.collapseCommit',
                )
              : tm(
                  'spcodeProjectLoad.diffSidebar.gitWorkflow.history.expandCommit',
                )
          "
          @click="toggleCommit(c.sha)"
        >
          <v-icon size="14" class="git-log-item-icon">mdi-source-commit</v-icon>
          <span class="git-log-item-sha">{{
            c.shaShort || c.sha.slice(0, 7)
          }}</span>
          <span class="git-log-item-subject">{{ c.subject }}</span>
        </button>
        <div class="git-log-item-meta">
          <span class="git-log-item-author">{{ c.author.name }}</span>
          <span class="git-log-item-sep">·</span>
          <span class="git-log-item-time">{{
            formatRelativeTime(c.date)
          }}</span>
          <span class="git-log-item-sep">·</span>
          <!--
            v3.9 (2026-06-25, elecvoid243): split stat rendering so the
            additions/deletions numbers can take git-diff colors
            (green / red). The i18n `filesStat` key now only renders
            the "N files" prefix; the colored +/ − spans are appended
            inline below.
          -->
          <span class="git-log-item-stat">
            {{
              tm(
                "spcodeProjectLoad.diffSidebar.gitWorkflow.history.filesStat",
                { files: c.shortstat.files },
              )
            }}
            <span class="git-log-item-stat-add"
              >+{{ c.shortstat.additions }}</span
            >
            <span class="git-log-item-stat-del"
              >−{{ c.shortstat.deletions }}</span
            >
          </span>
        </div>
        <div v-if="expanded.has(c.sha) && c.body" class="git-log-item-body">
          <pre class="git-log-item-body-pre">{{ c.body }}</pre>
        </div>

        <!-- Changed files section (spec 2026-06-25 §3.3). Only rendered
             when the commit is expanded. Auto-fetches via the watch
             on `expanded` above; idempotent on the composable side. -->
        <div v-if="expanded.has(c.sha)" class="git-log-item-files">
          <div
            v-if="gitShow.getState(c.sha).kind === 'loading'"
            class="git-log-files-status"
          >
            <v-progress-circular indeterminate :size="14" :width="2" />
            <span class="git-log-files-status-text">
              {{
                tm(
                  "spcodeProjectLoad.diffSidebar.gitWorkflow.history.loadingFiles",
                )
              }}
            </span>
          </div>
          <div
            v-else-if="gitShow.getState(c.sha).kind === 'error'"
            class="git-log-files-status is-error"
          >
            <v-icon size="14" color="error">mdi-alert-circle-outline</v-icon>
            <span class="git-log-files-status-text">
              {{ fileErrorMessage(gitShow.getState(c.sha)) }}
            </span>
            <button
              type="button"
              class="git-log-files-retry"
              :aria-label="
                tm(
                  'spcodeProjectLoad.diffSidebar.gitWorkflow.history.errorFilesAria',
                )
              "
              @click="gitShow.fetch(c.sha)"
            >
              {{ tm("spcodeProjectLoad.diffSidebar.error.retry") }}
            </button>
          </div>
          <template v-else-if="gitShow.getState(c.sha).kind === 'ok'">
            <div
              v-if="(gitShow.getData(c.sha)?.files.length ?? 0) === 0"
              class="git-log-files-status"
            >
              <v-icon size="14" color="grey">mdi-file-outline</v-icon>
              <span class="git-log-files-status-text">
                {{
                  tm(
                    "spcodeProjectLoad.diffSidebar.gitWorkflow.history.noFiles",
                  )
                }}
              </span>
            </div>
            <ul v-else class="git-log-files-list" :data-sha="c.sha">
              <li
                v-for="f in gitShow.getData(c.sha)?.files ?? []"
                :key="f.path"
                class="git-log-files-item"
              >
                <!--
                  v3.9 (2026-06-25): file row is now interactive. The
                  button toggles a lazy-loaded patch panel below the
                  row. `aria-expanded` mirrors isFileExpanded so screen
                  readers announce the new state. `aria-label` uses a
                  dedicated i18n key with the path interpolated; falls
                  back to a generic key for non-renamed paths.
                -->
                <button
                  type="button"
                  class="git-log-files-item-button"
                  :aria-expanded="isFileExpanded(c.sha, f.path)"
                  :aria-label="
                    tm(
                      'spcodeProjectLoad.diffSidebar.gitWorkflow.history.expandFileAria',
                      { path: renameLabel(f) ?? f.path },
                    )
                  "
                  @click="toggleFile(c.sha, f.path)"
                >
                  <v-icon :size="14" :color="fileIcon(f).color">
                    {{ fileIcon(f).icon }}
                  </v-icon>
                  <!-- Status label: localized via fileStatus.<status> key.
                       The label is informational; screen readers also get
                       the title="..." attribute that duplicates the label
                       plus the file path for full context. -->
                  <span
                    class="git-log-files-status-badge"
                    :title="fileStatusLabel(f.status)"
                  >
                    {{ fileStatusLabel(f.status) }}
                  </span>
                  <!-- For R / C: show the "old → new (similarity%)" label
                       inline instead of the bare `f.path`, so the rename
                       source is visible without needing a tooltip. Other
                       statuses render the plain path. -->
                  <span v-if="renameLabel(f)" class="git-log-files-path">{{
                    renameLabel(f)
                  }}</span>
                  <span v-else class="git-log-files-path" :title="f.path">{{
                    f.path
                  }}</span>
                  <span class="git-log-files-stats">
                    <span class="git-log-files-add">+{{ f.additions }}</span>
                    <span class="git-log-files-del">−{{ f.deletions }}</span>
                  </span>
                  <!-- Chevron indicator: up = expanded, down = collapsed.
                       Uses a literal mdi name to avoid pulling in extra
                       icon components; the row button already handles
                       click semantics. -->
                  <v-icon :size="14" class="git-log-files-chevron">
                    {{
                      isFileExpanded(c.sha, f.path)
                        ? "mdi-chevron-up"
                        : "mdi-chevron-down"
                    }}
                  </v-icon>
                </button>
                <!--
                  v3.9: lazy-loaded patch panel. States mirror the
                  composable's GitShowFileFetchState enum:
                    loading → spinner
                    error   → reason message + retry
                    ok      → DiffPreview (or fallback for binary/unknown)
                  We always render the panel container (not v-if) so
                  ARIA `aria-expanded` on the button stays consistent
                  with the visual layout; the inner content swaps
                  per-state.
                -->
                <div
                  v-if="isFileExpanded(c.sha, f.path)"
                  class="git-log-files-patch"
                >
                  <FilePatchPanel
                    :sha="c.sha"
                    :path="f.path"
                    :state="gitShow.getFileState(c.sha, f.path)"
                    :data="gitShow.getFileData(c.sha, f.path)"
                    @retry="gitShow.fetchFile(c.sha, f.path)"
                  />
                </div>
              </li>
            </ul>
            <div
              v-if="gitShow.getData(c.sha)?.truncated"
              class="git-log-files-truncated"
            >
              {{
                tm(
                  "spcodeProjectLoad.diffSidebar.gitWorkflow.history.filesTruncated",
                  {
                    shown: gitShow.getData(c.sha)?.count ?? 0,
                    total:
                      (gitShow.getData(c.sha)?.count ?? 0) +
                      // `count` is the returned count; the API doesn't
                      // expose the post-truncation hidden count, so we
                      // render "showing N of N+". The user can re-query
                      // with a higher max_files if needed.
                      0,
                    max: gitShow.getData(c.sha)?.maxFiles ?? 500,
                  },
                )
              }}
            </div>
          </template>
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
  /* Match the commit subject (.git-log-item-subject) so the filter
     row visually aligns with the history list below it. Reduced to
     12px (from 13px) to feel proportional next to the commit rows
     that use 11.5-13px text. */
  font-size: 12px;
}
.git-log-filter-field :deep(.v-field__input),
.git-log-filter-field :deep(.v-label) {
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
/* v3.9 (2026-06-25, elecvoid243): color the additions / deletions
   counters in the commit summary to match the diff-view palette so
   users can scan "+N" / "−N" deltas at a glance. Light-mode values
   mirror GitHub's diff colors; the dark-mode override below uses
   the brighter variants (matches DiffPreview). */
.git-log-item-stat-add {
  color: #2da44e;
  font-weight: 500;
}
.git-log-item-stat-del {
  color: #cf222e;
  font-weight: 500;
  margin-left: 4px;
}
/* Vuetify toggles `v-theme--dark` on the html root when the active
   theme is dark — use that selector (matches the rest of the
   dashboard, e.g. ConfigPage/ConversationPage) instead of the
   OS-level media query. */
.v-theme--dark .git-log-item-stat-add {
  color: #57ab5a;
}
.v-theme--dark .git-log-item-stat-del {
  color: #f47067;
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

/* ── Changed files section (spec 2026-06-25 §3.3) ──────────── */

.git-log-item-files {
  /* Indented to align with the commit body / meta text. The same
     20px gutter as .git-log-item-body keeps the visual rhythm
     consistent across the expanded state. */
  margin-top: 6px;
  padding-left: 20px;
}

.git-log-files-status {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 12px;
}
.git-log-files-status.is-error {
  color: rgb(248, 81, 73);
}
.git-log-files-status-text {
  flex: 1;
  min-width: 0;
}
.git-log-files-retry {
  background: transparent;
  border: 1px solid currentColor;
  border-radius: 4px;
  padding: 1px 8px;
  cursor: pointer;
  color: inherit;
  font-family: inherit;
  font-size: 11px;
  flex-shrink: 0;
}
.git-log-files-retry:hover {
  background: rgba(248, 81, 73, 0.1);
}

.git-log-files-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.git-log-files-item {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
  padding: 3px 6px;
  border-radius: 4px;
  font-size: 12px;
  /* Subtle hover so the row feels interactive even though clicking
     it does nothing in the history view (the diff view is the right
     place to inspect / restore). Matches the row density of the
     diff view's GitDiffFileItem without inheriting its full style. */
  transition: background 0.12s ease;
}
.git-log-files-item:hover {
  background: transparent;
}
/* The row is now a <button> for accessibility — keep its inner items
   on a single line (badge / path / stats / chevron) by turning the
   button itself into a flex container. v3.9 (2026-06-25). */
.git-log-files-item-button {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 3px 6px;
  border-radius: 4px;
  font-size: 12px;
  background: transparent;
  border: none;
  color: inherit;
  text-align: left;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.12s ease;
}
.git-log-files-item-button:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.git-log-files-item-button:focus-visible {
  outline: 2px solid rgba(var(--v-theme-primary), 0.5);
  outline-offset: -2px;
}
.git-log-files-chevron {
  margin-left: auto;
  flex-shrink: 0;
  transition: transform 0.15s ease;
}
.git-log-files-status-badge {
  display: inline-block;
  min-width: 28px;
  text-align: center;
  padding: 1px 4px;
  border-radius: 3px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  flex-shrink: 0;
}
.git-log-files-path {
  flex: 1;
  min-width: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.85);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.git-log-files-stats {
  display: flex;
  gap: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  flex-shrink: 0;
}
.git-log-files-add {
  color: rgb(46, 160, 67);
}
.git-log-files-del {
  color: rgb(248, 81, 73);
}

.git-log-files-truncated {
  margin-top: 4px;
  padding: 4px 6px;
  background: rgba(255, 193, 7, 0.1);
  color: rgb(255, 152, 0);
  font-size: 11px;
  border-radius: 3px;
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
