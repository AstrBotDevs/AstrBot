<script setup>
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  progress: {
    type: Object,
    required: true,
  },
});

const emit = defineEmits(["update:modelValue"]);
const { tm } = useModuleI18n("features/extension");

const title = computed(() =>
  props.progress.action === "uninstall"
    ? tm("batch.progress.uninstallTitle")
    : tm("batch.progress.installTitle"),
);

const progressPercent = computed(() => {
  if (!props.progress.total) return 0;
  return Math.round((props.progress.completed / props.progress.total) * 100);
});

const resultMessage = computed(() => {
  if (props.progress.running) return "";
  if (
    props.progress.failed === 0 &&
    props.progress.skipped === 0 &&
    props.progress.failures.length === 0
  ) {
    return tm("batch.progress.allSucceeded", {
      count: props.progress.succeeded,
    });
  }
  return tm("batch.progress.partial", {
    succeeded: props.progress.succeeded,
    failed: props.progress.failed,
    skipped: props.progress.skipped,
  });
});

const close = () => {
  if (!props.progress.running) {
    emit("update:modelValue", false);
  }
};
</script>

<template>
  <v-dialog :model-value="modelValue" max-width="680" persistent>
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">
        {{ title }}
      </v-card-title>
      <v-card-text>
        <div v-if="progress.running" class="mb-3 text-medium-emphasis">
          {{
            tm("batch.progress.current", {
              current: progress.current || tm("status.loading"),
              completed: progress.completed,
              total: progress.total,
            })
          }}
        </div>

        <v-progress-linear
          :model-value="progressPercent"
          :indeterminate="progress.running && progress.completed === 0"
          color="primary"
          height="10"
          rounded
          class="mb-4"
        />

        <div class="batch-progress-stats">
          <v-chip color="success" variant="tonal">
            {{ tm("batch.progress.succeeded", { count: progress.succeeded }) }}
          </v-chip>
          <v-chip color="error" variant="tonal">
            {{ tm("batch.progress.failed", { count: progress.failed }) }}
          </v-chip>
          <v-chip color="warning" variant="tonal">
            {{ tm("batch.progress.skipped", { count: progress.skipped }) }}
          </v-chip>
        </div>

        <v-alert
          v-if="progress.failures.length > 0"
          type="error"
          variant="tonal"
          density="comfortable"
          class="mt-4"
        >
          <div class="font-weight-medium mb-2">
            {{ tm("batch.progress.failureTitle") }}
          </div>
          <ul class="batch-result-list">
            <li
              v-for="(failure, index) in progress.failures"
              :key="`${failure.label}-${index}`"
            >
              <span class="font-weight-medium">{{ failure.label }}</span
              >:
              {{ failure.reason }}
            </li>
          </ul>
        </v-alert>

        <v-alert
          v-if="progress.skippedItems.length > 0"
          type="warning"
          variant="tonal"
          density="comfortable"
          class="mt-4"
        >
          <div class="font-weight-medium mb-2">
            {{ tm("batch.progress.skippedTitle") }}
          </div>
          <ul class="batch-result-list">
            <li
              v-for="(item, index) in progress.skippedItems"
              :key="`${item.label}-${index}`"
            >
              <span class="font-weight-medium">{{ item.label }}</span
              >:
              {{ item.reason }}
            </li>
          </ul>
        </v-alert>

        <v-alert
          v-if="!progress.running"
          :type="
            progress.failed === 0 &&
            progress.skipped === 0 &&
            progress.failures.length === 0
              ? 'success'
              : 'warning'
          "
          variant="tonal"
          class="mt-4"
        >
          {{ resultMessage }}
        </v-alert>
      </v-card-text>
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="text" :disabled="progress.running" @click="close">
          {{ tm("batch.actions.close") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.batch-progress-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.batch-result-list {
  max-height: 220px;
  overflow-y: auto;
  padding-left: 20px;
}
</style>
