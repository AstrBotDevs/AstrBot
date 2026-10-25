<template>
  <v-dialog
    :model-value="!!platform"
    :persistent="deleting"
    max-width="480"
    @update:model-value="!$event && $emit('update:platform', null)"
  >
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">
        {{ tm("deleteDialog.title") }}
      </v-card-title>
      <v-card-text class="px-6 pt-4 pb-2">
        <p class="text-body-1 mb-3 delete-message">
          {{ tm("deleteDialog.message", { id: platform?.id || "" }) }}
        </p>
        <div class="text-caption text-medium-emphasis">
          {{ tm("deleteDialog.cleanup") }}
        </div>
        <div class="cleanup-grid">
          <template v-for="target in cleanupTargets" :key="target">
            <div
              v-if="target === 'conversations'"
              class="history-controls d-flex align-center justify-space-between"
            >
              <span class="text-caption text-medium-emphasis">
                {{ tm("deleteDialog.history") }}
              </span>
              <v-btn
                variant="text"
                size="x-small"
                :disabled="deleting"
                @click="allHistorySelected = !allHistorySelected"
              >
                {{
                  tm(
                    allHistorySelected
                      ? "deleteDialog.deselectAll"
                      : "deleteDialog.selectAll",
                  )
                }}
              </v-btn>
            </div>
            <v-checkbox
              v-model="cleanup"
              :value="target"
              :disabled="deleting"
              density="compact"
              hide-details
              color="primary"
            >
              <template #label>
                <span>{{ tm(`deleteDialog.options.${target}`) }}</span>
                <v-tooltip
                  :text="tm(`deleteDialog.descriptions.${target}`)"
                  location="top"
                  max-width="280"
                  open-on-click
                >
                  <template #activator="{ props: tooltipProps }">
                    <v-btn
                      v-bind="tooltipProps"
                      :aria-label="tm(`deleteDialog.descriptions.${target}`)"
                      icon="mdi-information-outline"
                      variant="text"
                      size="20"
                      class="ms-1 text-disabled"
                      @click.stop
                    />
                  </template>
                </v-tooltip>
              </template>
            </v-checkbox>
          </template>
        </div>
        <p class="text-caption text-medium-emphasis mt-2 mb-0">
          {{ tm("deleteDialog.hint") }}
        </p>
        <p v-if="error" role="alert" class="text-body-2 text-error mt-2 mb-0">
          {{ error }}
        </p>
      </v-card-text>
      <v-card-actions class="px-6 pb-4 pt-2">
        <v-spacer />
        <v-btn
          variant="text"
          :disabled="deleting"
          @click="$emit('update:platform', null)"
        >
          {{ tm("dialog.cancel") }}
        </v-btn>
        <v-btn
          color="error"
          variant="tonal"
          :loading="deleting"
          @click="deletePlatform"
        >
          {{ tm("deleteDialog.confirm") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { botApi } from "@/api/v1";
import type { BotCleanupTarget } from "@/api/generated/openapi-v1";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{ platform: { id: string } | null }>();
const emit = defineEmits(["update:platform", "deleted"]);
const { tm } = useModuleI18n("features/platform");
const defaultCleanup: BotCleanupTarget[] = [
  "custom_rules",
  "preferences",
  "routing",
  "cron_jobs",
];
const historyTargets: BotCleanupTarget[] = [
  "conversations",
  "message_history",
  "traces",
  "stats",
];
const cleanupTargets = [...defaultCleanup, ...historyTargets];
const cleanup = ref<BotCleanupTarget[]>([...defaultCleanup]);
const deleting = ref(false);
const error = ref("");
const allHistorySelected = computed({
  get: () => historyTargets.every((target) => cleanup.value.includes(target)),
  set: (selected: boolean) => {
    cleanup.value = cleanup.value.filter(
      (target) => !historyTargets.includes(target),
    );
    if (selected) cleanup.value.push(...historyTargets);
  },
});

watch(
  () => props.platform,
  () => {
    cleanup.value = [...defaultCleanup];
    error.value = "";
  },
);

async function deletePlatform() {
  if (!props.platform || deleting.value) return;
  const id = props.platform.id;
  deleting.value = true;
  error.value = "";
  try {
    await botApi.delete(id, cleanup.value);
    emit("update:platform", null);
    emit("deleted", id);
  } catch (err) {
    error.value = tm("deleteDialog.failed");
  } finally {
    deleting.value = false;
  }
}
</script>

<style scoped>
.cleanup-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 8px;
}

.history-controls {
  grid-column: 1 / -1;
  min-height: 28px;
  margin-top: 4px;
}

.cleanup-grid :deep(.v-selection-control) {
  --v-selection-control-size: 32px;
  min-height: 32px;
}

.cleanup-grid :deep(.v-label) {
  font-size: 0.875rem;
  opacity: 1;
}

.delete-message {
  overflow-wrap: anywhere;
}
</style>
