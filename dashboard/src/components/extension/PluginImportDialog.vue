<script setup>
import LZString from "lz-string";
import axios from "axios";
import { computed, ref, watch } from "vue";

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

const selectedCount = computed(
  () => importPlugins.value.filter((_, idx) => selected.value[idx]).length,
);

const allSelected = computed(
  () =>
    importPlugins.value.length > 0 &&
    selectedCount.value === importPlugins.value.length,
);

const someSelected = computed(
  () => selectedCount.value > 0 && !allSelected.value,
);

const progressText = computed(() => {
  if (!installing.value && Object.keys(installStatus.value).length === 0) return "";
  const total = importPlugins.value.length;
  const done = Object.values(installStatus.value).filter(
    (s) => s === "success" || s === "error",
  ).length;
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
    importError.value = "请先粘贴插件码";
    return;
  }
  try {
    const jsonStr = LZString.decompressFromEncodedURIComponent(code);
    if (!jsonStr) {
      importError.value = "插件码解析失败，请检查格式";
      return;
    }
    const parsed = JSON.parse(jsonStr);
    if (!Array.isArray(parsed)) {
      importError.value = "插件码内容格式错误";
      return;
    }
    importPlugins.value = parsed;
    selected.value = parsed.map(() => true);
  } catch (err) {
    importError.value = "插件码解析失败：" + err.message;
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
      throw new Error("缺少仓库地址");
    }
    await axios.post("/api/plugin/install", {
      url: plugin.repo,
      proxy: props.proxy || "",
      ignore_version_check: false,
    });
    installStatus.value = { ...installStatus.value, [idx]: "success" };
  } catch (err) {
    const msg =
      err?.response?.data?.message || err?.message || "未知错误";
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
  const indices = importPlugins.value
    .map((_, i) => i)
    .filter((i) => selected.value[i]);
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
        <span>导入插件</span>
        <v-chip
          v-if="progressText"
          size="small"
          class="ml-3"
          :color="installing ? 'primary' : 'default'"
          variant="tonal"
        >
          {{ installing ? `导入中 ${progressText}` : `完成 ${progressText}` }}
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
          label="粘贴插件码"
          variant="outlined"
          density="compact"
          auto-grow
          rows="3"
          max-rows="6"
          hide-details="auto"
          :error-messages="importError"
          :disabled="installing"
          class="mb-3"
        />

        <div class="d-flex justify-end mb-3">
          <v-btn
            color="primary"
            variant="tonal"
            size="small"
            :disabled="installing"
            @click="parseImportCode"
          >
            解析
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
              共解析到 {{ importPlugins.length }} 个插件，已选 {{ selectedCount }} 个
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
                {{ plugin.name || "(未命名)" }}
                <span class="text-caption text-medium-emphasis ml-2">
                  v{{ plugin.version || "?" }}
                </span>
              </v-list-item-title>
              <v-list-item-subtitle v-if="plugin.repo" class="text-caption">
                {{ plugin.repo }}
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
          导入选中 ({{ selectedCount }})
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          size="small"
          :disabled="installing"
          :loading="installing"
          @click="importAll"
        >
          全部导入
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
</style>
