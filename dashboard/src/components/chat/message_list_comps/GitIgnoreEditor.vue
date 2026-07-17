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
   root gains `position: relative` in the wiring task to anchor
   this. */
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
