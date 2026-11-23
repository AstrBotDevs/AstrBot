<template>
  <div class="storage-cleanup-panel">
    <div class="text-subtitle-1 font-weight-medium mb-1">
      {{ tm("system.cleanup.title") }}
    </div>
    <div class="text-body-2 text-medium-emphasis mb-4">
      {{ tm("system.cleanup.subtitle") }}
    </div>

    <v-expansion-panels variant="accordion">
      <v-expansion-panel elevation="0" class="border rounded-lg">
        <v-expansion-panel-title class="py-4">
          <div
            class="d-flex align-center justify-space-between w-100 pr-4 ga-3"
          >
            <div class="d-flex align-center ga-3">
              <v-icon color="warning"> mdi-broom </v-icon>
              <div>
                <div class="font-weight-medium">
                  {{ tm("system.cleanup.panel.title") }}
                </div>
                <div class="text-caption text-medium-emphasis">
                  {{
                    tm("system.cleanup.panel.subtitle", {
                      size: formatBytes(storageStatus.total_bytes || 0),
                    })
                  }}
                </div>
              </div>
            </div>
            <v-chip size="small" color="warning" variant="tonal">
              {{ formatBytes(storageStatus.total_bytes || 0) }}
            </v-chip>
          </div>
        </v-expansion-panel-title>

        <v-expansion-panel-text>
          <div class="d-flex flex-wrap ga-2 mb-4">
            <v-btn
              size="small"
              variant="tonal"
              color="primary"
              :loading="statusLoading"
              @click="loadStorageStatus"
            >
              <v-icon class="mr-2"> mdi-refresh </v-icon>
              {{ tm("system.cleanup.refresh") }}
            </v-btn>
            <v-btn
              size="small"
              color="warning"
              :loading="cleaningTarget === 'all'"
              @click="cleanupStorage('all')"
            >
              <v-icon class="mr-2"> mdi-broom </v-icon>
              {{ tm("system.cleanup.cleanAll") }}
            </v-btn>
          </div>

          <v-row density="compact">
            <v-col
              v-for="item in storageCards"
              :key="item.key"
              cols="12"
              md="6"
            >
              <v-card variant="tonal" class="h-100">
                <v-card-text>
                  <div class="d-flex align-start justify-space-between ga-3">
                    <div>
                      <div class="text-subtitle-1 font-weight-medium">
                        {{ item.title }}
                      </div>
                      <div class="text-body-2 text-medium-emphasis mt-1">
                        {{ item.subtitle }}
                      </div>
                    </div>
                    <v-icon :color="item.color">
                      {{ item.icon }}
                    </v-icon>
                  </div>

                  <div class="text-h5 mt-4">
                    {{ formatBytes(item.sizeBytes) }}
                  </div>
                  <div class="text-caption text-medium-emphasis mt-1">
                    {{
                      tm("system.cleanup.fileCount", { count: item.fileCount })
                    }}
                  </div>
                  <div
                    class="text-caption text-medium-emphasis mt-2 storage-cleanup-path"
                  >
                    {{ item.path }}
                  </div>

                  <v-btn
                    class="mt-4"
                    size="small"
                    :color="item.color"
                    :loading="cleaningTarget === item.key"
                    @click="cleanupStorage(item.key)"
                  >
                    <v-icon class="mr-2"> mdi-delete-sweep-outline </v-icon>
                    {{ item.buttonText }}
                  </v-btn>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { statsApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import { useToastStore } from "@/stores/toast";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";
import { resolveErrorMessage } from "@/utils/errorUtils";

type CleanupTarget = "logs" | "cache" | "traces" | "all";

interface StorageDirectoryStatus {
  size_bytes?: number;
  file_count?: number;
  path?: string;
  exists?: boolean;
}

interface StorageStatus {
  logs?: StorageDirectoryStatus;
  cache?: StorageDirectoryStatus;
  traces?: StorageDirectoryStatus;
  total_bytes?: number;
}

interface StorageCard {
  key: Exclude<CleanupTarget, "all">;
  title: string;
  subtitle: string;
  color: string;
  fileCount: number;
  path: string;
  buttonText: string;
  icon: string;
  sizeBytes: number;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

const isStorageDirectoryStatus = (value: unknown): value is StorageDirectoryStatus =>
  isRecord(value) &&
  (value.size_bytes === undefined || typeof value.size_bytes === "number") &&
  (value.file_count === undefined || typeof value.file_count === "number") &&
  (value.path === undefined || typeof value.path === "string") &&
  (value.exists === undefined || typeof value.exists === "boolean");

const isStorageStatus = (value: unknown): value is StorageStatus =>
  isRecord(value) &&
  (value.total_bytes === undefined || typeof value.total_bytes === "number") &&
  ["logs", "cache", "traces"].every((key) => value[key] === undefined || isStorageDirectoryStatus(value[key]));

const parseStorageStatus = (value: unknown): StorageStatus => {
  if (!isStorageStatus(value)) {
    throw new Error("Invalid storage status response");
  }
  return value;
};

const { tm } = useModuleI18n("features/settings");
const toastStore = useToastStore();
const confirmDialog = useConfirmDialog();

const statusLoading = ref(false);
const cleaningTarget = ref<CleanupTarget | "">("");
const storageStatus = ref<StorageStatus>({
  logs: {
    size_bytes: 0,
    file_count: 0,
    path: "",
    exists: false,
  },
  cache: {
    size_bytes: 0,
    file_count: 0,
    path: "",
    exists: false,
  },
  traces: {
    size_bytes: 0,
    file_count: 0,
    path: "",
    exists: false,
  },
  total_bytes: 0,
});

const showToast = (message: string, color = "success") => {
  toastStore.add({
    message,
    color,
    timeout: 3000,
  });
};

const formatBytes = (bytes: number) => {
  const value = Number(bytes || 0);
  if (value <= 0) return "0 B";

  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }

  const decimals = size >= 10 || unitIndex === 0 ? 0 : 1;
  return `${size.toFixed(decimals)} ${units[unitIndex]}`;
};

const storageCards = computed<StorageCard[]>(() => [
  {
    key: "cache",
    title: tm("system.cleanup.targets.cache.title"),
    subtitle: tm("system.cleanup.targets.cache.subtitle"),
    color: "primary",
    fileCount: storageStatus.value.cache?.file_count || 0,
    path: storageStatus.value.cache?.path || "-",
    buttonText: tm("system.cleanup.targets.cache.button"),
    icon: "mdi-database-refresh-outline",
    sizeBytes: storageStatus.value.cache?.size_bytes || 0,
  },
  {
    key: "logs",
    title: tm("system.cleanup.targets.logs.title"),
    subtitle: tm("system.cleanup.targets.logs.subtitle"),
    color: "warning",
    fileCount: storageStatus.value.logs?.file_count || 0,
    path: storageStatus.value.logs?.path || "-",
    buttonText: tm("system.cleanup.targets.logs.button"),
    icon: "mdi-file-document-outline",
    sizeBytes: storageStatus.value.logs?.size_bytes || 0,
  },
  {
    key: "traces",
    title: tm("system.cleanup.targets.traces.title"),
    subtitle: tm("system.cleanup.targets.traces.subtitle"),
    color: "secondary",
    fileCount: storageStatus.value.traces?.file_count || 0,
    path: storageStatus.value.traces?.path || "-",
    buttonText: tm("system.cleanup.targets.traces.button"),
    icon: "mdi-database-outline",
    sizeBytes: storageStatus.value.traces?.size_bytes || 0,
  },
]);

const loadStorageStatus = async () => {
  statusLoading.value = true;
  try {
    const res = await statsApi.storage();
    if (res.data.status !== "ok") {
      showToast(res.data.message || tm("system.cleanup.messages.statusFailed"), "error");
      return;
    }
    storageStatus.value = parseStorageStatus(res.data.data || storageStatus.value);
  } catch (error) {
    showToast(resolveErrorMessage(error, tm("system.cleanup.messages.statusFailed")), "error");
  } finally {
    statusLoading.value = false;
  }
};

const cleanupStorage = async (target: CleanupTarget) => {
  const confirmed = await askForConfirmation(
    ["traces", "all"].includes(target)
      ? tm("system.cleanup.confirmWithTraces", { target: tm(`system.cleanup.targetNames.${target}`) })
      : tm("system.cleanup.confirm", { target: tm(`system.cleanup.targetNames.${target}`) }),
    confirmDialog,
  );
  if (!confirmed) return;

  cleaningTarget.value = target;
  try {
    const res = await statsApi.cleanupStorage(target);
    if (res.data.status !== "ok") {
      showToast(res.data.message || tm("system.cleanup.messages.cleanupFailed"), "error");
      return;
    }

    const cleanupData = res.data.data || {};
    storageStatus.value = parseStorageStatus(cleanupData.status || storageStatus.value);
    const removedBytes = typeof cleanupData.removed_bytes === "number" ? cleanupData.removed_bytes : 0;
    const removedTraces = typeof cleanupData.removed_traces === "number" ? cleanupData.removed_traces : 0;
    const processedFiles = typeof cleanupData.processed_files === "number" ? cleanupData.processed_files : 0;
    showToast(
      tm(
        target === "traces"
          ? "system.cleanup.messages.cleanupTracesSuccess"
          : removedTraces
            ? "system.cleanup.messages.cleanupWithTracesSuccess"
            : "system.cleanup.messages.cleanupSuccess",
        {
          size: formatBytes(removedBytes),
          count: target === "traces" ? removedTraces : processedFiles,
          traces: removedTraces,
        },
      ),
    );
  } catch (error) {
    showToast(resolveErrorMessage(error, tm("system.cleanup.messages.cleanupFailed")), "error");
  } finally {
    cleaningTarget.value = "";
  }
};

onMounted(() => {
  loadStorageStatus();
});
</script>

<style scoped>
.storage-cleanup-path {
  word-break: break-all;
}

.storage-cleanup-panel {
    margin: 0;
}

.storage-cleanup-card {
    overflow: hidden;
    border: 1px solid var(--settings-border, rgba(17, 24, 39, 0.13));
    border-radius: var(--astrbot-radius-card);
    background: rgb(var(--v-theme-surface));
    box-shadow: none;
}

.storage-cleanup-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(220px, 38%);
    gap: 18px;
    align-items: center;
    min-height: 60px;
    padding: 12px 16px;
}

.storage-cleanup-title {
    color: rgb(var(--v-theme-on-surface));
    font-size: 0.88rem;
    font-weight: 700;
    letter-spacing: 0;
    line-height: 1.4;
}

.storage-cleanup-hint {
    margin-top: 4px;
    color: rgba(var(--v-theme-on-surface), 0.76);
    font-size: 0.78rem;
    line-height: 1.45;
}

.storage-cleanup-control {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    justify-content: flex-end;
    min-width: 0;
    justify-self: end;
}

.storage-cleanup-control :deep(.v-btn),
.storage-cleanup-control :deep(.v-chip) {
    border-radius: var(--astrbot-radius-control);
}

.storage-cleanup-chip,
.storage-cleanup-action {
    background: rgba(var(--v-theme-on-surface), 0.06) !important;
    color: rgba(var(--v-theme-on-surface), 0.72) !important;
}

@media (max-width: 720px) {
    .storage-cleanup-row {
        grid-template-columns: 1fr;
        align-items: stretch;
        padding: 14px 16px;
    }

    .storage-cleanup-control {
        justify-content: flex-start;
        justify-self: stretch;
    }
}
</style>
