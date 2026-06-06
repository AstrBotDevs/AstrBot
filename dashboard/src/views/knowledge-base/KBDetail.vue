<template>
  <div class="kb-detail-page">
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <v-progress-circular indeterminate color="primary" size="64" />
    </div>

    <v-alert v-else-if="loadError" type="error" variant="tonal" class="mb-4">
      <div class="d-flex align-center justify-space-between gap-4">
        <span>{{ loadError }}</span>
        <v-btn variant="text" color="error" @click="loadKB">
          {{ t("actions.retry") }}
        </v-btn>
      </div>
    </v-alert>

    <!-- 主内容 -->
    <div v-else class="kb-content">
      <!-- 标签页 -->
      <v-tabs v-model="activeTab" class="mb-6" color="primary">
        <v-tab value="overview">
          <v-icon start>mdi-information-outline</v-icon>
          {{ t("tabs.overview") }}
        </v-tab>
        <v-tab value="documents">
          <v-icon start>mdi-file-document-multiple</v-icon>
          {{ t("tabs.documents") }}
          <v-chip class="ml-2" size="small" variant="tonal">{{
            documentCount
          }}</v-chip>
        </v-tab>
        <v-tab value="retrieval">
          <v-icon start>mdi-magnify</v-icon>
          {{ t("tabs.retrieval") }}
        </v-tab>
        <v-tab value="settings">
          <v-icon start>mdi-cog</v-icon>
          {{ t("tabs.settings") }}
        </v-tab>
      </v-tabs>

      <!-- 标签页内容 -->
      <v-window v-model="activeTab" style="padding: 8px">
        <!-- 概览 -->
        <v-window-item value="overview">
          <v-row class="overview-layout">
            <v-col cols="12" lg="4">
              <v-card
                variant="outlined"
                class="overview-card overview-card--fill"
              >
                <v-card-title>{{ t("overview.title") }}</v-card-title>
                <v-card-text>
                  <v-list density="comfortable">
                    <v-list-item>
                      <template #prepend>
                        <v-icon>mdi-label</v-icon>
                      </template>
                      <v-list-item-title>{{
                        t("overview.name")
                      }}</v-list-item-title>
                      <v-list-item-subtitle>{{
                        kb.kb_name
                      }}</v-list-item-subtitle>
                    </v-list-item>

                    <v-list-item v-if="kb.description">
                      <template #prepend>
                        <v-icon>mdi-text</v-icon>
                      </template>
                      <v-list-item-title>{{
                        t("overview.description")
                      }}</v-list-item-title>
                      <v-list-item-subtitle>{{
                        kb.description
                      }}</v-list-item-subtitle>
                    </v-list-item>

                    <v-list-item>
                      <template #prepend>
                        <v-icon>mdi-emoticon</v-icon>
                      </template>
                      <v-list-item-title>{{
                        t("overview.emoji")
                      }}</v-list-item-title>
                      <v-list-item-subtitle>{{
                        kb.emoji || "📚"
                      }}</v-list-item-subtitle>
                    </v-list-item>

                    <v-list-item>
                      <template #prepend>
                        <v-icon>mdi-calendar-plus</v-icon>
                      </template>
                      <v-list-item-title>{{
                        t("overview.createdAt")
                      }}</v-list-item-title>
                      <v-list-item-subtitle>{{
                        formatDate(kb.created_at)
                      }}</v-list-item-subtitle>
                    </v-list-item>

                    <v-list-item>
                      <template #prepend>
                        <v-icon>mdi-calendar-edit</v-icon>
                      </template>
                      <v-list-item-title>{{
                        t("overview.updatedAt")
                      }}</v-list-item-title>
                      <v-list-item-subtitle>{{
                        formatDate(kb.updated_at)
                      }}</v-list-item-subtitle>
                    </v-list-item>

                    <v-list-item>
                      <template #prepend>
                        <v-icon>mdi-vector-point</v-icon>
                      </template>
                      <v-list-item-title>{{
                        t("overview.embeddingModel")
                      }}</v-list-item-title>
                      <v-list-item-subtitle>{{
                        kb.embedding_provider_id || t("overview.notSet")
                      }}</v-list-item-subtitle>
                    </v-list-item>

                    <v-list-item>
                      <template #prepend>
                        <v-icon>mdi-sort-ascending</v-icon>
                      </template>
                      <v-list-item-title>{{
                        t("overview.rerankModel")
                      }}</v-list-item-title>
                      <v-list-item-subtitle>{{
                        kb.rerank_provider_id || t("overview.notSet")
                      }}</v-list-item-subtitle>
                    </v-list-item>
                  </v-list>
                </v-card-text>
              </v-card>
            </v-col>

            <v-col cols="12" lg="8">
              <v-card
                variant="outlined"
                class="overview-card overview-card--fill"
              >
                <v-card-title>{{ t("overview.stats") }}</v-card-title>
                <v-card-text>
                  <v-row dense class="stats-grid">
                    <v-col cols="12" sm="6" md="4">
                      <div class="stat-box">
                        <v-icon size="36" color="primary"
                          >mdi-file-document</v-icon
                        >
                        <div class="stat-value">{{ documentCount }}</div>
                        <div class="stat-label">
                          {{ t("overview.docCount") }}
                        </div>
                      </div>
                    </v-col>
                    <v-col cols="12" sm="6" md="4">
                      <div class="stat-box">
                        <v-icon size="36" color="secondary"
                          >mdi-text-box</v-icon
                        >
                        <div class="stat-value">{{ indexedChunkCount }}</div>
                        <div class="stat-label">
                          {{ t("overview.chunkCount") }}
                        </div>
                      </div>
                    </v-col>
                    <v-col cols="12" sm="6" md="4">
                      <div class="stat-box">
                        <v-icon size="36" color="success"
                          >mdi-check-circle-outline</v-icon
                        >
                        <div class="stat-value">{{ readyDocumentCount }}</div>
                        <div class="stat-label">
                          {{ t("overview.readyDocCount") }}
                        </div>
                      </div>
                    </v-col>
                    <v-col cols="12" sm="6" md="4">
                      <div class="stat-box">
                        <v-icon size="36" color="error"
                          >mdi-alert-circle-outline</v-icon
                        >
                        <div class="stat-value">{{ failedDocumentCount }}</div>
                        <div class="stat-label">
                          {{ t("overview.failedDocCount") }}
                        </div>
                      </div>
                    </v-col>
                    <v-col cols="12" sm="6" md="4">
                      <div class="stat-box">
                        <v-icon size="36" color="info">mdi-folder</v-icon>
                        <div class="stat-value">{{ sourceFileCount }}</div>
                        <div class="stat-label">
                          {{ t("overview.sourceFiles") }}
                        </div>
                      </div>
                    </v-col>
                    <v-col cols="12" sm="6" md="4">
                      <div class="stat-box">
                        <v-icon size="36" color="warning">mdi-database</v-icon>
                        <div class="stat-value">
                          {{ formatFileSize(storageBytes) }}
                        </div>
                        <div class="stat-label">
                          {{ t("overview.storageUsed") }}
                        </div>
                      </div>
                    </v-col>
                  </v-row>
                </v-card-text>
              </v-card>
            </v-col>

            <v-col cols="12" lg="7">
              <v-card variant="outlined" class="overview-card">
                <v-card-title
                  class="d-flex align-center justify-space-between flex-wrap ga-2"
                >
                  <span>{{ t("consistency.title") }}</span>
                  <div class="d-flex align-center flex-wrap ga-2">
                    <v-btn
                      v-if="canRepairConsistency"
                      color="warning"
                      variant="tonal"
                      size="small"
                      prepend-icon="mdi-wrench"
                      :loading="consistencyRepairing"
                      :disabled="
                        consistencyLoading ||
                        kbRebuilding
                      "
                      @click="repairConsistency"
                    >
                      {{ t("consistency.repair") }}
                    </v-btn>
                    <v-btn
                      v-if="supportsKbRebuild"
                      color="primary"
                      variant="tonal"
                      size="small"
                      prepend-icon="mdi-database-sync"
                      :loading="kbRebuilding"
                      :disabled="
                        consistencyLoading ||
                        consistencyRepairing
                      "
                      @click="startKbRebuild"
                    >
                      {{ t("maintenance.rebuild") }}
                    </v-btn>
                    <v-btn
                      v-if="supportsConsistencyCheck"
                      color="primary"
                      variant="tonal"
                      size="small"
                      prepend-icon="mdi-refresh"
                      :loading="consistencyLoading"
                      :disabled="consistencyRepairing"
                      @click="runConsistencyCheck"
                    >
                      {{ t("consistency.run") }}
                    </v-btn>
                  </div>
                </v-card-title>
                <v-card-text>
                  <v-alert
                    v-if="kbRebuilding"
                    type="info"
                    variant="tonal"
                    density="compact"
                    class="mb-4"
                  >
                    <div class="d-flex align-center justify-space-between ga-4">
                      <span>{{
                        getMaintenanceStageText(kbRebuildProgress.stage)
                      }}</span>
                      <span class="text-caption">
                        {{ kbRebuildProgress.current }} /
                        {{ kbRebuildProgress.total }}
                      </span>
                    </div>
                    <v-progress-linear
                      class="mt-2"
                      color="primary"
                      height="4"
                      rounded
                      striped
                      :model-value="getProgressPercentage(kbRebuildProgress)"
                    />
                  </v-alert>

                  <v-alert
                    v-if="consistencyReport"
                    :type="
                      consistencyReport.summary.healthy ? 'success' : 'warning'
                    "
                    variant="tonal"
                    density="compact"
                    class="mb-4"
                  >
                    <div
                      class="d-flex align-center justify-space-between flex-wrap ga-2"
                    >
                      <span>
                        {{
                          consistencyReport.summary.healthy
                            ? t("consistency.healthy")
                            : t("consistency.unhealthy", {
                                count: consistencyIssueCount,
                              })
                        }}
                      </span>
                      <span class="text-caption">
                        {{
                          t("consistency.checkedAt", {
                            time: formatDate(consistencyReport.checked_at),
                          })
                        }}
                      </span>
                    </div>
                  </v-alert>

                  <v-alert
                    v-else
                    :type="consistencyPrecheckType"
                    variant="tonal"
                    density="compact"
                    class="mb-0"
                  >
                    <div class="d-flex flex-column ga-1">
                      <span>{{ consistencyPrecheckMessage }}</span>
                      <span class="text-caption text-medium-emphasis">
                        {{ t("consistency.notRunHint") }}
                      </span>
                    </div>
                  </v-alert>

                  <v-row v-if="consistencyReport" dense class="mb-2">
                    <v-col cols="6" sm="3">
                      <div class="consistency-metric">
                        <div class="consistency-value">
                          {{ consistencyReport.summary.sqlite_document_count }}
                        </div>
                        <div class="consistency-label">
                          {{ t("consistency.sqliteDocuments") }}
                        </div>
                      </div>
                    </v-col>
                    <v-col cols="6" sm="3">
                      <div class="consistency-metric">
                        <div class="consistency-value">
                          {{ consistencyReport.summary.indexed_chunk_count }}
                        </div>
                        <div class="consistency-label">
                          {{ t("consistency.indexedChunks") }}
                        </div>
                      </div>
                    </v-col>
                    <v-col cols="6" sm="3">
                      <div class="consistency-metric">
                        <div class="consistency-value">
                          {{ consistencyReport.summary.document_chunk_count }}
                        </div>
                        <div class="consistency-label">
                          {{ t("consistency.documentChunks") }}
                        </div>
                      </div>
                    </v-col>
                    <v-col cols="6" sm="3">
                      <div class="consistency-metric">
                        <div class="consistency-value">
                          {{ consistencyReport.summary.source_file_count }}
                        </div>
                        <div class="consistency-label">
                          {{ t("consistency.sourceFiles") }}
                        </div>
                      </div>
                    </v-col>
                  </v-row>

                  <v-expansion-panels
                    v-if="consistencyReport && consistencyIssueCount > 0"
                    variant="accordion"
                  >
                    <v-expansion-panel
                      v-for="issueType in visibleConsistencyIssueTypes"
                      :key="issueType.key"
                    >
                      <v-expansion-panel-title>
                        <div class="d-flex align-center ga-2">
                          <v-icon color="warning" size="small">
                            mdi-alert-circle-outline
                          </v-icon>
                          <span>{{ t(issueType.labelKey) }}</span>
                          <v-chip
                            size="x-small"
                            color="warning"
                            variant="tonal"
                          >
                            {{ consistencyReport.summary[issueType.key] || 0 }}
                          </v-chip>
                        </div>
                      </v-expansion-panel-title>
                      <v-expansion-panel-text>
                        <v-list density="compact">
                          <v-list-item
                            v-for="(issue, index) in consistencyReport.issues[
                              issueType.key
                            ]"
                            :key="`${issueType.key}-${index}-${
                              issue.doc_id || issue.chunk_id || issue.storage_id
                            }`"
                          >
                            <template #prepend>
                              <v-icon size="small" color="warning">
                                mdi-alert-circle-outline
                              </v-icon>
                            </template>
                            <v-list-item-title>
                              {{ formatConsistencyIssueTitle(issue) }}
                            </v-list-item-title>
                            <v-list-item-subtitle>
                              {{ formatConsistencyIssueDetail(issue) }}
                            </v-list-item-subtitle>
                          </v-list-item>
                        </v-list>
                      </v-expansion-panel-text>
                    </v-expansion-panel>
                  </v-expansion-panels>
                </v-card-text>
              </v-card>
            </v-col>

            <v-col cols="12" lg="5">
              <div class="overview-side-stack">
                <v-card variant="outlined" class="overview-card">
                  <v-card-title
                    class="d-flex align-center justify-space-between flex-wrap ga-2"
                  >
                    <span>{{ t("tasks.title") }}</span>
                    <v-btn
                      icon="mdi-refresh"
                      variant="text"
                      size="small"
                      :loading="recentTasksLoading"
                      :title="t('tasks.refresh')"
                      @click="loadRecentTasks"
                    />
                  </v-card-title>
                  <v-card-text>
                    <v-skeleton-loader
                      v-if="recentTasksLoading && recentTasks.length === 0"
                      type="list-item-two-line@3"
                    />
                    <v-alert
                      v-else-if="recentTasksLoadError"
                      type="error"
                      variant="tonal"
                      density="compact"
                    >
                      {{ recentTasksLoadError }}
                    </v-alert>
                    <v-alert
                      v-else-if="recentTasks.length === 0"
                      type="info"
                      variant="tonal"
                      density="compact"
                    >
                      {{ t("tasks.empty") }}
                    </v-alert>
                    <template v-else>
                      <v-list density="compact" class="task-list task-list--timeline">
                      <v-list-item
                        v-for="task in recentTasks"
                        :key="task.task_id"
                        class="px-0"
                      >
                        <template #prepend>
                          <v-icon
                            :color="getTaskStatusColor(task.status)"
                            size="small"
                          >
                            {{ getTaskTypeIcon(task.task_type) }}
                          </v-icon>
                        </template>
                        <v-list-item-title class="d-flex align-center ga-2">
                          <span>{{ getTaskTypeText(task.task_type) }}</span>
                          <v-chip
                            size="x-small"
                            variant="tonal"
                            :color="getTaskStatusColor(task.status)"
                          >
                            {{ getTaskStatusText(task.status) }}
                          </v-chip>
                        </v-list-item-title>
                        <v-list-item-subtitle>
                          {{ formatTaskSubtitle(task) }}
                          <span
                            v-if="formatTaskDetail(task)"
                            class="task-detail-line"
                          >
                            {{ formatTaskDetail(task) }}
                          </span>
                        </v-list-item-subtitle>
                        <template #append>
                          <span
                            v-if="
                              task.status === 'pending' ||
                              task.status === 'processing'
                            "
                            class="text-caption text-medium-emphasis"
                          >
                            {{ formatTaskProgress(task) }}
                          </span>
                        </template>
                      </v-list-item>
                      </v-list>
                    </template>

                  </v-card-text>
                </v-card>
              </div>
            </v-col>
          </v-row>
        </v-window-item>

        <!-- 文档管理 -->
        <v-window-item value="documents">
          <DocumentsTab :kb-id="kbId" :kb="kb" @refresh="loadKB" />
        </v-window-item>

        <!-- 知识库检索 -->
        <v-window-item value="retrieval">
          <RetrievalTab :kb-id="kbId" :kb-name="kb.kb_name" />
        </v-window-item>

        <!-- 设置 -->
        <v-window-item value="settings">
          <SettingsTab :kb="kb" @updated="loadKB" />
        </v-window-item>
      </v-window>
    </div>

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color">
      {{ snackbar.text }}
    </v-snackbar>

  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import axios from "axios";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import DocumentsTab from "./components/DocumentsTab.vue";
import RetrievalTab from "./components/RetrievalTab.vue";
import SettingsTab from "./components/SettingsTab.vue";
import { useKnowledgeBaseCapabilities } from "./capabilities";
import {
  getRepairableConsistencyTypes,
  hasRepairableConsistencyIssues,
} from "./knowledgeBaseUi.mjs";
import { isKnowledgeBaseFeatureEnabled } from "./knowledgeBaseUi.mjs";
import {
  getKnowledgeBaseTaskErrorText,
  getKnowledgeBaseTaskProgress,
  getKnowledgeBaseTaskStatusColor,
  getKnowledgeBaseTaskTypeIcon,
} from "./knowledgeBaseUi.mjs";

const { tm: t } = useModuleI18n("features/knowledge-base/detail");
const { locale } = useI18n();
const route = useRoute();
const router = useRouter();
const { capabilities, loadCapabilities } = useKnowledgeBaseCapabilities();

const emit = defineEmits<{
  (event: "title-change", title: string): void;
}>();

const kbId = ref(route.params.kbId as string);
const loading = ref(true);
const tabValues = ["overview", "documents", "retrieval", "settings"];
const getTabFromRoute = () => {
  const tab = route.query.tab;
  return typeof tab === "string" && tabValues.includes(tab) ? tab : "overview";
};
const activeTab = ref(getTabFromRoute());
const kb = ref<any>({});
const loadError = ref("");

type ConsistencyIssueKey =
  | "missing_vectors"
  | "orphan_vectors"
  | "missing_source_files"
  | "chunk_count_mismatches"
  | "invalid_vector_metadata"
  | "unsafe_source_paths";

interface ConsistencyIssue {
  doc_id?: string;
  doc_name?: string;
  chunk_id?: string;
  storage_id?: number | string;
  status?: string;
  source_type?: string;
  file_path?: string;
  expected_chunk_count?: number;
  actual_chunk_count?: number;
  metadata_error?: string;
  reason?: string;
}

interface ConsistencySummary {
  sqlite_document_count: number;
  ready_document_count: number;
  failed_document_count: number;
  document_chunk_count: number;
  indexed_chunk_count: number;
  source_file_count: number;
  status_counts: Record<string, number>;
  missing_vectors: number;
  orphan_vectors: number;
  missing_source_files: number;
  chunk_count_mismatches: number;
  invalid_vector_metadata: number;
  unsafe_source_paths: number;
  healthy: boolean;
}

interface ConsistencyReport {
  kb_id: string;
  kb_name: string;
  checked_at: string;
  summary: ConsistencySummary;
  issues: Record<ConsistencyIssueKey, ConsistencyIssue[]>;
}

interface ConsistencyRepairReport {
  summary?: {
    repaired_count?: number;
    skipped_count?: number;
    failed_count?: number;
    healthy_after_repair?: boolean;
  };
  post_check?: ConsistencyReport;
}

interface KnowledgeBaseTask {
  task_id: string;
  kb_id: string;
  task_type: string;
  status: string;
  progress_stage?: string | null;
  progress_current?: number;
  progress_total?: number;
  progress?: Record<string, any> | null;
  result?: Record<string, any> | null;
  error?: any;
  created_at?: string;
  updated_at?: string;
}

const documentCount = computed(
  () => kb.value.document_count ?? kb.value.doc_count ?? 0,
);
const readyDocumentCount = computed(
  () =>
    kb.value.ready_document_count ??
    kb.value.status_counts?.ready ??
    documentCount.value,
);
const failedDocumentCount = computed(
  () => kb.value.failed_document_count ?? kb.value.status_counts?.failed ?? 0,
);
const indexedChunkCount = computed(
  () => kb.value.indexed_chunk_count ?? kb.value.chunk_count ?? 0,
);
const documentChunkCount = computed(
  () => kb.value.document_chunk_count ?? indexedChunkCount.value,
);
const sourceFileCount = computed(() => kb.value.source_file_count ?? 0);
const storageBytes = computed(() => kb.value.storage_bytes ?? 0);
const supportsConsistencyCheck = computed(() =>
  isKnowledgeBaseFeatureEnabled(capabilities.value, "consistency_check"),
);
const supportsConsistencyRepair = computed(() =>
  isKnowledgeBaseFeatureEnabled(capabilities.value, "consistency_repair"),
);
const supportsKbRebuild = computed(() =>
  isKnowledgeBaseFeatureEnabled(capabilities.value, "kb_rebuild"),
);
const consistencyLoading = ref(false);
const consistencyRepairing = ref(false);
const consistencyReport = ref<ConsistencyReport | null>(null);
const kbRebuilding = ref(false);
const kbRebuildTaskId = ref("");
const recentTasks = ref<KnowledgeBaseTask[]>([]);
const recentTasksLoading = ref(false);
const recentTasksLoadError = ref("");
const kbRebuildProgress = ref({
  stage: "waiting",
  current: 0,
  total: 100,
});
let kbRebuildPollingInterval: number | null = null;
const consistencyIssueTypes: {
  key: ConsistencyIssueKey;
  labelKey: string;
}[] = [
  { key: "missing_vectors", labelKey: "consistency.issues.missingVectors" },
  { key: "orphan_vectors", labelKey: "consistency.issues.orphanVectors" },
  {
    key: "missing_source_files",
    labelKey: "consistency.issues.missingSourceFiles",
  },
  {
    key: "chunk_count_mismatches",
    labelKey: "consistency.issues.chunkCountMismatches",
  },
  {
    key: "invalid_vector_metadata",
    labelKey: "consistency.issues.invalidVectorMetadata",
  },
  {
    key: "unsafe_source_paths",
    labelKey: "consistency.issues.unsafeSourcePaths",
  },
];
const consistencyIssueCount = computed(() => {
  if (!consistencyReport.value) return 0;
  return consistencyIssueTypes.reduce(
    (total, issueType) =>
      total + (consistencyReport.value?.summary[issueType.key] ?? 0),
    0,
  );
});
const visibleConsistencyIssueTypes = computed(() => {
  if (!consistencyReport.value) return [];
  return consistencyIssueTypes.filter(
    (issueType) => (consistencyReport.value?.summary[issueType.key] ?? 0) > 0,
  );
});
const hasChunkCountDrift = computed(
  () => documentChunkCount.value !== indexedChunkCount.value,
);
const consistencyPrecheckType = computed(() =>
  failedDocumentCount.value > 0 || hasChunkCountDrift.value ? "warning" : "info",
);
const consistencyPrecheckMessage = computed(() => {
  if (hasChunkCountDrift.value) {
    return t("consistency.notRunChunkMismatch", {
      metadata: documentChunkCount.value,
      indexed: indexedChunkCount.value,
    });
  }
  if (failedDocumentCount.value > 0) {
    return t("consistency.notRunFailedDocs", {
      count: failedDocumentCount.value,
    });
  }
  return t("consistency.notRun");
});
const repairableConsistencyTypes = computed(() =>
  getRepairableConsistencyTypes(consistencyReport.value),
);
const canRepairConsistency = computed(
  () =>
    supportsConsistencyRepair.value &&
    hasRepairableConsistencyIssues(consistencyReport.value),
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

const getProgressPercentage = (progress: {
  current: number;
  total: number;
}) => {
  if (!progress.total) return 0;
  return Math.min((progress.current / progress.total) * 100, 100);
};

const getMaintenanceStageText = (stage?: string) => {
  const stageMap: Record<string, string> = {
    waiting: t("maintenance.stages.waiting"),
    rebuilding: t("maintenance.stages.rebuilding"),
    parsing: t("maintenance.stages.parsing"),
    chunking: t("maintenance.stages.chunking"),
    embedding: t("maintenance.stages.embedding"),
    completed: t("maintenance.stages.completed"),
  };
  return stageMap[stage || "waiting"] || stage || "";
};

const loadKBStats = async () => {
  try {
    const response = await axios.get("/api/kb/stats", {
      params: { kb_id: kbId.value },
    });
    if (response.data.status === "ok") {
      kb.value = {
        ...kb.value,
        ...response.data.data,
      };
    }
  } catch (error) {
    console.warn("Failed to load knowledge base stats:", error);
  }
};

const loadRecentTasks = async () => {
  recentTasksLoading.value = true;
  recentTasksLoadError.value = "";
  try {
    const tasksResponse = await axios.get("/api/kb/task/list", {
      params: {
        kb_id: kbId.value,
        page: 1,
        page_size: 5,
      },
    });
    if (tasksResponse.data.status !== "ok") {
      recentTasksLoadError.value =
        tasksResponse.data.message || t("tasks.loadFailed");
      return;
    }
    recentTasks.value = tasksResponse.data.data.items || [];
  } catch (error) {
    console.error("Failed to load recent knowledge base tasks:", error);
    recentTasksLoadError.value = t("tasks.loadFailed");
  } finally {
    recentTasksLoading.value = false;
  }
};

const stopKbRebuildPolling = () => {
  if (kbRebuildPollingInterval !== null) {
    clearInterval(kbRebuildPollingInterval);
    kbRebuildPollingInterval = null;
  }
};

const finishKbRebuildTask = async () => {
  stopKbRebuildPolling();
  kbRebuilding.value = false;
  kbRebuildTaskId.value = "";
  await loadKB();
};

const pollKbRebuildProgress = (taskId: string) => {
  stopKbRebuildPolling();
  kbRebuildPollingInterval = window.setInterval(async () => {
    try {
      const response = await axios.get("/api/kb/document/upload/progress", {
        params: { task_id: taskId },
      });
      if (response.data.status !== "ok") {
        await finishKbRebuildTask();
        return;
      }

      const data = response.data.data;
      if (data.progress) {
        kbRebuildProgress.value = {
          stage: data.progress.stage || "waiting",
          current: Number(data.progress.current ?? 0),
          total: Number(data.progress.total ?? 100) || 100,
        };
      }

      if (data.status === "completed" || data.status === "partial_failed") {
        const result = data.result || {};
        await finishKbRebuildTask();
        const failedCount = result.failed_count || 0;
        if (failedCount > 0) {
          showSnackbar(
            t("maintenance.rebuildPartialSuccess", {
              success: result.success_count || 0,
              failed: failedCount,
            }),
            "warning",
          );
        } else {
          showSnackbar(t("maintenance.rebuildSuccess"), "success");
        }
      } else if (data.status === "failed") {
        const reason = data.error || t("maintenance.unknownError");
        await finishKbRebuildTask();
        showSnackbar(
          t("maintenance.rebuildFailedWithReason", { reason }),
          "error",
        );
      }
    } catch (error) {
      console.error("Failed to poll knowledge base rebuild progress:", error);
    }
  }, 1000);
};

const startKbRebuild = async () => {
  if (!supportsKbRebuild.value || kbRebuilding.value) return;
  kbRebuilding.value = true;
  kbRebuildProgress.value = {
    stage: "waiting",
    current: 0,
    total: 100,
  };
  try {
    const response = await axios.post("/api/kb/rebuild", {
      kb_id: kbId.value,
      background: true,
    });
    if (response.data.status === "ok") {
      const taskId = response.data.data?.task_id;
      if (taskId) {
        kbRebuildTaskId.value = taskId;
        consistencyReport.value = null;
        showSnackbar(t("maintenance.rebuildStarted"), "info");
        pollKbRebuildProgress(taskId);
      } else {
        await finishKbRebuildTask();
        showSnackbar(t("maintenance.rebuildSuccess"), "success");
      }
    } else {
      kbRebuilding.value = false;
      showSnackbar(
        response.data.message || t("maintenance.rebuildFailed"),
        "error",
      );
    }
  } catch (error) {
    console.error("Knowledge base rebuild failed:", error);
    kbRebuilding.value = false;
    showSnackbar(t("maintenance.rebuildFailed"), "error");
  }
};

const runConsistencyCheck = async () => {
  if (!supportsConsistencyCheck.value || consistencyRepairing.value) return;
  consistencyLoading.value = true;
  try {
    const response = await axios.get("/api/kb/consistency/check", {
      params: { kb_id: kbId.value },
    });
    if (response.data.status === "ok") {
      consistencyReport.value = response.data.data as ConsistencyReport;
      showSnackbar(
        consistencyReport.value.summary.healthy
          ? t("consistency.checkSuccessHealthy")
          : t("consistency.checkSuccessUnhealthy", {
              count: consistencyIssueCount.value,
            }),
        consistencyReport.value.summary.healthy ? "success" : "warning",
      );
    } else {
      showSnackbar(
        response.data.message || t("consistency.checkFailed"),
        "error",
      );
    }
  } catch (error) {
    console.error("Knowledge base consistency check failed:", error);
    showSnackbar(t("consistency.checkFailed"), "error");
  } finally {
    consistencyLoading.value = false;
  }
};

const repairConsistency = async () => {
  if (!canRepairConsistency.value || consistencyRepairing.value) return;
  consistencyRepairing.value = true;
  try {
    const response = await axios.post("/api/kb/consistency/repair", {
      kb_id: kbId.value,
      repair_types: repairableConsistencyTypes.value,
    });
    if (response.data.status === "ok") {
      const repairReport = response.data.data as ConsistencyRepairReport;
      await loadKB();
      if (repairReport.post_check) {
        consistencyReport.value = repairReport.post_check;
      }
      const failedCount = repairReport.summary?.failed_count ?? 0;
      showSnackbar(
        failedCount > 0
          ? t("consistency.repairPartialSuccess", {
              repaired: repairReport.summary?.repaired_count ?? 0,
              skipped: repairReport.summary?.skipped_count ?? 0,
              failed: failedCount,
            })
          : t("consistency.repairSuccess", {
              repaired: repairReport.summary?.repaired_count ?? 0,
              skipped: repairReport.summary?.skipped_count ?? 0,
            }),
        failedCount > 0 ? "warning" : "success",
      );
    } else {
      showSnackbar(
        response.data.message || t("consistency.repairFailed"),
        "error",
      );
    }
  } catch (error) {
    console.error("Knowledge base consistency repair failed:", error);
    showSnackbar(t("consistency.repairFailed"), "error");
  } finally {
    consistencyRepairing.value = false;
  }
};

// 加载知识库详情
const loadKB = async () => {
  loading.value = true;
  loadError.value = "";
  try {
    const response = await axios.get("/api/kb/get", {
      params: { kb_id: kbId.value },
    });
    if (response.data.status === "ok") {
      kb.value = response.data.data;
      await loadKBStats();
      await loadRecentTasks();
      emit("title-change", kb.value.kb_name || "");
    } else {
      loadError.value = response.data.message || t("messages.loadFailed");
      showSnackbar(loadError.value, "error");
    }
  } catch (error) {
    console.error("Failed to load knowledge base:", error);
    loadError.value = t("messages.loadFailed");
    showSnackbar(loadError.value, "error");
  } finally {
    loading.value = false;
  }
};

// 格式化日期
const formatDate = (dateStr: string) => {
  if (!dateStr) return "-";
  const date = new Date(dateStr);
  return date.toLocaleString(locale.value, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const formatFileSize = (bytes?: number | null) => {
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

const getTaskStatusColor = (status: string) =>
  getKnowledgeBaseTaskStatusColor(status);

const getTaskTypeIcon = (taskType: string) =>
  getKnowledgeBaseTaskTypeIcon(taskType);

const getTaskTypeText = (taskType: string) =>
  t(`tasks.types.${taskType}`) || taskType;

const getTaskStatusText = (status: string) =>
  t(`tasks.statuses.${status}`) || status;

const toTaskCount = (value: unknown) => {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : 0;
};

const getTaskResultCounts = (task: KnowledgeBaseTask) => {
  const result = task.result || {};
  const success = toTaskCount(result.success_count);
  const failed = toTaskCount(result.failed_count);
  const total = toTaskCount(result.total) || success + failed;
  return { success, failed, total };
};

const formatTaskProgress = (task: KnowledgeBaseTask) => {
  const progress = getKnowledgeBaseTaskProgress(task);
  return `${progress.current} / ${progress.total}`;
};

const formatTaskError = (task: KnowledgeBaseTask) =>
  getKnowledgeBaseTaskErrorText(task.error, t("tasks.noErrorMessage"));

const formatTaskSubtitle = (task: KnowledgeBaseTask) =>
  formatDate(task.updated_at || task.created_at || "");

const formatTaskDetail = (task: KnowledgeBaseTask) => {
  if (task.status === "pending" || task.status === "processing") {
    return t("tasks.progressDetail", {
      progress: formatTaskProgress(task),
    });
  }
  if (task.status === "failed") {
    return formatTaskError(task);
  }

  const { success, failed, total } = getTaskResultCounts(task);
  if (total > 0) {
    return t("tasks.resultSummary", {
      success,
      failed,
      total,
    });
  }
  return "";
};

const formatConsistencyIssueTitle = (issue: ConsistencyIssue) => {
  return (
    issue.doc_name || issue.doc_id || issue.chunk_id || String(issue.storage_id)
  );
};

const formatConsistencyIssueDetail = (issue: ConsistencyIssue) => {
  const parts = [];
  if (issue.expected_chunk_count !== undefined) {
    parts.push(
      t("consistency.expectedChunks", {
        count: issue.expected_chunk_count,
      }),
    );
  }
  if (issue.actual_chunk_count !== undefined) {
    parts.push(
      t("consistency.actualChunks", {
        count: issue.actual_chunk_count,
      }),
    );
  }
  if (issue.metadata_error) {
    parts.push(issue.metadata_error);
  }
  if (issue.reason) {
    parts.push(t(`consistency.reasons.${issue.reason}`));
  }
  if (issue.file_path) {
    parts.push(issue.file_path);
  }
  return parts.join(" · ") || "-";
};

onMounted(() => {
  loadCapabilities();
  loadKB();
});

onUnmounted(() => {
  stopKbRebuildPolling();
});

watch(
  () => kb.value?.kb_name,
  (name) => {
    emit("title-change", name || "");
  },
);

watch(activeTab, (tab) => {
  if (tab === route.query.tab || (tab === "overview" && !route.query.tab)) {
    return;
  }
  router.replace({
    query: {
      ...route.query,
      tab: tab === "overview" ? undefined : tab,
    },
  });
});

watch(
  () => route.query.tab,
  () => {
    activeTab.value = getTabFromRoute();
  },
);

</script>

<style scoped>
.kb-detail-page {
  width: 100%;
}

.kb-detail-page :deep(.v-card--variant-outlined) {
  background: rgb(var(--v-theme-surface));
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}

.overview-layout {
  align-items: stretch;
}

.overview-layout > .v-col {
  display: flex;
}

.overview-card {
  width: 100%;
}

.overview-card--fill {
  height: 100%;
}

.overview-side-stack {
  display: grid;
  gap: 16px;
  width: 100%;
}

.stats-grid > .v-col {
  display: flex;
}

.stat-box {
  min-height: 118px;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 18px 14px;
  text-align: center;
  border-radius: 8px;
  background: rgba(var(--v-theme-surface-variant), 0.1);
  transition: all 0.3s ease;
}

.stat-box:hover {
  background: rgba(var(--v-theme-surface-variant), 0.5);
}

.stat-value {
  font-size: 1.75rem;
  font-weight: 600;
  line-height: 1.2;
  margin-top: 8px;
  max-width: 100%;
  overflow-wrap: anywhere;
}

.stat-label {
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-size: 0.875rem;
  line-height: 1.35;
  margin-top: 4px;
  max-width: 100%;
  overflow-wrap: anywhere;
}

.consistency-metric {
  min-height: 72px;
  padding: 12px;
  border-radius: 8px;
  background: rgba(var(--v-theme-surface-variant), 0.12);
}

.consistency-value {
  font-size: 1.25rem;
  font-weight: 600;
  line-height: 1.4;
}

.consistency-label {
  margin-top: 2px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-size: 0.75rem;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.task-detail-line {
  display: block;
  margin-top: 2px;
  color: rgba(var(--v-theme-on-surface), 0.68);
  font-size: 0.75rem;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.task-list--timeline :deep(.v-list-item) {
  border-left: 2px solid rgba(var(--v-theme-outline), 0.16);
  padding-left: 12px !important;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .kb-title {
    font-size: 1.25rem;
  }

  .stat-box {
    min-height: 108px;
    padding: 16px 10px;
  }

  .stat-value {
    font-size: 1.45rem;
  }
}
</style>
