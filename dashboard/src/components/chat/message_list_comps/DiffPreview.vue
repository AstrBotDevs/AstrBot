<!-- Author: elecvoid243, 2026-06-28
     Added viewMode toggle (Unified / Split) for diff rendering.
     The split mode aligns del/add lines into a two-column layout
     (old on the left, new on the right), matching the standard
     side-by-side diff view (e.g. GitHub's split diff).

     All five call sites (ToolCallCard, GitDiffFileItem,
     FilePatchPanel, FileDiffResult, ThemeAwareMarkdownCodeBlock)
     automatically pick up the new toggle since it lives inside
     DiffPreview itself. The user choice is persisted to
     localStorage so it survives reloads. -->
<template>
  <div
    class="diff-preview"
    :class="{ 'is-dark': isDark, collapsed: isCollapsed, 'is-split': viewMode === 'split' }"
  >
    <!-- Summary header — always visible, clickable to toggle -->
    <button
      v-if="summary || filePath || statsAdds || statsDels"
      type="button"
      class="diff-header"
      @click="toggleCollapsed"
    >
      <div class="diff-header-left">
        <v-icon size="16" class="diff-header-icon"
          >mdi-file-document-edit-outline</v-icon
        >
        <span v-if="filePath" class="diff-file-path">{{ filePath }}</span>
      </div>
      <div class="diff-header-right">
        <template v-if="statsAdds || statsDels">
          <span v-if="statsAdds" class="diff-stats diff-stats-add"
            >+{{ statsAdds }}</span
          >
          <span v-if="statsDels" class="diff-stats diff-stats-del"
            >−{{ statsDels }}</span
          >
        </template>
        <!-- Unified / Split segmented toggle. Sits inside the header
             so it is always reachable, even when the body is collapsed.
             Stops propagation so clicking a button does not also toggle
             the body collapse. -->
        <div
          class="diff-view-toggle"
          role="group"
          :aria-label="viewModeAriaLabel"
        >
          <button
            type="button"
            class="diff-view-toggle-btn"
            :class="{ active: viewMode === 'unified' }"
            :aria-pressed="viewMode === 'unified'"
            :title="unifiedLabel"
            @click.stop="setViewMode('unified')"
          >
            <v-icon size="14">mdi-format-align-justify</v-icon>
          </button>
          <button
            type="button"
            class="diff-view-toggle-btn"
            :class="{ active: viewMode === 'split' }"
            :aria-pressed="viewMode === 'split'"
            :title="splitLabel"
            @click.stop="setViewMode('split')"
          >
            <v-icon size="14">mdi-view-split-vertical</v-icon>
          </button>
        </div>
        <!-- Fullscreen button (spec 2026-06-30-diff-fullscreen-design.md §3.1) -->
        <button
          ref="fullscreenBtnRef"
          type="button"
          class="diff-fullscreen-btn"
          :title="tm('diffPreview.fullscreen.enter')"
          :aria-label="tm('diffPreview.fullscreen.enter')"
          @click.stop="enterFullscreen"
        >
          <v-icon size="14">mdi-fullscreen</v-icon>
        </button>
        <v-icon
          v-if="collapsible"
          size="18"
          class="diff-chevron"
          :class="{ expanded: !isCollapsed }"
        >
          mdi-chevron-right
        </v-icon>
      </div>
    </button>

    <!-- Summary text (e.g. "Replaced 1 occurrence(s)...") -->
    <div v-if="summary && !isCollapsed" class="diff-summary-text">
      {{ summary }}
    </div>

    <!-- Diff hunks — hidden when collapsed -->
    <div v-if="!isCollapsed" class="diff-body">
      <div v-if="truncated" class="diff-truncation-warning">
        ⚠ Diff truncated (showing first
        {{ maxChars.toLocaleString() }} characters)
      </div>

      <!-- Unified mode: the original single-column layout.
           UI #8: hunk headers are now clickable buttons that fold /
           unfold the hunk. State is local to the component so a
           re-mount (file change) resets all folds — matches the
           "expansion state is per-file" mental model. -->
      <template v-if="viewMode === 'unified'">
        <div
          v-for="(hunk, hi) in parsedHunks"
          :key="hi"
          class="diff-hunk"
          :class="{ 'is-hunk-folded': collapsedHunks.has(hi) }"
        >
          <button
            type="button"
            class="hunk-header"
            :aria-expanded="!collapsedHunks.has(hi)"
            @click="toggleHunk(hi)"
          >
            <v-icon
              size="12"
              class="hunk-chevron"
              :class="{ expanded: !collapsedHunks.has(hi) }"
            >
              mdi-chevron-right
            </v-icon>
            <span class="hunk-header-text">{{ hunk.header }}</span>
            <span class="hunk-header-count">
              {{ hunk.lines.length }}
            </span>
          </button>
          <div
            v-show="!collapsedHunks.has(hi)"
            class="diff-hunk-body"
          >
            <div
              v-for="(line, li) in hunk.lines"
              :key="li"
              class="diff-line"
              :class="[
                line.type,
                {
                  'has-comment': isCommentable &&
                    !!line.newNo &&
                    commentsByNewLine.has(Number(line.newNo)),
                  'is-hovered': isCommentable &&
                    !!line.newNo &&
                    hoveredUnifiedLine === Number(line.newNo) &&
                    hoveredUnifiedHunk === hi,
                },
              ]"
              @mouseenter="onUnifiedRowEnter(line, hi)"
              @mouseleave="onUnifiedRowLeave"
            >
              <!-- Inline-comment gutter: only on lines that exist in
                   the new file (ctx / add). Always rendered (even
                   when invisible) so the layout doesn't shift when
                   the user hovers in. Positioned as the FIRST child
                   of .diff-line so it sits at the left edge. -->
              <span
                v-if="isCommentable && line.newNo"
                class="diff-line-gutter"
              >
                <button
                  v-if="hoveredUnifiedLine === Number(line.newNo) &&
                    hoveredUnifiedHunk === hi &&
                    !commentsByNewLine.has(Number(line.newNo))"
                  type="button"
                  class="diff-comment-add"
                  :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.addButtonAria', { line: line.newNo })"
                  @click.stop="openNewEditor(Number(line.newNo))"
                >+</button>
                <button
                  v-else-if="commentsByNewLine.has(Number(line.newNo))"
                  type="button"
                  class="diff-comment-indicator"
                  :title="commentsByNewLine.get(Number(line.newNo))?.text ?? ''"
                  :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.indicatorAria', {
                    line: line.newNo,
                    preview: commentsByNewLine.get(Number(line.newNo))?.text ?? '',
                  })"
                  @click.stop="openEditEditor(commentsByNewLine.get(Number(line.newNo))?.id ?? '')"
                >
                  <v-icon size="12">mdi-comment-text-outline</v-icon>
                </button>
              </span>
              <span class="line-number old">{{ line.oldNo }}</span>
              <span class="line-number new">{{ line.newNo }}</span>
              <span class="line-prefix">{{ line.prefix }}</span>
              <span class="line-content">{{ line.content }}</span>
            </div>
          </div>
        </div>
      </template>

      <!-- Split mode: two-column layout, del/add lines are paired
           into rows by alignHunkLines. A row with a missing side
           keeps the cell empty so the visual columns stay aligned.
           The inline-comment gutter is anchored to the RIGHT cell
           (the new-side column) so we don't have to decide what
           "the line" means on a row with two distinct contents.

           UI #8 (symmetric to unified mode): the hunk header is a
           button that folds/unfolds the body. We share the same
           `collapsedHunks` Set with the unified view, so a fold
           decision carries over when the user toggles view modes
           mid-review (no UX surprise). The row v-for is wrapped in
           `.diff-hunk-body` so a single `v-show` collapses the
           whole hunk at once — rows stay in the DOM, preserving
           scroll position and any in-progress comment hover state
           when the user re-expands. -->
      <template v-else>
        <div
          v-for="(hunk, hi) in splitHunks"
          :key="hi"
          class="diff-hunk diff-hunk-split"
          :class="{ 'is-hunk-folded': collapsedHunks.has(hi) }"
        >
          <button
            type="button"
            class="hunk-header"
            :aria-expanded="!collapsedHunks.has(hi)"
            @click="toggleHunk(hi)"
          >
            <v-icon
              size="12"
              class="hunk-chevron"
              :class="{ expanded: !collapsedHunks.has(hi) }"
            >
              mdi-chevron-right
            </v-icon>
            <span class="hunk-header-text">{{ hunk.header }}</span>
            <span class="hunk-header-count">{{ hunk.rows.length }}</span>
          </button>
          <div
            v-show="!collapsedHunks.has(hi)"
            class="diff-hunk-body"
          >
            <div
              v-for="(row, ri) in hunk.rows"
              :key="ri"
              class="diff-row-split"
              :class="[
                row.kind,
                {
                  'has-comment': isCommentable &&
                    !!row.right?.newNo &&
                    commentsByNewLine.has(Number(row.right.newNo)),
                  // Hunk index guard: `ri` is the row index WITHIN
                  // this hunk, so two hunks with a row at the same
                  // offset would otherwise both light up. Pairing
                  // (hi, ri) makes the key globally unique.
                  'is-hovered': isCommentable &&
                    !!row.right?.newNo &&
                    hoveredSplitRow === ri &&
                    hoveredSplitHunk === hi,
                },
              ]"
              @mouseenter="onSplitRowEnter(ri, row, hi)"
              @mouseleave="onSplitRowLeave"
            >
              <div class="diff-cell left">
                <span class="line-number">{{ row.left?.oldNo ?? '' }}</span>
                <span class="line-prefix">{{ row.left?.prefix ?? '' }}</span>
                <span class="line-content">{{ row.left?.content ?? '' }}</span>
              </div>
              <div class="diff-cell right">
                <!-- Inline-comment gutter: first child of the right
                     cell, absolutely positioned to the left edge via
                     CSS. Only on rows that have a new-side line. -->
                <span
                  v-if="isCommentable && row.right?.newNo"
                  class="diff-line-gutter"
                >
                  <button
                    v-if="hoveredSplitRow === ri &&
                      hoveredSplitHunk === hi &&
                      !commentsByNewLine.has(Number(row.right!.newNo))"
                    type="button"
                    class="diff-comment-add"
                    :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.addButtonAria', { line: row.right!.newNo })"
                    @click.stop="openNewEditor(Number(row.right!.newNo))"
                  >+</button>
                  <button
                    v-else-if="commentsByNewLine.has(Number(row.right!.newNo))"
                    type="button"
                    class="diff-comment-indicator"
                    :title="commentsByNewLine.get(Number(row.right!.newNo))?.text ?? ''"
                    :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.indicatorAria', {
                      line: row.right!.newNo,
                      preview: commentsByNewLine.get(Number(row.right!.newNo))?.text ?? '',
                    })"
                    @click.stop="openEditEditor(commentsByNewLine.get(Number(row.right!.newNo))?.id ?? '')"
                  >
                    <v-icon size="12">mdi-comment-text-outline</v-icon>
                  </button>
                </span>
                <span class="line-number">{{ row.right?.newNo ?? '' }}</span>
                <span class="line-prefix">{{ row.right?.prefix ?? '' }}</span>
                <span class="line-content">{{ row.right?.content ?? '' }}</span>
              </div>
            </div>
          </div>
        </div>
      </template>

      <div v-if="collapsedOverflow > 0" class="diff-overflow-bar">
        <button
          type="button"
          class="diff-show-more"
          @click="showAllLines = true"
        >
          Show all {{ totalLines.toLocaleString() }} lines ({{
            collapsedOverflow
          }}
          more)
        </button>
      </div>
    </div>

    <!-- Inline-comment editor. Rendered inside the preview root (as
         a sibling of the body) so it scrolls together with the
         diff in the parent container. Hidden when the diff is
         collapsed — there's no point editing a comment the user
         can't see the context for. `v-if` (not v-show) so a closed
         editor fully tears down its DOM (and the textarea's
         keydown listener). -->
    <FileCommentEditor
      v-if="!isCollapsed && activeEditLine !== null && isCommentable"
      :line="activeEditLine"
      :comment-id="activeEditCommentId"
      :initial-text="editorInitialText"
      :line-content="editorContext?.lineContent ?? null"
      :context-before="editorContext?.contextBefore ?? null"
      :context-after="editorContext?.contextAfter ?? null"
      :file-path="filePath"
      @save="onSaveComment"
      @cancel="closeEditor"
      @delete="onDeleteComment"
    />
  </div>

  <!-- Fullscreen overlay — Teleported to <body> to escape fixed-position
       stacking contexts. Shares same reactive refs as normal view.
       Spec 2026-06-30-diff-fullscreen-design.md §3.2 -->
  <Teleport to="body">
    <div
      v-if="isFullscreen"
      ref="overlayRef"
      class="diff-fullscreen-overlay"
      role="dialog"
      aria-modal="true"
      :aria-label="tm('diffPreview.fullscreen.ariaLabel')"
      tabindex="-1"
      @keydown.escape="exitFullscreen"
    >
      <!-- Back button: fixed top-right corner -->
      <button
        type="button"
        class="diff-fullscreen-back-btn"
        :title="tm('diffPreview.fullscreen.exit')"
        :aria-label="tm('diffPreview.fullscreen.exit')"
        @click="exitFullscreen"
      >
        <v-icon size="20">mdi-fullscreen-exit</v-icon>
        <span class="diff-fullscreen-back-label">{{
          tm("diffPreview.fullscreen.exitLabel")
        }}</span>
      </button>

      <!-- Fullscreen diff content — same refs as normal view.
           The header and diff body are re-rendered here so they appear
           inside the overlay. The isFullscreen ref is shared, so
           clicking the fullscreen button inside the overlay is a
           no-op (the button is at the normal view and is not rendered
           here because it is behind the overlay). -->
      <div class="diff-fullscreen-body">
        <div
          class="diff-preview is-fullscreen"
          :class="{ 'is-dark': isDark, collapsed: isCollapsed, 'is-split': viewMode === 'split' }"
        >
          <!-- Same header — the fullscreen button in the normal header
               is behind the overlay, so it doesn't appear here. -->
          <button
            v-if="summary || filePath || statsAdds || statsDels"
            type="button"
            class="diff-header"
            @click="toggleCollapsed"
          >
            <div class="diff-header-left">
              <v-icon size="16" class="diff-header-icon"
                >mdi-file-document-edit-outline</v-icon
              >
              <span v-if="filePath" class="diff-file-path">{{ filePath }}</span>
            </div>
            <div class="diff-header-right">
              <template v-if="statsAdds || statsDels">
                <span v-if="statsAdds" class="diff-stats diff-stats-add"
                  >+{{ statsAdds }}</span
                >
                <span v-if="statsDels" class="diff-stats diff-stats-del"
                  >−{{ statsDels }}</span
                >
              </template>
              <div
                class="diff-view-toggle"
                role="group"
                :aria-label="viewModeAriaLabel"
              >
                <button
                  type="button"
                  class="diff-view-toggle-btn"
                  :class="{ active: viewMode === 'unified' }"
                  :aria-pressed="viewMode === 'unified'"
                  :title="unifiedLabel"
                  @click.stop="setViewMode('unified')"
                >
                  <v-icon size="14">mdi-format-align-justify</v-icon>
                </button>
                <button
                  type="button"
                  class="diff-view-toggle-btn"
                  :class="{ active: viewMode === 'split' }"
                  :aria-pressed="viewMode === 'split'"
                  :title="splitLabel"
                  @click.stop="setViewMode('split')"
                >
                  <v-icon size="14">mdi-view-split-vertical</v-icon>
                </button>
              </div>
              <!-- Fullscreen button is intentionally omitted here:
                   the overlay has its own "Back" exit button above. -->
              <v-icon
                v-if="collapsible"
                size="18"
                class="diff-chevron"
                :class="{ expanded: !isCollapsed }"
              >
                mdi-chevron-right
              </v-icon>
            </div>
          </button>

          <!-- Summary text -->
          <div v-if="summary && !isCollapsed" class="diff-summary-text">
            {{ summary }}
          </div>

          <!-- Diff body -->
          <div v-if="!isCollapsed" class="diff-body">
            <div v-if="truncated" class="diff-truncation-warning">
              ⚠ Diff truncated (showing first
              {{ maxChars.toLocaleString() }} characters)
            </div>

            <!-- Unified mode (fullscreen copy) -->
            <template v-if="viewMode === 'unified'">
              <div
                v-for="(hunk, hi) in parsedHunks"
                :key="hi"
                class="diff-hunk"
                :class="{ 'is-hunk-folded': collapsedHunks.has(hi) }"
              >
                <button
                  type="button"
                  class="hunk-header"
                  :aria-expanded="!collapsedHunks.has(hi)"
                  @click="toggleHunk(hi)"
                >
                  <v-icon
                    size="12"
                    class="hunk-chevron"
                    :class="{ expanded: !collapsedHunks.has(hi) }"
                  >
                    mdi-chevron-right
                  </v-icon>
                  <span class="hunk-header-text">{{ hunk.header }}</span>
                  <span class="hunk-header-count">{{
                    hunk.lines.length
                  }}</span>
                </button>
                <div
                  v-show="!collapsedHunks.has(hi)"
                  class="diff-hunk-body"
                >
                  <div
                    v-for="(line, li) in hunk.lines"
                    :key="li"
                    class="diff-line"
                    :class="[
                      line.type,
                      {
                        'has-comment': isCommentable &&
                          !!line.newNo &&
                          commentsByNewLine.has(Number(line.newNo)),
                        // Fullscreen copy mirrors the normal view:
                        // hunk guard scopes the hover to the
                        // hunk the cursor is in.
                        'is-hovered': isCommentable &&
                          !!line.newNo &&
                          hoveredUnifiedLine === Number(line.newNo) &&
                          hoveredUnifiedHunk === hi,
                      },
                    ]"
                    @mouseenter="onUnifiedRowEnter(line, hi)"
                    @mouseleave="onUnifiedRowLeave"
                  >
                    <span
                      v-if="isCommentable && line.newNo"
                      class="diff-line-gutter"
                    >
                      <button
                        v-if="hoveredUnifiedLine === Number(line.newNo) &&
                          hoveredUnifiedHunk === hi &&
                          !commentsByNewLine.has(Number(line.newNo))"
                        type="button"
                        class="diff-comment-add"
                        :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.addButtonAria', { line: line.newNo })"
                        @click.stop="openNewEditor(Number(line.newNo))"
                      >+</button>
                      <button
                        v-else-if="commentsByNewLine.has(Number(line.newNo))"
                        type="button"
                        class="diff-comment-indicator"
                        :title="commentsByNewLine.get(Number(line.newNo))?.text ?? ''"
                        :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.indicatorAria', {
                          line: line.newNo,
                          preview: commentsByNewLine.get(Number(line.newNo))?.text ?? '',
                        })"
                        @click.stop="openEditEditor(commentsByNewLine.get(Number(line.newNo))?.id ?? '')"
                      >
                        <v-icon size="12">mdi-comment-text-outline</v-icon>
                      </button>
                    </span>
                    <span class="line-number old">{{ line.oldNo }}</span>
                    <span class="line-number new">{{ line.newNo }}</span>
                    <span class="line-prefix">{{ line.prefix }}</span>
                    <span class="line-content">{{ line.content }}</span>
                  </div>
                </div>
              </div>
            </template>

            <!-- Split mode (fullscreen copy). Mirrors the normal
                 view: same `collapsedHunks` Set, same toggleHunk
                 handler, same hunk-header button. Keeping the two
                 views symmetric means the user's fold decisions
                 survive the fullscreen toggle, and full-screen +
                 folded hunks give a "scannable overview of hunks"
                 mode not available elsewhere. -->
            <template v-else>
              <div
                v-for="(hunk, hi) in splitHunks"
                :key="hi"
                class="diff-hunk diff-hunk-split"
                :class="{ 'is-hunk-folded': collapsedHunks.has(hi) }"
              >
                <button
                  type="button"
                  class="hunk-header"
                  :aria-expanded="!collapsedHunks.has(hi)"
                  @click="toggleHunk(hi)"
                >
                  <v-icon
                    size="12"
                    class="hunk-chevron"
                    :class="{ expanded: !collapsedHunks.has(hi) }"
                  >
                    mdi-chevron-right
                  </v-icon>
                  <span class="hunk-header-text">{{ hunk.header }}</span>
                  <span class="hunk-header-count">{{ hunk.rows.length }}</span>
                </button>
                <div
                  v-show="!collapsedHunks.has(hi)"
                  class="diff-hunk-body"
                >
                  <div
                    v-for="(row, ri) in hunk.rows"
                    :key="ri"
                    class="diff-row-split"
                    :class="[
                      row.kind,
                      {
                        'has-comment': isCommentable &&
                          !!row.right?.newNo &&
                          commentsByNewLine.has(Number(row.right.newNo)),
                        // Fullscreen copy mirrors the normal view:
                        // hunk guard scopes the hover to the hunk
                        // the cursor is in. (Bugfix for per-hunk
                        // `ri` collision when multiple hunks share
                        // a row offset.)
                        'is-hovered': isCommentable &&
                          !!row.right?.newNo &&
                          hoveredSplitRow === ri &&
                          hoveredSplitHunk === hi,
                      },
                    ]"
                    @mouseenter="onSplitRowEnter(ri, row, hi)"
                    @mouseleave="onSplitRowLeave"
                  >
                    <div class="diff-cell left">
                      <span class="line-number">{{ row.left?.oldNo ?? '' }}</span>
                      <span class="line-prefix">{{ row.left?.prefix ?? '' }}</span>
                      <span class="line-content">{{ row.left?.content ?? '' }}</span>
                    </div>
                    <div class="diff-cell right">
                      <span
                        v-if="isCommentable && row.right?.newNo"
                        class="diff-line-gutter"
                      >
                        <button
                          v-if="hoveredSplitRow === ri &&
                            hoveredSplitHunk === hi &&
                            !commentsByNewLine.has(Number(row.right!.newNo))"
                          type="button"
                          class="diff-comment-add"
                          :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.addButtonAria', { line: row.right!.newNo })"
                          @click.stop="openNewEditor(Number(row.right!.newNo))"
                        >+</button>
                        <button
                          v-else-if="commentsByNewLine.has(Number(row.right!.newNo))"
                          type="button"
                          class="diff-comment-indicator"
                          :title="commentsByNewLine.get(Number(row.right!.newNo))?.text ?? ''"
                          :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.indicatorAria', {
                            line: row.right!.newNo,
                            preview: commentsByNewLine.get(Number(row.right!.newNo))?.text ?? '',
                          })"
                          @click.stop="openEditEditor(commentsByNewLine.get(Number(row.right!.newNo))?.id ?? '')"
                        >
                          <v-icon size="12">mdi-comment-text-outline</v-icon>
                        </button>
                      </span>
                      <span class="line-number">{{ row.right?.newNo ?? '' }}</span>
                      <span class="line-prefix">{{ row.right?.prefix ?? '' }}</span>
                      <span class="line-content">{{ row.right?.content ?? '' }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </template>

            <div v-if="collapsedOverflow > 0" class="diff-overflow-bar">
              <button
                type="button"
                class="diff-show-more"
                @click="showAllLines = true"
              >
                Show all {{ totalLines.toLocaleString() }} lines ({{
                  collapsedOverflow
                }}
                more)
              </button>
            </div>
          </div>

          <!-- Inline-comment editor (fullscreen copy). Same state as
               the normal view, so when the user opens the editor
               while fullscreen and then exits fullscreen, the
               editor simply migrates from the overlay to the normal
               view — no state to re-create. -->
          <FileCommentEditor
            v-if="!isCollapsed && activeEditLine !== null && isCommentable"
            :line="activeEditLine"
            :comment-id="activeEditCommentId"
            :initial-text="editorInitialText"
            :line-content="editorContext?.lineContent ?? null"
            :context-before="editorContext?.contextBefore ?? null"
            :context-after="editorContext?.contextAfter ?? null"
            :file-path="filePath"
            @save="onSaveComment"
            @cancel="closeEditor"
            @delete="onDeleteComment"
          />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, nextTick, watch, onBeforeUnmount } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import {
  extractLineContext,
  useFileComments,
  type DiffHunkContext,
  type FileComment,
  type LineContext,
} from "@/composables/useFileComments";
import FileCommentEditor from "./FileCommentEditor.vue";

// ── Types ──────────────────────────────────────────────────────────

interface DiffLine {
  type: "add" | "del" | "ctx" | "header-file";
  prefix: string;
  content: string;
  oldNo: string;
  newNo: string;
}

interface DiffHunk {
  header: string;
  lines: DiffLine[];
}

// A single visual row in split mode: holds the old-side line (or null
// when the row is a pure addition) and the new-side line (or null
// when the row is a pure deletion). `kind` drives the background tint
// so the user can tell ctx / modified / del-only / add-only apart at
// a glance.
type SplitRowKind = "ctx" | "modified" | "del-only" | "add-only";

interface SplitRow {
  left: DiffLine | null;
  right: DiffLine | null;
  kind: SplitRowKind;
}

interface SplitHunk {
  header: string;
  rows: SplitRow[];
}

type ViewMode = "unified" | "split";

// ── Props ──────────────────────────────────────────────────────────

const props = withDefaults(
  defineProps<{
    content: string;
    filePath?: string;
    summary?: string;
    maxLines?: number;
    maxChars?: number;
    collapsible?: boolean;
    isDark?: boolean;
    /**
     * When true (default), lines that exist in the new file (ctx +
     * add) expose an inline-comment gutter; lines that have a
     * comment already expose an indicator. Set to false to disable
     * the comment UI for a particular DiffPreview instance (e.g. for
     * a synthetic stub the user shouldn't be reviewing).
     */
    commentable?: boolean;
    /**
     * Pre-filtered comments for this file. When omitted, DiffPreview
     * pulls from the global useFileComments() store on its own.
     * Exposed as a prop so a parent that already maintains a scoped
     * comment list can pass it in without re-deriving.
     */
    comments?: FileComment[];
  }>(),
  {
    filePath: "",
    summary: "",
    maxLines: 30,
    maxChars: 2000,
    collapsible: true,
    isDark: false,
    commentable: true,
    comments: () => [],
  },
);

const { tm } = useModuleI18n("features/chat");

// ── State ──────────────────────────────────────────────────────────

const isCollapsed = ref(false);
const showAllLines = ref(false);
const effectiveMaxLines = computed(() =>
  showAllLines.value ? Infinity : props.maxLines,
);

// UI #8: per-hunk fold state. Local to the component, so re-mounting
// the diff (e.g. switching files) resets all folds — matches the
// "expansion state is per-file" mental model. We use a Set<number>
// of hunk indices; small memory footprint even for 100+ hunks.
const collapsedHunks = ref<Set<number>>(new Set());

function toggleHunk(idx: number): void {
  const next = new Set(collapsedHunks.value);
  if (next.has(idx)) next.delete(idx);
  else next.add(idx);
  collapsedHunks.value = next;
}

const VIEW_MODE_STORAGE_KEY = "astrbot.diff.viewMode";

function safeGetItem(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSetItem(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* no-op */
  }
}

// Restore the previously chosen view mode (Unified by default so
// existing users see no change on first load after this feature
// lands).
const viewMode = ref<ViewMode>(
  safeGetItem(VIEW_MODE_STORAGE_KEY) === "split" ? "split" : "unified",
);

function setViewMode(mode: ViewMode): void {
  if (viewMode.value === mode) return;
  viewMode.value = mode;
  safeSetItem(VIEW_MODE_STORAGE_KEY, mode);
}

// i18n labels for the toggle. The tm() values are evaluated lazily
// (inside computeds) so locale changes propagate without reload.
const unifiedLabel = computed(() => tm("diffPreview.viewMode.unified"));
const splitLabel = computed(() => tm("diffPreview.viewMode.split"));
const viewModeAriaLabel = computed(() => tm("diffPreview.viewMode.ariaLabel"));

const toggleCollapsed = () => {
  if (props.collapsible) {
    isCollapsed.value = !isCollapsed.value;
  }
};

// ── Fullscreen state (spec 2026-06-30-diff-fullscreen-design.md §4) ─
const isFullscreen = ref(false);
const fullscreenBtnRef = ref<HTMLElement | null>(null);
const overlayRef = ref<HTMLElement | null>(null);

function enterFullscreen(): void {
  isFullscreen.value = true;
  nextTick(() => overlayRef.value?.focus());
}

function exitFullscreen(): void {
  isFullscreen.value = false;
  nextTick(() => fullscreenBtnRef.value?.focus());
}

// Body scroll lock while fullscreen (spec §3.4)
watch(isFullscreen, (v) => {
  document.body.style.overflow = v ? "hidden" : "";
});

// Cleanup on unmount (spec §8 — edge case: component unmounts while fullscreen)
onBeforeUnmount(() => {
  if (isFullscreen.value) {
    document.body.style.overflow = "";
  }
});

// ── Inline comments (spec 2026-06-30-diff-inline-comments) ─────────
// Comments are anchored to the NEW file. A diff has up to 4 kinds of
// lines:
//   - ctx   — exists on both sides; newNo is set
//   - add   — only in new file; newNo is set
//   - del   — only in old file; newNo is ""  (we skip these)
//   - split del-only rows — right cell is null (we skip these)
//
// To avoid polluting useFileComments.contentCache (which is reserved
// for the real on-disk file content seen in the file browser), we
// reconstruct the "post-change file content" from the parsed diff and
// hand it directly to addCommentWithContext.

const fileComments = useFileComments();

/** Per-row hover state.
 *
 *  Unified mode keys off the new-side absolute line number — newNo
 *  is unique per file, so one number identifies one row.
 *
 *  Split mode keys off the per-hunk row index `ri` plus the hunk
 *  index `hi` — `ri` alone is naturally ambiguous because each
 *  hunk restarts its row counter from 0, so two hunks with the
 *  same number of rows would have a `ri` collision at every
 *  position. The pair (hi, ri) is unique.
 *
 *  We carry the hunk index in unified mode too for symmetry, even
 *  though `hoveredUnifiedLine` is already unambiguous — it makes
 *  the v-if's intent explicit ("the line in the same hunk") and
 *  shields against any future change to the newNo assignment.
 *
 *  `null` means "no row hovered". */
const hoveredUnifiedLine = ref<number | null>(null);
const hoveredUnifiedHunk = ref<number | null>(null);
const hoveredSplitRow = ref<number | null>(null);
const hoveredSplitHunk = ref<number | null>(null);

/** Editor state (mirrors FileBrowserFilePreview's pattern). When
 *  `activeEditLine` is non-null the editor is visible at the bottom
 *  of the preview. */
const activeEditLine = ref<number | null>(null);
const activeEditCommentId = ref<string | null>(null);
const editorContext = ref<LineContext | null>(null);
const editorInitialText = ref<string>("");

/** Effective opt-in: must be enabled AND a filePath must be set.
 *  filePath is empty for markdown ```diff``` blocks, so the comment
 *  UI silently disappears there. */
const isCommentable = computed<boolean>(
  () => props.commentable !== false && props.filePath.length > 0,
);

/** Resolved comment list: prefer the parent-supplied `props.comments`,
 *  fall back to querying the store. Splitting this from
 *  `commentsByNewLine` means a parent can pre-filter or scope the
 *  list (e.g. by worktree) without going through the store. */
const visibleComments = computed<FileComment[]>(() => {
  if (props.comments.length > 0) return props.comments;
  if (!isCommentable.value) return [];
  return fileComments.commentsForFile(props.filePath);
});

/** newNo → existing comment. First-wins: if a parent injects
 *  duplicates (shouldn't happen, but be defensive) the first one
 *  renders the indicator and the others are ignored. */
const commentsByNewLine = computed<Map<number, FileComment>>(() => {
  const m = new Map<number, FileComment>();
  for (const c of visibleComments.value) {
    if (Number.isInteger(c.line) && c.line > 0 && !m.has(c.line)) {
      m.set(c.line, c);
    }
  }
  return m;
});

/** Reconstruct the post-change file content by joining all ctx + add
 *  lines in order. This is the synthetic "current file" the diff
 *  describes, and it's what we hand to extractLineContext when the
 *  user opens a new comment. We deliberately do NOT register this
 *  in useFileComments.contentCache (see addCommentWithContext docs). */
const newFileContent = computed<string>(() => {
  const out: string[] = [];
  for (const hunk of parsedHunks.value) {
    for (const line of hunk.lines) {
      if (line.type === "ctx" || line.type === "add") {
        out.push(line.content);
      }
    }
  }
  return out.join("\n");
});

/**
 * Editor state carries the optional diff-hunk context for the line
 * being edited. We snapshot the hunk at the moment the editor opens
 * (NOT at save time) so the user can see the surrounding patch in
 * the comment preview, and so the saved comment reflects the patch
 * as the user saw it when they decided to write.
 *
 * `null` for file-browser paths and for synthetic diffs that have no
 * parseable hunk header.
 */
const pendingDiffHunk = ref<DiffHunkContext | null>(null);

/**
 * Find the parsed DiffHunk whose new-side range contains `line`.
 * The hunk header `@@ -X,A +Y,B @@` tells us the starting new-side
 * line Y and the new-side count B. We check whether the requested
 * line falls in [Y, Y+B) by counting ctx+add lines (we have the
 * parsed lines in `parsedHunks` already, so this is O(hunk-lines)
 * per hunk, not a re-parse).
 */
function findHunkForLine(line: number): DiffHunk | null {
  for (const hunk of parsedHunks.value) {
    const m = hunk.header.match(
      /^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@/,
    );
    if (!m) continue;
    const startNew = parseInt(m[1], 10);
    const newCount = hunk.lines.filter((l) => l.type !== "del").length;
    if (line >= startNew && line < startNew + newCount) {
      return hunk;
    }
  }
  return null;
}

/**
 * Convert a parsed DiffHunk into the serializable DiffHunkContext
 * that gets stored on the FileComment. The hunk's `oldNo`/`newNo`
 * strings are parsed back to numbers so the LLM-facing renderer
 * can format them without re-parsing. `header-file` lines are
 * dropped — they don't appear inside hunks in practice but we
 * filter defensively.
 */
function buildDiffHunkContext(hunk: DiffHunk, newLine: number): DiffHunkContext {
  return {
    header: hunk.header,
    lines: hunk.lines
      .filter((l) => l.type !== "header-file")
      .map((l) => ({
        type: l.type as "add" | "del" | "ctx",
        content: l.content,
        oldNo: l.oldNo ? Number(l.oldNo) : null,
        newNo: l.newNo ? Number(l.newNo) : null,
      })),
    newLine,
  };
}

/** Open the editor for a brand-new comment on a given new-side line. */
function openNewEditor(line: number): void {
  activeEditLine.value = line;
  activeEditCommentId.value = null;
  editorInitialText.value = "";
  // extractLineContext may return null when the line is out of range
  // (e.g. a stub diff that only contains del lines). The editor
  // handles a null context gracefully (no preview snippet shown).
  editorContext.value = extractLineContext(newFileContent.value, line);
  // Snapshot the surrounding diff hunk so the saved comment can
  // include the patch in the LLM-facing output. Falls back to null
  // when the line isn't in any parseable hunk (very rare: only
  // happens if the diff text is malformed and the parser couldn't
  // recover the @@ header).
  const hunk = findHunkForLine(line);
  pendingDiffHunk.value = hunk ? buildDiffHunkContext(hunk, line) : null;
}

/** Open the editor for an existing comment (look up by id in the
 *  global store so the comment's own lineContent/context is used —
 *  not whatever the current diff happens to contain). */
function openEditEditor(commentId: string): void {
  const existing = fileComments.findCommentById(commentId);
  if (!existing) return;
  activeEditLine.value = existing.line;
  activeEditCommentId.value = existing.id;
  editorInitialText.value = existing.text;
  editorContext.value = {
    lineContent: existing.lineContent,
    contextBefore: existing.contextBefore,
    contextAfter: existing.contextAfter,
  };
}

function onSaveComment(payload: {
  text: string;
  commentId: string | null;
  line: number;
}): void {
  if (payload.commentId) {
    fileComments.updateComment(payload.commentId, payload.text);
  } else {
    if (!isCommentable.value) {
      closeEditor();
      return;
    }
    // Fall back to a minimal context if the diff couldn't synthesize
    // a real one (e.g. out-of-range line). The comment is still
    // useful — the LLM can locate the line by number + file path.
    const ctx = editorContext.value ?? {
      lineContent: "",
      contextBefore: null,
      contextAfter: null,
    };
    fileComments.addCommentWithContext({
      filePath: props.filePath,
      line: payload.line,
      text: payload.text,
      context: ctx,
      // Attach the diff hunk so the LLM sees the surrounding
      // patch (with the target line marked) instead of just the
      // one line of context around the comment. `null` for
      // file-browser paths and for hunks that couldn't be parsed.
      diffHunk: pendingDiffHunk.value ?? undefined,
    });
  }
  closeEditor();
}

function onDeleteComment(commentId: string): void {
  fileComments.deleteComment(commentId);
  closeEditor();
}

function closeEditor(): void {
  activeEditLine.value = null;
  activeEditCommentId.value = null;
  editorContext.value = null;
  // Drop the snapshotted hunk — it's only meaningful while the
  // editor is open. Leaving it would leak memory if the editor is
  // never re-opened.
  pendingDiffHunk.value = null;
}

/** Hover handlers — using @mouseenter/@mouseleave on each row gives
 *  us a stable "which row is the mouse over" signal without the
 *  mousemove handler that FileBrowserCodeView needs (Shiki outputs
 *  one span per line so the file browser has to compute the hovered
 *  line from clientY; here we get it for free from the row element). */
function onUnifiedRowEnter(line: DiffLine, hi: number): void {
  if (!isCommentable.value) return;
  if (!line.newNo) return; // del lines don't have a new-side number
  hoveredUnifiedLine.value = Number(line.newNo);
  hoveredUnifiedHunk.value = hi;
}
function onUnifiedRowLeave(): void {
  hoveredUnifiedLine.value = null;
  hoveredUnifiedHunk.value = null;
}
function onSplitRowEnter(ri: number, row: SplitRow, hi: number): void {
  if (!isCommentable.value) return;
  if (!row.right || !row.right.newNo) return; // del-only rows
  hoveredSplitRow.value = ri;
  hoveredSplitHunk.value = hi;
}
function onSplitRowLeave(): void {
  hoveredSplitRow.value = null;
  hoveredSplitHunk.value = null;
}

/** Close the editor when the user switches files in the parent — the
 *  editor's line number is for a different file, so keeping it open
 *  would be confusing. */
watch(
  () => props.filePath,
  () => {
    closeEditor();
  },
);

// ── Parse unified diff ─────────────────────────────────────────────

const parsedHunks = computed<DiffHunk[]>(() => {
  const text = extractDiffContent(props.content);
  return parseUnifiedDiff(text, effectiveMaxLines.value);
});

const totalLines = computed(() =>
  parsedHunks.value.reduce((sum, h) => sum + h.lines.length, 0),
);

const truncated = computed(() => {
  const raw = extractDiffContent(props.content);
  return raw.length > props.maxChars;
});

const collapsedOverflow = computed(() => {
  if (showAllLines.value) return 0;
  const fullHunks = parseUnifiedDiff(
    extractDiffContent(props.content),
    Infinity,
  );
  const fullTotal = fullHunks.reduce((sum, h) => sum + h.lines.length, 0);
  return Math.max(0, fullTotal - totalLines.value);
});

// ── Split-view alignment ──────────────────────────────────────────

// Walk each parsed hunk and pair its del/add lines into rows of
// {left, right}. The hunk header is preserved unchanged. Truncation
// is applied here (after pairing) so we never split a del/add pair
// across the cutoff — paired rows stay together or are dropped
// together.
const splitHunks = computed<SplitHunk[]>(() => {
  const out: SplitHunk[] = [];
  let consumed = 0;
  const cap = effectiveMaxLines.value;
  for (const hunk of parsedHunks.value) {
    const allRows = alignHunkLines(hunk.lines);
    const rows: SplitRow[] = [];
    for (const row of allRows) {
      if (consumed >= cap) break;
      // ctx rows count as 1 line; a modified/del-only/add-only row
      // also counts as 1 visual row in the split layout.
      rows.push(row);
      consumed++;
    }
    out.push({ header: hunk.header, rows });
  }
  return out;
});

// Pair del/add lines inside a single hunk into visual rows.
//
// Algorithm (matches GitHub's split view):
//   - ctx lines are emitted as-is (both sides the same).
//   - dels are buffered.
//   - adds are buffered.
//   - when one of the buffers is non-empty and the other changes
//     type (or a ctx / hunk boundary is reached), flushPair() pairs
//     min(dels, adds) into "modified" rows, then drains leftover
//     dels into "del-only" rows (right=null) and leftover adds into
//     "add-only" rows (left=null).
function alignHunkLines(lines: DiffLine[]): SplitRow[] {
  const rows: SplitRow[] = [];
  let dels: DiffLine[] = [];
  let adds: DiffLine[] = [];

  const flush = (): void => {
    const pairCount = Math.min(dels.length, adds.length);
    for (let i = 0; i < pairCount; i++) {
      rows.push({ left: dels[i], right: adds[i], kind: "modified" });
    }
    for (let i = pairCount; i < dels.length; i++) {
      rows.push({ left: dels[i], right: null, kind: "del-only" });
    }
    for (let i = pairCount; i < adds.length; i++) {
      rows.push({ left: null, right: adds[i], kind: "add-only" });
    }
    dels = [];
    adds = [];
  };

  for (const line of lines) {
    if (line.type === "ctx") {
      flush();
      rows.push({ left: line, right: line, kind: "ctx" });
    } else if (line.type === "del") {
      dels.push(line);
    } else if (line.type === "add") {
      adds.push(line);
    }
    // header-file lines are skipped — they never appear inside a
    // hunk's `lines` array in practice (the parser filters them).
  }
  flush();
  return rows;
}

// ── Stats ──────────────────────────────────────────────────────────

const statsAdds = computed(() => {
  let adds = 0;
  for (const hunk of parsedHunks.value) {
    for (const line of hunk.lines) {
      if (line.type === "add") adds++;
    }
  }
  return adds || null;
});

const statsDels = computed(() => {
  let dels = 0;
  for (const hunk of parsedHunks.value) {
    for (const line of hunk.lines) {
      if (line.type === "del") dels++;
    }
  }
  return dels || null;
});

// ── Helpers ────────────────────────────────────────────────────────

function extractDiffContent(raw: string): string {
  // If the text contains a ```diff ... ``` block, extract its content
  const blockMatch = raw.match(/```diff\s*\n?([\s\S]*?)```/);
  if (blockMatch) return blockMatch[1];

  // Otherwise, try to strip leading "Diff:" / "Edited ..." lines
  const diffIdx = raw.indexOf("@@");
  if (diffIdx >= 0) return raw.slice(diffIdx);

  return raw;
}

function parseUnifiedDiff(text: string, maxLines: number): DiffHunk[] {
  const lines = text.split("\n");
  const hunks: DiffHunk[] = [];
  let currentHunk: DiffHunk | null = null;
  let totalLines = 0;
  let oldNo = 0;
  let newNo = 0;

  // Try to parse --- / +++ file headers to get old/new line numbers
  for (const rawLine of lines) {
    if (totalLines >= maxLines) break;

    const hunkMatch = rawLine.match(
      /^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)$/,
    );
    if (hunkMatch) {
      // Flush previous hunk
      if (currentHunk) hunks.push(currentHunk);

      oldNo = parseInt(hunkMatch[1], 10);
      newNo = parseInt(hunkMatch[3], 10);

      currentHunk = {
        header: rawLine,
        lines: [],
      };
      continue;
    }

    if (!currentHunk) continue;

    const ch = rawLine[0];
    let type: DiffLine["type"];
    let prefix: string;
    let content: string;

    if (ch === "+") {
      type = "add";
      prefix = "+";
      content = rawLine.slice(1);
    } else if (ch === "-") {
      type = "del";
      prefix = "−";
      content = rawLine.slice(1);
    } else if (ch === " ") {
      type = "ctx";
      prefix = " ";
      content = rawLine.slice(1);
    } else if (rawLine === "\\ No newline at end of file") {
      type = "ctx";
      prefix = " ";
      content = rawLine;
    } else {
      // Could be --- or +++ header lines; skip or treat as ctx
      if (rawLine.startsWith("---") || rawLine.startsWith("+++")) continue;
      type = "ctx";
      prefix = " ";
      content = rawLine;
    }

    const line: DiffLine = {
      type,
      prefix,
      content,
      oldNo: type === "add" ? "" : String(oldNo),
      newNo: type === "del" ? "" : String(newNo),
    };

    if (type !== "add") oldNo++;
    if (type !== "del") newNo++;

    currentHunk.lines.push(line);
    totalLines++;
  }

  if (currentHunk) hunks.push(currentHunk);
  return hunks;
}
</script>

<style scoped>
.diff-preview {
  --diff-add-bg: rgba(70, 200, 70, 0.12);
  --diff-add-border: rgba(70, 200, 70, 0.35);
  --diff-add-bg-strong: rgba(70, 200, 70, 0.22);
  --diff-del-bg: rgba(255, 100, 100, 0.12);
  --diff-del-border: rgba(255, 100, 100, 0.35);
  --diff-del-bg-strong: rgba(255, 100, 100, 0.22);
  --diff-hunk-bg: #e8f0fe;
  --diff-hunk-border: rgba(100, 150, 220, 0.3);
  --diff-line-no: rgba(0, 0, 0, 0.35);
  --diff-border: rgba(0, 0, 0, 0.08);
  --diff-divider: rgba(0, 0, 0, 0.12);

  margin: 4px 0;
  border: 1px solid var(--diff-border);
  border-radius: 8px;
  overflow: hidden;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.55;
}

.diff-preview.is-dark {
  --diff-add-bg: rgba(70, 200, 70, 0.16);
  --diff-add-border: rgba(70, 200, 70, 0.3);
  --diff-add-bg-strong: rgba(70, 200, 70, 0.3);
  --diff-del-bg: rgba(255, 100, 100, 0.16);
  --diff-del-border: rgba(255, 100, 100, 0.3);
  --diff-del-bg-strong: rgba(255, 100, 100, 0.3);
  --diff-hunk-bg: rgba(100, 150, 255, 0.12);
  --diff-hunk-border: rgba(100, 150, 255, 0.2);
  --diff-line-no: rgba(255, 255, 255, 0.35);
  --diff-border: rgba(255, 255, 255, 0.1);
  --diff-divider: rgba(255, 255, 255, 0.14);
}

/* ── Header ─────────────────────────────────────────────────────── */

.diff-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 12px;
  background: rgba(0, 0, 0, 0.02);
  border: 0;
  cursor: pointer;
  font: inherit;
  color: inherit;
  user-select: none;
}

.diff-preview.is-dark .diff-header {
  background: rgba(255, 255, 255, 0.03);
}

.diff-header:hover {
  background: rgba(0, 0, 0, 0.05);
}

.diff-preview.is-dark .diff-header:hover {
  background: rgba(255, 255, 255, 0.06);
}

.diff-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.diff-header-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.diff-header-icon {
  color: rgba(var(--v-theme-on-surface), 0.55);
  flex-shrink: 0;
}

.diff-file-path {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: rgba(var(--v-theme-on-surface), 0.8);
}

.diff-stats {
  font-size: 11px;
  font-weight: 600;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  white-space: nowrap;
}

.diff-stats-add {
  color: #2da44e;
  margin-right: 4px;
}

.diff-preview.is-dark .diff-stats-add {
  color: #57ab5a;
}

.diff-stats-del {
  color: #cf222e;
}

.diff-preview.is-dark .diff-stats-del {
  color: #f47067;
}

/* ── View-mode segmented toggle ─────────────────────────────────── */

.diff-view-toggle {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--diff-border);
  border-radius: 4px;
  overflow: hidden;
  margin: 0 4px;
  background: transparent;
}

.diff-view-toggle-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  background: transparent;
  border: 0;
  border-radius: 0;
  color: rgba(var(--v-theme-on-surface), 0.55);
  cursor: pointer;
  transition:
    background 0.12s ease,
    color 0.12s ease;
}

.diff-view-toggle-btn + .diff-view-toggle-btn {
  border-left: 1px solid var(--diff-border);
}

.diff-view-toggle-btn:hover {
  color: rgba(var(--v-theme-on-surface), 0.85);
  background: rgba(127, 127, 127, 0.08);
}

.diff-view-toggle-btn:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.diff-view-toggle-btn.active {
  background: rgba(var(--v-theme-primary), 0.15);
  color: rgb(var(--v-theme-primary));
}

.diff-chevron {
  color: rgba(var(--v-theme-on-surface), 0.45);
  transition: transform 0.2s ease;
}

.diff-chevron.expanded {
  transform: rotate(90deg);
}

/* ── Summary text ────────────────────────────────────────────────── */

.diff-summary-text {
  padding: 4px 12px 8px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-family: inherit;
}

/* ── Body ────────────────────────────────────────────────────────── */

.diff-body {
  border-top: 1px solid var(--diff-border);
}

.diff-truncation-warning {
  padding: 6px 12px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  background: rgba(var(--v-theme-warning), 0.08);
  border-bottom: 1px solid var(--diff-border);
}

/* ── Hunk (unified) ──────────────────────────────────────────────── */

.diff-hunk + .diff-hunk {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.04);
}

/* UI #8: hunk header is now a button (clickable to fold / unfold).
   Reset default button styles and let it fill the full row. The
   inner flex lays out: chevron | hunk text | line count badge. */
.hunk-header {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 4px 12px;
  font-size: 11px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.55);
  background: var(--diff-hunk-bg);
  border: 0;
  border-bottom: 1px solid var(--diff-hunk-border);
  font-family: inherit;
  cursor: pointer;
  text-align: left;
  user-select: none;
  transition: background 0.12s ease;
}

.hunk-header:hover {
  background: rgba(var(--v-theme-primary), 0.08);
}

.hunk-header:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.hunk-chevron {
  color: rgba(var(--v-theme-on-surface), 0.55);
  flex-shrink: 0;
  transition: transform 0.15s ease;
}

.hunk-chevron.expanded {
  transform: rotate(90deg);
}

.hunk-header-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hunk-header-count {
  font-size: 10px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgba(var(--v-theme-on-surface), 0.6);
  flex-shrink: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

/* ── Diff line (unified) ─────────────────────────────────────────── */

.diff-line {
  display: flex;
  align-items: baseline;
  padding: 1px 12px;
  min-height: 20px;
  transition: background 0.1s ease;
}

.diff-line:hover {
  filter: brightness(0.94);
}

.diff-preview.is-dark .diff-line:hover {
  filter: brightness(1.15);
}

.diff-line.add {
  background: var(--diff-add-bg);
  border-left: 3px solid var(--diff-add-border);
}

.diff-line.del {
  background: var(--diff-del-bg);
  border-left: 3px solid var(--diff-del-border);
}

.diff-line.ctx {
  border-left: 3px solid transparent;
}

/* ── Line numbers (unified) ──────────────────────────────────────── */

.line-number {
  width: 36px;
  flex-shrink: 0;
  text-align: right;
  padding-right: 8px;
  color: var(--diff-line-no);
  user-select: none;
}

.line-number.new {
  padding-right: 0;
  padding-left: 8px;
}

/* ── Prefix and content (unified) ────────────────────────────────── */

.line-prefix {
  width: 14px;
  flex-shrink: 0;
  text-align: center;
  font-weight: 700;
  user-select: none;
}

.diff-line.add .line-prefix {
  color: #2da44e;
}

.diff-preview.is-dark .diff-line.add .line-prefix {
  color: #57ab5a;
}

.diff-line.del .line-prefix {
  color: #cf222e;
}

.diff-preview.is-dark .diff-line.del .line-prefix {
  color: #f47067;
}

.line-content {
  white-space: pre-wrap;
  word-break: break-all;
  min-width: 0;
  padding-left: 4px;
}

/* ── Split-view rows ─────────────────────────────────────────────── */

/* In split mode the .diff-hunk itself becomes a vertical stack of
   .diff-row-split; the inner cells lay out as 1fr | 1fr. We omit
   horizontal padding (12px) here because the cells handle their own. */
.diff-hunk-split {
  /* nothing special — the per-row grid does the work */
}

.diff-row-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 20px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.03);
}

.diff-row-split:first-of-type {
  border-top: 0;
}

.diff-row-split .diff-cell {
  display: flex;
  align-items: baseline;
  padding: 1px 12px;
  min-width: 0;
  overflow: hidden;
}

.diff-row-split .diff-cell + .diff-cell {
  border-left: 1px solid var(--diff-divider);
}

/* ctx rows: both sides transparent. Use a subtle alternating shade so
   the eye can track the row across the divider. */
.diff-row-split.ctx .diff-cell {
  background: transparent;
}

/* modified rows: stronger tint on both sides to signal "this row
   changed". The right cell uses the add tint, the left uses the del
   tint — matching GitHub's split view exactly. */
.diff-row-split.modified .diff-cell.left {
  background: var(--diff-del-bg-strong);
}
.diff-row-split.modified .diff-cell.right {
  background: var(--diff-add-bg-strong);
}

/* del-only: left tinted, right blank. The blank cell still renders
   a faint background so the row visually contains two halves. */
.diff-row-split.del-only .diff-cell.left {
  background: var(--diff-del-bg-strong);
}
.diff-row-split.del-only .diff-cell.right {
  background: var(--diff-del-bg);
  opacity: 0.4;
}

/* add-only: right tinted, left blank. */
.diff-row-split.add-only .diff-cell.left {
  background: var(--diff-add-bg);
  opacity: 0.4;
}
.diff-row-split.add-only .diff-cell.right {
  background: var(--diff-add-bg-strong);
}

/* In split mode the line numbers and prefix are slightly tighter
   because we have 4 such spans per row (2 sides × old/new) but the
   cell is half the width. Keep them readable. */
.diff-row-split .line-number {
  width: 30px;
  padding-right: 6px;
  padding-left: 0;
}

.diff-row-split .line-prefix {
  width: 12px;
}

.diff-row-split .line-content {
  padding-left: 4px;
}

/* Prefix color carries over from unified rules via class hooks; in
   split we also need to color the side that holds an add/del. The
   `.left`/`.right` cell can't be styled via .add/.del directly
   (the line is nested), so we re-derive the color from the row kind. */
.diff-row-split.modified .diff-cell.left .line-prefix,
.diff-row-split.del-only .diff-cell.left .line-prefix {
  color: #cf222e;
}
.diff-preview.is-dark .diff-row-split.modified .diff-cell.left .line-prefix,
.diff-preview.is-dark .diff-row-split.del-only .diff-cell.left .line-prefix {
  color: #f47067;
}

.diff-row-split.modified .diff-cell.right .line-prefix,
.diff-row-split.add-only .diff-cell.right .line-prefix {
  color: #2da44e;
}
.diff-preview.is-dark .diff-row-split.modified .diff-cell.right .line-prefix,
.diff-preview.is-dark .diff-row-split.add-only .diff-cell.right .line-prefix {
  color: #57ab5a;
}

/* ── Show more ───────────────────────────────────────────────────── */

.diff-overflow-bar {
  border-top: 1px solid var(--diff-border);
  padding: 6px 12px;
}

.diff-show-more {
  background: none;
  border: 0;
  padding: 0;
  font: inherit;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  cursor: pointer;
}

.diff-show-more:hover {
  color: rgba(var(--v-theme-on-surface), 0.75);
  text-decoration: underline;
}

/* ── Collapsed state ─────────────────────────────────────────────── */

.diff-preview.collapsed .diff-body,
.diff-preview.collapsed .diff-summary-text {
  display: none;
}

/* ══════════════════════════════════════════════════════════════════
   Fullscreen overlay — spec 2026-06-30-diff-fullscreen-design.md §7
   ══════════════════════════════════════════════════════════════════ */

/* Overlay backdrop: fills entire viewport */
.diff-fullscreen-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgb(var(--v-theme-background));
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Back button: small FAB fixed at top-right corner */
.diff-fullscreen-back-btn {
  position: fixed;
  top: 12px;
  right: 12px;
  z-index: 10000;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border: 1px solid rgb(var(--v-theme-outline));
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  cursor: pointer;
  font-size: 13px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
  transition: background 0.15s;
  white-space: nowrap;
}
.diff-fullscreen-back-btn:hover {
  background: rgb(var(--v-theme-surface-variant));
}

/* Fullscreen body: scrollable container */
.diff-fullscreen-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  padding-top: 52px; /* room for the fixed back button at top-right */
}

/* Override for diff-preview inside fullscreen: wider border,
   no max-width constraint. */
.diff-preview.is-fullscreen {
  max-width: 100%;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 8px;
}

/* Fullscreen button in the normal header. Matches existing
   .diff-view-toggle-btn dimensions (22×22px) and transitions. */
.diff-fullscreen-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: none;
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.55);
  transition:
    border-color 0.15s,
    color 0.15s,
    background 0.15s;
  flex-shrink: 0;
}
.diff-fullscreen-btn:hover {
  border-color: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
}
.diff-fullscreen-btn:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

/* ══════════════════════════════════════════════════════════════════
   Inline-comment gutter (spec 2026-06-30-diff-inline-comments)
   ══════════════════════════════════════════════════════════════════

   Mirrors the file-browser gutter (FileBrowserCodeView.vue) so the
   two review surfaces feel identical. The gutter is a 24px-wide slot
   at the right end of each diff row; it stays in the layout (just
   invisible) so hovering doesn't shift the code column. The cell
   shows:
     - the primary-tinted "+" chip on hover (when the line has no
       existing comment)
     - the warning-tinted indicator (when a comment exists) — stays
       visible always, like the file-browser indicator
*/

/* Unified mode: a fixed 24px column at the very LEFT of .diff-line
   (which is a flex row). Mirrors the file-browser code view, which
   also puts the gutter on the left — keeps the two review surfaces
   visually consistent so the user's mouse doesn't have to learn a
   new hot-zone. */
.diff-line {
  position: relative;
}
.diff-line-gutter {
  width: 24px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.1s ease;
}
/* Show on row hover OR when a comment already exists on the line. */
.diff-line.is-hovered .diff-line-gutter,
.diff-line.has-comment .diff-line-gutter {
  opacity: 1;
}

/* The "add comment" chip — matches FileBrowserCodeView .gutter-add-btn. */
.diff-comment-add {
  width: 20px;
  height: 20px;
  background: rgba(var(--v-theme-primary), 0.2);
  border: 1.5px solid rgba(var(--v-theme-primary), 0.7);
  border-radius: 5px;
  cursor: pointer;
  color: rgb(var(--v-theme-primary));
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
  transition:
    background 0.12s ease,
    border-color 0.12s ease,
    transform 0.12s ease,
    box-shadow 0.12s ease;
}
.diff-preview.is-dark .diff-comment-add {
  background: rgba(var(--v-theme-primary), 0.28);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.45);
}
.diff-comment-add:hover,
.diff-comment-add:focus {
  background: rgba(var(--v-theme-primary), 0.4);
  border-color: rgb(var(--v-theme-primary));
  transform: scale(1.15);
  box-shadow: 0 2px 6px rgba(var(--v-theme-primary), 0.45);
}
.diff-comment-add:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

/* The "comment exists" indicator — matches FileBrowserCodeView
   .gutter-comment-indicator. Always visible when present, doesn't
   require hover. */
.diff-comment-indicator {
  width: 18px;
  height: 18px;
  background: rgba(var(--v-theme-warning), 0.15);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  color: rgb(var(--v-theme-warning));
  margin: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.12s ease, transform 0.12s ease;
}
.diff-comment-indicator:hover,
.diff-comment-indicator:focus {
  background: rgba(var(--v-theme-warning), 0.25);
  transform: scale(1.1);
}
.diff-comment-indicator:focus-visible {
  outline: 2px solid rgb(var(--v-theme-warning));
  outline-offset: 2px;
}

/* Split mode: the right cell already fills the right half of the
   row. The gutter is absolutely positioned at the LEFT edge of the
   right cell so it sits in the gap between the two columns' line
   numbers and the code text — the same place the file browser puts
   its gutter. */
.diff-row-split {
  position: relative;
}
.diff-cell.right {
  position: relative;
}
.diff-cell.right .diff-line-gutter {
  position: absolute;
  left: 4px;
  top: 50%;
  transform: translateY(-50%);
  width: auto;
  margin-left: 0;
}
/* In split mode the gutter appears as an overlay, not a flex
   column — otherwise it would push the line-number column around
   and break the left/right cell alignment. Override the visibility
   transitions to only apply when hover/has-comment. */
.diff-row-split .diff-line-gutter {
  opacity: 0;
  pointer-events: none;
}
.diff-row-split.is-hovered .diff-line-gutter,
.diff-row-split.has-comment .diff-line-gutter {
  opacity: 1;
  pointer-events: auto;
}
</style>
