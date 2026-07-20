<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.3
     Left pane: the docs root directory tree, plus a "new file"
     input. Reuses FileTreeList for the tree itself. The tree
     is filtered to .md / .txt (the only formats the doc manager
     edits), and clicking a matched file emits "select". -->
<script setup lang="ts">
import { computed, ref } from "vue";
import { useSpcodeFileBrowser } from "@/composables/useSpcodeFileBrowser";
import { useModuleI18n } from "@/i18n/composables";
import {
  projectRelativePath,
  docsRootRelativePath,
  absoluteFromSelectedDoc,
} from "@/composables/pathUtils";
import { isProjectRootDocs } from "@/composables/docsRootStorage";
import FileTreeList from "./FileTreeList.vue";
import type { SpcodeFileBrowserEntry } from "@/composables/parseSpcodeFileBrowser";

/** Whitelist of file extensions the document manager accepts.
 *  Used both for the tree filter (FileBrowserEntryList's
 *  allowedExtensions prop) AND for the "new file" filename
 *  validator + the click-to-select allowlist below. Keeping a
 *  single source of truth means adding ".adoc" later is a
 *  one-line change here. Typed as `string[]` (not `as const`)
 *  because the receiving prop is declared `string[]` — using
 *  `as const` here would yield `readonly [".md", ".txt"]`,
 *  which TS rejects as not assignable to a mutable `string[]`.
 *  Case is normalized at the comparison site so the values
 *  themselves can stay lowercase. */
const ALLOWED_DOC_EXTENSIONS: string[] = [".md", ".txt"];

function isAllowedDocFile(name: string): boolean {
  const lower = name.toLowerCase();
  return ALLOWED_DOC_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

const props = defineProps<{
  currentDir: string;
  rootPath: string | null;
  isDark: boolean;
  selectedFile: string | null;
}>();

const emit = defineEmits<{
  (e: "navigate", dirRel: string): void;
  (e: "select", fileRel: string): void;
  (e: "create-new", name: string): void;
  (e: "breadcrumb-navigate", dirRel: string): void;
}>();

const { tm } = useModuleI18n("features/chat");

// Path must combine projectRoot + currentDir (= docsRoot) so the
// tree lists the docs/ subtree, not the project root itself.
// Without this, the pathRef stays at the project root and the user
// sees the whole AstrBot directory instead of "docs/". When the
// user has set docsRoot to ".", the docs subtree IS the project
// root, so we skip the `${root}/${dir}` glue and just hand the
// projectRoot straight to the file-browser composable.
const fileBrowser = useSpcodeFileBrowser(
  computed(() => {
    const root = props.rootPath;
    if (!root) return "";
    const dir = props.currentDir?.trim() ?? "";
    if (!dir || isProjectRootDocs(dir)) return root;
    return `${root.replace(/[\\/]+$/, "")}/${dir.replace(/^[\\/]+/, "")}`;
  }),
);

const newName = ref("");
const newNameError = ref<string | null>(null);

/** Re-derive the absolute path that `entry.path` carries for the
 *  currently-selected file. The parent (DocumentManager) gives us
 *  a docsRoot-relative `selectedFile`, but FileBrowserEntryList's
 *  `is-selected` highlight compares against `entry.path`, which
 *  the backend always returns as an absolute path. Without this
 *  re-derivation the comparison never matches and the highlight
 *  is silently lost. We use the existing `absoluteFromSelectedDoc`
 *  helper (which is just the inverse of `docsRootRelativePath`)
 *  to keep the path-glue logic in one place. */
const selectedAbsolutePath = computed<string | null>(() => {
  if (!props.selectedFile) return null;
  return absoluteFromSelectedDoc(
    props.rootPath,
    props.currentDir,
    props.selectedFile,
  );
});

// The file-browser endpoint returns absolute paths on every entry
// (see SpcodeFileBrowserEntry.path — "Absolute path of this entry
// (round-trip from backend)"). DocumentManager keeps two distinct
// relative-path slots:
//   - docsRoot   — project-relative path, e.g. "docs/superpowers"
//   - selectedDoc — docsRoot-relative path, e.g. "specs/foo.md"
// and assembles the absolute path via `projectRoot + docsRoot +
// selectedDoc`. If we forwarded the absolute path here,
// DocumentManager would glue it back onto the prefix, producing
// paths like "F:\repo\docs\F:\repo\docs\README.md" that the
// backend resolves as path_not_found. The shared
// `projectRelativePath` / `docsRootRelativePath` helpers in
// pathUtils.ts handle that translation; this component just
// forwards the entry's absolute path through the right helper
// for each emit.

function onEntryNavigate(entry: SpcodeFileBrowserEntry) {
  if (entry.type === "directory") {
    // For a directory emit a project-relative path; DocumentManager
    // assigns it to docsRoot directly.
    emit("navigate", projectRelativePath(entry.path, props.rootPath));
  } else if (entry.type === "file" && isAllowedDocFile(entry.name)) {
    // For an allowed file emit a docsRoot-relative path;
    // DocumentManager assigns it to selectedDoc.
    emit(
      "select",
      docsRootRelativePath(entry.path, props.rootPath, props.currentDir),
    );
  }
  // Files outside the whitelist (e.g. .json, .py) are filtered
  // out by FileBrowserEntryList's allowedExtensions prop, so this
  // branch is only reached for directories and whitelist matches.
}

// 2026-07-20: the inner-tree breadcrumb now emits the same
// { dirPath, previewPath } payload shape as the top-level
// FileBrowserBreadcrumb in DocumentManager (via FileTreeList
// re-emission). We translate the file case into the existing
// "select" event so DocumentManager can stay on a string-typed
// breadcrumb-navigate contract and not need to know about the
// payload shape — it just sees "tree navigated to <dir>" plus,
// optionally, "tree also wants <file> selected".
//
// The directory case is unchanged: project-relative path goes
// out on `breadcrumb-navigate` and DocumentManager sets it as
// docsRoot.
function onBreadcrumbNavigate(payload: {
  dirPath: string;
  previewPath: string | null;
}) {
  const dirRel = projectRelativePath(payload.dirPath, props.rootPath);
  emit("breadcrumb-navigate", dirRel);
  if (payload.previewPath) {
    // File path typed into the inner breadcrumb: mirror what
    // DocumentManager's top-level onBreadcrumbNavigate does —
    // select the file (docsRoot-relative form so the rest of
    // DocumentManager can stay relative-path-typed).
    const fileRel = docsRootRelativePath(
      payload.previewPath,
      props.rootPath,
      dirRel,
    );
    emit("select", fileRel);
  }
}

// Exposed so the parent (DocumentManager) can force a re-fetch of
// the directory listing after save / rename / delete / create — the
// parent's own `fileBrowser` instance points at the *selected file*,
// not at this tree's docsRoot, so it can't refresh us implicitly.
defineExpose({
  refresh: () => fileBrowser.refresh(),
});

function onSubmitNew() {
  const name = newName.value.trim();
  // Build a regex like /^(...)\.(md|txt)$/i from the whitelist
  // so adding ".adoc" etc. is automatic. The character class
  // accepts the same set the previous .md-only validator did:
  // word chars, dash, dot, slash, space. Slash is permitted so
  // the user can pre-fill a path like "subdir/note.md", but
  // note that the backend will reject ".." segments; that's
  // handled in the rename/save path, not here.
  const exts = ALLOWED_DOC_EXTENSIONS.map((e) => e.slice(1)).join("|");
  const re = new RegExp(`^[\\w\\-./ ]+\\.(${exts})$`, "i");
  if (!re.test(name)) {
    newNameError.value = tm(
      "spcodeProjectLoad.documentManager.editor.filenameInvalid",
    );
    return;
  }
  newNameError.value = null;
  newName.value = "";
  emit("create-new", name);
}
</script>

<template>
  <div class="document-tree-panel">
    <FileTreeList
      :state="fileBrowser.state.value"
      :selected-path="selectedAbsolutePath"
      :root-path="rootPath"
      :preview-path="null"
      :is-dark="isDark"
      :allowed-extensions="ALLOWED_DOC_EXTENSIONS"
      @navigate="onEntryNavigate"
      @breadcrumb-navigate="onBreadcrumbNavigate"
    />
    <form class="document-tree-panel__new" @submit.prevent="onSubmitNew">
      <input
        v-model="newName"
        type="text"
        class="document-tree-panel__new-input"
        :placeholder="
          tm('spcodeProjectLoad.documentManager.editor.createFilePlaceholder')
        "
      />
      <button
        type="submit"
        class="document-tree-panel__new-btn"
        :title="tm('spcodeProjectLoad.documentManager.editor.newFile')"
        :disabled="!newName"
      >
        <v-icon size="14">mdi-plus</v-icon>
      </button>
    </form>
    <span v-if="newNameError" class="document-tree-panel__new-error">{{ newNameError }}</span>
  </div>
</template>


<style scoped>
.document-tree-panel {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}
.document-tree-panel__new {
  display: flex;
  gap: 4px;
  padding: 4px 8px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.document-tree-panel__new-input {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 11.5px;
  padding: 3px 6px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  border-radius: 4px;
  background: var(--v-theme-surface, transparent);
  color: rgb(var(--v-theme-on-surface));
  outline: none;
}
.document-tree-panel__new-input:focus {
  border-color: rgb(var(--v-theme-primary));
}
.document-tree-panel__new-btn {
  border: 1px solid rgba(var(--v-theme-primary), 0.4);
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
  border-radius: 4px;
  padding: 2px 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
}
.document-tree-panel__new-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.document-tree-panel__new-error {
  font-size: 11px;
  color: rgb(var(--v-theme-error));
  padding: 0 8px 4px;
}
</style>
