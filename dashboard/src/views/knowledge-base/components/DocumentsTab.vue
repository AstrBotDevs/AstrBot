<template>
  <div class="documents-tab">
    <!-- 操作栏 -->
    <div class="action-bar mb-4">
      <v-btn
        prepend-icon="mdi-upload"
        color="primary"
        variant="outlined"
        @click="showUploadDialog = true"
      >
        {{ t("documents.upload") }}
      </v-btn>
      <v-btn
        v-if="supportsBatchDelete"
        prepend-icon="mdi-delete-sweep"
        color="error"
        variant="tonal"
        :disabled="!batchDeleteState.hasSelection || batchDeleting"
        :loading="batchDeleting"
        @click="confirmBatchDelete"
      >
        {{
          t("documents.batchDelete", { count: batchDeleteState.selectedCount })
        }}
      </v-btn>
      <v-btn
        v-if="supportsBatchRebuild"
        prepend-icon="mdi-refresh"
        color="primary"
        variant="tonal"
        :disabled="!batchRebuildState.hasSelection || batchRebuilding"
        :loading="batchRebuilding"
        @click="confirmBatchRebuild"
      >
        {{
          t("documents.batchRebuild", {
            count: batchRebuildState.selectedCount,
          })
        }}
      </v-btn>
      <v-text-field
        v-model="searchQuery"
        prepend-inner-icon="mdi-magnify"
        :placeholder="t('documents.searchPlaceholder')"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 300px"
      />
      <v-select
        v-model="selectedStatus"
        :items="statusFilterOptions"
        :label="t('documents.statusFilter')"
        class="document-filter-select"
        variant="outlined"
        density="compact"
        hide-details
      />
      <v-select
        v-model="selectedSourceType"
        :items="sourceTypeFilterOptions"
        :label="t('documents.sourceFilter')"
        class="document-filter-select"
        variant="outlined"
        density="compact"
        hide-details
      />
      <span
        v-if="hasActiveDocumentFilters"
        class="text-caption text-medium-emphasis documents-filter-count"
      >
        {{
          t("documents.filteredCount", {
            filtered: totalDocuments,
            total: documentCount,
          })
        }}
      </span>
    </div>

    <!-- 文档列表 -->
    <v-card variant="outlined">
      <v-data-table-server
        :headers="headers"
        :items="documents"
        :loading="loading"
        :items-length="totalDocuments"
        :items-per-page-options="pageSizeOptions"
        v-model="selectedDocumentRows"
        v-model:items-per-page="pageSize"
        v-model:page="page"
        item-value="doc_id"
        item-selectable="selectable"
        :show-select="supportsBatchDelete || supportsBatchRebuild"
        return-object
        @update:options="loadDocuments"
      >
        <template #item.doc_name="{ item }">
          <div class="d-flex align-center gap-2">
            <v-icon :color="getFileColor(item.file_type)" class="mr-2">
              {{ getFileIcon(item.file_type) }}
            </v-icon>
            <div class="flex-grow-1" style="padding: 4px 0px">
              <span
                class="font-weight-medium doc-name"
                :title="item.doc_name"
                >{{ item.doc_name }}</span
              >
              <!-- 上传进度 -->
              <div v-if="item.uploading || item.rebuilding" class="mt-1">
                <div class="text-caption text-medium-emphasis mb-1">
                  {{ getStageText(item.uploadProgress?.stage || "waiting") }}
                  <span
                    v-if="
                      item.uploadProgress &&
                      item.uploadProgress.current !== undefined
                    "
                  >
                    ({{ item.uploadProgress.current }} /
                    {{ item.uploadProgress.total }})
                  </span>
                </div>
                <v-progress-linear
                  :model-value="getUploadPercentage(item)"
                  color="primary"
                  height="4"
                  rounded
                  striped
                />
              </div>
              <div
                v-else-if="item.status === 'failed'"
                class="doc-error text-caption mt-1"
                :title="getFailureSummary(item)"
              >
                {{ getFailureSummary(item) }}
              </div>
            </div>
          </div>
        </template>

        <template #item.status="{ item }">
          <v-chip
            size="small"
            variant="tonal"
            :color="getDocumentStatusColor(item.status)"
          >
            {{ getDocumentStatusText(item.status) }}
          </v-chip>
        </template>

        <template #item.file_size="{ item }">
          {{ formatFileSize(item.file_size) }}
        </template>

        <template #item.created_at="{ item }">
          {{ formatDate(item.created_at) }}
        </template>

        <template #item.actions="{ item }">
          <v-btn
            v-if="item.status === 'failed'"
            icon="mdi-content-copy"
            variant="text"
            size="small"
            color="warning"
            :disabled="
              item.uploading ||
              item.rebuilding ||
              rebuildingDocIds.has(item.doc_id)
            "
            :title="t('documents.copyFailure')"
            @click="copyFailureDetails(item)"
          />
          <v-btn
            v-if="item.status === 'failed' && supportsDocumentRebuild"
            icon="mdi-refresh"
            variant="text"
            size="small"
            color="primary"
            :loading="rebuildingDocIds.has(item.doc_id) || item.rebuilding"
            :disabled="!canRebuild(item)"
            :title="t('documents.rebuild')"
            @click="confirmRebuild(item)"
          />
          <v-btn
            icon="mdi-eye"
            variant="text"
            size="small"
            color="info"
            :disabled="item.uploading || item.rebuilding"
            @click="viewDocument(item)"
          />
          <v-btn
            icon="mdi-delete"
            variant="text"
            size="small"
            color="error"
            :disabled="item.uploading || item.rebuilding"
            @click="confirmDelete(item)"
          />
        </template>

        <template #no-data>
          <div class="text-center py-8">
            <v-icon size="64" color="grey-lighten-2"
              >mdi-file-document-outline</v-icon
            >
            <p class="mt-4 text-medium-emphasis">{{ t("documents.empty") }}</p>
          </div>
        </template>
      </v-data-table-server>
    </v-card>

    <!-- 上传对话框 -->
    <v-dialog
      v-model="showUploadDialog"
      max-width="650px"
      persistent
      @after-enter="initUploadSettings"
    >
      <v-card>
        <v-card-title class="pa-4 d-flex align-center">
          <span class="text-h5">{{ t("upload.title") }}</span>
          <v-spacer />
          <v-btn
            icon="mdi-close"
            variant="text"
            :disabled="uploading"
            @click="closeUploadDialog()"
          />
        </v-card-title>

        <v-tabs v-model="uploadMode" grow class="mb-4">
          <v-tab value="file">{{ t("upload.fileUpload") }}</v-tab>
          <v-tab v-if="supportsUrlImport" value="url">
            {{ t("upload.fromUrl") }}
            <v-badge
              color="warning"
              :content="t('upload.beta')"
              inline
              class="ml-2"
            />
          </v-tab>
        </v-tabs>

        <v-card-text class="pa-6 pt-2">
          <v-window v-model="uploadMode">
            <!-- 文件上传 -->
            <v-window-item value="file">
              <!-- 文件选择 -->
              <div
                class="upload-dropzone"
                :class="{ dragover: isDragging, disabled: uploading }"
                @drop.prevent="handleDrop"
                @dragover.prevent="isDragging = true"
                @dragleave="isDragging = false"
                @click="openFilePicker"
              >
                <v-icon size="64" color="primary">mdi-cloud-upload</v-icon>
                <p class="mt-4 text-h6">{{ t("upload.dropzone") }}</p>
                <p class="text-caption text-medium-emphasis mt-2">
                  {{
                    t("upload.supportedFormats", {
                      formats: supportedFormatsText,
                    })
                  }}
                </p>
                <p class="text-caption text-medium-emphasis">
                  {{ t("upload.maxSize", { size: maxFileSizeText }) }}
                </p>
                <p class="text-caption text-medium-emphasis">
                  {{ t("upload.maxFiles", { count: maxFilesPerUploadText }) }}
                </p>
                <input
                  ref="fileInput"
                  type="file"
                  multiple
                  hidden
                  :disabled="uploading"
                  :accept="fileAccept"
                  @change="handleFileSelect"
                />
              </div>

              <div v-if="selectedFiles.length > 0" class="mt-4">
                <div class="d-flex align-center justify-space-between mb-2">
                  <span class="text-subtitle-2">{{
                    t("upload.selectedFiles", { count: selectedFiles.length })
                  }}</span>
                  <v-btn
                    variant="text"
                    size="small"
                    :disabled="uploading"
                    @click="selectedFiles = []"
                    >{{ t("upload.clear") }}</v-btn
                  >
                </div>
                <div class="files-list">
                  <div
                    v-for="(file, index) in selectedFiles"
                    :key="index"
                    class="file-item pa-3 mb-2 rounded bg-surface-variant"
                  >
                    <div class="d-flex align-center justify-space-between">
                      <div class="d-flex align-center gap-2">
                        <v-icon>{{ getFileIcon(file.name) }}</v-icon>
                        <div>
                          <div class="font-weight-medium">{{ file.name }}</div>
                          <div class="text-caption">
                            {{ formatFileSize(file.size) }}
                          </div>
                        </div>
                      </div>
                      <v-btn
                        icon="mdi-close"
                        variant="text"
                        size="small"
                        :disabled="uploading"
                        @click="removeFile(index)"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </v-window-item>

            <!-- URL上传 -->
            <v-window-item value="url" class="pt-2">
              <!-- Tavily Key 快速配置 -->
              <div
                v-if="
                  tavilyConfigStatus === 'not_configured' ||
                  tavilyConfigStatus === 'error'
                "
                class="mb-4"
              >
                <v-alert
                  :type="tavilyConfigStatus === 'error' ? 'error' : 'info'"
                  variant="tonal"
                  density="compact"
                >
                  <div class="d-flex align-center justify-space-between">
                    <span>
                      {{
                        tavilyConfigStatus === "error"
                          ? t("upload.tavilyCheckFailed")
                          : t("upload.tavilyRequired")
                      }}
                    </span>
                    <v-btn
                      size="small"
                      variant="flat"
                      @click="showTavilyDialog = true"
                    >
                      {{ t("upload.configure") }}
                    </v-btn>
                  </div>
                </v-alert>
              </div>

              <v-text-field
                v-model="uploadUrl"
                :label="t('upload.urlPlaceholder')"
                variant="outlined"
                clearable
                :disabled="tavilyConfigStatus !== 'configured'"
                autofocus
                :hint="t('upload.urlHint', { supported: 'HTML' })"
                persistent-hint
              />
            </v-window-item>
          </v-window>

          <!-- 清洗设置 (仅在URL模式下显示) -->
          <div v-if="uploadMode === 'url' && supportsUrlImport" class="mt-6">
            <div class="d-flex align-center mb-4">
              <h3 class="text-h6">{{ t("upload.cleaningSettings") }}</h3>
            </div>
            <v-row>
              <v-col cols="12" sm="4">
                <v-switch
                  v-model="uploadSettings.enable_cleaning"
                  :label="t('upload.enableCleaning')"
                  color="primary"
                />
              </v-col>
              <v-col cols="12" sm="8">
                <v-select
                  v-model="uploadSettings.cleaning_provider_id"
                  :items="llmProviders"
                  item-title="id"
                  item-value="id"
                  :label="t('upload.cleaningProvider')"
                  :hint="t('upload.cleaningProviderHint')"
                  persistent-hint
                  variant="outlined"
                  density="compact"
                  :disabled="!uploadSettings.enable_cleaning"
                />
              </v-col>
            </v-row>
          </div>

          <!-- 分块设置 -->
          <div class="mt-6">
            <div class="d-flex align-center mb-4">
              <h3 class="text-h6">{{ t("upload.chunkSettings") }}</h3>
            </div>
            <v-row>
              <v-col cols="12" sm="6">
                <v-text-field
                  v-model.number="uploadSettings.chunk_size"
                  :label="t('upload.chunkSize')"
                  :hint="
                    t('upload.chunkSizeHint', {
                      value: capabilities?.defaults.chunk_size ?? '-',
                    })
                  "
                  persistent-hint
                  type="number"
                  variant="outlined"
                  density="compact"
                  :placeholder="chunkSizePlaceholder"
                  :rules="chunkSizeRules"
                />
              </v-col>
              <v-col cols="12" sm="6">
                <v-text-field
                  v-model.number="uploadSettings.chunk_overlap"
                  :label="t('upload.chunkOverlap')"
                  :hint="
                    t('upload.chunkOverlapHint', {
                      value: capabilities?.defaults.chunk_overlap ?? '-',
                    })
                  "
                  persistent-hint
                  type="number"
                  variant="outlined"
                  density="compact"
                  :placeholder="chunkOverlapPlaceholder"
                  :rules="chunkOverlapRules"
                />
              </v-col>
            </v-row>
          </div>

          <div class="mt-2">
            <h3 class="text-h6 mb-4">{{ t("upload.batchSettings") }}</h3>
            <v-row>
              <v-col cols="12" sm="4">
                <v-text-field
                  v-model.number="uploadSettings.batch_size"
                  :label="t('upload.batchSize')"
                  :hint="
                    t('upload.batchSizeHint', {
                      value: capabilities?.defaults.batch_size ?? '-',
                    })
                  "
                  persistent-hint
                  type="number"
                  variant="outlined"
                  density="compact"
                  :rules="positiveIntegerRules"
                />
              </v-col>
              <v-col cols="12" sm="4">
                <v-text-field
                  v-model.number="uploadSettings.tasks_limit"
                  :label="t('upload.tasksLimit')"
                  :hint="
                    t('upload.tasksLimitHint', {
                      value: capabilities?.defaults.tasks_limit ?? '-',
                    })
                  "
                  persistent-hint
                  type="number"
                  variant="outlined"
                  density="compact"
                  :rules="positiveIntegerRules"
                />
              </v-col>
              <v-col cols="12" sm="4">
                <v-text-field
                  v-model.number="uploadSettings.max_retries"
                  :label="t('upload.maxRetries')"
                  :hint="
                    t('upload.maxRetriesHint', {
                      value: capabilities?.defaults.max_retries ?? '-',
                    })
                  "
                  persistent-hint
                  type="number"
                  variant="outlined"
                  density="compact"
                  :rules="nonNegativeIntegerRules"
                />
              </v-col>
            </v-row>
          </div>
        </v-card-text>

        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn
            variant="text"
            @click="closeUploadDialog()"
            :disabled="uploading"
          >
            {{ t("upload.cancel") }}
          </v-btn>
          <v-btn
            color="primary"
            variant="elevated"
            @click="startUpload"
            :loading="uploading"
            :disabled="isUploadDisabled"
          >
            {{ t("upload.submit") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 删除确认对话框 -->
    <v-dialog v-model="showDeleteDialog" max-width="450px">
      <v-card>
        <v-card-title class="pa-4 text-h6">{{
          t("documents.delete")
        }}</v-card-title>
        <v-card-text class="pa-6">
          <p>
            {{
              t("documents.deleteConfirm", {
                name: deleteTarget?.doc_name || "",
              })
            }}
          </p>
          <v-alert type="error" variant="tonal" density="compact" class="mt-4">
            {{ t("documents.deleteWarning") }}
          </v-alert>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn
            variant="text"
            @click="showDeleteDialog = false"
            :disabled="deleting"
            >{{ t("documents.cancel") }}</v-btn
          >
          <v-btn
            color="error"
            variant="elevated"
            @click="deleteDocument"
            :loading="deleting"
          >
            {{ t("documents.delete") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 批量删除确认对话框 -->
    <v-dialog v-model="showBatchDeleteDialog" max-width="500px">
      <v-card>
        <v-card-title class="pa-4 text-h6">{{
          t("documents.batchDeleteTitle")
        }}</v-card-title>
        <v-card-text class="pa-6">
          <p>
            {{
              t("documents.batchDeleteConfirm", {
                count: batchDeleteState.selectedCount,
              })
            }}
          </p>
          <div v-if="selectedBatchDeletePreview.length" class="mt-4">
            <v-chip
              v-for="doc in selectedBatchDeletePreview"
              :key="doc.doc_id"
              size="small"
              variant="tonal"
              class="mr-1 mb-1"
            >
              {{ doc.doc_name || doc.doc_id }}
            </v-chip>
            <v-chip
              v-if="batchDeleteRemainingCount > 0"
              size="small"
              variant="outlined"
              class="mr-1 mb-1"
            >
              {{
                t("documents.batchDeleteMore", {
                  count: batchDeleteRemainingCount,
                })
              }}
            </v-chip>
          </div>
          <v-alert type="error" variant="tonal" density="compact" class="mt-4">
            {{ t("documents.deleteWarning") }}
          </v-alert>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn
            variant="text"
            @click="showBatchDeleteDialog = false"
            :disabled="batchDeleting"
            >{{ t("documents.cancel") }}</v-btn
          >
          <v-btn
            color="error"
            variant="elevated"
            @click="batchDeleteDocuments"
            :loading="batchDeleting"
            :disabled="!batchDeleteState.canDelete"
          >
            {{ t("documents.delete") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Batch rebuild confirmation dialog -->
    <v-dialog v-model="showBatchRebuildDialog" max-width="500px">
      <v-card>
        <v-card-title class="pa-4 text-h6">{{
          t("documents.batchRebuildTitle")
        }}</v-card-title>
        <v-card-text class="pa-6">
          <p>
            {{
              t("documents.batchRebuildConfirm", {
                count: batchRebuildState.selectedCount,
              })
            }}
          </p>
          <div v-if="selectedBatchRebuildPreview.length" class="mt-4">
            <v-chip
              v-for="doc in selectedBatchRebuildPreview"
              :key="doc.doc_id"
              size="small"
              variant="tonal"
              class="mr-1 mb-1"
            >
              {{ doc.doc_name || doc.doc_id }}
            </v-chip>
            <v-chip
              v-if="batchRebuildRemainingCount > 0"
              size="small"
              variant="outlined"
              class="mr-1 mb-1"
            >
              {{
                t("documents.batchRebuildMore", {
                  count: batchRebuildRemainingCount,
                })
              }}
            </v-chip>
          </div>
          <v-alert
            type="warning"
            variant="tonal"
            density="compact"
            class="mt-4"
          >
            {{ t("documents.batchRebuildWarning") }}
          </v-alert>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn
            variant="text"
            @click="showBatchRebuildDialog = false"
            :disabled="batchRebuilding"
            >{{ t("documents.cancel") }}</v-btn
          >
          <v-btn
            color="primary"
            variant="elevated"
            @click="batchRebuildDocuments"
            :loading="batchRebuilding"
            :disabled="!batchRebuildState.canRebuild"
          >
            {{ t("documents.rebuild") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Rebuild confirmation dialog -->
    <v-dialog v-model="showRebuildDialog" max-width="450px">
      <v-card>
        <v-card-title class="pa-4 text-h6">{{
          t("documents.rebuildTitle")
        }}</v-card-title>
        <v-card-text class="pa-6">
          <p>
            {{
              t("documents.rebuildConfirm", {
                name: rebuildTarget?.doc_name || "",
              })
            }}
          </p>
          <v-alert
            type="warning"
            variant="tonal"
            density="compact"
            class="mt-4"
          >
            {{ t("documents.rebuildWarning") }}
          </v-alert>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn
            variant="text"
            @click="showRebuildDialog = false"
            :disabled="isRebuildTargetBusy"
            >{{ t("documents.cancel") }}</v-btn
          >
          <v-btn
            color="primary"
            variant="elevated"
            @click="rebuildDocument"
            :loading="isRebuildTargetBusy"
            :disabled="!canRebuildTarget"
          >
            {{ t("documents.rebuild") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color">
      <div>{{ snackbar.text }}</div>
      <div v-if="snackbar.details.length" class="mt-2 text-caption">
        <div v-for="detail in snackbar.details" :key="detail">{{ detail }}</div>
      </div>
    </v-snackbar>

    <!-- Tavily Key 配置对话框 -->
    <TavilyKeyDialog v-model="showTavilyDialog" @success="onTavilyKeySet" />
  </div>
</template>

<script setup lang="ts">
import TavilyKeyDialog from "./TavilyKeyDialog.vue";
import { ref, onMounted, onUnmounted, computed, watch } from "vue";
import { useRouter } from "vue-router";
import axios from "axios";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import { copyToClipboard } from "@/utils/clipboard";
import { useKnowledgeBaseCapabilities } from "../capabilities";
import {
  applyActiveRebuildState,
  applyDocumentTaskProgress,
  buildDocumentDisplayTotals,
  buildDocumentFailureText,
  buildDocumentListParams,
  canRebuildDocument,
  clearDocumentTaskState,
  countUploadingDocuments,
  DEFAULT_DOCUMENT_PAGE_SIZE,
  getBatchDeleteState,
  getBatchRebuildState,
  getDocumentFailureSummary,
  getKnowledgeBasePaginationConfig,
  isKnowledgeBaseFeatureEnabled,
  markDocumentRebuildStarted,
  markDocumentsRebuildStarted,
} from "../knowledgeBaseUi.mjs";

const { tm: t } = useModuleI18n("features/knowledge-base/detail");
const { locale } = useI18n();
const router = useRouter();

const props = defineProps<{
  kbId: string;
  kb: any;
}>();

const emit = defineEmits(["refresh"]);
const { capabilities, loadCapabilities } = useKnowledgeBaseCapabilities();

// 状态
const loading = ref(false);
const uploading = ref(false);
const deleting = ref(false);
const batchDeleting = ref(false);
const batchRebuilding = ref(false);
const rebuildingDocIds = ref(new Set<string>());
const documents = ref<any[]>([]);
const selectedDocumentRows = ref<any[]>([]);
const backendMatchedDocuments = ref(0);
const backendDocumentCount = ref(0);
const page = ref(1);
const pageSize = ref(DEFAULT_DOCUMENT_PAGE_SIZE);
const searchQuery = ref("");
const selectedStatus = ref<string | null>(null);
const selectedSourceType = ref<string | null>(null);
const showUploadDialog = ref(false);
const showDeleteDialog = ref(false);
const showBatchDeleteDialog = ref(false);
const showBatchRebuildDialog = ref(false);
const showRebuildDialog = ref(false);
const selectedFiles = ref<File[]>([]);
const deleteTarget = ref<any>(null);
const rebuildTarget = ref<any>(null);
const isDragging = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
const uploadMode = ref("file"); // 'file' or 'url'
const uploadUrl = ref("");
const llmProviders = ref<any[]>([]);
const progressPollingIntervals = new Map<string, number>();
const tavilyConfigStatus = ref("loading"); // 'loading', 'configured', 'not_configured', 'error'
const showTavilyDialog = ref(false);
const paginationConfig = computed(() =>
  getKnowledgeBasePaginationConfig(capabilities.value),
);
const pageSizeOptions = computed(() =>
  paginationConfig.value.documentPageSizeOptions.map((value) => ({
    value,
    title: value.toString(),
  })),
);

const uploadingDocumentCount = computed(() =>
  countUploadingDocuments(documents.value),
);
const documentDisplayTotals = computed(() =>
  buildDocumentDisplayTotals({
    matchedTotal: backendMatchedDocuments.value,
    documentCount: backendDocumentCount.value,
    uploadingCount: uploadingDocumentCount.value,
  }),
);
const totalDocuments = computed(
  () => documentDisplayTotals.value.filteredTotal,
);
const documentCount = computed(() => documentDisplayTotals.value.documentCount);
const documentFilterStatuses = computed(
  () => capabilities.value?.document_filters?.statuses ?? [],
);
const documentFilterSourceTypes = computed(
  () => capabilities.value?.document_filters?.source_types ?? [],
);
const hasKnownDocumentFilterCapabilities = computed(
  () =>
    documentFilterStatuses.value.length > 0 ||
    documentFilterSourceTypes.value.length > 0,
);
const statusFilterOptions = computed(() => [
  { title: t("documents.allStatuses"), value: null },
  ...documentFilterStatuses.value.map((status) => ({
    title: getDocumentStatusText(status),
    value: status,
  })),
]);
const sourceTypeFilterOptions = computed(() => [
  { title: t("documents.allSources"), value: null },
  ...documentFilterSourceTypes.value.map((sourceType) => ({
    title: getSourceTypeText(sourceType),
    value: sourceType,
  })),
]);
const hasActiveDocumentFilters = computed(
  () =>
    Boolean(
      typeof searchQuery.value === "string" && searchQuery.value.trim(),
    ) ||
    Boolean(selectedStatus.value) ||
    Boolean(selectedSourceType.value),
);

const snackbar = ref({
  show: false,
  text: "",
  color: "success",
  details: [] as string[],
});

const showSnackbar = (
  text: string,
  color: string = "success",
  details: string[] = [],
) => {
  snackbar.value.text = text;
  snackbar.value.color = color;
  snackbar.value.details = details;
  snackbar.value.show = true;
};

const updateRebuildingDocIds = (docId: string, rebuilding: boolean) => {
  const next = new Set(rebuildingDocIds.value);
  if (rebuilding) {
    next.add(docId);
  } else {
    next.delete(docId);
  }
  rebuildingDocIds.value = next;
};

// 上传设置
const uploadSettings = ref({
  chunk_size: null as number | null,
  chunk_overlap: null as number | null,
  batch_size: null as number | null,
  tasks_limit: null as number | null,
  max_retries: null as number | null,
  enable_cleaning: false,
  cleaning_provider_id: null as string | null,
});

// 初始化上传设置
const initUploadSettings = () => {
  const defaults = capabilities.value?.defaults;
  uploadSettings.value = {
    chunk_size: props.kb?.chunk_size || null,
    chunk_overlap: props.kb?.chunk_overlap || null,
    batch_size: defaults?.batch_size ?? null,
    tasks_limit: defaults?.tasks_limit ?? null,
    max_retries: defaults?.max_retries ?? null,
    enable_cleaning: false,
    cleaning_provider_id: null,
  };
};

const allowedExtensions = computed(
  () => new Set(capabilities.value?.upload.allowed_extensions ?? []),
);
const maxFilesPerUpload = computed(
  () => capabilities.value?.upload.max_files_per_upload ?? null,
);
const maxFileSize = computed(
  () => capabilities.value?.upload.max_file_size_bytes ?? null,
);
const supportedFormatsText = computed(() => {
  const extensions = capabilities.value?.upload.allowed_extensions;
  if (!extensions?.length) {
    return "-";
  }
  return extensions.map((extension) => `.${extension}`).join(", ");
});
const maxFileSizeText = computed(() =>
  maxFileSize.value === null ? "-" : formatFileSize(maxFileSize.value),
);
const maxFilesPerUploadText = computed(() => maxFilesPerUpload.value ?? "-");
const supportsUrlImport = computed(() =>
  isKnowledgeBaseFeatureEnabled(capabilities.value, "url_import"),
);
const supportsDocumentRebuild = computed(() =>
  isKnowledgeBaseFeatureEnabled(capabilities.value, "document_rebuild"),
);
const supportsBatchDelete = computed(() =>
  isKnowledgeBaseFeatureEnabled(capabilities.value, "batch_delete"),
);
const supportsBatchRebuild = computed(() =>
  isKnowledgeBaseFeatureEnabled(capabilities.value, "batch_rebuild"),
);
const maxBatchDeleteDocuments = computed(
  () => capabilities.value?.limits.max_batch_delete_documents ?? null,
);
const maxBatchRebuildDocuments = computed(
  () => capabilities.value?.limits.max_batch_rebuild_documents ?? null,
);
const batchDeleteState = computed(() =>
  getBatchDeleteState({
    selected: selectedDocumentRows.value,
    documents: documents.value,
    maxDocuments: maxBatchDeleteDocuments.value,
    enabled: supportsBatchDelete.value,
    busy: batchDeleting.value,
  }),
);
const batchRebuildState = computed(() =>
  getBatchRebuildState({
    selectedIds: batchDeleteState.value.selectedIds,
    documents: documents.value,
    maxDocuments: maxBatchRebuildDocuments.value,
    enabled: supportsBatchRebuild.value,
    busy: batchRebuilding.value,
  }),
);
const selectedBatchDeletePreview = computed(() =>
  documents.value
    .filter((doc) => batchDeleteState.value.selectedIds.includes(doc.doc_id))
    .slice(0, 5),
);
const batchDeleteRemainingCount = computed(() =>
  Math.max(
    batchDeleteState.value.selectedCount -
      selectedBatchDeletePreview.value.length,
    0,
  ),
);
const selectedBatchRebuildPreview = computed(() =>
  documents.value
    .filter((doc) => batchRebuildState.value.selectedIds.includes(doc.doc_id))
    .slice(0, 5),
);
const batchRebuildRemainingCount = computed(() =>
  Math.max(
    batchRebuildState.value.selectedCount -
      selectedBatchRebuildPreview.value.length,
    0,
  ),
);
const canRebuild = (doc: any) =>
  canRebuildDocument(doc, {
    supportsDocumentRebuild: supportsDocumentRebuild.value,
    rebuildingDocIds: rebuildingDocIds.value,
  });
const isRebuildTargetBusy = computed(() =>
  Boolean(
    rebuildTarget.value?.rebuilding ||
      (rebuildTarget.value?.doc_id &&
        rebuildingDocIds.value.has(rebuildTarget.value.doc_id)),
  ),
);
const canRebuildTarget = computed(() => canRebuild(rebuildTarget.value));
const fileAccept = computed(() => {
  const extensions = capabilities.value?.upload.allowed_extensions;
  return extensions?.length
    ? extensions.map((extension) => `.${extension}`).join(",")
    : undefined;
});
const chunkSizePlaceholder = computed(
  () =>
    props.kb?.chunk_size?.toString() ||
    capabilities.value?.defaults.chunk_size.toString() ||
    "",
);
const chunkOverlapPlaceholder = computed(
  () =>
    props.kb?.chunk_overlap?.toString() ||
    capabilities.value?.defaults.chunk_overlap.toString() ||
    "",
);

const isPositiveInteger = (value: number | null) =>
  Number.isInteger(value) && Number(value) > 0;
const isNonNegativeInteger = (value: number | null) =>
  Number.isInteger(value) && Number(value) >= 0;
const positiveIntegerRules = [
  (value: number) =>
    value === null ||
    isPositiveInteger(value) ||
    t("validation.positiveInteger"),
];
const nonNegativeIntegerRules = [
  (value: number) =>
    value === null ||
    isNonNegativeInteger(value) ||
    t("validation.nonNegativeInteger"),
];
const chunkSizeRules = [
  (value: number | null) =>
    value === null ||
    isPositiveInteger(value) ||
    t("validation.positiveInteger"),
];
const chunkOverlapRules = [
  (value: number | null) =>
    value === null || Number.isInteger(value) || t("validation.integer"),
  (value: number | null) =>
    value === null || value >= 0 || t("validation.nonNegativeInteger"),
  (value: number | null) =>
    value === null ||
    uploadSettings.value.chunk_size === null ||
    value < uploadSettings.value.chunk_size ||
    t("validation.overlapLessThanSize"),
];

const isUploadSettingsValid = () => {
  const settings = uploadSettings.value;
  if (settings.chunk_size !== null && !isPositiveInteger(settings.chunk_size))
    return false;
  if (
    settings.chunk_overlap !== null &&
    !isNonNegativeInteger(settings.chunk_overlap)
  )
    return false;
  if (
    settings.chunk_size !== null &&
    settings.chunk_overlap !== null &&
    settings.chunk_overlap >= settings.chunk_size
  ) {
    return false;
  }
  return (
    (settings.batch_size === null || isPositiveInteger(settings.batch_size)) &&
    (settings.tasks_limit === null ||
      isPositiveInteger(settings.tasks_limit)) &&
    (settings.max_retries === null ||
      isNonNegativeInteger(settings.max_retries))
  );
};

const isUploadDisabled = computed(() => {
  if (uploading.value) {
    return true;
  }
  if (!isUploadSettingsValid()) {
    return true;
  }
  if (uploadMode.value === "file") {
    return selectedFiles.value.length === 0;
  }
  if (uploadMode.value === "url") {
    if (!supportsUrlImport.value) {
      return true;
    }
    if (!uploadUrl.value) {
      return true;
    }
    if (tavilyConfigStatus.value !== "configured") {
      return true;
    }
    if (
      uploadSettings.value.enable_cleaning &&
      !uploadSettings.value.cleaning_provider_id
    ) {
      return true;
    }
    return false;
  }
  return true;
});

// 表格列
const headers = computed(() => [
  { title: t("documents.name"), key: "doc_name", sortable: true },
  { title: t("documents.type"), key: "file_type", sortable: true },
  { title: t("documents.status"), key: "status", sortable: true },
  { title: t("documents.size"), key: "file_size", sortable: true },
  { title: t("documents.chunks"), key: "chunk_count", sortable: true },
  { title: t("documents.createdAt"), key: "created_at", sortable: true },
  {
    title: t("documents.actions"),
    key: "actions",
    sortable: false,
    align: "end" as const,
  },
]);

// 加载文档列表
const loadDocuments = async () => {
  loading.value = true;
  try {
    const response = await axios.get("/api/kb/document/list", {
      params: buildDocumentListParams({
        kbId: props.kbId,
        page: page.value,
        pageSize: pageSize.value,
        search: searchQuery.value || undefined,
        status: selectedStatus.value,
        sourceType: selectedSourceType.value,
        allowedStatuses: documentFilterStatuses.value,
        allowedSourceTypes: documentFilterSourceTypes.value,
      }),
    });
    if (response.data.status === "ok") {
      const uploadingDocs = documents.value.filter((doc) => doc.uploading);
      const loadedDocs = applyActiveRebuildState(
        response.data.data.items || [],
        documents.value,
      ).map((doc: any) => ({
        ...doc,
        selectable: !doc.uploading && !doc.rebuilding,
      }));
      const matchedTotal =
        response.data.data.filtered_total ?? response.data.data.total ?? 0;
      const unfilteredTotal =
        response.data.data.document_count ?? response.data.data.total ?? 0;
      documents.value = [...uploadingDocs, ...loadedDocs];
      selectedDocumentRows.value = selectedDocumentRows.value.filter((doc) =>
        loadedDocs.some((loadedDoc: any) => loadedDoc.doc_id === doc.doc_id),
      );
      backendMatchedDocuments.value = matchedTotal;
      backendDocumentCount.value = unfilteredTotal;
      const lastPage = Math.max(Math.ceil(matchedTotal / pageSize.value), 1);
      if (loadedDocs.length === 0 && page.value > lastPage) {
        page.value = lastPage;
      }
    } else {
      showSnackbar(response.data.message || t("documents.loadFailed"), "error");
    }
  } catch (error) {
    console.error("Failed to load documents:", error);
    showSnackbar(t("documents.loadFailed"), "error");
  } finally {
    loading.value = false;
  }
};

watch([searchQuery, selectedStatus, selectedSourceType], () => {
  page.value = 1;
  loadDocuments();
});

watch(capabilities, () => {
  if (!hasKnownDocumentFilterCapabilities.value) {
    return;
  }
  let shouldReload = false;
  if (
    selectedStatus.value &&
    !documentFilterStatuses.value.includes(selectedStatus.value)
  ) {
    selectedStatus.value = null;
    shouldReload = true;
  }
  if (
    selectedSourceType.value &&
    !documentFilterSourceTypes.value.includes(selectedSourceType.value)
  ) {
    selectedSourceType.value = null;
    shouldReload = true;
  }
  if (shouldReload) {
    page.value = 1;
    loadDocuments();
  }
});

const openFilePicker = () => {
  if (uploading.value) {
    return;
  }
  fileInput.value?.click();
};

// 文件选择
const handleFileSelect = (event: Event) => {
  if (uploading.value) {
    return;
  }
  const target = event.target as HTMLInputElement;
  if (target.files && target.files.length > 0) {
    const newFiles = Array.from(target.files);
    addFiles(newFiles);
  }
  target.value = "";
};

// 添加文件（检查数量限制）
const addFiles = (files: File[]) => {
  const totalFiles = selectedFiles.value.length + files.length;
  if (
    maxFilesPerUpload.value !== null &&
    totalFiles > maxFilesPerUpload.value
  ) {
    showSnackbar(
      t("upload.maxFilesWarning", { count: maxFilesPerUpload.value }),
      "warning",
    );
    return;
  }
  const acceptedFiles: File[] = [];
  const rejectedFiles: string[] = [];
  files.forEach((file) => {
    const extension = getFileExtension(file.name);
    if (
      allowedExtensions.value.size > 0 &&
      !allowedExtensions.value.has(extension)
    ) {
      rejectedFiles.push(t("upload.unsupportedFile", { name: file.name }));
      return;
    }
    if (maxFileSize.value !== null && file.size > maxFileSize.value) {
      rejectedFiles.push(
        t("upload.fileTooLarge", {
          name: file.name,
          size: formatFileSize(maxFileSize.value),
        }),
      );
      return;
    }
    acceptedFiles.push(file);
  });
  if (rejectedFiles.length > 0) {
    showSnackbar(t("upload.someFilesRejected"), "warning", rejectedFiles);
  }
  selectedFiles.value.push(...acceptedFiles);
};

// 移除文件
const removeFile = (index: number) => {
  selectedFiles.value.splice(index, 1);
};

// 拖放上传
const handleDrop = (event: DragEvent) => {
  isDragging.value = false;
  if (uploading.value) {
    return;
  }
  if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
    const newFiles = Array.from(event.dataTransfer.files);
    addFiles(newFiles);
  }
};

// 上传调度器
const startUpload = async () => {
  if (!isUploadSettingsValid()) {
    showSnackbar(t("upload.invalidSettings"), "warning");
    return;
  }
  if (uploadMode.value === "file") {
    await uploadFiles();
  } else if (uploadMode.value === "url" && supportsUrlImport.value) {
    await uploadFromUrl();
  }
};

// 上传文件
const uploadFiles = async () => {
  if (selectedFiles.value.length === 0) {
    showSnackbar(t("upload.fileRequired"), "warning");
    return;
  }

  uploading.value = true;

  try {
    const formData = new FormData();

    // 添加所有文件
    selectedFiles.value.forEach((file, index) => {
      formData.append(`file${index}`, file);
    });

    formData.append("kb_id", props.kbId);
    if (uploadSettings.value.chunk_size !== null) {
      formData.append("chunk_size", uploadSettings.value.chunk_size.toString());
    }
    if (uploadSettings.value.chunk_overlap !== null) {
      formData.append(
        "chunk_overlap",
        uploadSettings.value.chunk_overlap.toString(),
      );
    }
    if (uploadSettings.value.batch_size !== null) {
      formData.append("batch_size", uploadSettings.value.batch_size.toString());
    }
    if (uploadSettings.value.tasks_limit !== null) {
      formData.append(
        "tasks_limit",
        uploadSettings.value.tasks_limit.toString(),
      );
    }
    if (uploadSettings.value.max_retries !== null) {
      formData.append(
        "max_retries",
        uploadSettings.value.max_retries.toString(),
      );
    }

    const response = await axios.post("/api/kb/document/upload", formData);

    if (response.data.status === "ok") {
      const result = response.data.data;
      const taskId = result.task_id;

      showSnackbar(
        t("upload.backgroundUploading", { count: result.file_count }),
        "info",
      );

      // 为每个文件添加占位条目到文档列表
      const uploadingDocs = selectedFiles.value.map((file, index) => ({
        doc_id: `uploading_${taskId}_${index}`,
        doc_name: file.name,
        file_type: file.name.split(".").pop() || "",
        file_size: file.size,
        chunk_count: 0,
        created_at: new Date().toISOString(),
        uploading: true,
        taskId: taskId,
        uploadProgress: {
          stage: "waiting",
          current: 0,
          total: 100,
        },
        selectable: false,
      }));

      // 添加到文档列表顶部
      page.value = 1;
      documents.value = [...uploadingDocs, ...documents.value];

      // 关闭对话框
      closeUploadDialog(true);

      if (taskId) {
        startProgressPolling(taskId, "upload");
      }
    } else {
      showSnackbar(
        response.data.message || t("documents.uploadFailed"),
        "error",
      );
    }
  } catch (error: any) {
    console.error("Failed to upload document:", error);
    const message =
      error.response?.data?.message || t("documents.uploadFailed");
    showSnackbar(message, "error");
  } finally {
    uploading.value = false;
  }
};

// 从 URL 上传
const uploadFromUrl = async () => {
  if (!supportsUrlImport.value) {
    showSnackbar(t("upload.unsupportedUrlImport"), "warning");
    uploadMode.value = "file";
    return;
  }
  if (!uploadUrl.value) {
    showSnackbar(t("upload.urlRequired"), "warning");
    return;
  }

  uploading.value = true;

  try {
    const payload: any = {
      kb_id: props.kbId,
      url: uploadUrl.value,
    };
    if (uploadSettings.value.batch_size !== null) {
      payload.batch_size = uploadSettings.value.batch_size;
    }
    if (uploadSettings.value.tasks_limit !== null) {
      payload.tasks_limit = uploadSettings.value.tasks_limit;
    }
    if (uploadSettings.value.max_retries !== null) {
      payload.max_retries = uploadSettings.value.max_retries;
    }
    if (uploadSettings.value.chunk_size !== null) {
      payload.chunk_size = uploadSettings.value.chunk_size;
    }
    if (uploadSettings.value.chunk_overlap !== null) {
      payload.chunk_overlap = uploadSettings.value.chunk_overlap;
    }
    if (uploadSettings.value.enable_cleaning) {
      payload.enable_cleaning = true;
      if (uploadSettings.value.cleaning_provider_id) {
        payload.cleaning_provider_id =
          uploadSettings.value.cleaning_provider_id;
      }
    }

    const response = await axios.post("/api/kb/document/upload/url", payload);

    if (response.data.status === "ok") {
      const result = response.data.data;
      const taskId = result.task_id;

      showSnackbar(t("upload.backgroundUrlUploading"), "info");

      // 添加占位条目
      const uploadingDoc = {
        doc_id: `uploading_${taskId}_0`,
        doc_name: result.url,
        file_type: "url",
        file_size: 0, // URL has no size
        chunk_count: 0,
        created_at: new Date().toISOString(),
        uploading: true,
        taskId: taskId,
        uploadProgress: {
          stage: "waiting",
          current: 0,
          total: 100,
        },
        selectable: false,
      };

      page.value = 1;
      documents.value = [uploadingDoc, ...documents.value];
      closeUploadDialog(true);

      if (taskId) {
        startProgressPolling(taskId, "upload");
      }
    } else {
      showSnackbar(
        response.data.message || t("documents.uploadFailed"),
        "error",
      );
    }
  } catch (error: any) {
    console.error("Failed to upload from URL:", error);
    const message =
      error.response?.data?.message || t("documents.uploadFailed");
    showSnackbar(message, "error");
  } finally {
    uploading.value = false;
  }
};

// 开始轮询进度
const startProgressPolling = (
  taskId: string,
  mode: "upload" | "rebuild" = "upload",
) => {
  if (progressPollingIntervals.has(taskId)) {
    return;
  }

  const interval = window.setInterval(async () => {
    try {
      const response = await axios.get("/api/kb/document/upload/progress", {
        params: { task_id: taskId },
      });

      if (response.data.status === "ok") {
        const data = response.data.data;
        const status = data.status;

        if (status === "processing" && data.progress) {
          documents.value = applyDocumentTaskProgress(
            documents.value,
            taskId,
            data.progress,
          );
        } else if (status === "completed") {
          stopProgressPolling(taskId);

          const result = data.result;
          const successCount = result?.success_count || 0;
          const failedCount = result?.failed_count || 0;
          const failedDetails = (result?.failed || [])
            .map((item: any) => item.error || item.file_name)
            .filter(Boolean);
          const failedReason =
            data.error || failedDetails[0] || t("upload.unknownError");

          documents.value = clearDocumentTaskState(documents.value, taskId);

          await loadDocuments();
          emit("refresh");

          if (mode === "rebuild") {
            if (failedCount === 0) {
              showSnackbar(t("documents.rebuildSuccess"));
            } else {
              showSnackbar(
                t("documents.rebuildPartialSuccess", {
                  success: successCount,
                  failed: failedCount,
                }),
                "warning",
                failedDetails,
              );
            }
          } else if (failedCount === 0) {
            showSnackbar(t("upload.successCount", { count: successCount }));
          } else if (successCount === 0) {
            showSnackbar(
              t("upload.failedWithReason", { reason: failedReason }),
              "error",
              failedDetails,
            );
          } else {
            showSnackbar(
              t("upload.partialSuccess", {
                success: successCount,
                failed: failedCount,
              }),
              "warning",
              failedDetails,
            );
          }
        } else if (status === "failed") {
          stopProgressPolling(taskId);

          documents.value = clearDocumentTaskState(documents.value, taskId);
          await loadDocuments();
          emit("refresh");

          const failedDetails = (data.result?.failed || [])
            .map((item: any) => item.error || item.file_name)
            .filter(Boolean);
          const reason =
            data.error || failedDetails[0] || t("upload.unknownError");
          showSnackbar(
            mode === "rebuild"
              ? t("documents.rebuildFailedWithReason", { reason })
              : t("upload.failedWithReason", { reason }),
            "error",
            failedDetails,
          );
        }
      } else {
        stopProgressPolling(taskId);
        documents.value = clearDocumentTaskState(documents.value, taskId);
        await loadDocuments();
        emit("refresh");
      }
    } catch (error) {
      console.error("Failed to fetch progress:", error);
      // 不立即停止，允许重试
    }
  }, 1000);
  progressPollingIntervals.set(taskId, interval);
};

// 停止轮询进度
const stopProgressPolling = (taskId: string) => {
  const interval = progressPollingIntervals.get(taskId);
  if (interval) {
    clearInterval(interval);
    progressPollingIntervals.delete(taskId);
  }
};

const stopAllProgressPolling = () => {
  progressPollingIntervals.forEach((interval) => clearInterval(interval));
  progressPollingIntervals.clear();
};

// 获取上传百分比
const getUploadPercentage = (item: any) => {
  if (!item.uploadProgress) return 0;
  const { current, total } = item.uploadProgress;
  if (!total || total === 0) return 0;
  return (current / total) * 100;
};

// 获取阶段文本
const getStageText = (stage: string) => {
  const stageMap: Record<string, string> = {
    waiting: t("upload.stages.waiting"),
    extracting: t("upload.stages.extracting"),
    cleaning: t("upload.stages.cleaning"),
    parsing: t("upload.stages.parsing"),
    chunking: t("upload.stages.chunking"),
    embedding: t("upload.stages.embedding"),
    rebuilding: t("upload.stages.rebuilding"),
    completed: t("upload.stages.completed"),
  };
  return stageMap[stage] || stage;
};

const getDocumentStatusText = (status?: string) => {
  const normalizedStatus = status || "ready";
  const statusMap: Record<string, string> = {
    pending: t("documents.statuses.pending"),
    parsing: t("documents.statuses.parsing"),
    chunking: t("documents.statuses.chunking"),
    embedding: t("documents.statuses.embedding"),
    ready: t("documents.statuses.ready"),
    failed: t("documents.statuses.failed"),
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

const getSourceTypeText = (sourceType?: string) => {
  const normalizedSourceType = sourceType || "file";
  const sourceTypeMap: Record<string, string> = {
    file: t("documents.sourceTypes.file"),
    url: t("documents.sourceTypes.url"),
    import: t("documents.sourceTypes.import"),
  };
  return sourceTypeMap[normalizedSourceType] || normalizedSourceType;
};

const getFailureLabels = () => ({
  document: t("documents.failureDocument"),
  documentId: t("documents.failureDocumentId"),
  stage: t("documents.failureStage"),
  message: t("documents.failureMessage"),
  unknownStage: t("documents.unknownFailureStage"),
  noErrorMessage: t("documents.noFailureMessage"),
});

const getFailureSummary = (doc: any) =>
  getDocumentFailureSummary(doc, getFailureLabels());

const copyFailureDetails = async (doc: any) => {
  const copied = await copyToClipboard(
    buildDocumentFailureText(doc, getFailureLabels()),
  );
  showSnackbar(
    copied
      ? t("documents.copyFailureSuccess")
      : t("documents.copyFailureFailed"),
    copied ? "success" : "error",
  );
};

const confirmRebuild = (doc: any) => {
  if (!canRebuild(doc)) {
    return;
  }
  rebuildTarget.value = doc;
  showRebuildDialog.value = true;
};

const rebuildDocument = async () => {
  const doc = rebuildTarget.value;
  if (!canRebuild(doc)) {
    return;
  }
  updateRebuildingDocIds(doc.doc_id, true);
  try {
    const response = await axios.post("/api/kb/document/rebuild", {
      doc_id: doc.doc_id,
      kb_id: props.kbId,
      background: true,
    });
    if (response.data.status === "ok") {
      const taskId = response.data.data?.task_id;
      if (taskId) {
        documents.value = markDocumentRebuildStarted(
          documents.value,
          doc.doc_id,
          taskId,
        );
        showSnackbar(t("documents.rebuildStarted"), "info");
        startProgressPolling(taskId, "rebuild");
        showRebuildDialog.value = false;
        rebuildTarget.value = null;
      } else {
        showSnackbar(t("documents.rebuildSuccess"));
        showRebuildDialog.value = false;
        rebuildTarget.value = null;
        await loadDocuments();
        emit("refresh");
      }
    } else {
      showSnackbar(
        response.data.message || t("documents.rebuildFailed"),
        "error",
      );
    }
  } catch (error) {
    console.error("Failed to rebuild document:", error);
    showSnackbar(t("documents.rebuildFailed"), "error");
  } finally {
    updateRebuildingDocIds(doc.doc_id, false);
  }
};

// 关闭上传对话框
const closeUploadDialog = (force = false) => {
  if (uploading.value && !force) {
    return;
  }
  showUploadDialog.value = false;
  selectedFiles.value = [];
  uploadUrl.value = "";
  uploadMode.value = "file";
  initUploadSettings();
};

watch(supportsUrlImport, (supported) => {
  if (!supported && uploadMode.value === "url") {
    uploadMode.value = "file";
  }
});

// 查看文档
const viewDocument = (doc: any) => {
  if (doc.uploading) return;
  router.push({
    name: "NativeDocumentDetail",
    params: { kbId: props.kbId, docId: doc.doc_id },
  });
};

// 确认删除
const confirmDelete = (doc: any) => {
  if (doc.uploading) return;
  deleteTarget.value = doc;
  showDeleteDialog.value = true;
};

// 删除文档
const deleteDocument = async () => {
  if (!deleteTarget.value) return;

  deleting.value = true;
  try {
    const response = await axios.post("/api/kb/document/delete", {
      doc_id: deleteTarget.value.doc_id,
      kb_id: props.kbId,
    });

    if (response.data.status === "ok") {
      showSnackbar(t("documents.deleteSuccess"));
      showDeleteDialog.value = false;
      await loadDocuments();
      emit("refresh");
    } else {
      showSnackbar(
        response.data.message || t("documents.deleteFailed"),
        "error",
      );
    }
  } catch (error) {
    console.error("Failed to delete document:", error);
    showSnackbar(t("documents.deleteFailed"), "error");
  } finally {
    deleting.value = false;
  }
};

const confirmBatchDelete = () => {
  if (!batchDeleteState.value.canDelete) {
    if (batchDeleteState.value.exceedsLimit && batchDeleteState.value.limit) {
      showSnackbar(
        t("documents.batchDeleteLimitExceeded", {
          limit: batchDeleteState.value.limit,
        }),
        "warning",
      );
    }
    return;
  }
  showBatchDeleteDialog.value = true;
};

const batchDeleteDocuments = async () => {
  if (!batchDeleteState.value.canDelete) return;

  const deletingCount = batchDeleteState.value.selectedCount;
  batchDeleting.value = true;
  try {
    const response = await axios.post("/api/kb/document/batch-delete", {
      kb_id: props.kbId,
      doc_ids: batchDeleteState.value.selectedIds,
    });

    if (response.data.status === "ok") {
      const data = response.data.data || {};
      showBatchDeleteDialog.value = false;
      selectedDocumentRows.value = [];
      if (data.failed_count > 0) {
        showSnackbar(
          t("documents.batchDeletePartialSuccess", {
            success: data.success_count || 0,
            failed: data.failed_count || 0,
          }),
          "warning",
        );
      } else {
        showSnackbar(
          t("documents.batchDeleteSuccess", {
            count: data.success_count ?? deletingCount,
          }),
        );
      }
      await loadDocuments();
      emit("refresh");
    } else {
      showSnackbar(
        response.data.message || t("documents.batchDeleteFailed"),
        "error",
      );
    }
  } catch (error) {
    console.error("Failed to batch delete documents:", error);
    showSnackbar(t("documents.batchDeleteFailed"), "error");
  } finally {
    batchDeleting.value = false;
  }
};

const confirmBatchRebuild = () => {
  if (!batchRebuildState.value.canRebuild) {
    if (batchRebuildState.value.exceedsLimit && batchRebuildState.value.limit) {
      showSnackbar(
        t("documents.batchRebuildLimitExceeded", {
          limit: batchRebuildState.value.limit,
        }),
        "warning",
      );
    }
    return;
  }
  showBatchRebuildDialog.value = true;
};

const batchRebuildDocuments = async () => {
  if (!batchRebuildState.value.canRebuild) return;

  const rebuildingIds = batchRebuildState.value.selectedIds.filter(
    (docId): docId is string => typeof docId === "string" && docId.length > 0,
  );
  if (!rebuildingIds.length) {
    return;
  }
  batchRebuilding.value = true;
  rebuildingIds.forEach((docId) => updateRebuildingDocIds(docId, true));
  try {
    const response = await axios.post("/api/kb/document/batch-rebuild", {
      kb_id: props.kbId,
      doc_ids: rebuildingIds,
    });

    if (response.data.status === "ok") {
      const taskId = response.data.data?.task_id;
      showBatchRebuildDialog.value = false;
      selectedDocumentRows.value = [];
      if (taskId) {
        documents.value = markDocumentsRebuildStarted(
          documents.value,
          rebuildingIds,
          taskId,
        );
        showSnackbar(
          t("documents.batchRebuildStarted", {
            count: rebuildingIds.length,
          }),
          "info",
        );
        startProgressPolling(taskId, "rebuild");
      } else {
        showSnackbar(t("documents.rebuildStarted"), "info");
        await loadDocuments();
        emit("refresh");
      }
    } else {
      showSnackbar(
        response.data.message || t("documents.batchRebuildFailed"),
        "error",
      );
    }
  } catch (error) {
    console.error("Failed to batch rebuild documents:", error);
    showSnackbar(t("documents.batchRebuildFailed"), "error");
  } finally {
    rebuildingIds.forEach((docId) => updateRebuildingDocIds(docId, false));
    batchRebuilding.value = false;
  }
};

// 工具函数
const getFileIcon = (fileType: string) => {
  const type = fileType?.toLowerCase() || "";
  if (type.includes("pdf")) return "mdi-file-pdf-box";
  if (type.includes("epub")) return "mdi-book-open-page-variant";
  if (type.includes("rst") || type.includes("adoc"))
    return "mdi-file-document-outline";
  if (type.includes("md") || type.includes("markdown"))
    return "mdi-language-markdown";
  if (type.includes("txt")) return "mdi-file-document-outline";
  if (type.includes("url")) return "mdi-link-variant";
  return "mdi-file";
};

const getFileExtension = (fileName: string) =>
  fileName.includes(".") ? fileName.split(".").pop()?.toLowerCase() || "" : "";

const getFileColor = (fileType: string) => {
  const type = fileType?.toLowerCase() || "";
  if (type.includes("pdf")) return "error";
  if (type.includes("epub")) return "warning";
  if (type.includes("rst") || type.includes("adoc")) return "success";
  if (type.includes("md")) return "info";
  if (type.includes("txt")) return "success";
  if (type.includes("url")) return "primary";
  return "grey";
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

// 加载LLM providers
const loadLlmProviders = async () => {
  try {
    const response = await axios.get("/api/config/provider/list", {
      params: { provider_type: "chat_completion" },
    });
    if (response.data.status === "ok") {
      llmProviders.value = response.data.data;
    }
  } catch (error) {
    console.error("Failed to load LLM providers:", error);
  }
};

// 检查Tavily Key配置
const checkTavilyConfig = async () => {
  tavilyConfigStatus.value = "loading";
  try {
    const response = await axios.get("/api/config/abconf", {
      params: { id: "default" },
    });
    if (response.data.status === "ok") {
      const config = response.data.data.config;
      const tavilyKeys = config?.provider_settings?.websearch_tavily_key;
      if (
        Array.isArray(tavilyKeys) &&
        tavilyKeys.length > 0 &&
        tavilyKeys.some((key) => key.trim() !== "")
      ) {
        tavilyConfigStatus.value = "configured";
      } else {
        tavilyConfigStatus.value = "not_configured";
      }
    } else {
      tavilyConfigStatus.value = "error";
    }
  } catch (error) {
    console.warn("Failed to check Tavily key config:", error);
    tavilyConfigStatus.value = "error";
  }
};

const onTavilyKeySet = () => {
  showSnackbar(t("upload.tavilyConfigured"), "success");
  checkTavilyConfig();
};

onMounted(() => {
  loadCapabilities().then(() => {
    initUploadSettings();
    pageSize.value = paginationConfig.value.defaultDocumentPageSize;
    loadDocuments();
  });
  loadLlmProviders();
  checkTavilyConfig();
});

onUnmounted(() => {
  stopAllProgressPolling();
});
</script>

<style scoped>
.documents-tab {
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

.action-bar {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.document-filter-select {
  max-width: 180px;
  min-width: 150px;
}

.documents-filter-count {
  min-width: fit-content;
}

.doc-name {
  display: block;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-error {
  max-width: 320px;
  color: rgb(var(--v-theme-error));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-dropzone {
  border: 2px dashed rgba(var(--v-theme-primary), 0.3);
  border-radius: 12px;
  padding: 48px 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  background: rgba(var(--v-theme-surface-variant), 0.3);
}

.upload-dropzone:hover,
.upload-dropzone.dragover {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.05);
  transform: scale(1.02);
}

.upload-dropzone.disabled {
  cursor: not-allowed;
  opacity: 0.7;
  transform: none;
}

.files-list {
  max-height: 300px;
  overflow-y: auto;
}

.file-item {
  transition: all 0.2s ease;
}

.file-item:hover {
  background: rgba(var(--v-theme-surface-variant), 0.8) !important;
}

@media (max-width: 768px) {
  .action-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .action-bar > * {
    width: 100%;
  }
}
</style>
