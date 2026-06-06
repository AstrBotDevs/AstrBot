<template>
  <div class="retrieval-tab">
    <v-card variant="outlined">
      <v-card-title class="pa-4 pb-0">{{ t("retrieval.title") }}</v-card-title>
      <v-card-subtitle class="pb-4 pt-2">
        {{ t("retrieval.subtitle") }}
      </v-card-subtitle>

      <v-progress-linear
        v-if="loading"
        indeterminate
        color="primary"
        height="2"
      />

      <v-card-text class="pa-6">
        <v-row class="mb-4">
          <v-col cols="12" md="8">
            <v-textarea
              v-model="query"
              :label="t('retrieval.query')"
              :placeholder="t('retrieval.queryPlaceholder')"
              variant="outlined"
              rows="3"
              auto-grow
              clearable
            />

            <div v-if="debugVisualize" class="mt-2">
              <v-card variant="outlined">
                <v-img
                  :src="`data:image/png;base64,${debugVisualize}`"
                  :alt="t('retrieval.tsneVisualization')"
                  contain
                >
                  <template #placeholder>
                    <div class="d-flex align-center justify-center fill-height">
                      <v-progress-circular indeterminate color="primary" />
                    </div>
                  </template>
                </v-img>
              </v-card>
            </div>
          </v-col>

          <v-col cols="12" md="4">
            <v-card variant="outlined" class="pa-4">
              <h4 class="text-subtitle-2 mb-3">
                {{ t("retrieval.settings") }}
              </h4>

              <v-text-field
                v-model.number="topK"
                :label="t('retrieval.topK')"
                :hint="t('retrieval.topKHint')"
                type="number"
                variant="outlined"
                density="compact"
                persistent-hint
                class="mb-3"
                :rules="topKRules"
              />

              <v-switch
                v-model="debugMode"
                color="primary"
                density="compact"
                hide-details
              >
                <template #label>
                  <span class="text-caption">
                    <v-icon size="small" class="mr-1">mdi-bug</v-icon>
                    {{ t("retrieval.debugModeTsne") }}
                  </span>
                </template>
              </v-switch>

              <v-switch
                v-model="traceMode"
                color="primary"
                density="compact"
                hide-details
                class="mt-1"
              >
                <template #label>
                  <span class="text-caption">
                    <v-icon size="small" class="mr-1">
                      mdi-chart-timeline-variant
                    </v-icon>
                    {{ t("retrieval.traceMode") }}
                  </span>
                </template>
              </v-switch>
            </v-card>
          </v-col>
        </v-row>

        <div class="d-flex justify-end mb-4 ga-2 flex-wrap">
          <v-btn
            prepend-icon="mdi-magnify"
            color="primary"
            variant="elevated"
            :loading="loading"
            :disabled="!query || query.trim() === ''"
            @click="performRetrieval"
          >
            {{ loading ? t("retrieval.searching") : t("retrieval.search") }}
          </v-btn>
        </div>

        <div v-if="hasSearched" class="results-section">
          <div class="d-flex align-center mb-4">
            <h3 class="text-h6">{{ t("retrieval.results") }}</h3>
            <v-chip class="ml-3" color="primary" variant="tonal" size="small">
              {{ results.length }} {{ t("retrieval.results") }}
            </v-chip>
          </div>

          <div v-if="hasTrace" class="trace-section mb-4">
            <div class="d-flex align-center mb-3 flex-wrap ga-2">
              <h4 class="text-subtitle-1">{{ t("retrieval.traceTitle") }}</h4>
              <v-chip color="info" variant="tonal" size="small">
                {{ t("retrieval.traceStageCount", { count: traceStages.length }) }}
              </v-chip>
            </div>

            <v-expansion-panels
              v-model="expandedTraceStages"
              multiple
              variant="accordion"
              class="trace-panels"
            >
              <v-expansion-panel
                v-for="stage in traceStages"
                :key="stage.key"
                :value="stage.key"
              >
                <v-expansion-panel-title>
                  <div class="trace-stage-title">
                    <v-icon size="small">{{ stage.icon }}</v-icon>
                    <span>{{ stage.label }}</span>
                    <v-chip size="x-small" variant="tonal">
                      {{ t("retrieval.traceHits", { count: stage.items.length }) }}
                    </v-chip>
                  </div>
                </v-expansion-panel-title>

                <v-expansion-panel-text>
                  <div v-if="stage.items.length > 0" class="trace-list">
                    <div
                      v-for="(item, index) in stage.items"
                      :key="traceItemKey(stage.key, item, index)"
                      class="trace-item"
                    >
                      <div class="trace-item-header">
                        <v-chip size="x-small" color="primary" variant="tonal">
                          #{{ item.rank ?? index + 1 }}
                        </v-chip>
                        <v-chip
                          size="x-small"
                          variant="tonal"
                          :disabled="!item.doc_id"
                          @click="openTraceDocument(item)"
                        >
                          <v-icon start size="small">mdi-file-document</v-icon>
                          {{ item.doc_name || t("retrieval.unknownDocument") }}
                        </v-chip>
                        <v-chip size="x-small" variant="tonal">
                          <v-icon start size="small">mdi-text</v-icon>
                          {{
                            t("retrieval.chunk", {
                              index: item.chunk_index ?? 0,
                            })
                          }}
                        </v-chip>
                        <v-spacer />
                        <v-chip size="x-small" :color="getScoreColor(item.score)">
                          {{ t("retrieval.score") }}:
                          {{ formatScore(item.score) }}
                        </v-chip>
                      </div>

                      <div class="trace-metrics">
                        <span v-if="item.dense_rank">
                          {{
                            t("retrieval.traceDenseRank", {
                              rank: item.dense_rank,
                            })
                          }}
                        </span>
                        <span v-if="item.sparse_rank">
                          {{
                            t("retrieval.traceSparseRank", {
                              rank: item.sparse_rank,
                            })
                          }}
                        </span>
                        <span v-if="item.duplicate_of_chunk_id">
                          {{
                            t("retrieval.traceDuplicateOf", {
                              chunk: item.duplicate_of_chunk_id,
                            })
                          }}
                        </span>
                        <span v-if="item.dedup_similarity !== undefined">
                          {{
                            t("retrieval.traceDedupSimilarity", {
                              value: formatPercent(item.dedup_similarity),
                            })
                          }}
                        </span>
                        <v-chip
                          v-for="chip in traceScoreChips(item)"
                          :key="chip.key"
                          size="x-small"
                          variant="tonal"
                        >
                          {{ t(chip.labelKey) }}:
                          {{ formatScore(chip.value) }}
                        </v-chip>
                        <span v-if="item.chunk_id">{{ item.chunk_id }}</span>
                      </div>

                      <div
                        v-if="traceSourceChips(item).length > 0"
                        class="source-chip-row mt-2"
                      >
                        <v-chip
                          v-for="chip in traceSourceChips(item)"
                          :key="chip.key"
                          size="x-small"
                          variant="tonal"
                        >
                          <v-icon start size="small">{{ chip.icon }}</v-icon>
                          {{ formatSourceChipLabel(chip) }}
                        </v-chip>
                      </div>

                      <div class="trace-preview">
                        {{
                          item.content_preview ||
                          t("retrieval.tracePreviewEmpty")
                        }}
                      </div>
                    </div>
                  </div>

                  <div v-else class="trace-empty">
                    {{ t("retrieval.traceEmpty") }}
                  </div>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </div>

          <div v-if="results.length > 0" class="results-list">
            <v-card
              v-for="(result, index) in results"
              :key="result.chunk_id"
              variant="outlined"
              class="mb-4"
            >
              <v-card-title class="d-flex align-center pa-2">
                <v-chip size="x-small" color="primary" class="mr-2">
                  #{{ index + 1 }}
                </v-chip>
                <span class="text-subtitle-1">
                  {{ t("retrieval.chunk", { index: result.chunk_index }) }}
                </span>
                <div class="ml-4 result-meta">
                  <v-chip
                    size="x-small"
                    variant="tonal"
                    class="mr-2"
                    @click="openDocument(result)"
                  >
                    <v-icon start size="small">mdi-file-document</v-icon>
                    {{ result.doc_name }}
                  </v-chip>
                  <v-chip size="x-small" variant="tonal">
                    <v-icon start size="small">mdi-text</v-icon>
                    {{ t("retrieval.charCount", { count: result.char_count }) }}
                  </v-chip>
                </div>
                <v-spacer />
                <v-chip size="x-small" :color="getScoreColor(result.score)">
                  {{ t("retrieval.score") }}: {{ formatScore(result.score) }}
                </v-chip>
              </v-card-title>

              <v-card-text class="pa-4">
                <div
                  v-if="sourceChips(result.source).length > 0"
                  class="source-chip-row mb-3"
                >
                  <v-chip
                    v-for="chip in sourceChips(result.source)"
                    :key="chip.key"
                    size="x-small"
                    variant="tonal"
                  >
                    <v-icon start size="small">{{ chip.icon }}</v-icon>
                    {{ formatSourceChipLabel(chip) }}
                  </v-chip>
                </div>

                <div class="content-box">
                  {{ result.content }}
                </div>
              </v-card-text>
            </v-card>
          </div>

          <div v-else class="text-center py-12">
            <v-icon size="80" color="grey-lighten-2">
              mdi-text-box-search-outline
            </v-icon>
            <p class="text-h6 mt-4 text-medium-emphasis">
              {{ t("retrieval.noResults") }}
            </p>
            <p class="text-body-2 text-medium-emphasis">
              {{ t("retrieval.tryDifferentQuery") }}
            </p>
          </div>
        </div>
      </v-card-text>
    </v-card>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import axios from "axios";
import { useModuleI18n } from "@/i18n/composables";
import { useKnowledgeBaseCapabilities } from "../capabilities";
import {
  buildRetrievalSourceChips,
  buildTraceScoreChips,
  createDocumentChunkRouteLocation,
} from "../knowledgeBaseUi.mjs";

const { tm: t } = useModuleI18n("features/knowledge-base/detail");
const router = useRouter();

const props = defineProps<{
  kbId: string;
  kbName: string;
}>();
const { capabilities, loadCapabilities } = useKnowledgeBaseCapabilities();

type TraceStageKey =
  | "dense"
  | "sparse"
  | "fusion"
  | "dedup"
  | "dedup_removed"
  | "rerank"
  | "final";

interface RetrievalResult {
  chunk_id: string;
  doc_id: string;
  kb_id: string;
  kb_name: string;
  doc_name: string;
  chunk_index: number;
  content: string;
  score: number;
  char_count: number;
  source?: RetrievalSource;
}

interface RetrievalTraceItem {
  rank?: number;
  chunk_id?: string | null;
  doc_id?: string | null;
  doc_name?: string | null;
  kb_id?: string | null;
  kb_name?: string | null;
  chunk_index?: number | null;
  score?: number | null;
  dense_rank?: number | null;
  sparse_rank?: number | null;
  dense_score?: number | null;
  sparse_score?: number | null;
  rrf_score?: number | null;
  rerank_score?: number | null;
  duplicate_of_chunk_id?: string | null;
  duplicate_of_doc_id?: string | null;
  dedup_similarity?: number | null;
  stage?: string;
  content_preview?: string | null;
  title_path?: string[] | null;
  page_number?: number | null;
  section_index?: number | null;
  parent_chunk_id?: string | null;
}

type RetrievalTrace = Record<TraceStageKey, RetrievalTraceItem[]>;

interface RetrievalSource {
  kb_name?: string | null;
  document_name?: string | null;
  chunk_index?: number | null;
  section_index?: number | null;
  title_path?: string[] | null;
  page_number?: number | null;
  parent_chunk_id?: string | null;
}

interface RetrievalSourceChip {
  key: string;
  icon: string;
  label?: string;
  labelKey?: string;
  params?: Record<string, string | number>;
}

const emptyTrace = (): RetrievalTrace => ({
  dense: [],
  sparse: [],
  fusion: [],
  dedup: [],
  dedup_removed: [],
  rerank: [],
  final: [],
});

const loading = ref(false);
const query = ref("");
const topK = ref<number | null>(null);
const debugMode = ref(false);
const traceMode = ref(false);
const results = ref<RetrievalResult[]>([]);
const hasSearched = ref(false);
const debugVisualize = ref<string | null>(null);
const retrievalTrace = ref<RetrievalTrace | null>(null);
const expandedTraceStages = ref<TraceStageKey[]>(["fusion", "final"]);
const maxRetrieveTopK = computed(
  () => capabilities.value?.limits.max_retrieve_top_k ?? null,
);

const isValidTopK = (value: number | null) =>
  value === null ||
  (Number.isInteger(value) &&
    value > 0 &&
    (maxRetrieveTopK.value === null || value <= maxRetrieveTopK.value));
const topKRules = [
  (value: number | null) =>
    isValidTopK(value) ||
    t("validation.topKRange", { max: maxRetrieveTopK.value ?? "-" }),
];

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

const traceStageDefinitions: Array<{
  key: TraceStageKey;
  icon: string;
}> = [
  { key: "dense", icon: "mdi-vector-point" },
  { key: "sparse", icon: "mdi-format-list-bulleted" },
  { key: "fusion", icon: "mdi-call-merge" },
  { key: "dedup", icon: "mdi-filter-variant-remove" },
  { key: "dedup_removed", icon: "mdi-close-circle-outline" },
  { key: "rerank", icon: "mdi-sort-descending" },
  { key: "final", icon: "mdi-check-circle-outline" },
];

const hasTrace = computed(() => retrievalTrace.value !== null);
const traceStages = computed(() => {
  const trace = retrievalTrace.value ?? emptyTrace();
  return traceStageDefinitions.map((stage) => ({
    ...stage,
    label: t(`retrieval.traceStages.${stage.key}`),
    items: trace[stage.key] ?? [],
  }));
});

const formatScore = (score?: number | null) =>
  typeof score === "number" && Number.isFinite(score) ? score.toFixed(4) : "-";

const formatPercent = (value?: number | null) =>
  typeof value === "number" && Number.isFinite(value)
    ? `${(value * 100).toFixed(1)}%`
    : "-";

const traceItemKey = (
  stage: TraceStageKey,
  item: RetrievalTraceItem,
  index: number,
) => `${stage}-${item.chunk_id || "chunk"}-${item.rank ?? index}`;

const sourceChips = (source?: RetrievalSource | null) => {
  return buildRetrievalSourceChips(source ?? {}) as RetrievalSourceChip[];
};

const formatSourceChipLabel = (chip: RetrievalSourceChip) => {
  if (chip.label) return chip.label;
  if (chip.labelKey) return t(chip.labelKey, chip.params ?? {});
  return "";
};

const traceSourceChips = (item: RetrievalTraceItem) =>
  sourceChips({
    title_path: item.title_path,
    page_number: item.page_number,
    section_index: item.section_index,
    parent_chunk_id: item.parent_chunk_id,
  });

const traceScoreChips = (item: RetrievalTraceItem) =>
  buildTraceScoreChips(item) as Array<{
    key: string;
    labelKey: string;
    value: number;
  }>;

const performRetrieval = async () => {
  if (!query.value || query.value.trim() === "") {
    showSnackbar(t("retrieval.queryRequired"), "warning");
    return;
  }
  if (!isValidTopK(topK.value)) {
    showSnackbar(
      t("validation.topKRange", { max: maxRetrieveTopK.value ?? "-" }),
      "warning",
    );
    return;
  }

  loading.value = true;
  debugVisualize.value = null;
  retrievalTrace.value = null;

  try {
    const payload: Record<string, any> = {
      query: query.value,
      kb_ids: [props.kbId],
      debug: debugMode.value,
      trace: traceMode.value,
    };
    if (topK.value !== null) {
      payload.top_k = topK.value;
    }
    const response = await axios.post("/api/kb/retrieve", payload);

    if (response.data.status === "ok") {
      results.value = response.data.data.results || [];
      retrievalTrace.value = response.data.data.trace || null;
      hasSearched.value = true;

      if (debugMode.value && response.data.data.visualization) {
        debugVisualize.value = response.data.data.visualization;
      }

      showSnackbar(
        t("retrieval.searchSuccess", { count: results.value.length }),
      );
    } else {
      showSnackbar(
        response.data.message || t("retrieval.searchFailed"),
        "error",
      );
    }
  } catch (error) {
    console.error("Retrieval failed:", error);
    showSnackbar(t("retrieval.searchFailed"), "error");
  } finally {
    loading.value = false;
  }
};

const getScoreColor = (score?: number | null) => {
  if (typeof score !== "number" || !Number.isFinite(score)) return "default";
  if (score >= 0.8) return "success";
  if (score >= 0.6) return "info";
  if (score >= 0.4) return "warning";
  return "error";
};

const openDocument = (
  result: Pick<RetrievalResult, "doc_id" | "kb_id" | "chunk_id">,
) => {
  if (!result?.doc_id) return;
  router.push(
    createDocumentChunkRouteLocation({
      kbId: result.kb_id || props.kbId,
      docId: result.doc_id,
      chunkId: result.chunk_id,
    }),
  );
};

const openTraceDocument = (item: RetrievalTraceItem) => {
  if (!item?.doc_id) return;
  router.push(
    createDocumentChunkRouteLocation({
      kbId: item.kb_id || props.kbId,
      docId: item.doc_id,
      chunkId: item.chunk_id || "",
    }),
  );
};

onMounted(() => {
  loadCapabilities().then((loadedCapabilities) => {
    if (topK.value === null) {
      topK.value = loadedCapabilities?.defaults?.top_m_final ?? null;
    }
  });
});
</script>

<style scoped>
.retrieval-tab {
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

.results-section {
  animation: slideUp 0.4s ease;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.content-box {
  background: rgba(var(--v-theme-surface-variant), 0.1);
  border-radius: 8px;
  padding: 16px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: "Consolas", "Monaco", "Courier New", monospace;
  line-height: 1.6;
  height: 120px;
  overflow-y: auto;
  font-size: 13px;
}

.trace-section {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding-top: 16px;
}

.trace-stage-title {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
  width: 100%;
}

.trace-list {
  display: grid;
  gap: 10px;
}

.trace-item {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: 12px;
}

.trace-item-header {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.trace-metrics {
  color: rgba(var(--v-theme-on-surface), 0.68);
  display: flex;
  flex-wrap: wrap;
  font-size: 12px;
  gap: 10px;
  margin-top: 8px;
  word-break: break-all;
}

.source-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.trace-preview {
  background: rgba(var(--v-theme-surface-variant), 0.1);
  border-radius: 6px;
  font-family: "Consolas", "Monaco", "Courier New", monospace;
  font-size: 12px;
  line-height: 1.5;
  margin-top: 8px;
  max-height: 96px;
  overflow-y: auto;
  padding: 10px;
  white-space: pre-wrap;
  word-break: break-word;
}

.trace-empty {
  color: rgba(var(--v-theme-on-surface), 0.68);
  padding: 12px 0;
}

.result-meta :deep(.v-chip) {
  cursor: pointer;
}
</style>
