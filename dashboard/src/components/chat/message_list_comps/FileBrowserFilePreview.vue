<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.5 -->
<script setup lang="ts">
import { computed, ref, onBeforeUnmount, onMounted, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import {
  ensureShikiLanguages,
  renderShikiCode,
  escapeHtml,
} from "@/utils/shiki";
import { copyToClipboard } from "@/utils/clipboard";
import type { FileBrowserFetchState } from "@/composables/useSpcodeFileBrowser";
import { useDisplay } from "vuetify";
import {
  extractLineContext,
  useFileComments,
  type LineContext,
} from "@/composables/useFileComments";
import FileBrowserCodeView from "./FileBrowserCodeView.vue";
import FileCommentEditor from "./FileCommentEditor.vue";

const props = defineProps<{
  state: FileBrowserFetchState;
  isDark: boolean;
  /**
   * 2026-07-02 sidebar-search: 1-based line number to center in the
   * code view after a search-result click. null = no scroll.
   * Forwarded to <FileBrowserCodeView>, where the scrollIntoView()
   * watcher lives.
   */
  scrollToLine?: number | null;
}>();
const emit = defineEmits<{
  (e: "navigate-target", resolvedPath: string): void;
  (e: "retry"): void;
}>();
const { tm } = useModuleI18n("features/chat");

/**
 * Resolve a symlink target string (which may be relative) against the
 * symlink's parent directory. Mirrors POSIX symlink semantics:
 * - Absolute target: use as-is
 * - Relative target: join with parent dir of the symlink
 *
 * The backend does NOT resolve symlinks (per file-browser spec §3.5.4);
 * if the user wants to view the resolved content, we manually re-issue
 * the request with the resolved path so the backend re-classifies it.
 */
function resolveTargetPath(symlinkPath: string, target: string): string {
  const isWindows = symlinkPath.includes("\\");
  const sep = isWindows ? "\\" : "/";
  if (target.startsWith("/") || /^[a-zA-Z]:[\\/]/.test(target)) {
    return target; // Absolute path
  }
  const lastSep = Math.max(
    symlinkPath.lastIndexOf("/"),
    symlinkPath.lastIndexOf("\\"),
  );
  const parentDir = lastSep >= 0 ? symlinkPath.slice(0, lastSep) : symlinkPath;
  return parentDir + sep + target;
}

// Mirror of detectLanguage in ToolResultView.vue (line 160-165) to ensure
// consistent language detection between the tool result view and this preview.
const EXT_TO_LANG: Record<string, string> = {
  ".py": "python",
  ".js": "javascript",
  ".mjs": "javascript",
  ".cjs": "javascript",
  ".ts": "typescript",
  ".tsx": "tsx",
  ".jsx": "jsx",
  ".vue": "vue",
  ".json": "json",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".sh": "bash",
  ".bash": "bash",
  ".zsh": "bash",
  ".css": "css",
  ".html": "html",
  ".htm": "html",
  ".xml": "xml",
  ".svg": "xml",
  ".md": "markdown",
  ".sql": "sql",
  ".java": "java",
  ".ini": "ini",
  ".diff": "diff",
  ".patch": "diff",
  ".ps1": "powershell",
  ".dockerfile": "dockerfile",
  ".txt": "text",
  ".c": "c",
  ".h": "c",
  ".cpp": "cpp",
  ".cc": "cpp",
  ".cxx": "cpp",
  ".hpp": "cpp",
  ".c++": "cpp",
  ".go": "go",
  ".rs": "rust",
  // Verilog / SystemVerilog
  ".v": "verilog",
  ".vh": "verilog",
  ".sv": "system-verilog",
  ".svh": "system-verilog",
  // MATLAB. `.m` is also the Objective-C extension, but
  // objective-c is not in the shiki whitelist, so claiming it
  // here does not collide with anything currently supported.
  // `.matlab` is the explicit form for the rare cases where a
  // file is named without the canonical `.m` (e.g. for clarity
  // when the project mixes OC-style and matlab tooling).
  ".m": "matlab",
  ".matlab": "matlab",
};

function detectLanguage(filePath: string): string {
  const m = filePath.match(/\.([\w]+)$/i);
  if (!m) return "text";
  const key = "." + m[1].toLowerCase();
  return EXT_TO_LANG[key] || "text";
}

const shikiHighlighter = ref<any>(null);
const shikiReady = ref(false);

onMounted(async () => {
  // Pattern mirrored verbatim from ToolResultView.vue:289 — do NOT
  // pass an array arg to ensureShikiLanguages (it takes zero args
  // and silently ignores any). Assign the returned highlighter so
  // the !shikiHighlighter.value guard in highlightedHtml is satisfied.
  try {
    shikiHighlighter.value = await ensureShikiLanguages();
    shikiReady.value = true;
  } catch (err) {
    console.error("Shiki init failed:", err);
  }
});

const highlightedHtml = computed(() => {
  if (props.state.kind !== "file") return "";
  const snapshot = props.state.snapshot;
  if (snapshot.content === null) return "";
  if (!shikiReady.value || !shikiHighlighter.value) {
    return `<pre><code>${escapeHtml(snapshot.content)}</code></pre>`;
  }
  try {
    // renderShikiCode signature: (highlighter, code, language, colorMode)
    // colorMode="auto" enables dual-theme (light/dark) auto-switching.
    return renderShikiCode(
      shikiHighlighter.value,
      snapshot.content,
      detectLanguage(snapshot.meta.path),
      "auto",
    );
  } catch (err) {
    console.error("Shiki render failed:", err);
    return `<pre><code>${escapeHtml(snapshot.content)}</code></pre>`;
  }
});

const copyButtonText = ref<string>("");
// Vuetify `color` accepts the theme token name; success/error give the
// user a clear visual hint that distinguishes "已复制" (green) from
// "复制失败" (red), instead of two identical grey states.
const copyButtonColor = ref<"success" | "error" | undefined>(undefined);
let copyResetTimer: ReturnType<typeof setTimeout> | null = null;

watch(highlightedHtml, () => {
  // New file loaded → reset the transient success/fail feedback so
  // a "复制失败" toast from the previous file does not leak into the
  // freshly rendered header. Color is reset here too — without that,
  // a failed copy on the previous file would tint the new file's
  // copy button red before the user even clicks it.
  copyButtonText.value = tm("spcodeProjectLoad.fileBrowser.preview.copy");
  copyButtonColor.value = undefined;
});

async function copyContent(): Promise<void> {
  if (props.state.kind !== "file" || !props.state.snapshot.content) return;
  // Cancel any in-flight reset timer before scheduling a new one so
  // rapid double-clicks do not race the old timer into flipping the
  // button back to the default state mid-feedback.
  if (copyResetTimer) {
    clearTimeout(copyResetTimer);
    copyResetTimer = null;
  }
  // Use the shared clipboard utility: it auto-selects between
  // navigator.clipboard.writeText (secure context) and a
  // <textarea>+execCommand("copy") fallback for HTTP / non-secure
  // deployments, and logs `[clipboard] ...` breadcrumbs so we can
  // diagnose future failures from the console alone.
  const ok = await copyToClipboard(props.state.snapshot.content);
  if (ok) {
    copyButtonColor.value = "success";
    copyButtonText.value = tm(
      "spcodeProjectLoad.fileBrowser.preview.copySuccess",
    );
  } else {
    copyButtonColor.value = "error";
    copyButtonText.value = tm("spcodeProjectLoad.fileBrowser.preview.copyFail");
  }
  copyResetTimer = setTimeout(() => {
    copyButtonText.value = tm("spcodeProjectLoad.fileBrowser.preview.copy");
    copyButtonColor.value = undefined;
    copyResetTimer = null;
  }, 2000);
}

// Drop any pending reset timer on unmount. Without this the closure
// would hold a stale ref to the destroyed component's copyButtonText
// and write to it 2s after the user has navigated away, tripping
// Vue's "set operation on key ... failed" warning.
onBeforeUnmount(() => {
  if (copyResetTimer) {
    clearTimeout(copyResetTimer);
    copyResetTimer = null;
  }
});

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}
function formatMtime(mtime: number | null): string {
  if (!mtime) return "—";
  return new Date(mtime * 1000).toLocaleString();
}

// Map the composable's reason codes to localized messages.
const REASON_I18N_KEYS: Record<string, string> = {
  path_not_found: "spcodeProjectLoad.fileBrowser.error.pathNotFound",
  permission_denied: "spcodeProjectLoad.fileBrowser.error.permissionDenied",
  special_file: "spcodeProjectLoad.fileBrowser.error.specialFile",
};

function localizedReason(reason: string): string {
  const key = REASON_I18N_KEYS[reason];
  if (key) return tm(key);
  if (reason === "network") {
    return tm("spcodeProjectLoad.fileBrowser.error.network");
  }
  return tm("spcodeProjectLoad.fileBrowser.error.unknown", { reason });
}

// --- inline comments (Chunk 3) ---
// The file-comments store is a module-level singleton (see
// useFileComments.ts header for why provide/inject was abandoned).
// Every component that calls useFileComments() gets the same instance.
const fileComments = useFileComments();

const activeEditLine = ref<number | null>(null);
const activeEditCommentId = ref<string | null>(null);
const editorInitialText = ref<string>("");
const editorContext = ref<LineContext | null>(null);
const snackbar = ref<{ visible: boolean; text: string }>({
  visible: false,
  text: "",
});

const { width } = useDisplay();
const isMobile = computed<boolean>(() => width.value < 760);

function currentFilePath(): string | null {
  return props.state.kind === "file" ? props.state.snapshot.meta.path : null;
}
function currentFileContent(): string | null {
  return props.state.kind === "file" ? props.state.snapshot.content : null;
}

/** INVARIANT: this watch is the ONLY point that writes to
 *  fileComments.contentCache. Both `onRequestAdd` (via extractLineContext
 *  on state.snapshot.content) and `addComment` (via contentCache) read
 *  the same value, so they MUST stay in sync — a stale preview would
 *  show context that doesn't match what the comment will actually store. */
watch(
  () => currentFileContent(),
  (content) => {
    const path = currentFilePath();
    if (path && content !== null) {
      fileComments.registerFileContent(path, content);
    }
  },
  { immediate: true },
);

function onRequestAdd(line: number): void {
  const path = currentFilePath();
  const content = currentFileContent();
  if (!path || content === null) return;
  activeEditLine.value = line;
  activeEditCommentId.value = null;
  editorInitialText.value = "";
  editorContext.value = extractLineContext(content, line);
}

function onRequestEdit(commentId: string): void {
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
    closeEditor();
    return;
  }
  const path = currentFilePath();
  if (!path) return;
  const created = fileComments.addComment({
    filePath: path,
    line: payload.line,
    text: payload.text,
  });
  if (created === null) {
    snackbar.value = {
      visible: true,
      text: tm("spcodeProjectLoad.fileBrowser.comment.saveError"),
    };
    return;
  }
  closeEditor();
}

function closeEditor(): void {
  activeEditLine.value = null;
  activeEditCommentId.value = null;
  editorContext.value = null;
}

function onDeleteComment(commentId: string): void {
  fileComments.deleteComment(commentId);
  closeEditor();
}
</script>

<template>
  <div class="file-browser-preview" :class="{ 'is-mobile': isMobile }">
    <!-- 加载中 -->
    <div
      v-if="state.kind === 'idle' || state.kind === 'loading'"
      class="preview-center"
    >
      <v-progress-circular indeterminate color="primary" :size="32" />
      <span>{{ tm("spcodeProjectLoad.fileBrowser.loading") }}</span>
    </div>

    <!-- 错误(真错误:path_not_found / permission_denied / special_file / network / unknown) -->
    <div v-else-if="state.kind === 'error'" class="preview-center">
      <v-icon size="32" color="error">mdi-alert-circle-outline</v-icon>
      <div class="preview-error-title">
        {{ tm("spcodeProjectLoad.fileBrowser.error.loadFailedTitle") }}
      </div>
      <div class="preview-error-detail">
        {{ localizedReason(state.reason) }}
      </div>
      <v-btn
        size="small"
        color="primary"
        variant="tonal"
        prepend-icon="mdi-refresh"
        @click="emit('retry')"
      >
        {{ tm("spcodeProjectLoad.fileBrowser.error.retry") }}
      </v-btn>
    </div>

    <!-- 目录状态:左栏已经显示列表,右栏只显示提示 -->
    <div v-else-if="state.kind === 'directory'" class="preview-center">
      <v-icon size="32" color="grey">mdi-folder-open-outline</v-icon>
      <span class="preview-hint">{{
        tm("spcodeProjectLoad.fileBrowser.preview.selectFromLeft")
      }}</span>
    </div>

    <!-- symlink 状态 -->
    <div v-else-if="state.kind === 'symlink'" class="preview-center">
      <v-icon size="32" color="info">mdi-link-variant</v-icon>
      <div class="preview-symlink-info">
        <div class="preview-symlink-target-label">
          → {{ state.snapshot.meta.target }}
        </div>
        <div
          v-if="!state.snapshot.meta.targetExists"
          class="preview-symlink-dangling"
        >
          {{ tm("spcodeProjectLoad.fileBrowser.entryType.dangling") }}
        </div>
      </div>
      <v-btn
        v-if="state.snapshot.meta.targetExists"
        size="small"
        variant="tonal"
        prepend-icon="mdi-arrow-right"
        @click="
          emit(
            'navigate-target',
            resolveTargetPath(
              state.snapshot.meta.path,
              state.snapshot.meta.target,
            ),
          )
        "
      >
        {{ tm("spcodeProjectLoad.fileBrowser.preview.goToTarget") }}
      </v-btn>
    </div>

    <!-- 文件 -->
    <div v-else-if="state.kind === 'file'" class="preview-file">
      <!-- 元信息头 -->
      <div class="preview-file-meta">
        <span class="preview-file-path" :title="state.snapshot.meta.path">{{
          state.snapshot.meta.name
        }}</span>
        <!-- 2026-07-03 ANSI/GBK 支持:当文件编码不是 utf-8 时,
             在元信息头显示一个 subtle 灰色 chip 提示用户。utf-8
             不显示(主流情况,避免视觉噪声);cp936/gbk/gb18030/
             latin-1/utf-8-sig 等显示完整编码名。 -->
        <span
          v-if="state.snapshot.meta.encoding && state.snapshot.meta.encoding !== 'utf-8'"
          class="preview-file-encoding"
          :title="tm('spcodeProjectLoad.fileBrowser.preview.encodingLabel', {
            encoding: state.snapshot.meta.encoding,
          })"
        >
          {{ state.snapshot.meta.encoding }}
        </span>
        <span class="preview-file-size">{{
          formatBytes(state.snapshot.meta.size)
        }}</span>
        <span class="preview-file-mtime">{{
          formatMtime(state.snapshot.meta.mtime)
        }}</span>
        <v-btn
          v-if="state.snapshot.content"
          size="x-small"
          variant="text"
          :color="copyButtonColor"
          prepend-icon="mdi-content-copy"
          @click="copyContent"
        >
          {{ copyButtonText }}
        </v-btn>
      </div>

      <!-- 二进制文件 -->
      <div v-if="state.snapshot.meta.isBinary === true" class="preview-binary">
        <v-icon size="32" color="grey">mdi-file-question-outline</v-icon>
        <span>{{ tm("spcodeProjectLoad.fileBrowser.preview.binary") }}</span>
      </div>

      <!-- 过大文件 -->
      <div v-else-if="state.snapshot.content === null" class="preview-binary">
        <v-icon size="32" color="grey">mdi-file-alert-outline</v-icon>
        <span>{{
          tm("spcodeProjectLoad.fileBrowser.preview.tooLarge", {
            size: formatBytes(state.snapshot.meta.size),
          })
        }}</span>
      </div>

      <!-- 文本内容(Shiki 高亮) + 行内评论 gutter/编辑器 -->
      <FileBrowserCodeView
        v-else
        :highlighted-html="highlightedHtml"
        :file-path="state.snapshot.meta.path"
        :comments="fileComments.commentsForFile(state.snapshot.meta.path)"
        :active-edit-line="activeEditLine"
        :active-edit-comment-id="activeEditCommentId"
        :is-dark="isDark"
        :scroll-to-line="props.scrollToLine ?? null"
        @request-add="onRequestAdd"
        @request-edit="onRequestEdit"
      />
      <FileCommentEditor
        v-if="activeEditLine !== null"
        :line="activeEditLine"
        :comment-id="activeEditCommentId"
        :initial-text="editorInitialText"
        :line-content="editorContext?.lineContent ?? null"
        :context-before="editorContext?.contextBefore ?? null"
        :context-after="editorContext?.contextAfter ?? null"
        :file-path="state.snapshot.meta.path"
        @save="onSaveComment"
        @cancel="closeEditor"
        @delete="onDeleteComment"
      />
    </div>
    <v-snackbar
      v-model="snackbar.visible"
      :timeout="4000"
      color="error"
      location="bottom"
    >
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<style scoped>
.file-browser-preview {
  /* Width is now driven by FileBrowserView's draggable divider
     (sets `width` via inline style on .file-browser-pane-right, which
     this root element inherits as its wrapping class). */
  flex: 1 1 auto;
  min-width: 0;
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: transparent;
}
.preview-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  height: 100%;
  padding: 32px 16px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 13px;
  text-align: center;
}
.preview-hint {
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 12.5px;
}
.preview-error-title {
  color: rgba(var(--v-theme-error), 1);
  font-weight: 500;
  font-size: 14px;
}
.preview-error-detail {
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-size: 12.5px;
  max-width: 320px;
}

.preview-file {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.preview-file-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 14px;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-surface), 0.4);
}
.preview-file-path {
  flex: 1;
  font-family: ui-monospace, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preview-file-size,
.preview-file-mtime {
  font-variant-numeric: tabular-nums;
  color: rgba(var(--v-theme-on-surface), 0.4);
}
/* 2026-07-03 ANSI/GBK 支持:非 utf-8 文件在元信息头显示编码徽章。
   视觉上与 .preview-file-size 同级但用 monospace + 浅色背景区分,
   让用户一眼看出"这不是 utf-8"。hover 时显示 i18n 完整提示。 */
.preview-file-encoding {
  font-family: ui-monospace, monospace;
  font-size: 10.5px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgba(var(--v-theme-on-surface), 0.7);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  cursor: help;
  user-select: none;
}
.preview-file-content {
  flex: 1;
  margin: 0;
  padding: 12px 14px;
  overflow: auto;
  font-family: ui-monospace, monospace;
  font-size: 12.5px;
  line-height: 1.55;
  background: transparent !important;
}
.preview-binary {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 16px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 13px;
}
.preview-symlink-info {
  font-family: ui-monospace, monospace;
  font-size: 13px;
  text-align: center;
}
.preview-symlink-target-label {
  color: rgb(var(--v-theme-info));
}
.preview-symlink-dangling {
  color: rgb(248, 81, 73);
  font-size: 12px;
  margin-top: 6px;
}

/* Mobile fullscreen overlay for the inline-comment editor.
   Lives here (not in FileCommentEditor.vue) so the .file-browser-preview
   class is in the same Vue scope - see Chunk 2 review. */
.file-browser-preview.is-mobile .comment-editor {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgb(var(--v-theme-surface));
  display: flex;
  flex-direction: column;
}
.file-browser-preview.is-mobile .comment-editor-input {
  flex: 1;
  resize: none;
}
</style>
