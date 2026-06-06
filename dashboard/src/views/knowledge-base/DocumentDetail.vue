<template>
  <div class="document-detail-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <v-btn
        icon="mdi-arrow-left"
        variant="text"
        @click="$router.push({ name: 'NativeKBDetail', params: { kbId } })"
      />
      <div class="header-content">
        <h1 class="text-h4">{{ document.doc_name }}</h1>
        <p class="text-subtitle-1 text-medium-emphasis mt-2">
          {{ t("title") }}
        </p>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <v-progress-circular indeterminate color="primary" size="64" />
    </div>

    <v-alert v-else-if="loadError" type="error" variant="tonal" class="mb-4">
      <div class="d-flex align-center justify-space-between gap-4">
        <span>{{ loadError }}</span>
        <v-btn variant="text" color="error" @click="loadAll">
          {{ t("actions.retry") }}
        </v-btn>
      </div>
    </v-alert>

    <!-- 主内容 -->
    <div v-else class="document-content">
      <!-- 文档信息卡片 -->
      <v-card variant="outlined" class="mb-6">
        <v-card-title>{{ t("info.title") }}</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="3">
              <div class="info-item">
                <v-icon start>mdi-label</v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">
                    {{ t("info.name") }}
                  </div>
                  <div class="text-body-1">{{ document.doc_name }}</div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="2">
              <div class="info-item">
                <v-icon start :color="getFileColor(document.file_type)">
                  {{ getFileIcon(document.file_type) }}
                </v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">
                    {{ t("info.type") }}
                  </div>
                  <div class="text-body-1">{{ document.file_type || "-" }}</div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="2">
              <div class="info-item">
                <v-icon start>mdi-file-chart</v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">
                    {{ t("info.size") }}
                  </div>
                  <div class="text-body-1">
                    {{ formatFileSize(document.file_size) }}
                  </div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="2">
              <div class="info-item">
                <v-icon start>mdi-text-box</v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">
                    {{ t("info.chunkCount") }}
                  </div>
                  <div class="text-body-1">{{ document.chunk_count || 0 }}</div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="3">
              <div class="info-item">
                <v-icon start>mdi-calendar</v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">
                    {{ t("info.createdAt") }}
                  </div>
                  <div class="text-body-1">
                    {{ formatDate(document.created_at) }}
                  </div>
                </div>
              </div>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <v-card variant="outlined" class="mb-6">
        <v-card-title>{{ t("processing.title") }}</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="3">
              <div class="info-item">
                <v-icon start :color="getDocumentStatusColor(document.status)">
                  {{ getDocumentStatusIcon(document.status) }}
                </v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">
                    {{ t("processing.status") }}
                  </div>
                  <v-chip
                    size="small"
                    variant="tonal"
                    :color="getDocumentStatusColor(document.status)"
                  >
                    {{ getDocumentStatusText(document.status) }}
                  </v-chip>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="3">
              <div class="info-item">
                <v-icon start>mdi-source-branch</v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">
                    {{ t("processing.sourceType") }}
                  </div>
                  <div class="text-body-1">
                    {{ getSourceTypeText(document.source_type) }}
                  </div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="3">
              <div class="info-item">
                <v-icon start>mdi-counter</v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">
                    {{ t("processing.version") }}
                  </div>
                  <div class="text-body-1">
                    {{ document.version || 1 }}
                  </div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="3">
              <div class="info-item">
                <v-icon start>mdi-calendar-check</v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">
                    {{ t("processing.indexedAt") }}
                  </div>
                  <div class="text-body-1">
                    {{ formatDate(document.indexed_at) }}
                  </div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="6">
              <div class="info-item">
                <v-icon start>mdi-link-variant</v-icon>
                <div class="metadata-value">
                  <div class="text-caption text-medium-emphasis">
                    {{ t("processing.sourceUri") }}
                  </div>
                  <div class="text-body-2 metadata-text">
                    {{ document.source_uri || "-" }}
                  </div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="6">
              <div class="info-item">
                <v-icon start>mdi-fingerprint</v-icon>
                <div class="metadata-value">
                  <div class="text-caption text-medium-emphasis">
                    {{ t("processing.contentHash") }}
                  </div>
                  <div class="text-body-2 metadata-text">
                    {{ document.content_hash || "-" }}
                  </div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="6">
              <div class="info-item">
                <v-icon start>mdi-file-cog-outline</v-icon>
                <div class="metadata-value">
                  <div class="text-caption text-medium-emphasis">
                    {{ t("processing.parser") }}
                  </div>
                  <div class="text-body-2">
                    {{
                      formatProcessor(
                        document.parser_name,
                        document.parser_version,
                      )
                    }}
                  </div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="6">
              <div class="info-item">
                <v-icon start>mdi-text-box-check-outline</v-icon>
                <div class="metadata-value">
                  <div class="text-caption text-medium-emphasis">
                    {{ t("processing.chunker") }}
                  </div>
                  <div class="text-body-2">
                    {{
                      formatProcessor(
                        document.chunker_name,
                        document.chunker_version,
                      )
                    }}
                  </div>
                </div>
              </div>
            </v-col>
            <v-col v-if="document.parent_doc_id" cols="12" md="6">
              <div class="info-item">
                <v-icon start>mdi-file-replace-outline</v-icon>
                <div class="metadata-value">
                  <div class="text-caption text-medium-emphasis">
                    {{ t("processing.parentDocId") }}
                  </div>
                  <div class="text-body-2 metadata-text">
                    {{ document.parent_doc_id }}
                  </div>
                </div>
              </div>
            </v-col>
          </v-row>
          <v-alert
            v-if="document.status === 'failed'"
            type="error"
            variant="tonal"
            class="mt-4"
          >
            <div
              class="d-flex align-center justify-space-between flex-wrap ga-4"
            >
              <div class="metadata-value">
                <div class="text-subtitle-2">
                  {{ document.error_stage || t("processing.unknownStage") }}
                </div>
                <div class="text-body-2 mt-1">
                  {{ document.error_message || t("processing.noErrorMessage") }}
                </div>
                <v-progress-linear
                  v-if="document.rebuilding"
                  :model-value="getRebuildPercentage(document)"
                  color="error"
                  height="4"
                  rounded
                  striped
                  class="mt-3"
                />
              </div>
              <v-btn
                v-if="supportsDocumentRebuild"
                class="flex-shrink-0"
                color="error"
                variant="tonal"
                prepend-icon="mdi-refresh"
                :loading="isDocumentRebuildBusy"
                :disabled="isDocumentRebuildBusy || !document.doc_id"
                @click="retryDocumentRebuild"
              >
                {{ t("actions.retryRebuild") }}
              </v-btn>
            </div>
          </v-alert>
        </v-card-text>
      </v-card>

      <!-- 分块列表 -->
      <v-card variant="outlined">
        <v-card-title class="chunk-card-title pa-4">
          <div class="chunk-card-title-main">
            <span>{{ t("chunks.title") }}</span>
            <v-chip size="small" variant="tonal">
              {{
                hasChunkSearch
                  ? t("chunks.filteredTotal", {
                      filtered: totalChunks,
                      total: displayDocumentChunkCount,
                    })
                  : t("chunks.total", { count: displayDocumentChunkCount })
              }}
            </v-chip>
          </div>
          <v-text-field
            v-model="searchQuery"
            class="chunk-search"
            prepend-inner-icon="mdi-magnify"
            :placeholder="t('chunks.searchPlaceholder')"
            variant="outlined"
            density="compact"
            hide-details
            clearable
          />
        </v-card-title>

        <v-card-text class="pa-0">
          <div class="chunks-table-scroller">
            <v-data-table
              class="chunks-table"
              :headers="headers"
              :items="chunks"
              :loading="loadingChunks"
              :items-per-page="pageSize"
              hide-default-footer
            >
              <template #item.chunk_index="{ item }">
                <v-chip
                  class="chunk-index-chip"
                  size="small"
                  variant="tonal"
                  color="primary"
                >
                  #{{ item.chunk_index + 1 }}
                </v-chip>
              </template>

              <template #item.content="{ item }">
                <div class="chunk-content-preview" :title="item.content">
                  {{ item.content }}
                </div>
              </template>

              <template #item.title_path="{ item }">
                <span class="chunk-title-path text-caption">
                  {{ formatTitlePath(item.title_path) }}
                </span>
              </template>

              <template #item.char_count="{ item }">
                <v-chip class="chunk-count-chip" size="small" variant="outlined">
                  {{ t("chunks.charCountValue", { count: item.char_count }) }}
                </v-chip>
              </template>

              <template #item.token_count_estimate="{ item }">
                <v-chip class="chunk-count-chip" size="small" variant="outlined">
                  {{ formatTokenEstimate(item.token_count_estimate) }}
                </v-chip>
              </template>

              <template #item.offset="{ item }">
                <span class="chunk-offset text-caption">
                  {{ formatChunkOffset(item) }}
                </span>
              </template>

              <template #item.content_hash="{ item }">
                <span
                  class="chunk-hash text-caption"
                  :title="item.content_hash || '-'"
                >
                  {{ formatShortHash(item.content_hash) }}
                </span>
              </template>

              <template #item.actions="{ item }">
                <div class="chunk-actions">
                  <v-btn
                    icon="mdi-eye"
                    variant="text"
                    size="small"
                    color="info"
                    @click="viewChunk(item)"
                  />
                  <v-btn
                    icon="mdi-delete"
                    variant="text"
                    size="small"
                    color="error"
                    @click="deleteChunk(item)"
                  />
                </div>
              </template>

              <template #no-data>
                <div class="text-center py-8">
                  <v-icon size="64" color="grey-lighten-2"
                    >mdi-text-box-outline</v-icon
                  >
                  <p class="mt-4 text-medium-emphasis">
                    {{ t("chunks.empty") }}
                  </p>
                </div>
              </template>
            </v-data-table>
          </div>

          <!-- 自定义分页器 -->
          <div
            v-if="totalChunks > 0"
            class="chunk-pagination-bar pa-4"
          >
            <div class="text-caption text-medium-emphasis">
              {{
                t("chunks.showingRange", {
                  start: (page - 1) * pageSize + 1,
                  end: Math.min(page * pageSize, totalChunks),
                  total: totalChunks,
                })
              }}
            </div>
            <div class="chunk-pagination-controls">
              <v-select
                v-model="pageSize"
                :items="chunkPageSizeOptions"
                density="compact"
                variant="outlined"
                hide-details
                style="width: 100px"
                @update:model-value="handlePageSizeChange"
              />
              <v-pagination
                v-model="page"
                :length="Math.ceil(totalChunks / pageSize)"
                :total-visible="5"
                @update:model-value="handlePageChange"
              />
            </div>
          </div>
        </v-card-text>
      </v-card>
    </div>

    <!-- 查看分块对话框 -->
    <v-dialog
      v-model="showViewDialog"
      max-width="960px"
      width="calc(100vw - 32px)"
      scrollable
    >
      <v-card class="chunk-dialog-card">
        <v-card-title class="pa-4 d-flex align-center">
          <span>{{ t("view.title") }}</span>
          <v-spacer />
          <v-btn
            icon="mdi-close"
            variant="text"
            @click="showViewDialog = false"
          />
        </v-card-title>
        <v-card-text class="pa-5 pa-md-6">
          <div class="chunk-meta-grid">
            <div
              v-for="field in selectedChunkMetadata"
              :key="field.key"
              class="chunk-meta-item"
              :class="{ 'chunk-meta-item--wide': field.wide }"
            >
              <v-icon class="chunk-meta-icon" size="20">
                {{ field.icon }}
              </v-icon>
              <div class="chunk-meta-body">
                <div class="chunk-meta-label">{{ field.label }}</div>
                <div
                  class="chunk-meta-value"
                  :class="{ 'is-monospace': field.monospace }"
                >
                  {{ field.value }}
                </div>
              </div>
            </div>
          </div>

          <div class="text-caption text-medium-emphasis mb-2">
            {{ t("view.content") }}
          </div>
          <div class="chunk-content-view">
            {{ selectedChunk?.content }}
          </div>

          <div class="d-flex align-center mt-6 mb-2">
            <div class="text-caption text-medium-emphasis">
              {{ t("view.context") }}
            </div>
            <v-spacer />
            <v-progress-circular
              v-if="loadingContext"
              indeterminate
              size="18"
              width="2"
            />
          </div>
          <div class="chunk-context-list">
            <div
              v-for="slot in contextSlots"
              :key="slot.key"
              class="chunk-context-item"
              :class="{ active: slot.key === 'current' }"
            >
              <div class="chunk-context-header">
                <v-chip
                  size="x-small"
                  variant="tonal"
                  :color="slot.key === 'current' ? 'primary' : 'default'"
                >
                  {{ slot.label }}
                </v-chip>
                <span class="text-caption text-medium-emphasis">
                  {{ formatContextMeta(slot.chunk) }}
                </span>
              </div>
              <div class="chunk-context-content">
                {{ slot.chunk?.content || t("view.contextMissing") }}
              </div>
            </div>
          </div>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="showViewDialog = false">
            {{ t("view.close") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import axios from "axios";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";
import { useKnowledgeBaseCapabilities } from "./capabilities";
import {
  applyActiveRebuildState,
  applyDocumentTaskProgress,
  canRebuildDocument,
  clearDocumentTaskState,
  DEFAULT_CHUNK_PAGE_SIZE,
  getFocusedChunkId,
  getKnowledgeBasePaginationConfig,
  isKnowledgeBaseFeatureEnabled,
  markDocumentRebuildStarted,
  removeFocusedChunkQuery,
} from "./knowledgeBaseUi.mjs";

const { tm: t } = useModuleI18n("features/knowledge-base/document");
const { locale } = useI18n();
const route = useRoute();
const router = useRouter();
const { capabilities, loadCapabilities } = useKnowledgeBaseCapabilities();

const confirmDialog = useConfirmDialog();

const kbId = computed(() => String(route.params.kbId || ""));
const docId = computed(() => String(route.params.docId || ""));

// 状态
const loading = ref(true);
const loadingChunks = ref(false);
const rebuilding = ref(false);
const document = ref<any>({});
const chunks = ref<any[]>([]);
const searchQuery = ref("");
const showViewDialog = ref(false);
const selectedChunk = ref<any>(null);
const chunkContext = ref<any>(null);
const loadingContext = ref(false);
const loadError = ref("");
const focusedChunkId = computed(() => getFocusedChunkId(route.query));

// 分页状态
const page = ref(1);
const pageSize = ref(DEFAULT_CHUNK_PAGE_SIZE);
const totalChunks = ref(0);
const documentChunkCount = ref<number | null>(null);
let searchTimer: number | undefined;
let rebuildPollingInterval: number | undefined;
const paginationConfig = computed(() =>
  getKnowledgeBasePaginationConfig(capabilities.value),
);
const chunkPageSizeOptions = computed(
  () => paginationConfig.value.chunkPageSizeOptions,
);
const supportsDocumentRebuild = computed(() =>
  isKnowledgeBaseFeatureEnabled(capabilities.value, "document_rebuild"),
);
const isDocumentRebuildBusy = computed(
  () => rebuilding.value || Boolean(document.value?.rebuilding),
);

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

// 表格列
const headers = computed(() => [
  {
    title: t("chunks.index"),
    key: "chunk_index",
    width: 88,
    minWidth: "88px",
  },
  {
    title: t("chunks.content"),
    key: "content",
    sortable: false,
    width: 390,
    minWidth: "320px",
  },
  {
    title: t("chunks.titlePath"),
    key: "title_path",
    sortable: false,
    width: 220,
    minWidth: "180px",
  },
  { title: t("chunks.charCount"), key: "char_count", width: 120 },
  {
    title: t("chunks.tokenEstimate"),
    key: "token_count_estimate",
    width: 130,
  },
  { title: t("chunks.offset"), key: "offset", sortable: false, width: 112 },
  {
    title: t("chunks.contentHash"),
    key: "content_hash",
    sortable: false,
    width: 140,
  },
  {
    title: t("chunks.actions"),
    key: "actions",
    sortable: false,
    align: "end" as const,
    width: 96,
  },
]);

const contextSlots = computed(() => [
  {
    key: "previous",
    label: t("view.previous"),
    chunk: chunkContext.value?.previous,
  },
  {
    key: "current",
    label: t("view.current"),
    chunk: chunkContext.value?.current || selectedChunk.value,
  },
  {
    key: "next",
    label: t("view.next"),
    chunk: chunkContext.value?.next,
  },
]);
const hasChunkSearch = computed(() => searchQuery.value.trim().length > 0);
const displayDocumentChunkCount = computed(
  () =>
    documentChunkCount.value ?? document.value.chunk_count ?? totalChunks.value,
);
const selectedChunkMetadata = computed(() => [
  {
    key: "index",
    icon: "mdi-pound",
    label: t("view.index"),
    value: `#${Number(selectedChunk.value?.chunk_index ?? 0) + 1}`,
  },
  {
    key: "char_count",
    icon: "mdi-text",
    label: t("view.charCount"),
    value: t("chunks.charCountValue", {
      count: selectedChunk.value?.char_count ?? 0,
    }),
  },
  {
    key: "token_count_estimate",
    icon: "mdi-counter",
    label: t("view.tokenEstimate"),
    value: formatTokenEstimate(selectedChunk.value?.token_count_estimate),
  },
  {
    key: "title_path",
    icon: "mdi-format-title",
    label: t("view.titlePath"),
    value: formatTitlePath(selectedChunk.value?.title_path),
    wide: true,
  },
  {
    key: "section_index",
    icon: "mdi-file-tree-outline",
    label: t("view.section"),
    value: formatOneBasedIndex(selectedChunk.value?.section_index),
  },
  {
    key: "page_number",
    icon: "mdi-file-document-outline",
    label: t("view.pageNumber"),
    value: formatNullableValue(selectedChunk.value?.page_number),
  },
  {
    key: "offset",
    icon: "mdi-map-marker-distance",
    label: t("view.offset"),
    value: formatChunkOffset(selectedChunk.value),
    monospace: true,
  },
  {
    key: "content_hash",
    icon: "mdi-fingerprint",
    label: t("view.contentHash"),
    value: selectedChunk.value?.content_hash || "-",
    monospace: true,
    wide: true,
  },
  {
    key: "adjacent_chunks",
    icon: "mdi-arrow-left-right",
    label: t("view.adjacentChunks"),
    value: [
      t("view.previousChunk", {
        id: selectedChunk.value?.previous_chunk_id || "-",
      }),
      t("view.nextChunk", {
        id: selectedChunk.value?.next_chunk_id || "-",
      }),
    ].join("\n"),
    monospace: true,
    wide: true,
  },
  {
    key: "parent_chunk_id",
    icon: "mdi-file-link-outline",
    label: t("view.parentChunk"),
    value: selectedChunk.value?.parent_chunk_id || "-",
    monospace: true,
    wide: true,
  },
  {
    key: "chunk_id",
    icon: "mdi-key",
    label: t("view.vecDocId"),
    value: selectedChunk.value?.chunk_id || "-",
    monospace: true,
    wide: true,
  },
]);

// 加载文档详情
const loadDocument = async () => {
  loading.value = true;
  loadError.value = "";
  try {
    const response = await axios.get("/api/kb/document/get", {
      params: { doc_id: docId.value, kb_id: kbId.value },
    });
    if (response.data.status === "ok") {
      document.value = applyActiveRebuildState(
        [response.data.data],
        [document.value],
      )[0];
      documentChunkCount.value = response.data.data.chunk_count ?? null;
    } else {
      loadError.value =
        response.data.message || t("messages.loadDocumentFailed");
      showSnackbar(loadError.value, "error");
    }
  } catch (error) {
    console.error("Failed to load document:", error);
    loadError.value = t("messages.loadDocumentFailed");
    showSnackbar(loadError.value, "error");
  } finally {
    loading.value = false;
  }
};

// 加载分块列表
const loadChunks = async () => {
  loadingChunks.value = true;
  try {
    const response = await axios.get("/api/kb/chunk/list", {
      params: {
        doc_id: docId.value,
        kb_id: kbId.value,
        page: page.value,
        page_size: pageSize.value,
        search: searchQuery.value || undefined,
      },
    });
    if (response.data.status === "ok") {
      chunks.value = response.data.data.items || [];
      totalChunks.value =
        response.data.data.filtered_total ?? response.data.data.total ?? 0;
      documentChunkCount.value =
        response.data.data.document_chunk_count ??
        response.data.data.total ??
        documentChunkCount.value;
    } else {
      showSnackbar(
        response.data.message || t("messages.loadChunksFailed"),
        "error",
      );
    }
  } catch (error) {
    console.error("Failed to load chunks:", error);
    showSnackbar(t("messages.loadChunksFailed"), "error");
  } finally {
    loadingChunks.value = false;
  }
};

// 处理分页变化
const handlePageChange = (newPage: number) => {
  page.value = newPage;
  loadChunks();
};

const handlePageSizeChange = (newPageSize: number) => {
  pageSize.value = newPageSize;
  page.value = 1;
  loadChunks();
};

// 查看分块
const viewChunk = (chunk: any) => {
  selectedChunk.value = chunk;
  chunkContext.value = null;
  showViewDialog.value = true;
  loadChunkContext(chunk);
};

const loadChunkContext = async (chunk: any) => {
  if (!chunk?.chunk_id) return;
  loadingContext.value = true;
  try {
    const response = await axios.get("/api/kb/chunk/context", {
      params: {
        chunk_id: chunk.chunk_id,
        doc_id: docId.value,
        kb_id: kbId.value,
      },
    });
    if (response.data.status === "ok") {
      chunkContext.value = response.data.data;
    } else {
      showSnackbar(
        response.data.message || t("messages.loadChunkContextFailed"),
        "error",
      );
    }
  } catch (error) {
    console.error("Failed to load chunk context:", error);
    showSnackbar(t("messages.loadChunkContextFailed"), "error");
  } finally {
    loadingContext.value = false;
  }
};

const getRebuildPercentage = (doc: any) => {
  const current = Number(doc?.uploadProgress?.current ?? 0);
  const total = Number(doc?.uploadProgress?.total ?? 100);
  if (!Number.isFinite(total) || total <= 0) {
    return 0;
  }
  return (current / total) * 100;
};

const stopRebuildProgressPolling = () => {
  if (rebuildPollingInterval !== undefined) {
    window.clearInterval(rebuildPollingInterval);
    rebuildPollingInterval = undefined;
  }
};

const refreshAfterRebuildTask = async (taskId: string) => {
  document.value =
    clearDocumentTaskState([document.value], taskId)[0] || document.value;
  await loadDocument();
  await loadChunks();
};

const startRebuildProgressPolling = (taskId: string) => {
  stopRebuildProgressPolling();
  rebuildPollingInterval = window.setInterval(async () => {
    try {
      const response = await axios.get("/api/kb/document/upload/progress", {
        params: { task_id: taskId },
      });
      if (response.data.status !== "ok") {
        stopRebuildProgressPolling();
        await refreshAfterRebuildTask(taskId);
        return;
      }

      const task = response.data.data;
      if (task.status === "processing" && task.progress) {
        document.value =
          applyDocumentTaskProgress(
            [document.value],
            taskId,
            task.progress,
          )[0] || document.value;
        return;
      }

      if (task.status === "completed") {
        stopRebuildProgressPolling();
        showSnackbar(t("messages.rebuildCompleted"));
        await refreshAfterRebuildTask(taskId);
        return;
      }

      if (task.status === "failed") {
        stopRebuildProgressPolling();
        const reason = task.error || t("messages.rebuildFailed");
        showSnackbar(
          t("messages.rebuildFailedWithReason", { reason }),
          "error",
        );
        await refreshAfterRebuildTask(taskId);
      }
    } catch (error) {
      console.error("Failed to poll document rebuild progress:", error);
    }
  }, 1000);
};

const retryDocumentRebuild = async () => {
  if (
    !canRebuildDocument(document.value, {
      supportsDocumentRebuild: supportsDocumentRebuild.value,
    })
  ) {
    return;
  }
  if (
    !(await askForConfirmation(t("actions.retryRebuildConfirm"), confirmDialog))
  ) {
    return;
  }

  rebuilding.value = true;
  try {
    const response = await axios.post("/api/kb/document/rebuild", {
      doc_id: document.value.doc_id,
      kb_id: kbId.value,
      background: true,
    });
    if (response.data.status === "ok") {
      const taskId = response.data.data?.task_id;
      if (taskId) {
        document.value =
          markDocumentRebuildStarted(
            [document.value],
            document.value.doc_id,
            taskId,
          )[0] || document.value;
        showSnackbar(t("messages.rebuildStarted"), "info");
        startRebuildProgressPolling(taskId);
      } else {
        showSnackbar(t("messages.rebuildCompleted"));
        await loadDocument();
        await loadChunks();
      }
    } else {
      showSnackbar(
        response.data.message || t("messages.rebuildFailed"),
        "error",
      );
    }
  } catch (error) {
    console.error("Failed to retry document rebuild:", error);
    showSnackbar(t("messages.rebuildFailed"), "error");
  } finally {
    rebuilding.value = false;
  }
};

const clearFocusedChunk = () => {
  if (!focusedChunkId.value) return;
  router.replace({ query: removeFocusedChunkQuery(route.query) });
};

const focusChunkFromQuery = async () => {
  if (!focusedChunkId.value || loading.value || loadError.value) return;

  loadingContext.value = true;
  try {
    const response = await axios.get("/api/kb/chunk/context", {
      params: {
        chunk_id: focusedChunkId.value,
        doc_id: docId.value,
        kb_id: kbId.value,
      },
    });
    if (response.data.status === "ok") {
      chunkContext.value = response.data.data;
      selectedChunk.value = response.data.data?.current || null;
      if (!selectedChunk.value) {
        showSnackbar(t("messages.focusChunkNotFound"), "warning");
        clearFocusedChunk();
        return;
      }
      showViewDialog.value = true;
      await nextTick();
      showSnackbar(t("messages.focusChunkLoaded"));
    } else {
      showSnackbar(
        response.data.message || t("messages.focusChunkFailed"),
        "error",
      );
      clearFocusedChunk();
    }
  } catch (error) {
    console.error("Failed to focus chunk:", error);
    showSnackbar(t("messages.focusChunkFailed"), "error");
    clearFocusedChunk();
  } finally {
    loadingContext.value = false;
  }
};

// 删除分块
const deleteChunk = async (chunk: any) => {
  if (!(await askForConfirmation(t("chunks.deleteConfirm"), confirmDialog)))
    return;
  try {
    const response = await axios.post("/api/kb/chunk/delete", {
      chunk_id: chunk.chunk_id,
      doc_id: docId.value,
      kb_id: kbId.value,
    });
    if (response.data.status === "ok") {
      showSnackbar(t("chunks.deleteSuccess"));
      const nextTotal = Math.max(totalChunks.value - 1, 0);
      const lastPage = Math.max(Math.ceil(nextTotal / pageSize.value), 1);
      if (page.value > lastPage) {
        page.value = lastPage;
      }
      await loadDocument();
      await loadChunks();
    } else {
      showSnackbar(response.data.message || t("chunks.deleteFailed"), "error");
    }
  } catch (error) {
    console.error("Failed to delete chunk:", error);
    showSnackbar(t("chunks.deleteFailed"), "error");
  }
};

// 工具函数
const getFileIcon = (fileType: string) => {
  const type = fileType?.toLowerCase() || "";
  if (type.includes("pdf")) return "mdi-file-pdf-box";
  if (type.includes("epub")) return "mdi-book-open-page-variant";
  if (type.includes("md")) return "mdi-language-markdown";
  if (type.includes("txt")) return "mdi-file-document-outline";
  return "mdi-file";
};

const getFileColor = (fileType: string) => {
  const type = fileType?.toLowerCase() || "";
  if (type.includes("pdf")) return "error";
  if (type.includes("epub")) return "warning";
  if (type.includes("md")) return "info";
  if (type.includes("txt")) return "success";
  return "grey";
};

const getDocumentStatusText = (status?: string) => {
  const normalizedStatus = status || "ready";
  const statusMap: Record<string, string> = {
    pending: t("processing.statuses.pending"),
    parsing: t("processing.statuses.parsing"),
    chunking: t("processing.statuses.chunking"),
    embedding: t("processing.statuses.embedding"),
    ready: t("processing.statuses.ready"),
    failed: t("processing.statuses.failed"),
  };
  return statusMap[normalizedStatus] || normalizedStatus;
};

const getDocumentStatusColor = (status?: string) => {
  switch (status) {
    case "failed":
      return "error";
    case "pending":
      return "grey";
    case "parsing":
    case "chunking":
    case "embedding":
      return "warning";
    case "ready":
    default:
      return "success";
  }
};

const getDocumentStatusIcon = (status?: string) => {
  switch (status) {
    case "failed":
      return "mdi-alert-circle-outline";
    case "pending":
      return "mdi-clock-outline";
    case "parsing":
    case "chunking":
    case "embedding":
      return "mdi-progress-clock";
    case "ready":
    default:
      return "mdi-check-circle-outline";
  }
};

const getSourceTypeText = (sourceType?: string) => {
  const normalizedSourceType = sourceType || "file";
  const sourceTypeMap: Record<string, string> = {
    file: t("processing.sourceTypes.file"),
    url: t("processing.sourceTypes.url"),
    import: t("processing.sourceTypes.import"),
    api: t("processing.sourceTypes.api"),
  };
  return sourceTypeMap[normalizedSourceType] || normalizedSourceType;
};

const formatProcessor = (name?: string, version?: string) => {
  if (!name) return "-";
  return version ? `${name} v${version}` : name;
};

const formatChunkOffset = (chunk?: any) => {
  if (
    chunk?.start_offset === undefined ||
    chunk?.start_offset === null ||
    chunk?.end_offset === undefined ||
    chunk?.end_offset === null
  ) {
    return "-";
  }
  return `${chunk.start_offset} - ${chunk.end_offset}`;
};

const formatContextMeta = (chunk?: any) => {
  if (!chunk) return "-";
  return `#${(chunk.chunk_index || 0) + 1} | ${formatTitlePath(
    chunk.title_path,
  )} | ${formatChunkOffset(chunk)}`;
};

const formatTitlePath = (titlePath?: string[] | null) => {
  if (!Array.isArray(titlePath) || titlePath.length === 0) return "-";
  return titlePath.filter(Boolean).join(" / ") || "-";
};

const formatNullableValue = (value?: number | null) => {
  if (value === undefined || value === null) return "-";
  return String(value);
};

const formatOneBasedIndex = (value?: number | null) => {
  if (value === undefined || value === null) return "-";
  return String(value + 1);
};

const formatTokenEstimate = (value?: number | null) => {
  if (value === undefined || value === null) return "-";
  return t("chunks.tokenEstimateValue", { count: value });
};

const formatShortHash = (hash?: string) => {
  if (!hash) return "-";
  return hash.length > 12 ? `${hash.slice(0, 12)}...` : hash;
};

const formatFileSize = (bytes: number) => {
  if (!bytes) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  return `${size.toFixed(2)} ${units[unitIndex]}`;
};

const formatDate = (dateStr: string) => {
  if (!dateStr) return "-";
  return new Date(dateStr).toLocaleString(locale.value, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

onMounted(() => {
  loadCapabilities().then((loadedCapabilities) => {
    pageSize.value =
      getKnowledgeBasePaginationConfig(loadedCapabilities).defaultChunkPageSize;
    loadAll();
  });
});

watch(focusedChunkId, () => {
  focusChunkFromQuery();
});

watch([kbId, docId], () => {
  stopRebuildProgressPolling();
  showViewDialog.value = false;
  selectedChunk.value = null;
  chunkContext.value = null;
  page.value = 1;
  loadAll();
});

watch(searchQuery, () => {
  page.value = 1;
  if (searchTimer !== undefined) {
    window.clearTimeout(searchTimer);
  }
  searchTimer = window.setTimeout(() => {
    loadChunks();
  }, 250);
});

onUnmounted(() => {
  if (searchTimer !== undefined) {
    window.clearTimeout(searchTimer);
  }
  stopRebuildProgressPolling();
});

const loadAll = async () => {
  await loadDocument();
  if (!loadError.value) {
    await loadChunks();
    await focusChunkFromQuery();
  }
};
</script>

<style scoped>
.document-detail-page {
  padding: 0;
  width: 100%;
  animation: fadeIn 0.3s ease;
}

.document-detail-page :deep(.v-card--variant-outlined) {
  background: rgb(var(--v-theme-surface));
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.page-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 24px;
}

.header-content {
  flex: 1;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}

.document-content {
  animation: slideUp 0.4s ease;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.info-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.metadata-value {
  min-width: 0;
  flex: 1;
}

.metadata-text {
  overflow-wrap: anywhere;
}

.chunk-card-title {
  align-items: center;
  display: flex;
  gap: 16px;
  justify-content: space-between;
}

.chunk-card-title-main {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.chunk-search {
  flex: 0 1 320px;
  max-width: 320px;
}

.chunks-table-scroller {
  overflow-x: auto;
  width: 100%;
}

.chunks-table {
  min-width: 1180px;
}

.chunks-table :deep(table) {
  min-width: 1180px;
  table-layout: fixed;
}

.chunks-table :deep(th) {
  line-height: 1.25;
  white-space: normal;
}

.chunks-table :deep(td) {
  vertical-align: middle;
}

.chunk-index-chip,
.chunk-count-chip {
  white-space: nowrap;
}

.chunk-content-preview {
  display: -webkit-box;
  font-size: 0.875rem;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: normal;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.chunk-title-path {
  color: rgba(var(--v-theme-on-surface), 0.7);
  display: -webkit-box;
  line-height: 1.4;
  overflow: hidden;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.chunk-offset,
.chunk-hash {
  display: block;
  font-family: "Consolas", "Monaco", monospace;
  white-space: nowrap;
}

.chunk-hash {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chunk-actions {
  align-items: center;
  display: flex;
  gap: 2px;
  justify-content: flex-end;
}

.chunk-pagination-bar {
  align-items: center;
  display: flex;
  gap: 16px;
  justify-content: space-between;
}

.chunk-pagination-controls {
  align-items: center;
  display: flex;
  gap: 8px;
}

.chunk-dialog-card {
  max-height: calc(100vh - 64px);
}

.chunk-meta-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-bottom: 24px;
}

.chunk-meta-item {
  align-items: flex-start;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  display: flex;
  gap: 12px;
  min-width: 0;
  padding: 12px;
}

.chunk-meta-item--wide {
  grid-column: 1 / -1;
}

.chunk-meta-icon {
  color: rgba(var(--v-theme-on-surface), 0.62);
  flex: 0 0 auto;
  margin-top: 2px;
}

.chunk-meta-body {
  flex: 1;
  min-width: 0;
}

.chunk-meta-label {
  color: rgba(var(--v-theme-on-surface), 0.68);
  font-size: 0.75rem;
  line-height: 1.35;
}

.chunk-meta-value {
  font-size: 0.875rem;
  line-height: 1.45;
  margin-top: 2px;
  overflow-wrap: anywhere;
  white-space: pre-line;
}

.chunk-meta-value.is-monospace {
  font-family: "Consolas", "Monaco", monospace;
}

.chunk-content-view {
  padding: 16px;
  background: rgba(var(--v-theme-surface-variant), 0.3);
  border-radius: 8px;
  max-height: 300px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  font-family: "Consolas", "Monaco", monospace;
}

.chunk-context-list {
  display: grid;
  gap: 12px;
}

.chunk-context-item {
  padding: 12px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
}

.chunk-context-item.active {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.04);
}

.chunk-context-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.chunk-context-content {
  max-height: 180px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.875rem;
  line-height: 1.6;
}

.gap-2 {
  gap: 8px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .chunk-card-title,
  .chunk-pagination-bar,
  .chunk-pagination-controls {
    align-items: stretch;
    flex-direction: column;
  }

  .chunk-search {
    flex-basis: auto;
    max-width: none;
    width: 100%;
  }

  .chunk-meta-grid {
    grid-template-columns: 1fr;
  }
}
</style>
