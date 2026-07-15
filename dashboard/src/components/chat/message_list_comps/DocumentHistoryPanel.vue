<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.5
     Per-file commit list. Reuses the parent's useSpcodeGitLog
     instance with `?path=` filter. Each row has two actions:
     "view this revision" + "compare with current". A pseudo row
     for the working tree is always shown. -->
<script setup lang="ts">
import { computed, inject, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { UseSpcodeGitLog } from "@/composables/useSpcodeGitLog";
import type { SpcodeLogCommit } from "@/composables/parseSpcodeGitWorkflow";

const props = defineProps<{
  gitLog: UseSpcodeGitLog;
  fileRelative: string | null;
  currentRevision: string | null;
  isLoading: boolean;
}>();
const emit = defineEmits<{
  (e: "select-revision", sha: string): void;
  (e: "compare-current", sha: string): void;
  (e: "collapse"): void;
}>();
const { tm } = useModuleI18n("features/chat");

watch(
  () => props.fileRelative,
  (p) => {
    if (!p) return;
    void props.gitLog.refresh({ ref: "HEAD", n: 50, path: p });
  },
  { immediate: true },
);

const commits = computed<SpcodeLogCommit[]>(() => {
  const s = props.gitLog.state.value;
  if (s.kind === "ok") return s.snapshot.commits;
  if (s.kind === "error") {
    return s.previousSnapshot?.commits ?? [];
  }
  return [];
});

const errorReason = computed<string | null>(() => {
  const s = props.gitLog.state.value;
  return s.kind === "error" ? s.reason : null;
});

const isWorkingTreeActive = computed(
  () => props.currentRevision === null && !!props.fileRelative,
);

function shortSha(sha: string): string {
  return sha.slice(0, 7);
}

/**
 * 2026-07-15 history-sha-jump: clicking the SHA jumps the user
 * to the global Git Log tab with that commit highlighted + scrolled
 * into view. The inject key is provided by <GitDiffSidebar>; both
 * <FileBrowserView> (workspace tab) and <DocumentManager> (docs
 * tab) sit inside it, so the same handler covers both surfaces.
 *
 * The noop default keeps this component reusable in isolation
 * (stories / tests where the sidebar isn't mounted).
 */
const focusCommit = inject<(sha: string) => void>(
  "spcode:focusCommit",
  () => {},
);
function onShaClick(sha: string): void {
  // .stop so the row's own click semantics (none today, but the
  // row uses `cursor: default` for now) don't get tangled with
  // future row-level handlers — the action buttons (view /
  // compare) are separate elements with their own listeners.
  focusCommit(sha);
}
</script>

<template>
  <aside class="document-history-panel">
    <header class="document-history-panel__header">
      <span>{{ tm("spcodeProjectLoad.documentManager.history.title") }}</span>
      <!--
        Collapse affordance lives INSIDE the panel so its absolute
        positioning anchors to the panel itself (which carries
        position: relative). Placing it in the parent DocumentManager
        with a hard-coded `right: 226px` was fragile — when the
        history width changed the button drifted, and when the body
        lacked a `position: relative` ancestor it could escape to
        the entire dashboard container and end up in the wrong place
        (top-center of the chat area).
      -->
      <button
        type="button"
        class="document-history-panel__collapse"
        data-testid="document-history-collapse"
        :title="tm('spcodeProjectLoad.documentManager.pane.collapseHistory')"
        :aria-label="tm('spcodeProjectLoad.documentManager.pane.collapseHistory')"
        @click="emit('collapse')"
      >
        <v-icon size="14">mdi-chevron-double-right</v-icon>
      </button>
    </header>
    <div v-if="!fileRelative" class="document-history-panel__empty">
      <!-- 2026-07-15 document-history-empty: this is the *history*
           pane's idle state ("no file picked"), not the file-tree's
           "directory has no .md files" state. Using tree.empty here
           was misleading because the user is looking at a right-side
           panel with no file context, not a folder listing. -->
      {{ tm("spcodeProjectLoad.documentManager.history.noSelection") }}
    </div>
    <div v-else-if="isLoading" class="document-history-panel__loading">
      <v-progress-circular indeterminate size="16" width="2" />
    </div>
    <div v-else-if="errorReason && commits.length === 0" class="document-history-panel__error">
      {{ tm("spcodeProjectLoad.documentManager.history.loadFail") }}: {{ errorReason }}
    </div>
    <div v-else-if="commits.length === 0" class="document-history-panel__empty">
      {{ tm("spcodeProjectLoad.documentManager.tree.noHistory") }}
    </div>
    <ul v-else class="document-history-panel__list">
      <li
        :class="['document-history-panel__row', { active: isWorkingTreeActive }]"
      >
        <div class="document-history-panel__row-sha">working</div>
        <div class="document-history-panel__row-subject">
          {{ tm("spcodeProjectLoad.documentManager.history.currentPlaceholder") }}
        </div>
      </li>
      <li
        v-for="c in commits"
        :key="c.sha"
        :class="['document-history-panel__row', { active: currentRevision === c.sha }]"
      >
        <!--
          2026-07-15 history-sha-jump: the SHA is now an
          interactive control. Clicking it jumps to the global Git
          Log tab with this commit highlighted and scrolled into
          view (handled by <GitLogView>'s `focusedCommitSha` prop
          + watcher). The `__row-sha-link` modifier carries the
          click/hover affordances; the base `__row-sha` class is
          kept so the existing 56px column / monospace font /
          muted color stay byte-identical to the previous span.
        -->
        <button
          type="button"
          class="document-history-panel__row-sha document-history-panel__row-sha-link"
          :title="c.sha"
          :aria-label="
            tm(
              'spcodeProjectLoad.documentManager.history.jumpToCommit',
              { sha: shortSha(c.sha) },
            )
          "
          @click.stop="onShaClick(c.sha)"
        >
          {{ shortSha(c.sha) }}
        </button>
        <div class="document-history-panel__row-subject">
          <div class="document-history-panel__row-subject-text">{{ c.subject }}</div>
          <div class="document-history-panel__row-author">{{ c.author }}</div>
        </div>
        <div class="document-history-panel__row-actions">
          <button
            type="button"
            class="document-history-panel__action"
            :title="tm('spcodeProjectLoad.documentManager.history.viewThisRevision')"
            @click="emit('select-revision', c.sha)"
          >
            <v-icon size="12">mdi-eye-outline</v-icon>
          </button>
          <button
            type="button"
            class="document-history-panel__action"
            :title="tm('spcodeProjectLoad.documentManager.history.compareWithCurrent')"
            @click="emit('compare-current', c.sha)"
          >
            <v-icon size="12">mdi-compare</v-icon>
          </button>
        </div>
      </li>
    </ul>
  </aside>
</template>

<style scoped>
.document-history-panel {
  display: flex;
  flex-direction: column;
  flex: 0 0 220px;
  min-height: 0;
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  background: rgba(var(--v-theme-on-surface), 0.03);
  overflow: hidden;
  position: relative;
}
.document-history-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.document-history-panel__collapse {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  background: transparent;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 4px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  cursor: pointer;
  padding: 0;
  transition:
    background 0.1s ease,
    color 0.1s ease,
    border-color 0.1s ease;
}
.document-history-panel__collapse:hover,
.document-history-panel__collapse:focus-visible {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
  border-color: rgba(var(--v-theme-primary), 0.4);
  outline: none;
}
.document-history-panel__empty,
.document-history-panel__loading,
.document-history-panel__error {
  padding: 12px 10px;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  text-align: center;
}
.document-history-panel__error {
  color: rgb(var(--v-theme-error));
}
.document-history-panel__list {
  list-style: none;
  margin: 0;
  padding: 4px 0;
  overflow-y: auto;
  flex: 1 1 auto;
  min-height: 0;
}

.document-history-panel__row {
  display: grid;
  grid-template-columns: 56px 1fr auto;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  font-size: 11.5px;
  cursor: default;
  border-left: 2px solid transparent;
}
.document-history-panel__row:hover {
  background: rgba(var(--v-theme-primary), 0.06);
}
.document-history-panel__row.active {
  background: rgba(var(--v-theme-primary), 0.12);
  border-left-color: rgb(var(--v-theme-primary));
}
.document-history-panel__row-sha {
  font-family: monospace;
  color: rgba(var(--v-theme-on-surface), 0.55);
}
/* 2026-07-15 history-sha-jump: the SHA is rendered as a button
   that jumps to the global Git log. Resets the default button
   chrome and matches the previous text styling so the rest of
   the row layout is byte-identical when no link class is
   applied (e.g. the "working" pseudo row). The 56px grid
   column is already very tight (the 7-char shortSha barely
   fits) so we keep padding/min-width off and let `width: 100%`
   cover the cell. The full SHA is on the title attribute. */
.document-history-panel__row-sha-link {
  border: none;
  background: transparent;
  padding: 0;
  margin: 0;
  /* `font: inherit` re-applies the row's `font-size: 11.5px`
     and the document's default `font-family`; restore the
     monospace family the base `__row-sha` class set so the
     short SHA renders the same as the original span. */
  font: inherit;
  font-family: monospace;
  color: inherit;
  text-align: left;
  width: 100%;
  cursor: pointer;
  border-radius: 3px;
  transition:
    background 0.1s ease,
    color 0.1s ease;
}
.document-history-panel__row-sha-link:hover,
.document-history-panel__row-sha-link:focus-visible {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
  outline: none;
}
/* Active row's blue background swallows the hover background —
   keep the link color readable instead. */
.document-history-panel__row.active
  .document-history-panel__row-sha-link,
.document-history-panel__row.active
  .document-history-panel__row-sha-link:hover {
  color: rgb(var(--v-theme-primary));
}
.document-history-panel__row-subject {
  min-width: 0;
  overflow: hidden;
}
.document-history-panel__row-subject-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.document-history-panel__row-author {
  font-size: 10.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.document-history-panel__row-actions {
  display: flex;
  gap: 2px;
}
.document-history-panel__action {
  border: none;
  background: transparent;
  padding: 2px;
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.55);
  display: flex;
  align-items: center;
  border-radius: 3px;
}
.document-history-panel__action:hover {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}
</style>
