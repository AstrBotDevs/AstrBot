<script setup>
import LZString from "lz-string";
import { ref, watch } from "vue";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["update:modelValue"]);

const importCode = ref("");
const importPlugins = ref([]);
const importError = ref("");

watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      importCode.value = "";
      importPlugins.value = [];
      importError.value = "";
    }
  },
);

const close = () => {
  emit("update:modelValue", false);
};

const parseImportCode = () => {
  importError.value = "";
  importPlugins.value = [];
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
  } catch (err) {
    importError.value = "插件码解析失败：" + err.message;
  }
};
</script>

<template>
  <v-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" max-width="640">
    <v-card class="rounded-lg">
      <v-card-title class="d-flex align-center pa-4">
        <v-icon class="mr-2">mdi-import</v-icon>
        <span>导入插件</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="close" />
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
          class="mb-3"
        />

        <div class="d-flex justify-end mb-3">
          <v-btn color="primary" variant="tonal" size="small" @click="parseImportCode">
            解析
          </v-btn>
        </div>

        <v-divider v-if="importPlugins.length > 0" class="mb-2" />

        <div v-if="importPlugins.length > 0">
          <div class="text-body-2 text-medium-emphasis mb-2">
            共解析到 {{ importPlugins.length }} 个插件
          </div>
          <v-list density="compact" class="import-plugin-list">
            <v-list-item
              v-for="(plugin, idx) in importPlugins"
              :key="idx"
              class="rounded-lg mb-1"
              border
            >
              <template #prepend>
                <v-icon size="small" class="mr-2">mdi-puzzle</v-icon>
              </template>
              <v-list-item-title class="text-body-2 font-weight-medium">
                {{ plugin.name || "(未命名)" }}
                <span class="text-caption text-medium-emphasis ml-2">v{{ plugin.version || "?" }}</span>
              </v-list-item-title>
              <v-list-item-subtitle v-if="plugin.repo" class="text-caption">
                {{ plugin.repo }}
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>
