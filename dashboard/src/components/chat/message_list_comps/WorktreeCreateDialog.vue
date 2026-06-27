<!-- Author: elecvoid243
     Date: 2026-06-27
     Spec: docs/superpowers/specs/2026-06-27-git-worktree-frontend-management-design.md §2.2.A
     Form for POST /spcode/git-worktree-add. Emits 'submit' on success
     with validated params; emits 'cancel' on close. -->
<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import type { WorktreeAddParams } from "@/composables/useSpcodeWorktrees";

const { tm } = useModuleI18n("features/chat");
const spcodeStatus = useSpcodeProjectStatus();

const props = defineProps<{
  modelValue: boolean;
  isSubmitting?: boolean;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
  (e: "submit", params: WorktreeAddParams): void;
  (e: "cancel"): void;
}>();

// ── Form state (spec §2.2.A table) ────────────────────────
type CreateMode = "create" | "force" | "detach";
const createMode = ref<CreateMode>("create");
const branch = ref<string>("");
const path = ref<string>("");
const base = ref<string>("main");

const projectRoot = computed(
  () => spcodeStatus.status.value.directory ?? "",
);

// Branch sanitization for default path suggestion.
function defaultPath(branchName: string, root: string): string {
  if (!root || !branchName) return "";
  const sep = root.includes("\\") ? "\\" : "/";
  return `${root}${sep}.worktrees${sep}${branchName.replace(/\//g, "-")}`;
}

// Track whether the user has manually edited the path field, so the
// branch→path auto-suggestion stops overwriting their choice once
// they've touched it.
//
// Important: we must NOT use `watch(path, ...)` to detect user edits,
// because that watcher also fires for our own programmatic assignments
// in the branch watcher below — which would mark the suggestion as
// "user-edited" on the very first keystroke and freeze the path. We
// detect real user input via the @update:model-value handler on the
// v-text-field instead, which only fires for DOM input events.
const userEditedPath = ref(false);
function onPathUserInput(next: string): void {
  path.value = next;
  userEditedPath.value = true;
}
watch(branch, (b) => {
  if (!userEditedPath.value && b) {
    path.value = defaultPath(b, projectRoot.value);
  }
});

// Field-level validation (aligns with backend 5-step preflight).
const errors = computed(() => {
  const errs: { branch?: string; path?: string; base?: string } = {};
  if (createMode.value !== "detach" && !branch.value.trim()) {
    errs.branch = tm(
      "spcodeProjectLoad.diffSidebar.worktreeMgmt.create.branchRequired",
    );
  }
  if (!path.value.trim()) {
    errs.path = tm(
      "spcodeProjectLoad.diffSidebar.worktreeMgmt.create.pathRequired",
    );
  }
  return errs;
});

const canSubmit = computed(
  () => Object.keys(errors.value).length === 0 && !props.isSubmitting,
);

function onCancel(): void {
  if (props.isSubmitting) return;
  emit("update:modelValue", false);
  emit("cancel");
}

function onSubmit(): void {
  if (!canSubmit.value) return;
  const params: WorktreeAddParams = {
    path: path.value.trim(),
    umo: spcodeStatus.status.value.umo,
  };
  if (createMode.value !== "detach") {
    params.branch = branch.value.trim();
  }
  if (createMode.value === "create") {
    params.create = true;
    if (base.value.trim()) params.base = base.value.trim();
  } else if (createMode.value === "force") {
    params.force = true;
  } else if (createMode.value === "detach") {
    params.detach = true;
  }
  emit("submit", params);
}
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    persistent
    max-width="520"
  >
    <v-card>
      <v-card-title class="text-h6">
        {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.create.title") }}
      </v-card-title>
      <v-card-text>
        <!-- Mode radio group (mutually exclusive) -->
        <div class="worktree-create-mode">
          <v-radio-group v-model="createMode" inline density="compact">
            <v-radio
              value="create"
              :label="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.modeCreate')"
            />
            <v-radio
              value="force"
              :label="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.modeForce')"
            />
            <v-radio
              value="detach"
              :label="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.modeDetach')"
            />
          </v-radio-group>
          <v-chip
            v-if="createMode === 'force'"
            size="x-small"
            color="warning"
            variant="tonal"
            class="ml-2"
          >
            <v-icon start size="12">mdi-alert</v-icon>
            {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.create.modeForceWarning") }}
          </v-chip>
        </div>

        <!-- Branch (disabled in detach mode) -->
        <v-text-field
          v-model="branch"
          :label="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.branch')"
          :hint="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.branchHint')"
          :error-messages="errors.branch ? [errors.branch] : []"
          :disabled="createMode === 'detach'"
          density="comfortable"
          variant="outlined"
          class="mt-3"
        />

        <!-- Path (absolute). Use @update:model-value instead of
                     v-model so we can distinguish user typing from programmatic
                     writes done by the branch→path watcher. See comment on
                     onPathUserInput. -->
                <v-text-field
                  :model-value="path"
                  :label="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.path')"
                  :hint="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.pathHint')"
                  :error-messages="errors.path ? [errors.path] : []"
                  density="comfortable"
                  variant="outlined"
                  class="mt-2"
                  @update:model-value="onPathUserInput"
                />

        <!-- Base (only in create mode) -->
        <v-text-field
          v-if="createMode === 'create'"
          v-model="base"
          :label="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.base')"
          :hint="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.create.baseHint')"
          density="comfortable"
          variant="outlined"
          class="mt-2"
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="isSubmitting" @click="onCancel">
          {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.create.cancel") }}
        </v-btn>
        <v-btn
          variant="flat"
          color="primary"
          :loading="isSubmitting"
          :disabled="!canSubmit"
          @click="onSubmit"
        >
          {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.create.submit") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.worktree-create-mode {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
