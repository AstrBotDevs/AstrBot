# Workspace History Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the workspace page's "查看文件历史" affordance so it provides the same functionality as the file-manager page's history sidebar: per-file commit list with "view this revision" and "compare with current" actions, a banner showing the active SHA, and a "回到当前" button.

**Architecture:** Replace the standalone `GitLogView` inside `GitDiffSidebar.vue`'s History tab with a two-column layout: a new `<GitHistorySidebar>` (mirror of `DocumentHistoryPanel`) on the left, and a new `<GitRevisionPreview>` on the right that uses the existing `useSpcodeGitFile` and `useSpcodeGitShow` composables (both already in production via `DocumentManager.vue`) to fetch historical blobs and diffs. No backend changes are required.

**Tech Stack:** Vue 3.3.4, Vuetify 3.7.11, TypeScript 5.1.6, vitest 1.6, vue-tsc 1.8.8, pnpm 9.

**Spec:** `docs/superpowers/specs/2026-07-15-workspace-history-sidebar-design.md`
**Backend contract (verified during Task 1):** `GET /spcode/git-file?ref=<sha>&path=<rel>` returns `{ content, is_binary, sha, ... }` — already used by `DocumentManager.vue`. `GET /spcode/git-show?ref=<sha>&path=<rel>` returns `patch: string` — already used by `DocumentManager.vue` for its "compare with current" affordance. **No backend changes required.**

## Global Constraints

- Backend plugin lives in `F:\github\astrbot_plugin_spcode_toolkit` — **do not modify**. This task is frontend-only.
- Vue 3 `<script setup lang="ts">` with Composition API; reuse `useModuleI18n("features/chat")` for i18n.
- Styling follows BEM within the new components (`git-history-sidebar__*`, `git-revision-preview__*`); mirror the look of `DocumentHistoryPanel` / `DocumentManager`'s banner.
- All i18n keys live under `spcodeProjectLoad.*` (zh-CN + en-US).
- Comments and logs in English per AGENTS.md §1.5.
- Run `pnpm lint` (or `pnpm exec ruff check dashboard` if ruff covers TS) and `pnpm build` at the end to verify.
- Use `pathlib`-style path handling (frontend uses `@/composables/...` import aliases; no string concatenation).
- Conventional commits: `feat(dashboard): ...`, `refactor(dashboard): ...`.

## File Structure

| Path | Responsibility |
|---|---|
| `dashboard/src/components/chat/message_list_comps/GitHistorySidebar.vue` | New. Per-file commit list with working-tree pseudo-row, eye/compare actions, collapse button. |
| `dashboard/src/components/chat/message_list_comps/GitRevisionPreview.vue` | New. Renders banner + raw/diff view of selected revision. |
| `dashboard/src/components/chat/GitDiffSidebar.vue` | Modify. Add history state, mount the two new components in History tab, update `setLogPathFilter`. |
| `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue` | Modify. Hide the "查看文件历史" button when the file is binary. |
| `dashboard/src/i18n/locales/zh-CN/features/chat.json` | Modify. Add 6 keys under `spcodeProjectLoad.gitHistory.*`. |
| `dashboard/src/i18n/locales/en-US/features/chat.json` | Modify. Add matching 6 en-US keys. |
| `dashboard/src/components/chat/message_list_comps/GitHistorySidebar.spec.ts` | New. Vitest spec mirroring `DocumentManager.spec.ts` strategy. |
| `dashboard/src/components/chat/message_list_comps/GitRevisionPreview.spec.ts` | New. Vitest spec. |

`useSpcodeGitFile` and `useSpcodeGitShow` are reused as-is (already verified at task time of `DocumentManager`).

---

## Task 1: Verify backend endpoints and i18n baseline

**Files:**
- Read-only check (no edits this task).

**Steps:**

- [ ] **Step 1: Verify `useSpcodeGitFile.fetchRef(path, ref)` returns content for non-md text files**

Open `dashboard/src/composables/useSpcodeGitFile.ts`. Confirm the response handler accepts arbitrary text content (not markdown-specific). Expected: the `content` field is read generically (`typeof data.content === "string"`) and `isBinary` is the only type-specific branch. Confirmed by reading lines 130-180 of the existing file: yes, it is generic.

- [ ] **Step 2: Verify `useSpcodeGitShow.fetchFile(sha, path)` returns a patch string**

Open `dashboard/src/composables/useSpcodeGitShow.ts`. Search for `fetchFile` definition. Expected signature: `fetchFile(refName: string, filePath: string): Promise<void>`; read result via `getFileData(sha, path)?.patch`. Confirmed by reading the watch block in `DocumentManager.vue` line 232 — the existing usage pulls `snap.patch ?? null`.

- [ ] **Step 3: Commit marker (no code change)**

This task produces no diff. Run `git status --short` and confirm it is empty.

```bash
cd F:\github\Astrbot && git status --short
```

Expected: empty output.

---

## Task 2: Add i18n keys (zh-CN + en-US)

**Files:**
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json` (under `spcodeProjectLoad.gitHistory`)
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json` (under `spcodeProjectLoad.gitHistory`)

**Steps:**

- [ ] **Step 1: Locate the `spcodeProjectLoad.documentManager.history` block in zh-CN**

```bash
cd F:\github\Astrbot
grep -n "spcodeProjectLoad.documentManager.history" dashboard/src/i18n/locales/zh-CN/features/chat.json
```

Expected: a `history: { title, currentPlaceholder, viewThisRevision, compareWithCurrent, loadFail, noSelection }` block.

- [ ] **Step 2: Add `gitHistory` keys after the `documentManager` block in zh-CN**

In `dashboard/src/i18n/locales/zh-CN/features/chat.json`, find the closing `}` of the `documentManager` object and append immediately after:

```json
,
"gitHistory": {
  "banner": {
    "viewing": "正在查看历史版本 {sha}",
    "backToCurrent": "回到当前"
  },
  "preview": {
    "tabRaw": "原文",
    "tabDiff": "本次改动",
    "placeholder": "选择左侧 commit 查看历史版本",
    "binaryUnsupported": "二进制文件不支持历史版本预览",
    "diffLoadFail": "无法加载 diff: {reason}",
    "rawLoadFail": "无法读取历史版本: {reason}",
    "loading": "加载中…"
  },
  "sidebar": {
    "title": "历史",
    "collapse": "隐藏历史",
    "expand": "显示历史"
  }
}
```

(The leading `,` is intentional — the previous object ends with `}` and we are inserting a new sibling key.)

- [ ] **Step 3: Add matching keys in en-US**

In `dashboard/src/i18n/locales/en-US/features/chat.json`, find the matching `spcodeProjectLoad.documentManager.history` block and insert the same `gitHistory` block, with these English values:

```json
,
"gitHistory": {
  "banner": {
    "viewing": "Viewing historical revision {sha}",
    "backToCurrent": "Back to current"
  },
  "preview": {
    "tabRaw": "Raw",
    "tabDiff": "Diff",
    "placeholder": "Select a commit on the left to view its content.",
    "binaryUnsupported": "Binary files cannot be previewed from history.",
    "diffLoadFail": "Failed to load diff: {reason}",
    "rawLoadFail": "Failed to read historical revision: {reason}",
    "loading": "Loading…"
  },
  "sidebar": {
    "title": "History",
    "collapse": "Hide history",
    "expand": "Show history"
  }
}
```

- [ ] **Step 4: Verify both files are valid JSON**

```bash
cd F:\github\Astrbot\dashboard
node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/zh-CN/features/chat.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/en-US/features/chat.json','utf8')); console.log('ok')"
```

Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
cd F:\github\Astrbot && git add dashboard/src/i18n/locales/ && git commit -m "feat(dashboard): add workspace history sidebar i18n keys"
```

---

## Task 3: Create `GitHistorySidebar.vue`

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/GitHistorySidebar.vue`
- Create: `dashboard/src/components/chat/message_list_comps/GitHistorySidebar.spec.ts`

**Interfaces:**
- Consumes: `UseSpcodeGitLog` (exported from `@/composables/useSpcodeGitLog`).
- Produces (props/emits — used by Task 5):
  - props: `{ gitLog: UseSpcodeGitLog; fileRelative: string | null; currentRevision: string | null; isLoading: boolean }`
  - emits: `(e: 'select-revision', sha: string): void`, `(e: 'compare-current', sha: string): void`, `(e: 'collapse'): void`

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `dashboard/src/components/chat/message_list_comps/GitHistorySidebar.spec.ts`:

```ts
// Author: elecvoid243, 2026-07-15
// Spec: docs/superpowers/specs/2026-07-15-workspace-history-sidebar-design.md §4.5
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { ref } from "vue";
import GitHistorySidebar from "./GitHistorySidebar.vue";

const sampleCommits = [
  { sha: "abcdef1234567", subject: "init", author: "alice", date: "2026-01-01" },
  { sha: "1234567abcdef", subject: "fix typo", author: "bob", date: "2026-01-02" },
];

function makeGitLog() {
  return {
    state: ref({ kind: "ok", snapshot: { commits: sampleCommits, has_more: false }, notModified: false }),
    filter: ref({}),
    refresh: () => Promise.resolve(),
  };
}

describe("GitHistorySidebar", () => {
  it("renders a working-tree pseudo-row", () => {
    const wrapper = mount(GitHistorySidebar, {
      props: { gitLog: makeGitLog(), fileRelative: "docs/a.md", currentRevision: null, isLoading: false },
      global: { mocks: { $t: (k: string) => k } },
    });
    expect(wrapper.text()).toContain("currentPlaceholder");
  });

  it("emits select-revision when the eye action is clicked", async () => {
    const wrapper = mount(GitHistorySidebar, {
      props: { gitLog: makeGitLog(), fileRelative: "docs/a.md", currentRevision: null, isLoading: false },
      global: { mocks: { $t: (k: string) => k } },
    });
    const eyeButtons = wrapper.findAll('[title="viewThisRevision"]');
    await eyeButtons[0].trigger("click");
    expect(wrapper.emitted("select-revision")?.[0]).toEqual([sampleCommits[0].sha]);
  });

  it("emits compare-current when the compare action is clicked", async () => {
    const wrapper = mount(GitHistorySidebar, {
      props: { gitLog: makeGitLog(), fileRelative: "docs/a.md", currentRevision: null, isLoading: false },
      global: { mocks: { $t: (k: string) => k } },
    });
    const cmpButtons = wrapper.findAll('[title="compareWithCurrent"]');
    await cmpButtons[0].trigger("click");
    expect(wrapper.emitted("compare-current")?.[0]).toEqual([sampleCommits[0].sha]);
  });

  it("emits collapse when the collapse button is clicked", async () => {
    const wrapper = mount(GitHistorySidebar, {
      props: { gitLog: makeGitLog(), fileRelative: "docs/a.md", currentRevision: null, isLoading: false },
      global: { mocks: { $t: (k: string) => k } },
    });
    await wrapper.find(".git-history-sidebar__collapse").trigger("click");
    expect(wrapper.emitted("collapse")).toBeTruthy();
  });

  it("marks the active row when currentRevision matches a commit", () => {
    const wrapper = mount(GitHistorySidebar, {
      props: { gitLog: makeGitLog(), fileRelative: "docs/a.md", currentRevision: "abcdef1234567", isLoading: false },
      global: { mocks: { $t: (k: string) => k } },
    });
    const activeRows = wrapper.findAll(".git-history-sidebar__row.active");
    expect(activeRows.length).toBe(1);
    expect(activeRows[0].text()).toContain("abcdef1");
  });
});
```

- [ ] **Step 2: Run the test and confirm it fails (component does not exist yet)**

```bash
cd F:\github\Astrbot\dashboard && pnpm vitest run src/components/chat/message_list_comps/GitHistorySidebar.spec.ts
```

Expected: FAIL with "Cannot find module './GitHistorySidebar.vue'" or similar.

- [ ] **Step 3: Create `GitHistorySidebar.vue`**

Create `dashboard/src/components/chat/message_list_comps/GitHistorySidebar.vue`:

```vue
<!-- Author: elecvoid243, 2026-07-15
     Spec: docs/superpowers/specs/2026-07-15-workspace-history-sidebar-design.md §"GitHistorySidebar"
     Per-file commit list for the workspace page's History tab.
     Mirrors DocumentHistoryPanel.vue's structure: working-tree
     pseudo-row + per-commit eye/compare actions + collapse button.
     BEM root renamed to git-history-sidebar__* so the two panels
     do not collide. -->
<script setup lang="ts">
import { computed, watch } from "vue";
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
  if (s.kind === "error") return s.previousSnapshot?.commits ?? [];
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
</script>

<template>
  <aside class="git-history-sidebar">
    <header class="git-history-sidebar__header">
      <span>{{ tm("spcodeProjectLoad.gitHistory.sidebar.title") }}</span>
      <button
        type="button"
        class="git-history-sidebar__collapse"
        data-testid="git-history-collapse"
        :title="tm('spcodeProjectLoad.gitHistory.sidebar.collapse')"
        :aria-label="tm('spcodeProjectLoad.gitHistory.sidebar.collapse')"
        @click="emit('collapse')"
      >
        <v-icon size="14">mdi-chevron-double-right</v-icon>
      </button>
    </header>
    <div v-if="!fileRelative" class="git-history-sidebar__empty">
      {{ tm("spcodeProjectLoad.documentManager.history.noSelection") }}
    </div>
    <div v-else-if="isLoading" class="git-history-sidebar__loading">
      <v-progress-circular indeterminate size="16" width="2" />
    </div>
    <div
      v-else-if="errorReason && commits.length === 0"
      class="git-history-sidebar__error"
    >
      {{ tm("spcodeProjectLoad.documentManager.history.loadFail") }}:
      {{ errorReason }}
    </div>
    <div v-else-if="commits.length === 0" class="git-history-sidebar__empty">
      {{ tm("spcodeProjectLoad.documentManager.tree.noHistory") }}
    </div>
    <ul v-else class="git-history-sidebar__list">
      <li
        :class="['git-history-sidebar__row', { active: isWorkingTreeActive }]"
      >
        <div class="git-history-sidebar__row-sha">working</div>
        <div class="git-history-sidebar__row-subject">
          {{
            tm(
              "spcodeProjectLoad.documentManager.history.currentPlaceholder",
            )
          }}
        </div>
      </li>
      <li
        v-for="c in commits"
        :key="c.sha"
        :class="[
          'git-history-sidebar__row',
          { active: currentRevision === c.sha },
        ]"
      >
        <div class="git-history-sidebar__row-sha">{{ shortSha(c.sha) }}</div>
        <div class="git-history-sidebar__row-subject">
          <div class="git-history-sidebar__row-subject-text">{{ c.subject }}</div>
          <div class="git-history-sidebar__row-author">{{ c.author }}</div>
        </div>
        <div class="git-history-sidebar__row-actions">
          <button
            type="button"
            class="git-history-sidebar__action"
            :title="
              tm('spcodeProjectLoad.documentManager.history.viewThisRevision')
            "
            @click="emit('select-revision', c.sha)"
          >
            <v-icon size="12">mdi-eye-outline</v-icon>
          </button>
          <button
            type="button"
            class="git-history-sidebar__action"
            :title="
              tm(
                'spcodeProjectLoad.documentManager.history.compareWithCurrent',
              )
            "
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
.git-history-sidebar {
  display: flex;
  flex-direction: column;
  flex: 0 0 220px;
  min-height: 0;
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  background: rgba(var(--v-theme-on-surface), 0.03);
  overflow: hidden;
  position: relative;
}
.git-history-sidebar__header {
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
.git-history-sidebar__collapse {
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
.git-history-sidebar__collapse:hover,
.git-history-sidebar__collapse:focus-visible {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
  border-color: rgba(var(--v-theme-primary), 0.4);
  outline: none;
}
.git-history-sidebar__empty,
.git-history-sidebar__loading,
.git-history-sidebar__error {
  padding: 12px 10px;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  text-align: center;
}
.git-history-sidebar__error {
  color: rgb(var(--v-theme-error));
}
.git-history-sidebar__list {
  list-style: none;
  margin: 0;
  padding: 4px 0;
  overflow-y: auto;
  flex: 1 1 auto;
  min-height: 0;
}
.git-history-sidebar__row {
  display: grid;
  grid-template-columns: 56px 1fr auto;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  font-size: 11.5px;
  cursor: default;
  border-left: 2px solid transparent;
}
.git-history-sidebar__row:hover {
  background: rgba(var(--v-theme-primary), 0.06);
}
.git-history-sidebar__row.active {
  background: rgba(var(--v-theme-primary), 0.12);
  border-left-color: rgb(var(--v-theme-primary));
}
.git-history-sidebar__row-sha {
  font-family: monospace;
  color: rgba(var(--v-theme-on-surface), 0.55);
}
.git-history-sidebar__row-subject {
  min-width: 0;
  overflow: hidden;
}
.git-history-sidebar__row-subject-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.git-history-sidebar__row-author {
  font-size: 10.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.git-history-sidebar__row-actions {
  display: flex;
  gap: 2px;
}
.git-history-sidebar__action {
  border: none;
  background: transparent;
  padding: 2px;
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.55);
  display: flex;
  align-items: center;
  border-radius: 3px;
}
.git-history-sidebar__action:hover {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}
</style>
```

- [ ] **Step 4: Run the test, confirm it passes**

```bash
cd F:\github\Astrbot\dashboard && pnpm vitest run src/components/chat/message_list_comps/GitHistorySidebar.spec.ts
```

Expected: 5 passing tests.

- [ ] **Step 5: Commit**

```bash
cd F:\github\Astrbot && git add dashboard/src/components/chat/message_list_comps/GitHistorySidebar.vue dashboard/src/components/chat/message_list_comps/GitHistorySidebar.spec.ts && git commit -m "feat(dashboard): add GitHistorySidebar component"
```

---

## Task 4: Create `GitRevisionPreview.vue`

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/GitRevisionPreview.vue`
- Create: `dashboard/src/components/chat/message_list_comps/GitRevisionPreview.spec.ts`

**Interfaces:**
- Consumes: `UseSpcodeGitFile` (from `@/composables/useSpcodeGitFile`), a `diffPatch: string | null` string already fetched by the parent.
- Produces:
  - props: `{ fileRelative: string | null; selectedRevision: string | null; previewMode: 'raw' | 'diff'; isDark: boolean; gitFile: UseSpcodeGitFile; diffPatch: string | null; diffLoading: boolean }`
  - emits: `(e: 'back-to-current'): void`, `(e: 'update:previewMode', mode: 'raw' | 'diff'): void`

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `dashboard/src/components/chat/message_list_comps/GitRevisionPreview.spec.ts`:

```ts
// Author: elecvoid243, 2026-07-15
// Spec: docs/superpowers/specs/2026-07-15-workspace-history-sidebar-design.md §"GitRevisionPreview"
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { ref } from "vue";
import GitRevisionPreview from "./GitRevisionPreview.vue";

function makeGitFile(data: { content: string; isBinary?: boolean } | null = null) {
  return {
    fetchRef: () => Promise.resolve(),
    getData: () =>
      data
        ? {
            sha: "abc",
            path: "docs/a.md",
            content: data.content,
            isBinary: data.isBinary ?? false,
            ref: "abc",
            size: data.content.length,
            truncated: false,
            maxBytes: 1048576,
            resolvedSha: "abc",
          }
        : null,
    getState: () => ({ kind: data ? "ok" : "idle" }),
    isLoading: () => false,
    invalidateAll: () => {},
    dispose: () => {},
  };
}

describe("GitRevisionPreview", () => {
  it("shows the placeholder when no revision is selected", () => {
    const wrapper = mount(GitRevisionPreview, {
      props: {
        fileRelative: "docs/a.md",
        selectedRevision: null,
        previewMode: "raw",
        isDark: false,
        gitFile: makeGitFile(null),
        diffPatch: null,
        diffLoading: false,
      },
      global: { mocks: { $t: (k: string) => k } },
    });
    expect(wrapper.text()).toContain("preview.placeholder");
  });

  it("renders the banner when a revision is selected", () => {
    const wrapper = mount(GitRevisionPreview, {
      props: {
        fileRelative: "docs/a.md",
        selectedRevision: "abcdef1234567",
        previewMode: "raw",
        isDark: false,
        gitFile: makeGitFile({ content: "# hi" }),
        diffPatch: null,
        diffLoading: false,
      },
      global: { mocks: { $t: (k: string) => k } },
    });
    expect(wrapper.text()).toContain("abcdef1");
  });

  it("emits back-to-current when the back button is clicked", async () => {
    const wrapper = mount(GitRevisionPreview, {
      props: {
        fileRelative: "docs/a.md",
        selectedRevision: "abcdef1234567",
        previewMode: "raw",
        isDark: false,
        gitFile: makeGitFile({ content: "# hi" }),
        diffPatch: null,
        diffLoading: false,
      },
      global: { mocks: { $t: (k: string) => k } },
    });
    await wrapper.find(".git-revision-preview__back").trigger("click");
    expect(wrapper.emitted("back-to-current")).toBeTruthy();
  });

  it("renders the binary fallback when the file is binary", () => {
    const wrapper = mount(GitRevisionPreview, {
      props: {
        fileRelative: "img.png",
        selectedRevision: "abcdef1234567",
        previewMode: "raw",
        isDark: false,
        gitFile: makeGitFile({ content: "", isBinary: true }),
        diffPatch: null,
        diffLoading: false,
      },
      global: { mocks: { $t: (k: string) => k } },
    });
    expect(wrapper.text()).toContain("preview.binaryUnsupported");
  });
});
```

- [ ] **Step 2: Run the test and confirm it fails**

```bash
cd F:\github\Astrbot\dashboard && pnpm vitest run src/components/chat/message_list_comps/GitRevisionPreview.spec.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Create `GitRevisionPreview.vue`**

Create `dashboard/src/components/chat/message_list_comps/GitRevisionPreview.vue`:

```vue
<!-- Author: elecvoid243, 2026-07-15
     Spec: docs/superpowers/specs/2026-07-15-workspace-history-sidebar-design.md §"GitRevisionPreview"
     Right column of the workspace History tab. Shows a banner
     "viewing revision {sha}" with a back button, a raw/diff tab
     strip, and either the historical file content (text rendered
     via FileBrowserCodeView; .md via MarkdownView; binary via the
     binary fallback placeholder) or the unified-diff patch.
     Diff mode delegates to the parent's diffPatch prop — the
     parent already owns the useSpcodeGitShow.fetchFile call,
     matching how DocumentManager.vue drives its diff region. -->
<script setup lang="ts">
import { computed, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { UseSpcodeGitFile } from "@/composables/useSpcodeGitFile";
import FileBrowserCodeView from "@/components/chat/message_list_comps/FileBrowserCodeView.vue";
import MarkdownView from "@/components/shared/MarkdownView.vue";
import DiffPreview from "@/components/chat/message_list_comps/DiffPreview.vue";

const props = defineProps<{
  fileRelative: string | null;
  selectedRevision: string | null;
  previewMode: "raw" | "diff";
  isDark: boolean;
  gitFile: UseSpcodeGitFile;
  diffPatch: string | null;
  diffLoading: boolean;
}>();
const emit = defineEmits<{
  (e: "back-to-current"): void;
  (e: "update:previewMode", mode: "raw" | "diff"): void;
}>();
const { tm } = useModuleI18n("features/chat");

// Trigger blob fetch whenever a revision becomes selected (raw mode).
watch(
  () => [props.fileRelative, props.selectedRevision] as const,
  ([path, rev]) => {
    if (!path || !rev) return;
    void props.gitFile.fetchRef(path, rev);
  },
  { immediate: true },
);

const isMarkdown = computed(
  () => !!props.fileRelative && props.fileRelative.toLowerCase().endsWith(".md"),
);

const rawData = computed(() => {
  if (!props.fileRelative || !props.selectedRevision) return null;
  return props.gitFile.getData(props.fileRelative, props.selectedRevision);
});

const rawState = computed(() => {
  if (!props.fileRelative || !props.selectedRevision) return { kind: "idle" };
  return props.gitFile.getState(props.fileRelative, props.selectedRevision);
});

const rawLoading = computed(
  () => !!props.selectedRevision && props.previewMode === "raw" && rawState.value.kind === "loading",
);

const rawErrorReason = computed<string | null>(() => {
  const s = rawState.value;
  return s.kind === "error" ? s.reason : null;
});

const rawContent = computed(() => rawData.value?.content ?? "");

function shortSha(sha: string): string {
  return sha.slice(0, 7);
}

function selectMode(mode: "raw" | "diff") {
  if (mode !== props.previewMode) emit("update:previewMode", mode);
}
</script>

<template>
  <section class="git-revision-preview">
    <header
      v-if="selectedRevision"
      class="git-revision-preview__banner"
      data-testid="git-revision-banner"
    >
      <span>
        {{
          tm("spcodeProjectLoad.gitHistory.banner.viewing", {
            sha: shortSha(selectedRevision),
          })
        }}
      </span>
      <button
        type="button"
        class="git-revision-preview__back"
        :title="tm('spcodeProjectLoad.gitHistory.banner.backToCurrent')"
        :aria-label="tm('spcodeProjectLoad.gitHistory.banner.backToCurrent')"
        @click="emit('back-to-current')"
      >
        <v-icon size="14">mdi-arrow-u-left-top</v-icon>
        <span>{{ tm("spcodeProjectLoad.gitHistory.banner.backToCurrent") }}</span>
      </button>
    </header>
    <div v-if="selectedRevision" class="git-revision-preview__tabs">
      <button
        type="button"
        :class="[
          'git-revision-preview__tab',
          { active: previewMode === 'raw' },
        ]"
        @click="selectMode('raw')"
      >
        {{ tm("spcodeProjectLoad.gitHistory.preview.tabRaw") }}
      </button>
      <button
        type="button"
        :class="[
          'git-revision-preview__tab',
          { active: previewMode === 'diff' },
        ]"
        @click="selectMode('diff')"
      >
        {{ tm("spcodeProjectLoad.gitHistory.preview.tabDiff") }}
      </button>
    </div>
    <div class="git-revision-preview__body">
      <div
        v-if="!selectedRevision"
        class="git-revision-preview__placeholder"
      >
        {{ tm("spcodeProjectLoad.gitHistory.preview.placeholder") }}
      </div>
      <template v-else-if="previewMode === 'raw'">
        <div v-if="rawLoading" class="git-revision-preview__loading">
          <v-progress-circular indeterminate size="16" width="2" />
          <span>{{ tm("spcodeProjectLoad.gitHistory.preview.loading") }}</span>
        </div>
        <div
          v-else-if="rawErrorReason"
          class="git-revision-preview__error"
        >
          {{
            tm("spcodeProjectLoad.gitHistory.preview.rawLoadFail", {
              reason: rawErrorReason,
            })
          }}
        </div>
        <div
          v-else-if="rawData?.isBinary"
          class="git-revision-preview__binary"
        >
          <v-icon size="32" color="grey">mdi-file-question-outline</v-icon>
          <span>{{
            tm("spcodeProjectLoad.gitHistory.preview.binaryUnsupported")
          }}</span>
        </div>
        <MarkdownView
          v-else-if="isMarkdown"
          class="git-revision-preview__markdown"
          :source="rawContent"
          :is-dark="isDark"
        />
        <FileBrowserCodeView
          v-else
          class="git-revision-preview__code"
          :source="rawContent"
          :file-name="fileRelative ?? ''"
          :is-dark="isDark"
        />
      </template>
      <template v-else>
        <div v-if="diffLoading" class="git-revision-preview__loading">
          <v-progress-circular indeterminate size="16" width="2" />
          <span>{{ tm("spcodeProjectLoad.gitHistory.preview.loading") }}</span>
        </div>
        <DiffPreview
          v-else
          class="git-revision-preview__diff"
          :content="diffPatch ?? ''"
          :is-dark="isDark"
        />
      </template>
    </div>
  </section>
</template>

<style scoped>
.git-revision-preview {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  background: transparent;
  overflow: hidden;
}
.git-revision-preview__banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  font-size: 11.5px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.75);
  background: rgba(var(--v-theme-primary), 0.08);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.git-revision-preview__back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 4px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.75);
  font-size: 11px;
  cursor: pointer;
}
.git-revision-preview__back:hover,
.git-revision-preview__back:focus-visible {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
  border-color: rgba(var(--v-theme-primary), 0.4);
  outline: none;
}
.git-revision-preview__tabs {
  display: flex;
  gap: 4px;
  padding: 4px 12px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: transparent;
}
.git-revision-preview__tab {
  padding: 2px 10px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  cursor: pointer;
}
.git-revision-preview__tab.active {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
  border-color: rgba(var(--v-theme-primary), 0.3);
}
.git-revision-preview__body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 8px 12px;
}
.git-revision-preview__placeholder,
.git-revision-preview__loading,
.git-revision-preview__error,
.git-revision-preview__binary {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 6px;
  height: 100%;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  text-align: center;
}
.git-revision-preview__error {
  color: rgb(var(--v-theme-error));
}
.git-revision-preview__loading {
  flex-direction: row;
}
.git-revision-preview__markdown,
.git-revision-preview__code,
.git-revision-preview__diff {
  display: block;
  min-height: 0;
}
</style>
```

- [ ] **Step 4: Run the test, confirm it passes**

```bash
cd F:\github\Astrbot\dashboard && pnpm vitest run src/components/chat/message_list_comps/GitRevisionPreview.spec.ts
```

Expected: 4 passing tests.

- [ ] **Step 5: Commit**

```bash
cd F:\github\Astrbot && git add dashboard/src/components/chat/message_list_comps/GitRevisionPreview.vue dashboard/src/components/chat/message_list_comps/GitRevisionPreview.spec.ts && git commit -m "feat(dashboard): add GitRevisionPreview component"
```

---

## Task 5: Hide "查看文件历史" button on binary files in `FileBrowserFilePreview.vue`

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue` (add `v-if` to the existing button around line 530)

**Steps:**

- [ ] **Step 1: Locate the button**

```bash
cd F:\github\Astrbot && grep -n "showHistory" dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue
```

Expected: one match at the line with `tm("spcodeProjectLoad.fileBrowser.preview.showHistory")`.

- [ ] **Step 2: Add `v-if` to hide the button when binary**

In `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue`, replace the existing `<v-btn>` block (the one with `prepend-icon="mdi-history"`) with:

```vue
<v-btn
  v-if="state.snapshot.meta.isBinary !== true"
  size="x-small"
  variant="text"
  color="primary"
  prepend-icon="mdi-history"
  :title="tm('spcodeProjectLoad.fileBrowser.preview.showHistory')"
  @click="setLogPathFilter(state.snapshot.meta.path)"
>
  {{ tm("spcodeProjectLoad.fileBrowser.preview.showHistory") }}
</v-btn>
```

The only change is the new `v-if` line. Everything else is byte-for-byte identical.

- [ ] **Step 3: Verify the file still parses (vue-tsc)**

```bash
cd F:\github\Astrbot\dashboard && pnpm exec vue-tsc --noEmit
```

Expected: exit code 0 (or only pre-existing errors unrelated to this file).

- [ ] **Step 4: Commit**

```bash
cd F:\github\Astrbot && git add dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue && git commit -m "feat(dashboard): hide file history button for binary files"
```

---

## Task 6: Wire up `GitDiffSidebar.vue` History tab

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue`

**Interfaces (consumed by this task, produced earlier):**
- `GitHistorySidebar` props: `{ gitLog, fileRelative, currentRevision, isLoading }`; emits `select-revision`, `compare-current`, `collapse`.
- `GitRevisionPreview` props: `{ fileRelative, selectedRevision, previewMode, isDark, gitFile, diffPatch, diffLoading }`; emits `back-to-current`, `update:previewMode`.

**Steps:**

- [ ] **Step 1: Locate the relevant insertion points**

```bash
cd F:\github\Astrbot
grep -n "useSpcodeGitShow\|useSpcodeGitFile\|setLogPathFilter\|viewMode === 'history'\|useResizableSplit" dashboard/src/components/chat/GitDiffSidebar.vue
```

Note the line numbers of: (a) existing `setLogPathFilter` definition, (b) the existing `<GitLogView v-else-if="viewMode === 'history'" ... />` block, (c) where `useResizableSplit` is currently imported and used.

- [ ] **Step 2: Add new imports and composable instances**

In the `<script setup>` block of `GitDiffSidebar.vue`, add to the existing imports section:

```ts
import { useSpcodeGitFile } from "@/composables/useSpcodeGitFile";
import { useSpcodeGitShow } from "@/composables/useSpcodeGitShow";
import GitHistorySidebar from "@/components/chat/message_list_comps/GitHistorySidebar.vue";
import GitRevisionPreview from "@/components/chat/message_list_comps/GitRevisionPreview.vue";
```

(Adjust to your codebase's actual import order; keep these adjacent to the existing `useSpcodeGitLog` import if present.)

Inside the setup body, near the existing `useResizableSplit({ initialPercent: 22, ... })` declaration, add a second one for the history pane:

```ts
// History tab split: sidebar (commit list) on the left, preview on
// the right. Default 35/65; clamp 25–60 so neither column collapses.
// Initial percent intentionally smaller than the file tree split
// because the commit list is denser (small text, no long subjects).
const historySplit = useResizableSplit({
  initialPercent: 35,
  minPercent: 25,
  maxPercent: 60,
});
```

And right after the existing `gitLog` composable line (search for `useSpcodeGitLog(`):

```ts
// History tab composables. Distinct from the existing diff/log
// instances so caching keys (umo + worktree + ref [+ path]) stay
// independent of the diff tab's view of the same commits.
const historyGitFile = useSpcodeGitFile(worktree);
const historyGitShow = useSpcodeGitShow(worktree);
```

(`worktree` is the existing `worktree` ref already passed to other composables in this file. If the existing callsites pass it as a positional argument or as a ref, mirror that exact style.)

- [ ] **Step 3: Add session state refs**

In the same `<script setup>` block, after the existing `stagedFiles` declaration (or wherever session refs live), add:

```ts
// History tab session state — never persisted.
const historyFilePath = ref<string | null>(null);
const selectedRevision = ref<string | null>(null);
const historyPreviewMode = ref<"raw" | "diff">("raw");
const diffPatch = ref<string | null>(null);
const diffLoading = ref<boolean>(false);
const isHistoryCollapsed = ref<boolean>(false);
```

- [ ] **Step 4: Update `setLogPathFilter` to reset state**

Find the existing `setLogPathFilter` function and replace its body with:

```ts
function setLogPathFilter(path: string): void {
  if (!path) return;
  viewMode.value = "history";
  historyFilePath.value = path;
  // Switching the file resets any active revision so the user is
  // not silently viewing a stale commit's content under the new
  // file. Mirrors DocumentManager.vue's onSelectFile logic.
  selectedRevision.value = null;
  historyPreviewMode.value = "raw";
  diffPatch.value = null;
  diffLoading.value = false;
  // Preserve the user's current filter shape (ref / author / since
  // / until / n) and only override path. The composable's refresh()
  // replaces (not merges) the filter, so we have to spread here.
  const next: LogFilter = { ref: "HEAD", n: 50, path, ...gitLog.filter.value };
  gitLog.filter.value = next;
}
```

(If the existing function signature or surrounding code differs, keep the existing `gitLog.filter.value = next` shape but ensure the six new reset lines are inserted before the existing `gitLog.filter.value` mutation.)

- [ ] **Step 5: Add watcher that drives the diff patch fetch**

After the existing composable instances (or anywhere in `<script setup>`), add:

```ts
// Drive diff-patch fetch when the user clicks "compare with current".
// We mirror DocumentManager.vue's watch at lines 224–248 so the
// patch lands before the diff tab is shown.
watch(
  () => [historyFilePath.value, selectedRevision.value, historyPreviewMode.value] as const,
  async ([path, rev, mode]) => {
    if (mode !== "diff" || !path || !rev) {
      diffPatch.value = null;
      diffLoading.value = false;
      return;
    }
    diffPatch.value = null;
    diffLoading.value = true;
    try {
      await historyGitShow.fetchFile(rev, path);
      const snap = historyGitShow.getFileData(rev, path);
      diffPatch.value = snap?.patch ?? null;
    } finally {
      diffLoading.value = false;
    }
  },
  { immediate: true },
);

// Add event handlers used by the two new child components.
function onSelectRevision(sha: string) {
  selectedRevision.value = sha;
  historyPreviewMode.value = "raw";
}
function onCompareCurrent(sha: string) {
  selectedRevision.value = sha;
  historyPreviewMode.value = "diff";
}
function onBackToCurrent() {
  selectedRevision.value = null;
  historyPreviewMode.value = "raw";
  diffPatch.value = null;
}
function onHistoryCollapse() {
  isHistoryCollapsed.value = true;
}
function onHistoryExpand() {
  isHistoryCollapsed.value = false;
}
function onHistoryPreviewMode(mode: "raw" | "diff") {
  historyPreviewMode.value = mode;
}
```

- [ ] **Step 6: Replace the History tab template**

In the `<template>` block, find the existing `<GitLogView v-else-if="viewMode === 'history'" ... />` element and replace it with:

```vue
<div v-else-if="viewMode === 'history'" class="git-diff-sidebar-history">
  <div v-if="!isHistoryCollapsed" class="git-diff-sidebar-history__split">
    <GitHistorySidebar
      class="git-diff-sidebar-history__sidebar"
      :git-log="gitLog"
      :file-relative="historyFilePath"
      :current-revision="selectedRevision"
      :is-loading="gitLog.state.value.kind === 'loading'"
      :style="{ width: historySplit.percent.value + '%' }"
      @select-revision="onSelectRevision"
      @compare-current="onCompareCurrent"
      @collapse="onHistoryCollapse"
    />
    <div
      class="git-diff-sidebar-history__divider"
      role="separator"
      aria-orientation="vertical"
      :aria-valuenow="Math.round(historySplit.percent.value)"
      :aria-valuemin="25"
      :aria-valuemax="60"
      @mousedown="historySplit.startResize"
    />
    <GitRevisionPreview
      class="git-diff-sidebar-history__preview"
      :file-relative="historyFilePath"
      :selected-revision="selectedRevision"
      :preview-mode="historyPreviewMode"
      :is-dark="isDark"
      :git-file="historyGitFile"
      :diff-patch="diffPatch"
      :diff-loading="diffLoading"
      @back-to-current="onBackToCurrent"
      @update:preview-mode="onHistoryPreviewMode"
    />
  </div>
  <button
    v-if="isHistoryCollapsed"
    type="button"
    class="git-diff-sidebar-history__expand"
    :title="tm('spcodeProjectLoad.gitHistory.sidebar.expand')"
    :aria-label="tm('spcodeProjectLoad.gitHistory.sidebar.expand')"
    @click="onHistoryExpand"
  >
    <v-icon size="14">mdi-chevron-double-left</v-icon>
  </button>
</div>
```

If the existing element has a different outer parent (e.g. wraps in `<div class="git-diff-sidebar-page">`), preserve that wrapper and only replace the inner content. The class names `git-diff-sidebar-history__*` are new and live alongside the existing sidebar styles.

- [ ] **Step 7: Add scoped styles for the new layout**

In the existing `<style scoped>` block of `GitDiffSidebar.vue`, append:

```css
.git-diff-sidebar-history {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
}
.git-diff-sidebar-history__split {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
}
.git-diff-sidebar-history__sidebar {
  flex: 0 0 auto;
  min-width: 0;
}
.git-diff-sidebar-history__divider {
  flex: 0 0 4px;
  cursor: col-resize;
  background: rgba(var(--v-theme-on-surface), 0.06);
}
.git-diff-sidebar-history__divider:hover,
.git-diff-sidebar-history__divider:focus-visible {
  background: rgba(var(--v-theme-primary), 0.3);
  outline: none;
}
.git-diff-sidebar-history__preview {
  flex: 1 1 auto;
  min-width: 0;
}
.git-diff-sidebar-history__expand {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  border: none;
  background: rgba(var(--v-theme-on-surface), 0.03);
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.git-diff-sidebar-history__expand:hover {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}
.git-diff-sidebar-history,
.git-diff-sidebar-history__split,
.git-diff-sidebar-history__sidebar,
.git-diff-sidebar-history__divider,
.git-diff-sidebar-history__preview,
.git-diff-sidebar-history__expand {
  transition:
    width 0.2s ease,
    background 0.1s ease;
}
```

- [ ] **Step 8: Verify type-check + existing tests**

```bash
cd F:\github\Astrbot\dashboard && pnpm exec vue-tsc --noEmit && pnpm vitest run src/components/chat/message_list_comps/GitHistorySidebar.spec.ts src/components/chat/message_list_comps/GitRevisionPreview.spec.ts
```

Expected: type-check passes; both spec files report 4 + 5 passing tests.

- [ ] **Step 9: Commit**

```bash
cd F:\github\Astrbot && git add dashboard/src/components/chat/GitDiffSidebar.vue && git commit -m "feat(dashboard): wire workspace history sidebar into GitDiffSidebar"
```

---

## Task 7: Final verification — build + lint + manual smoke

**Files:**
- Read-only verification (no edits this task).

**Steps:**

- [ ] **Step 1: Format and lint**

```bash
cd F:\github\Astrbot\dashboard && pnpm lint
```

Expected: zero errors. If `pnpm lint` is not configured, run `pnpm exec eslint dashboard/src --ext .ts,.vue` or the project's documented equivalent.

- [ ] **Step 2: Production build**

```bash
cd F:\github\Astrbot\dashboard && pnpm build
```

Expected: `vite v... building for production...` then `✓ built in N.NNs`. Restore the MDI font subset CSS artifact afterwards if it changes:

```bash
cd F:\github\Astrbot && git checkout -- dashboard/src/assets/mdi-subset/materialdesignicons-subset.css
```

- [ ] **Step 3: Run all relevant vitest specs**

```bash
cd F:\github\Astrbot\dashboard && pnpm vitest run src/components/chat/message_list_comps/GitHistorySidebar.spec.ts src/components/chat/message_list_comps/GitRevisionPreview.spec.ts
```

Expected: 9 passing tests across the two files.

- [ ] **Step 4: Manual smoke checklist**

Use the dev server (`cd dashboard && pnpm dev` in a separate terminal) and verify:

1. Open the workspace sidebar → Files tab → click any text file → click "查看文件历史".
   - Sidebar switches to History tab, filter form pre-fills the file path.
   - Left column shows the per-file commit list with working-tree pseudo-row.
2. Click the eye icon on a commit.
   - Right column shows the file content at that revision, banner reads "正在查看历史版本 abc1234", "回到当前" button visible.
3. Click the compare icon on a commit.
   - Right column switches to diff view; unified diff renders below.
4. Click "回到当前".
   - Banner disappears; right column shows the placeholder.
5. On a binary file (e.g. a `.png`), the "查看文件历史" button is absent.
6. Drag the divider left/right; the sidebar/preview widths adjust and persist across reloads (localStorage).
7. Switch to another tab and back; selected revision is preserved within the session.
8. Close the sidebar; state is cleared.

If any check fails, write a follow-up commit before claiming completion.

- [ ] **Step 5: Commit (no code change expected)**

```bash
cd F:\github\Astrbot && git status --short
```

Expected: empty output. If MDI subset CSS changed, restore it (per Step 2).

---

## Self-Review

After writing this plan I performed the following self-checks against the spec:

- **Spec coverage** — every behavior in §"Behavior" of the spec is covered:
  - "查看文件历史" pre-fills path → Task 6 step 4 (`setLogPathFilter`).
  - Eye action selects revision → Task 6 step 5 (`onSelectRevision`) + Task 4 step 3 (banner).
  - Compare action switches to diff mode → Task 6 step 5 (`onCompareCurrent`) + Task 4 step 3 (diff tab) + Task 6 step 5 (diff patch watcher).
  - "回到当前" clears state → Task 6 step 5 (`onBackToCurrent`).
  - Path filter change resets selectedRevision → Task 6 step 4 (reset block inside `setLogPathFilter`).
  - Tab switch preserves state → Task 6 step 3 (no unmount).
  - Sidebar close clears state → handled by component unmount lifecycle (no code needed).
  - Binary hide → Task 5.
  - Layout (left/right split + collapse) → Task 6 step 6.
  - Persistence (historySplit.percent only) → Task 6 step 2 (the existing `useResizableSplit` already persists).
  - i18n → Task 2.
- **Placeholder scan** — searched for "TBD", "TODO", "implement later", "fill in details", "similar to". None present.
- **Type consistency** —
  - `historySplit`, `historyFilePath`, `selectedRevision`, `historyPreviewMode`, `diffPatch`, `diffLoading`, `isHistoryCollapsed` are used identically across Tasks 6 steps 2-7.
  - `historyGitFile` / `historyGitShow` instances created in Task 6 step 2 and consumed identically in steps 5-6.
  - `onSelectRevision`, `onCompareCurrent`, `onBackToCurrent`, `onHistoryCollapse`, `onHistoryExpand`, `onHistoryPreviewMode` defined once in step 5 and used exactly once in the template at step 6.
  - `GitHistorySidebar` props / emits match between Task 3 step 3 (component) and Task 6 step 6 (call site).
  - `GitRevisionPreview` props / emits match between Task 4 step 3 and Task 6 step 6.
- **Backend assumptions** — Tasks 1 and the "Backend contract" note explicitly verify the two endpoints exist (no backend edits required). If a future endpoint shape changes, this plan needs revision; current code matches `DocumentManager.vue`'s established usage.
