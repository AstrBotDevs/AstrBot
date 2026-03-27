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

          <v-row dense>
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
import axios from "axios";
import { useModuleI18n } from "@/i18n/composables";
import { useToastStore } from "@/stores/toast";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";

const { tm } = useModuleI18n("features/settings");
const toastStore = useToastStore();
const confirmDialog = useConfirmDialog();

const statusLoading = ref(false);
const cleaningTarget = ref("");
const storageStatus = ref({
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
  total_bytes: 0,
});

const showToast = (message, color = "success") => {
  toastStore.add({
    message,
    color,
    timeout: 3000,
  });
};

const formatBytes = (bytes) => {
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

const storageCards = computed(() => [
  {
    key: "cache",
    title: tm("system.cleanup.targets.cache.title"),
    subtitle: tm("system.cleanup.targets.cache.subtitle"),
    buttonText: tm("system.cleanup.targets.cache.button"),
    icon: "mdi-database-refresh-outline",
    color: "primary",
    sizeBytes: storageStatus.value.cache?.size_bytes || 0,
    fileCount: storageStatus.value.cache?.file_count || 0,
    path: storageStatus.value.cache?.path || "-",
  },
  {
    key: "logs",
    title: tm("system.cleanup.targets.logs.title"),
    subtitle: tm("system.cleanup.targets.logs.subtitle"),
    buttonText: tm("system.cleanup.targets.logs.button"),
    icon: "mdi-file-document-outline",
    color: "warning",
    sizeBytes: storageStatus.value.logs?.size_bytes || 0,
    fileCount: storageStatus.value.logs?.file_count || 0,
    path: storageStatus.value.logs?.path || "-",
  },
]);

const loadStorageStatus = async () => {
  statusLoading.value = true;
  try {
    const res = await axios.get("/api/stat/storage");
    if (res.data.status !== "ok") {
      showToast(
        res.data.message || tm("system.cleanup.messages.statusFailed"),
        "error",
      );
      return;
    }
    storageStatus.value = res.data.data || storageStatus.value;
  } catch (error) {
    showToast(
      error?.response?.data?.message ||
        tm("system.cleanup.messages.statusFailed"),
      "error",
    );
  } finally {
    statusLoading.value = false;
  }
};

const cleanupStorage = async (target) => {
  const confirmed = await askForConfirmation(
    tm("system.cleanup.confirm", {
      target: tm(`system.cleanup.targetNames.${target}`),
    }),
    confirmDialog,
  );
  if (!confirmed) return;

  cleaningTarget.value = target;
  try {
    const res = await axios.post("/api/stat/storage/cleanup", { target });
    if (res.data.status !== "ok") {
      showToast(
        res.data.message || tm("system.cleanup.messages.cleanupFailed"),
        "error",
      );
      return;
    }

    const cleanupData = res.data.data || {};
    storageStatus.value = cleanupData.status || storageStatus.value;
    showToast(
      tm("system.cleanup.messages.cleanupSuccess", {
        size: formatBytes(cleanupData.removed_bytes || 0),
        count: cleanupData.processed_files || 0,
      }),
    );
  } catch (error) {
    showToast(
      error?.response?.data?.message ||
        tm("system.cleanup.messages.cleanupFailed"),
      "error",
    );
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
  margin: 8px 0 12px;
}
</style>
