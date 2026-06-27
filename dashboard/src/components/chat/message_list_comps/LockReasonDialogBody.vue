<!-- Author: elecvoid243
     Date: 2026-06-27
     Inline body for the lock dialog. Kept separate from GitDiffSidebar
     to avoid bloating its template; same pattern as GitCommitDialog. -->
<script setup lang="ts">
import { ref, computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/chat");

const props = defineProps<{
  targetBranch: string | null;
  isLocking: boolean;
}>();

const emit = defineEmits<{
  (e: "submit", reason: string | null): void;
  (e: "cancel"): void;
}>();

const reason = ref<string>("");
const reasonTooLong = computed(() => reason.value.length > 200);

const canSubmit = computed(() => !reasonTooLong.value && !props.isLocking);

function onSubmit(): void {
  if (!canSubmit.value) return;
  emit("submit", reason.value.trim() || null);
}
</script>

<template>
  <v-card>
    <v-card-title class="text-h6">
      {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.lock.dialogTitle") }}
    </v-card-title>
    <v-card-text>
      <p class="mb-3 text-body-2">
        {{
          tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.lock.targetInfo", {
            branch: targetBranch ?? "",
          })
        }}
      </p>
      <v-textarea
        v-model="reason"
        :label="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.lock.reason')"
        :hint="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.lock.reasonHint')"
        :counter="200"
        :error-messages="reasonTooLong ? [tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.lock.reasonHint')] : []"
        rows="3"
        density="comfortable"
        variant="outlined"
        :maxlength="200"
      />
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn variant="text" :disabled="isLocking" @click="emit('cancel')">
        {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.lock.cancel") }}
      </v-btn>
      <v-btn
        variant="flat"
        color="primary"
        :loading="isLocking"
        :disabled="!canSubmit"
        @click="onSubmit"
      >
        {{ tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.lock.submit") }}
      </v-btn>
    </v-card-actions>
  </v-card>
</template>
