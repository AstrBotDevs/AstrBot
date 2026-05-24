<script setup>
import LZString from "lz-string";
import { computed, ref, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import axios from "@/utils/request";

const { tm } = useModuleI18n("features/extension");

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  proxy: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["update:modelValue", "done"]);

const importCode = ref("");
const importPlugins = ref([]);
const importError = ref("");
const selected = ref([]);
const installStatus = ref({});
const installing = ref(false);

const selectedCount = computed(() => importPlugins.value.filter((_, idx) => selected.value[idx]).length);

const allSelected = computed(
  () => importPlugins.value.length > 0 && selectedCount.value === importPlugins.value.length,
);

const someSelected = computed(() => selectedCount.value > 0 && !allSelected.value);

const progressText = computed(() => {
  const entries = Object.entries(installStatus.value).filter(([key]) => !key.endsWith("_msg"));
  if (!installing.value && entries.length === 0) return "";
  const total = entries.length;
  const done = entries.filter(([_, status]) => status === "success" || status === "error").length;
  return `${done}/${total}`;
});

watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      importCode.value = "";
      importPlugins.value = [];
      importError.value = "";
      selected.value = [];
      installStatus.value = {};
      installing.value = false;
    }
  },
);

const close = () => {
  if (installing.value) return;
  emit("update:modelValue", false);
};

const parseImportCode = () => {
  importError.value = "";
  importPlugins.value = [];
  selected.value = [];
  installStatus.value = {};
  const code = (importCode.value || "").trim();
  if (!code) {
    importError.value = tm("exportImport.errors.needCode");
    return;
  }
  try {
    const jsonStr = LZString.decompressFromEncodedURIComponent(code);
    if (!jsonStr) {
      importError.value = tm("exportImport.errors.parseFailedFormat");
      return;
    }
    const parsed = JSON.parse(jsonStr);
    if (!Array.isArray(parsed)) {
      importError.value = tm("exportImport.errors.parseFailedContent");
      return;
    }
    importPlugins.value = parsed;
    selected.value = parsed.map(() => true);
  } catch (err) {
    importError.value = tm("exportImport.errors.parseFailed", { msg: err.message });
  }
};

const toggleSelectAll = () => {
  const next = !allSelected.value;
  selected.value = importPlugins.value.map(() => next);
};

const toggleSelect = (idx) => {
  selected.value[idx] = !selected.value[idx];
};

const installOne = async (plugin, idx) => {
  installStatus.value = { ...installStatus.value, [idx]: "installing" };
  try {
    if (!plugin.repo) {
      throw new Error(tm("exportImport.errors.missingRepo"));
    }
    await axios.post("/api/plugin/install", {
      url: plugin.repo,
      proxy: props.proxy || "",
      ignore_version_check: false,
    });
    installStatus.value = { ...installStatus.value, [idx]: "success" };
  } catch (err) {
    const msg = err?.response?.data?.message || err?.message || tm("exportImport.errors.unknownError");
    installStatus.value = { ...installStatus.value, [idx]: "error", [`${idx}_msg`]: msg };
  }
};

const runInstall = async (indices) => {
  if (installing.value || indices.length === 0) return;
  installing.value = true;
  installStatus.value = {};
  indices.forEach((i) => {
    installStatus.value[i] = "pending";
  });
  for (const idx of indices) {
    await installOne(importPlugins.value[idx], idx);
  }
  installing.value = false;
  emit("done");
};

const importSelected = () => {
  const indices = importPlugins.value.map((_, i) => i).filter((i) => selected.value[i]);
  runInstall(indices);
};

const importAll = () => {
  const indices = importPlugins.value.map((_, i) => i);
  runInstall(indices);
};

const statusIcon = (idx) => {
  const s = installStatus.value[idx];
  switch (s) {
    case "pending":
      return { icon: "mdi-clock-outline", color: "grey" };
    case "installing":
      return { icon: "mdi-loading mdi-spin", color: "primary" };
    case "success":
      return { icon: "mdi-check-circle", color: "success" };
    case "error":
      return { icon: "mdi-alert-circle", color: "error" };
    default:
      return null;
  }
};
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    :persistent="installing"
    max-width="640"
  >
    <v-card class="rounded-lg">
      <v-card-title class="d-flex align-center pa-4">
        <v-icon class="mr-2">mdi-import</v-icon>
        <span>{{ tm("exportImport.importPlugin") }}</span>
        <v-chip
          v-if="progressText"
          size="small"
          class="ml-3"
          :color="installing ? 'primary' : 'default'"
          variant="tonal"
        >
          {{ installing ? `${tm("exportImport.importing")} ${progressText}` : `${tm("exportImport.completed")} ${progressText}` }}
        </v-chip>
        <v-spacer />
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          :disabled="installing"
          @click="close"
        />
      </v-card-title>

      <v-card-text>
        <v-textarea
          v-model="importCode"
          :label="tm('exportImport.pasteCode')"
          variant="outlined"
          density="compact"
          auto-grow
          rows="3"
          max-rows="6"
          hide-details="auto"
          :error-messages="importError"
          :disabled="installing"
          class="mb-2"
        />

        <v-alert
          type="warning"
          variant="tonal"
          density="compact"
          icon="mdi-shield-alert-outline"
          class="mb-3 text-caption"
        >
          {{ tm("exportImport.securityHint") }}
        </v-alert>

        <div class="d-flex justify-end mb-3">
          <v-btn
            color="primary"
            variant="tonal"
            size="small"
            :disabled="installing"
            @click="parseImportCode"
          >
            {{ tm("exportImport.parse") }}
          </v-btn>
        </div>

        <v-divider v-if="importPlugins.length > 0" class="mb-2" />

        <div v-if="importPlugins.length > 0">
          <div class="d-flex align-center mb-2">
            <v-checkbox
              :model-value="allSelected"
              :indeterminate="someSelected"
              density="compact"
              hide-details
              color="primary"
              :disabled="installing"
              @update:model-value="toggleSelectAll"
            />
            <span class="text-body-2 ml-1">
              {{ tm("exportImport.importSummary", { total: importPlugins.length, selected: selectedCount }) }}
            </span>
          </div>

          <v-list density="compact" class="import-plugin-list">
            <v-list-item
              v-for="(plugin, idx) in importPlugins"
              :key="idx"
              class="rounded-lg mb-1"
              border
            >
              <template #prepend>
                <v-checkbox
                  :model-value="!!selected[idx]"
                  density="compact"
                  hide-details
                  color="primary"
                  :disabled="installing"
                  @update:model-value="toggleSelect(idx)"
                />
                <v-icon size="small" class="mr-2">mdi-puzzle</v-icon>
              </template>
              <v-list-item-title class="text-body-2 font-weight-medium">
                {{ plugin.name || tm("exportImport.unnamed") }}
                <span class="text-caption text-medium-emphasis ml-2">
                  v{{ plugin.version || "?" }}
                </span>
              </v-list-item-title>
              <v-list-item-subtitle v-if="plugin.repo" class="text-caption">
                <a
                  :href="plugin.repo"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="repo-link"
                  @click.stop
                >
                  {{ plugin.repo }}
                </a>
              </v-list-item-subtitle>
              <v-list-item-subtitle
                v-if="installStatus[`${idx}_msg`]"
                class="text-caption text-error"
              >
                {{ installStatus[`${idx}_msg`] }}
              </v-list-item-subtitle>
              <template #append>
                <v-icon
                  v-if="statusIcon(idx)"
                  :icon="statusIcon(idx).icon"
                  :color="statusIcon(idx).color"
                  size="small"
                />
              </template>
            </v-list-item>
          </v-list>
        </div>
      </v-card-text>

      <v-card-actions v-if="importPlugins.length > 0" class="pa-4 pt-0">
        <v-spacer />
        <v-btn
          variant="tonal"
          size="small"
          :disabled="installing || selectedCount === 0"
          :loading="installing"
          @click="importSelected"
        >
          {{ tm("exportImport.importSelected") }} ({{ selectedCount }})
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          size="small"
          :disabled="installing"
          :loading="installing"
          @click="importAll"
        >
          {{ tm("exportImport.importAll") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.mdi-spin {
  animation: mdi-spin 1s infinite linear;
}

@keyframes mdi-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.repo-link {
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
  word-break: break-all;
}

.repo-link:hover {
  text-decoration: underline;
}
</style>
