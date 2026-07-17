# .gitignore 编辑器（Git 变更页）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 GitDiffSidebar「Git变更」子页面内闭环查看/编辑仓库根 `.gitignore`（覆盖层编辑器，不离开 diff 页）。

**Architecture:** 纯展示组件 `GitIgnoreEditor.vue`（v-model 进、save/cancel/retry 出）+ `GitDiffSidebar` 装配（读取/保存编排、刷新链路）。复用既有 `ShikiEditor`、`useSpcodeFileWrite`（POST /spcode/file-write，repo 相对路径）、一次性 `GET /spcode/file-browser`（绝对路径读取，先例 `useSpcodeNewFileLineCounts.ts:125`）。

**Tech Stack:** Vue 3 `<script setup>` + Vuetify + vitest + @vue/test-utils。

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-17-gitignore-editor-design.md`（已批准）。
- i18n 仅 zh-CN（`spcodeProjectLoad` 段落惯例；en/zh-TW 走回退），键前缀 `spcodeProjectLoad.diffSidebar.gitWorkflow.gitignore.`。
- 代码注释用英文（AGENTS.md），组件头注 `Author: elecvoid243, 2026-07-17`。
- 不新增后端端点；不改 `ShikiEditor.vue` / `useSpcodeFileWrite.ts`。
- 验证命令：`cd dashboard && pnpm typecheck && pnpm test`。
- Commit 用 conventional commits。

---

### Task 1: GitIgnoreEditor.vue 组件 + 测试

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/GitIgnoreEditor.vue`
- Test: `dashboard/src/components/chat/message_list_comps/GitIgnoreEditor.spec.ts`

**Interfaces:**
- Consumes: `ShikiEditor.vue`（props `modelValue: string`、`filePath: string`；emit `update:modelValue`）；`useModuleI18n("features/chat")`。
- Produces（Task 2 依赖的契约）:
  - props: `modelValue: string`、`isNewFile: boolean`、`isDirty: boolean`、`isSaving: boolean`、`saveError: string | null`、`loadError: string | null`
  - emits: `update:modelValue(v: string)`、`save`、`cancel`、`retry`

- [ ] **Step 1: 写失败测试**

创建 `dashboard/src/components/chat/message_list_comps/GitIgnoreEditor.spec.ts`：

```ts
// Author: elecvoid243, 2026-07-17
import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

// Same self-contained i18n mock as GitRepoInitPrompt.spec.ts: returns
// the key (plus k=v params) so text assertions verify substitution.
const tmMock = vi.fn(
  (key: string, params?: Record<string, string | number>) => {
    if (!params) return key;
    return Object.entries(params).reduce(
      (acc, [k, v]) => `${acc} ${k}=${String(v)}`,
      key,
    );
  },
);
vi.mock("@/i18n/composables", () => ({
  useModuleI18n: () => ({ tm: tmMock, getRaw: vi.fn() }),
}));

import GitIgnoreEditor from "./GitIgnoreEditor.vue";

const vuetifyStubs = {
  "v-icon": { template: "<i />" },
  // Render a real <button> so click + disabled flow through.
  "v-btn": {
    props: ["disabled", "loading"],
    template:
      '<button :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
  },
  // ShikiEditor is a heavy async child (Shiki highlighter); stub it.
  ShikiEditor: { props: ["modelValue", "filePath"], template: "<div />" },
};

const PREFIX =
  "spcodeProjectLoad.diffSidebar.gitWorkflow.gitignore";

function mountEditor(props: Record<string, unknown> = {}) {
  return mount(GitIgnoreEditor, {
    props: {
      modelValue: "",
      isNewFile: false,
      isDirty: false,
      isSaving: false,
      saveError: null,
      loadError: null,
      ...props,
    },
    global: { stubs: vuetifyStubs },
  });
}

describe("GitIgnoreEditor", () => {
  it("renders the .gitignore title and the new-file hint when isNewFile", () => {
    const w = mountEditor({ isNewFile: true });
    expect(w.text()).toContain(".gitignore");
    expect(w.text()).toContain(`${PREFIX}.newFileHint`);
  });

  it("hides the new-file hint for an existing file", () => {
    const w = mountEditor({ isNewFile: false });
    expect(w.text()).not.toContain(`${PREFIX}.newFileHint`);
  });

  it("clean cancel emits cancel on the first click", async () => {
    const w = mountEditor({ isDirty: false });
    await w.find('[data-testid="gitignore-cancel"]').trigger("click");
    expect(w.emitted("cancel")).toBeTruthy();
  });

  it("dirty cancel arms confirmation first, emits on second click", async () => {
    const w = mountEditor({ isDirty: true });
    const btn = w.find('[data-testid="gitignore-cancel"]');
    await btn.trigger("click");
    expect(w.emitted("cancel")).toBeFalsy();
    expect(w.text()).toContain(`${PREFIX}.confirmDiscard`);
    await btn.trigger("click");
    expect(w.emitted("cancel")).toBeTruthy();
  });

  it("save click emits save", async () => {
    const w = mountEditor({ isDirty: true });
    await w.find('[data-testid="gitignore-save"]').trigger("click");
    expect(w.emitted("save")).toBeTruthy();
  });

  it("renders the inline save error bar", () => {
    const w = mountEditor({ saveError: "boom" });
    expect(w.find('[data-testid="gitignore-error"]').text()).toContain("boom");
  });

  it("load error swaps the body for a retry button", async () => {
    const w = mountEditor({ loadError: "nope" });
    expect(w.text()).toContain("nope");
    await w.find('[data-testid="gitignore-retry"]').trigger("click");
    expect(w.emitted("retry")).toBeTruthy();
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd dashboard && pnpm vitest run src/components/chat/message_list_comps/GitIgnoreEditor.spec.ts`
Expected: FAIL（组件不存在，import 报错）

- [ ] **Step 3: 实现组件**

创建 `dashboard/src/components/chat/message_list_comps/GitIgnoreEditor.vue`：

```vue
<!-- Author: elecvoid243, 2026-07-17
     Spec: docs/superpowers/specs/2026-07-17-gitignore-editor-design.md
     In-sidebar overlay editor for the repo-root .gitignore, opened
     from the Git-diff view header. The parent (GitDiffSidebar) owns
     loading/saving; this component is purely presentational:
     content in via v-model, save/cancel/retry out via events. -->
<script setup lang="ts">
import { onBeforeUnmount, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import ShikiEditor from "./ShikiEditor.vue";

const props = defineProps<{
  modelValue: string;
  /** True when the repo has no .gitignore yet — the toolbar shows a
   *  "will be created" hint (not an error). */
  isNewFile: boolean;
  /** Buffer differs from the on-disk content; drives the two-click
   *  discard confirmation on Cancel and the Save disabled state. */
  isDirty: boolean;
  isSaving: boolean;
  /** Save failure text (already localized by the parent); inline bar,
   *  buffer stays intact. */
  saveError: string | null;
  /** Load failure text; when set the body swaps to error + retry. */
  loadError: string | null;
}>();
const emit = defineEmits<{
  (e: "update:modelValue", v: string): void;
  (e: "save"): void;
  (e: "cancel"): void;
  (e: "retry"): void;
}>();
const { tm } = useModuleI18n("features/chat");

const PREFIX = "spcodeProjectLoad.diffSidebar.gitWorkflow.gitignore";

// Two-click discard: first Cancel click while dirty arms the
// confirmation (button relabels); a second click within 3s emits.
// Auto-disarm so a stray arm never lingers.
const discardArmed = ref(false);
let disarmTimer: ReturnType<typeof setTimeout> | null = null;

function onCancelClick(): void {
  if (!props.isDirty || discardArmed.value) {
    emit("cancel");
    return;
  }
  discardArmed.value = true;
  if (disarmTimer) clearTimeout(disarmTimer);
  disarmTimer = setTimeout(() => {
    discardArmed.value = false;
    disarmTimer = null;
  }, 3000);
}
onBeforeUnmount(() => {
  if (disarmTimer) clearTimeout(disarmTimer);
});
</script>

<template>
  <div class="gitignore-editor">
    <div class="gitignore-editor-toolbar">
      <v-icon size="15" class="gitignore-editor-icon"
        >mdi-file-cancel-outline</v-icon
      >
      <span class="gitignore-editor-title">.gitignore</span>
      <span
        v-if="isDirty"
        class="gitignore-editor-dirty"
        :title="tm(`${PREFIX}.unsavedTitle`)"
        >●</span
      >
      <span v-if="isNewFile" class="gitignore-editor-new-hint">
        {{ tm(`${PREFIX}.newFileHint`) }}
      </span>
      <div class="gitignore-editor-actions">
        <v-btn
          size="x-small"
          variant="text"
          :disabled="isSaving"
          data-testid="gitignore-cancel"
          @click="onCancelClick"
        >
          {{
            discardArmed
              ? tm(`${PREFIX}.confirmDiscard`)
              : tm(`${PREFIX}.cancel`)
          }}
        </v-btn>
        <v-btn
          size="x-small"
          variant="flat"
          color="primary"
          :loading="isSaving"
          :disabled="!isDirty"
          data-testid="gitignore-save"
          @click="emit('save')"
        >
          {{ tm(`${PREFIX}.save`) }}
        </v-btn>
      </div>
    </div>
    <div
      v-if="saveError"
      class="gitignore-editor-error"
      data-testid="gitignore-error"
    >
      {{ saveError }}
    </div>
    <div class="gitignore-editor-body">
      <div v-if="loadError" class="gitignore-editor-load-error">
        <v-icon size="16" color="error">mdi-alert-circle-outline</v-icon>
        <span class="gitignore-editor-load-error-text">{{ loadError }}</span>
        <button
          type="button"
          class="gitignore-editor-retry"
          data-testid="gitignore-retry"
          @click="emit('retry')"
        >
          {{ tm(`${PREFIX}.retry`) }}
        </button>
      </div>
      <ShikiEditor
        v-else
        :model-value="modelValue"
        file-path=".gitignore"
        @update:model-value="emit('update:modelValue', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
/* Overlay: covers the whole sidebar (header included) — the toolbar
   below replaces the header affordances while editing. The sidebar
   root gains `position: relative` in Task 2 to anchor this. */
.gitignore-editor {
  position: absolute;
  inset: 0;
  z-index: 30;
  display: flex;
  flex-direction: column;
  background: rgb(var(--v-theme-surface));
}
.gitignore-editor-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  font-size: 12px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  flex-shrink: 0;
}
.gitignore-editor-title {
  font-family: ui-monospace, monospace;
  font-weight: 600;
}
.gitignore-editor-dirty {
  color: rgb(var(--v-theme-warning));
  font-size: 10px;
}
.gitignore-editor-new-hint {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
}
.gitignore-editor-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px;
}
.gitignore-editor-error {
  padding: 6px 14px;
  font-size: 12px;
  color: rgb(var(--v-theme-error));
  background: rgba(var(--v-theme-error), 0.08);
  border-bottom: 1px solid rgba(var(--v-theme-error), 0.2);
  flex-shrink: 0;
}
.gitignore-editor-body {
  flex: 1;
  min-height: 0;
}
.gitignore-editor-load-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.75);
}
.gitignore-editor-retry {
  margin-left: auto;
  font-size: 11.5px;
  padding: 2px 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.2);
  border-radius: 4px;
  background: transparent;
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
}
</style>
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd dashboard && pnpm vitest run src/components/chat/message_list_comps/GitIgnoreEditor.spec.ts`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/chat/message_list_comps/GitIgnoreEditor.vue dashboard/src/components/chat/message_list_comps/GitIgnoreEditor.spec.ts
git commit -m "feat(dashboard): GitIgnoreEditor overlay component"
```

---

### Task 2: GitDiffSidebar 装配 + i18n

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue`（script 状态与编排 / header 按钮 / 覆盖层挂载 / root CSS）
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json`（gitWorkflow 下新增 gitignore 块）

**Interfaces:**
- Consumes: Task 1 的 `GitIgnoreEditor` props/emits 契约；`useSpcodeFileWrite(selectedWorktree)`（`save({path, content})` → `{ ok: true } | { ok: false; reason: string }`）；`pluginExtensionApi.get`（sidebar 第 59 行已 import）；`currentRoot` computed（sidebar 已有，供 DocumentManager 的 project-root）；`showSnackbar(message, color, stderr?)`、`gitStatus.refresh()`、`composable.refresh()`（均已有）。
- Produces: 无对外契约（终端装配）。

- [ ] **Step 1: i18n 键（zh-CN）**

在 `dashboard/src/i18n/locales/zh-CN/features/chat.json` 的 `gitWorkflow` 对象内（与 `"history"` 同级）插入：

```json
          "gitignore": {
            "openTooltip": "编辑 .gitignore",
            "newFileHint": "仓库还没有 .gitignore，保存后将新建",
            "unsavedTitle": "有未保存的改动",
            "save": "保存",
            "cancel": "取消",
            "confirmDiscard": "确认放弃改动？",
            "retry": "重试",
            "saveSuccess": ".gitignore 已保存",
            "loadError": "读取 .gitignore 失败（{reason}）",
            "saveError": "保存 .gitignore 失败（{reason}）"
          },
```

验证 JSON 合法：`python -c "import json; json.load(open(r'dashboard/src/i18n/locales/zh-CN/features/chat.json', encoding='utf-8'))"`

- [ ] **Step 2: script — import 与状态**

`GitDiffSidebar.vue` script 顶部 import 区（第 52 行 `useSpcodeGitLog` import 附近）追加：

```ts
import { useSpcodeFileWrite } from "@/composables/useSpcodeFileWrite";
import GitIgnoreEditor from "@/components/chat/message_list_comps/GitIgnoreEditor.vue";
```

在 `const gitRevert = useSpcodeGitRevert();` 之后追加：

```ts
// ── .gitignore editor overlay (2026-07-17) ───────────────────────
// Spec: docs/superpowers/specs/2026-07-17-gitignore-editor-design.md
// The sidebar owns load/save orchestration; GitIgnoreEditor is a
// purely presentational overlay (v-model in, save/cancel/retry out).
const gitIgnoreEditorOpen = ref(false);
const gitIgnoreBuffer = ref("");
const gitIgnoreLoadedContent = ref("");
const gitIgnoreIsNewFile = ref(false);
const gitIgnoreLoadError = ref<string | null>(null);
const gitIgnoreSaveError = ref<string | null>(null);
const gitIgnoreFileWrite = useSpcodeFileWrite(selectedWorktree);
const gitIgnoreIsDirty = computed(
  () => gitIgnoreBuffer.value !== gitIgnoreLoadedContent.value,
);
// Repo-root .gitignore as an absolute path for the read endpoint
// (file-browser takes absolute paths; trailing slashes stripped).
const gitIgnoreAbsPath = computed(
  () => `${(currentRoot.value ?? "").replace(/\/+$/, "")}/.gitignore`,
);
const GITIGNORE_I18N_PREFIX =
  "spcodeProjectLoad.diffSidebar.gitWorkflow.gitignore";
```

（若 `computed` 未在 vue import 中则补上——sidebar 已大量使用 computed，预期已导入。）

- [ ] **Step 3: script — 编排函数**

在 Step 2 状态块之后追加：

```ts
async function loadGitIgnore(): Promise<void> {
  gitIgnoreLoadError.value = null;
  try {
    const resp = await pluginExtensionApi.get<unknown>(
      "spcode/file-browser",
      { params: { path: gitIgnoreAbsPath.value } },
    );
    const data = (
      resp.data as {
        data?: {
          type?: string | null;
          content?: unknown;
          reason?: string | null;
        };
      }
    )?.data;
    if (data?.type === "file" && typeof data.content === "string") {
      gitIgnoreBuffer.value = data.content;
      gitIgnoreLoadedContent.value = data.content;
      gitIgnoreIsNewFile.value = false;
      return;
    }
    // type === null + reason path_not_found → the repo simply has no
    // .gitignore yet: empty buffer + "will be created" hint.
    if (data?.reason === "path_not_found") {
      gitIgnoreBuffer.value = "";
      gitIgnoreLoadedContent.value = "";
      gitIgnoreIsNewFile.value = true;
      return;
    }
    gitIgnoreLoadError.value = tm(`${GITIGNORE_I18N_PREFIX}.loadError`, {
      reason: data?.reason ?? "unknown",
    });
  } catch (err) {
    const anyErr = err as { code?: string; message?: string };
    gitIgnoreLoadError.value = tm(`${GITIGNORE_I18N_PREFIX}.loadError`, {
      reason:
        anyErr.code === "ERR_NETWORK" || /network/i.test(anyErr.message ?? "")
          ? "network"
          : "unknown",
    });
  }
}

function onOpenGitIgnoreEditor(): void {
  gitIgnoreSaveError.value = null;
  gitIgnoreEditorOpen.value = true;
  void loadGitIgnore();
}

function onGitIgnoreCancel(): void {
  gitIgnoreEditorOpen.value = false;
}

async function onGitIgnoreSave(): Promise<void> {
  if (!gitIgnoreIsDirty.value || gitIgnoreFileWrite.isSaving.value) return;
  gitIgnoreSaveError.value = null;
  const r = await gitIgnoreFileWrite.save({
    // Repo-relative path — the backend resolves it against the
    // worktree passed by the composable.
    path: ".gitignore",
    content: gitIgnoreBuffer.value,
  });
  if (r.ok) {
    gitIgnoreEditorOpen.value = false;
    showSnackbar(tm(`${GITIGNORE_I18N_PREFIX}.saveSuccess`), "success");
    // .gitignore changes which untracked files appear — refresh the
    // status + diff views in parallel.
    void Promise.all([gitStatus.refresh(), composable.refresh()]);
    return;
  }
  if (r.reason === "aborted") return;
  gitIgnoreSaveError.value = tm(`${GITIGNORE_I18N_PREFIX}.saveError`, {
    reason: r.reason,
  });
}

// The buffer belongs to the old worktree after a switch — close.
watch(selectedWorktree, () => {
  gitIgnoreEditorOpen.value = false;
});
```

在 `onBeforeUnmount` 中 `gitRevert.dispose();` 之后追加 `gitIgnoreFileWrite.dispose();`。

- [ ] **Step 4: 模板 — header 按钮**

在 header actions 区的刷新 `v-tooltip`（`@click="onManualRefresh"` 所在块）之前插入：

```html
            <!-- 2026-07-17 gitignore-editor: entry only meaningful in
                 the diff view (stage/diff workflow context). -->
            <v-tooltip
              v-if="viewMode === 'diff'"
              location="bottom"
              :open-delay="200"
            >
              <template #activator="{ props: tipProps }">
                <v-btn
                  v-bind="tipProps"
                  icon
                  size="small"
                  variant="text"
                  @click="onOpenGitIgnoreEditor"
                >
                  <v-icon size="18">mdi-file-cancel-outline</v-icon>
                </v-btn>
              </template>
              {{ tm(`${GITIGNORE_I18N_PREFIX}.openTooltip`) }}
            </v-tooltip>
```

- [ ] **Step 5: 模板 — 覆盖层挂载 + root CSS**

在 result snackbar 块（`<!-- Spec §6.4: result snackbar` 注释）之前插入：

```html
        <!-- 2026-07-17 gitignore-editor: full-sidebar overlay. Mounted
             as a direct child of the root so position:absolute inset:0
             covers header + body + commit bar alike. -->
        <GitIgnoreEditor
          v-if="gitIgnoreEditorOpen"
          v-model="gitIgnoreBuffer"
          :is-new-file="gitIgnoreIsNewFile"
          :is-dirty="gitIgnoreIsDirty"
          :is-saving="gitIgnoreFileWrite.isSaving.value"
          :save-error="gitIgnoreSaveError"
          :load-error="gitIgnoreLoadError"
          @save="onGitIgnoreSave"
          @cancel="onGitIgnoreCancel"
          @retry="loadGitIgnore"
        />
```

在 `.git-diff-sidebar {` 规则内追加一行（使覆盖层的 absolute 定位锚定到侧栏根）：

```css
  position: relative;
```

- [ ] **Step 6: 全量验证**

Run: `cd dashboard && pnpm typecheck && pnpm test`
Expected: typecheck 无错误；57+7 测试全过

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/components/chat/GitDiffSidebar.vue dashboard/src/i18n/locales/zh-CN/features/chat.json
git commit -m "feat(dashboard): wire gitignore editor into git diff view"
```
