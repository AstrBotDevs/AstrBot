<template>
  <div class="settings-tab">
    <v-card variant="outlined">
      <v-card-title class="pa-4">{{ t("settings.title") }}</v-card-title>

      <v-card-text class="pa-6">
        <v-form ref="formRef">
          <!-- 基本设置 -->
          <h3 class="text-h6 mb-4">{{ t("settings.basic") }}</h3>

          <v-row>
            <v-col cols="12" md="6">
              <v-text-field
                v-model.number="formData.chunk_size"
                :label="t('settings.chunkSize')"
                type="number"
                variant="outlined"
                density="comfortable"
                :rules="chunkSizeRules"
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model.number="formData.chunk_overlap"
                :label="t('settings.chunkOverlap')"
                type="number"
                variant="outlined"
                density="comfortable"
                :rules="chunkOverlapRules"
              />
            </v-col>
          </v-row>

          <!-- 检索设置 -->
          <h3 class="text-h6 mb-4 mt-6">{{ t("settings.retrieval") }}</h3>

          <v-row>
            <v-col cols="12" md="4">
              <v-text-field
                v-model.number="formData.top_k_dense"
                :label="t('settings.topKDense')"
                type="number"
                variant="outlined"
                density="comfortable"
                :rules="positiveIntegerRules"
              />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field
                v-model.number="formData.top_k_sparse"
                :label="t('settings.topKSparse')"
                type="number"
                variant="outlined"
                density="comfortable"
                :rules="positiveIntegerRules"
              />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field
                v-model.number="formData.top_m_final"
                :label="t('settings.topMFinal')"
                type="number"
                variant="outlined"
                density="comfortable"
                :rules="positiveIntegerRules"
              />
            </v-col>
          </v-row>

          <v-row>
            <v-col cols="12" md="6">
              <v-select
                v-model="formData.index_type"
                :items="indexTypeOptions"
                :label="t('settings.indexType')"
                variant="outlined"
                density="comfortable"
                :hint="t('settings.indexTypeHint')"
                persistent-hint
              />
            </v-col>
          </v-row>

          <!-- 模型设置 -->
          <h3 class="text-h6 mb-4 mt-6">
            {{ t("settings.embeddingProvider") }}
          </h3>

          <v-row>
            <v-col cols="12" md="6">
              <v-select
                v-model="formData.embedding_provider_id"
                :items="embeddingProviders"
                :item-title="(item) => item.embedding_model || item.id"
                :item-value="'id'"
                :label="t('settings.embeddingProvider')"
                variant="outlined"
                density="comfortable"
                :disabled="true"
                :hint="t('settings.embeddingProviderHint')"
                persistent-hint
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-select
                v-model="formData.rerank_provider_id"
                :items="rerankProviders"
                :item-title="(item) => item.rerank_model || item.id"
                :item-value="'id'"
                :label="t('settings.rerankProvider')"
                variant="outlined"
                density="comfortable"
                clearable
              />
            </v-col>
          </v-row>

          <v-alert type="info" variant="tonal" class="mt-4">
            {{ t("settings.tips") }}
          </v-alert>
        </v-form>
      </v-card-text>

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn
          color="primary"
          variant="elevated"
          prepend-icon="mdi-content-save"
          @click="saveSettings"
          :loading="saving"
        >
          {{ t("settings.save") }}
        </v-btn>
      </v-card-actions>
    </v-card>

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted } from "vue";
import axios from "axios";
import { useModuleI18n } from "@/i18n/composables";

const { tm: t } = useModuleI18n("features/knowledge-base/detail");

const props = defineProps<{
  kb: any;
}>();

const emit = defineEmits(["updated"]);

// 状态
const saving = ref(false);
const formRef = ref();
const embeddingProviders = ref<any[]>([]);
const rerankProviders = ref<any[]>([]);

const snackbar = ref({
  show: false,
  text: "",
  color: "success",
});

const showSnackbar = (text: string, color: string = "success") => {
  snackbar.value.text = text;
  snackbar.value.color = color;
  snackbar.value.show = true;
};

// 表单数据
const formData = ref({
  chunk_size: 512,
  chunk_overlap: 50,
  top_k_dense: 50,
  top_k_sparse: 50,
  top_m_final: 5,
  index_type: "flat",
  embedding_provider_id: "",
  rerank_provider_id: null as string | null,
});

const indexTypeOptions = computed(() => [
  { title: t("settings.indexTypes.flat"), value: "flat" },
  { title: t("settings.indexTypes.hnsw"), value: "hnsw" },
]);

const isPositiveInteger = (value: number) =>
  Number.isInteger(value) && value > 0;
const positiveIntegerRules = [
  (value: number) =>
    isPositiveInteger(value) || t("validation.positiveInteger"),
];
const chunkSizeRules = [
  (value: number) =>
    isPositiveInteger(value) || t("validation.positiveInteger"),
];
const chunkOverlapRules = [
  (value: number) => Number.isInteger(value) || t("validation.integer"),
  (value: number) => value >= 0 || t("validation.nonNegativeInteger"),
  (value: number) =>
    value < formData.value.chunk_size || t("validation.overlapLessThanSize"),
];

// 监听 kb 变化,更新表单
watch(
  () => props.kb,
  (kb) => {
    if (kb) {
      formData.value = {
        chunk_size: kb.chunk_size || 512,
        chunk_overlap: kb.chunk_overlap || 50,
        top_k_dense: kb.top_k_dense || 50,
        top_k_sparse: kb.top_k_sparse || 50,
        top_m_final: kb.top_m_final || 5,
        index_type: kb.index_type || "flat",
        embedding_provider_id: kb.embedding_provider_id || "",
        rerank_provider_id: kb.rerank_provider_id || null,
      };
    }
  },
  { immediate: true },
);

// 加载提供商列表
const loadProviders = async () => {
  try {
    const response = await axios.get("/api/config/provider/list", {
      params: { provider_type: "embedding,rerank" },
    });
    if (response.data.status === "ok") {
      embeddingProviders.value = response.data.data.filter(
        (p: any) => p.provider_type === "embedding",
      );
      rerankProviders.value = response.data.data.filter(
        (p: any) => p.provider_type === "rerank",
      );
    }
  } catch (error) {
    console.error("Failed to load providers:", error);
    showSnackbar(t("settings.providersLoadFailed"), "error");
  }
};

// 保存设置
const saveSettings = async () => {
  const { valid } = await formRef.value.validate();
  if (!valid) return;

  saving.value = true;
  try {
    const response = await axios.post("/api/kb/update", {
      kb_id: props.kb.kb_id,
      chunk_size: formData.value.chunk_size,
      chunk_overlap: formData.value.chunk_overlap,
      top_k_dense: formData.value.top_k_dense,
      top_k_sparse: formData.value.top_k_sparse,
      top_m_final: formData.value.top_m_final,
      index_type: formData.value.index_type,
      rerank_provider_id: formData.value.rerank_provider_id,
    });

    if (response.data.status === "ok") {
      showSnackbar(t("settings.saveSuccess"));
      emit("updated");
    } else {
      showSnackbar(response.data.message || t("settings.saveFailed"), "error");
    }
  } catch (error) {
    console.error("Failed to save settings:", error);
    showSnackbar(t("settings.saveFailed"), "error");
  } finally {
    saving.value = false;
  }
};

onMounted(() => {
  loadProviders();
});
</script>

<style scoped>
.settings-tab {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
</style>
