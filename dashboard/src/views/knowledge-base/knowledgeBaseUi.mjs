export const DEFAULT_KB_PAGE_SIZE = 20;
export const DEFAULT_DOCUMENT_PAGE_SIZE = 10;
export const DEFAULT_CHUNK_PAGE_SIZE = 10;
export const DEFAULT_BULK_PAGE_SIZE = 100;
export const DEFAULT_DOCUMENT_PAGE_SIZE_OPTIONS = [10, 20, 50, 100];
export const DEFAULT_CHUNK_PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

/**
 * @param {unknown} value
 * @param {number} fallback
 */
const toPositiveInteger = (value, fallback) => {
  const numericValue = Number(value);
  return Number.isInteger(numericValue) && numericValue > 0
    ? numericValue
    : fallback;
};

const toNonNegativeInteger = (value, fallback = 0) => {
  const numericValue = Number(value);
  return Number.isInteger(numericValue) && numericValue >= 0
    ? numericValue
    : fallback;
};

/**
 * @param {unknown} values
 * @param {number[]} fallback
 */
const normalizePageSizeOptions = (values, fallback) => {
  const normalized = Array.isArray(values)
    ? values
        .map((value) => Number(value))
        .filter((value) => Number.isInteger(value) && value > 0)
    : [];
  return normalized.length > 0 ? [...new Set(normalized)] : fallback;
};

/**
 * @param {{
 *   pagination?: {
 *     document_page_size_options?: unknown,
 *     chunk_page_size_options?: unknown,
 *     default_kb_page_size?: unknown,
 *     default_document_page_size?: unknown,
 *     default_chunk_page_size?: unknown,
 *     bulk_page_size?: unknown,
 *   },
 * } | null | undefined} capabilities
 */
export const getKnowledgeBasePaginationConfig = (capabilities = null) => {
  const pagination = capabilities?.pagination ?? {};
  const documentPageSizeOptions = normalizePageSizeOptions(
    pagination.document_page_size_options,
    DEFAULT_DOCUMENT_PAGE_SIZE_OPTIONS,
  );
  const chunkPageSizeOptions = normalizePageSizeOptions(
    pagination.chunk_page_size_options,
    DEFAULT_CHUNK_PAGE_SIZE_OPTIONS,
  );
  const defaultKbPageSize = toPositiveInteger(
    pagination.default_kb_page_size,
    DEFAULT_KB_PAGE_SIZE,
  );
  const defaultDocumentPageSize = toPositiveInteger(
    pagination.default_document_page_size,
    documentPageSizeOptions[0] ?? DEFAULT_DOCUMENT_PAGE_SIZE,
  );
  const defaultChunkPageSize = toPositiveInteger(
    pagination.default_chunk_page_size,
    chunkPageSizeOptions[0] ?? DEFAULT_CHUNK_PAGE_SIZE,
  );

  return {
    documentPageSizeOptions,
    chunkPageSizeOptions,
    defaultKbPageSize,
    defaultDocumentPageSize: documentPageSizeOptions.includes(
      defaultDocumentPageSize,
    )
      ? defaultDocumentPageSize
      : documentPageSizeOptions[0],
    defaultChunkPageSize: chunkPageSizeOptions.includes(defaultChunkPageSize)
      ? defaultChunkPageSize
      : chunkPageSizeOptions[0],
    bulkPageSize: toPositiveInteger(
      pagination.bulk_page_size,
      DEFAULT_BULK_PAGE_SIZE,
    ),
  };
};

export const normalizePaginatedPayload = (
  payload,
  fallbackPage = 1,
  fallbackPageSize = DEFAULT_BULK_PAGE_SIZE,
) => {
  const items = Array.isArray(payload?.items) ? payload.items : [];
  return {
    items,
    page: toPositiveInteger(payload?.page, fallbackPage),
    pageSize: toPositiveInteger(payload?.page_size, fallbackPageSize),
    total: toNonNegativeInteger(payload?.total, items.length),
  };
};

export const fetchAllPaginatedItems = async (fetchPage, options = {}) => {
  if (typeof fetchPage !== "function") {
    throw new TypeError("fetchPage must be a function");
  }

  const pageSize = toPositiveInteger(options.pageSize, DEFAULT_BULK_PAGE_SIZE);
  const items = [];
  let page = 1;

  while (true) {
    const payload = normalizePaginatedPayload(
      await fetchPage({ page, pageSize }),
      page,
      pageSize,
    );
    items.push(...payload.items);

    const total = Math.max(payload.total, items.length);
    if (items.length >= total || payload.items.length === 0) {
      return items;
    }

    const nextPage = payload.page + 1;
    if (nextPage <= page) {
      throw new Error("Pagination did not advance while loading all items");
    }
    page = nextPage;
  }
};

export const buildKnowledgeBaseListParams = ({
  page,
  pageSize,
  refreshStats = false,
}) => {
  const params = {
    page,
    page_size: pageSize,
  };

  if (refreshStats) {
    params.refresh_stats = "true";
  }

  return params;
};

export const loadKnowledgeBaseListPages = async ({
  fetchPage,
  pageSize,
  refreshStats = false,
}) =>
  fetchAllPaginatedItems(
    async ({ page, pageSize: currentPageSize }) => {
      const response = await fetchPage(
        buildKnowledgeBaseListParams({
          page,
          pageSize: currentPageSize,
          refreshStats,
        }),
      );

      if (response?.status !== "ok") {
        throw new Error(response?.message || "");
      }

      return response.data;
    },
    { pageSize },
  );

export function getKnowledgeBaseListStats(kb = {}) {
  return {
    documentCount: toNonNegativeInteger(
      kb?.document_count,
      toNonNegativeInteger(kb?.doc_count),
    ),
    chunkCount: toNonNegativeInteger(
      kb?.indexed_chunk_count,
      toNonNegativeInteger(kb?.chunk_count),
    ),
  };
}

const REPAIRABLE_CONSISTENCY_ISSUE_TYPES = [
  "orphan_vectors",
  "chunk_count_mismatches",
];

const isRepairableChunkCountMismatch = (issue = {}) => {
  const expected = Number(issue.expected_chunk_count ?? 0);
  const actual = Number(issue.actual_chunk_count ?? 0);
  return (
    Number.isFinite(expected) && Number.isFinite(actual) && actual > expected
  );
};

export function getRepairableConsistencyTypes(report) {
  if (!report?.issues || !report?.summary) {
    return [];
  }

  const repairTypes = [];
  const orphanCount = Number(report.summary.orphan_vectors ?? 0);
  if (orphanCount > 0) {
    repairTypes.push("orphan_vectors");
  }

  const mismatches = Array.isArray(report.issues.chunk_count_mismatches)
    ? report.issues.chunk_count_mismatches
    : [];
  if (mismatches.some(isRepairableChunkCountMismatch)) {
    repairTypes.push("chunk_count_mismatches");
  }

  return REPAIRABLE_CONSISTENCY_ISSUE_TYPES.filter((issueType) =>
    repairTypes.includes(issueType),
  );
}

export function hasRepairableConsistencyIssues(report) {
  return getRepairableConsistencyTypes(report).length > 0;
}

export const isKnowledgeBaseFeatureEnabled = (capabilities, featureKey) =>
  capabilities?.features?.[featureKey] ?? true;

const TASK_TYPE_ICONS = {
  upload: "mdi-upload",
  import: "mdi-file-import",
  url: "mdi-link-variant",
  document_rebuild: "mdi-refresh",
  document_batch_rebuild: "mdi-refresh",
  kb_rebuild: "mdi-database-sync",
};

const TASK_STATUS_COLORS = {
  pending: "grey",
  processing: "warning",
  completed: "success",
  failed: "error",
};

function toFiniteNumber(value, fallback) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : fallback;
}

export function getKnowledgeBaseTaskTypeIcon(taskType) {
  return TASK_TYPE_ICONS[taskType] || "mdi-progress-clock";
}

export function getKnowledgeBaseTaskStatusColor(status) {
  return TASK_STATUS_COLORS[status] || "grey";
}

export function getKnowledgeBaseTaskProgress(task = {}) {
  const progress =
    task.progress && typeof task.progress === "object" ? task.progress : {};
  const total = Math.max(
    toFiniteNumber(progress.total ?? task.progress_total, 100),
    1,
  );
  return {
    stage: progress.stage || task.progress_stage || "waiting",
    current: toFiniteNumber(progress.current ?? task.progress_current, 0),
    total,
  };
}

export function getKnowledgeBaseTaskErrorText(error, fallback = "") {
  if (!error) {
    return fallback;
  }
  if (typeof error === "string") {
    return error;
  }
  if (typeof error.message === "string" && error.message.trim()) {
    return error.message;
  }
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

const hasDocumentId = (collection, docId) => {
  if (!docId || !collection) {
    return false;
  }
  if (typeof collection.has === "function") {
    return collection.has(docId);
  }
  if (Array.isArray(collection)) {
    return collection.includes(docId);
  }
  return false;
};

export const hasRebuildableSource = (document) => {
  if (!document) {
    return false;
  }
  const sourceType = document.source_type || "file";
  if (sourceType === "file") {
    return Boolean(document.file_path);
  }
  if (sourceType === "url") {
    return Boolean(document.source_uri);
  }
  if (sourceType === "import") {
    return Number(document.chunk_count || 0) > 0;
  }
  return false;
};

/**
 * @param {{ doc_id?: string, uploading?: boolean, rebuilding?: boolean, source_type?: string, source_uri?: string, file_path?: string, chunk_count?: number }} document
 * @param {{ supportsDocumentRebuild?: boolean, rebuildingDocIds?: Set<string> | string[] }} [options]
 */
export const canRebuildDocument = (
  document,
  { supportsDocumentRebuild = true, rebuildingDocIds = [] } = {},
) =>
  Boolean(
    supportsDocumentRebuild &&
      document?.doc_id &&
      hasRebuildableSource(document) &&
      !document.uploading &&
      !document.rebuilding &&
      !hasDocumentId(rebuildingDocIds, document.doc_id),
  );

/**
 * @param {{
 *   selectedIds?: Array<string | null | undefined>,
 *   documents?: Array<{ doc_id?: string, source_type?: string, source_uri?: string, file_path?: string, chunk_count?: number } | null | undefined>,
 *   maxDocuments?: unknown,
 *   enabled?: boolean,
 *   busy?: boolean,
 * }} [options]
 */
export const getBatchRebuildState = ({
  selectedIds = [],
  documents = [],
  maxDocuments = null,
  enabled = true,
  busy = false,
} = {}) => {
  const limitValue = Number(maxDocuments);
  const limit =
    Number.isInteger(limitValue) && limitValue > 0 ? limitValue : null;
  const uniqueSelectedIds = [
    ...new Set(
      selectedIds.filter((docId) => typeof docId === "string" && docId.length),
    ),
  ];
  const documentById = new Map(
    documents
      .filter((document) => document?.doc_id)
      .map((document) => [document.doc_id, document]),
  );
  const rebuildableIds = uniqueSelectedIds.filter((docId) => {
    if (!documentById.size) {
      return true;
    }
    return hasRebuildableSource(documentById.get(docId));
  });
  const exceedsLimit = limit !== null && rebuildableIds.length > Number(limit);

  return {
    selectedIds: rebuildableIds,
    selectedCount: rebuildableIds.length,
    limit,
    exceedsLimit,
    hasSelection: rebuildableIds.length > 0,
    canRebuild:
      Boolean(enabled) && !busy && rebuildableIds.length > 0 && !exceedsLimit,
  };
};

/**
 * @param {unknown} value
 */
const normalizeLimit = (value) => {
  const numericValue = Number(value);
  return Number.isInteger(numericValue) && numericValue > 0
    ? numericValue
    : null;
};

/**
 * @param {{ doc_id?: string, uploading?: boolean, rebuilding?: boolean, disabled?: boolean } | null | undefined} document
 */
export const isBatchSelectableDocument = (document) =>
  Boolean(
    document?.doc_id &&
      !document.uploading &&
      !document.rebuilding &&
      !document.disabled,
  );

/**
 * @param {Array<{ doc_id?: string, uploading?: boolean, rebuilding?: boolean, disabled?: boolean } | null | undefined>} documents
 */
export const getSelectableDocumentIds = (documents = []) =>
  documents
    .filter(isBatchSelectableDocument)
    .map((document) => document.doc_id)
    .filter(Boolean);

/**
 * @param {Array<string | { doc_id?: string } | null | undefined>} selected
 * @param {Array<{ doc_id?: string, uploading?: boolean, rebuilding?: boolean, disabled?: boolean } | null | undefined>} documents
 */
export const normalizeSelectedDocumentIds = (selected = [], documents = []) => {
  const selectableIds = new Set(getSelectableDocumentIds(documents));
  return [
    ...new Set(
      selected
        .map((item) => (typeof item === "string" ? item : item?.doc_id))
        .filter((docId) => docId && selectableIds.has(docId)),
    ),
  ];
};

/**
 * @param {{
 *   selected?: Array<string | { doc_id?: string } | null | undefined>,
 *   documents?: Array<{ doc_id?: string, uploading?: boolean, rebuilding?: boolean, disabled?: boolean } | null | undefined>,
 *   maxDocuments?: unknown,
 *   enabled?: boolean,
 *   busy?: boolean,
 * }} [options]
 */
export const getBatchDeleteState = ({
  selected = [],
  documents = [],
  maxDocuments = null,
  enabled = true,
  busy = false,
} = {}) => {
  const selectedIds = normalizeSelectedDocumentIds(selected, documents);
  const limit = normalizeLimit(maxDocuments);
  const exceedsLimit = limit !== null && selectedIds.length > limit;

  return {
    selectedIds,
    selectedCount: selectedIds.length,
    limit,
    exceedsLimit,
    hasSelection: selectedIds.length > 0,
    canDelete:
      Boolean(enabled) && !busy && selectedIds.length > 0 && !exceedsLimit,
  };
};

export const isFailedDocument = (doc) => doc?.status === "failed";

export const getDocumentFailureSummary = (doc, labels = {}) => {
  if (!isFailedDocument(doc)) return "";
  const stage = String(doc.error_stage || "").trim();
  const message = String(doc.error_message || "").trim();
  const displayStage = stage || labels.unknownStage || "Unknown stage";
  const displayMessage = message || labels.noErrorMessage || "No error message";
  return `${displayStage}: ${displayMessage}`;
};

export const buildDocumentFailureText = (doc, labels = {}) => {
  const lines = [];
  const addLine = (label, value) => {
    const normalizedValue = String(value || "").trim();
    if (normalizedValue) {
      lines.push(`${label}: ${normalizedValue}`);
    }
  };

  addLine(labels.document || "Document", doc?.doc_name);
  addLine(labels.documentId || "Document ID", doc?.doc_id);
  addLine(labels.stage || "Stage", doc?.error_stage);
  addLine(labels.message || "Message", doc?.error_message);

  if (lines.length === 0) {
    return labels.noErrorMessage || "No error message";
  }
  return lines.join("\n");
};

const normalizeOptionalText = (value) => {
  if (typeof value !== "string") {
    return undefined;
  }
  const normalized = value.trim();
  return normalized || undefined;
};

const normalizeAllowedValue = (value, allowedValues = []) => {
  const normalized = normalizeOptionalText(value);
  if (!normalized) {
    return undefined;
  }
  if (allowedValues.length > 0 && !allowedValues.includes(normalized)) {
    return undefined;
  }
  return normalized;
};

export const buildDocumentListParams = ({
  kbId,
  page,
  pageSize,
  search,
  status,
  sourceType,
  allowedStatuses = [],
  allowedSourceTypes = [],
} = {}) => ({
  kb_id: kbId,
  page,
  page_size: pageSize,
  search: normalizeOptionalText(search),
  status: normalizeAllowedValue(status, allowedStatuses),
  source_type: normalizeAllowedValue(sourceType, allowedSourceTypes),
});

export const createDocumentChunkRouteLocation = ({ kbId, docId, chunkId }) => {
  const routeLocation = {
    name: "NativeDocumentDetail",
    params: { kbId, docId },
  };
  if (chunkId) {
    routeLocation.query = { chunkId };
  }
  return routeLocation;
};

export const getFocusedChunkId = (query = {}) => {
  const value = query.chunkId;
  return typeof value === "string" && value.trim() ? value.trim() : "";
};

export const removeFocusedChunkQuery = (query = {}) => {
  const nextQuery = { ...query };
  delete nextQuery.chunkId;
  return nextQuery;
};

/**
 * @param {unknown} value
 */
const toDocumentCount = (value) => {
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue) || numberValue <= 0) {
    return 0;
  }
  return Math.floor(numberValue);
};

/**
 * @param {Array<{ uploading?: boolean } | null | undefined>} documents
 */
export const countUploadingDocuments = (documents = []) =>
  documents.reduce(
    (count, document) => count + (document?.uploading ? 1 : 0),
    0,
  );

/**
 * @param {{
 *   matchedTotal?: unknown,
 *   documentCount?: unknown,
 *   total?: unknown,
 *   uploadingCount?: unknown,
 * }} [options]
 */
export const buildDocumentDisplayTotals = (options = {}) => {
  const { matchedTotal, documentCount, total, uploadingCount = 0 } = options;
  const backendMatchedTotal = toDocumentCount(matchedTotal ?? total);
  const backendDocumentCount = toDocumentCount(
    documentCount ?? total ?? backendMatchedTotal,
  );
  const activeUploadingCount = toDocumentCount(uploadingCount);

  return {
    filteredTotal: backendMatchedTotal + activeUploadingCount,
    documentCount: backendDocumentCount + activeUploadingCount,
  };
};

const DEFAULT_PROGRESS = {
  stage: "waiting",
  current: 0,
  total: 100,
};

function toNumber(value, fallback) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : fallback;
}

function normalizeProgress(progress = {}) {
  return {
    stage: progress.stage || DEFAULT_PROGRESS.stage,
    current: toNumber(progress.current, DEFAULT_PROGRESS.current),
    total: toNumber(progress.total, DEFAULT_PROGRESS.total),
  };
}

function getUploadPlaceholderIndex(doc) {
  const parts = String(doc?.doc_id || "").split("_");
  return toNumber(parts[parts.length - 1], 0);
}

export function markDocumentRebuildStarted(documents, docId, taskId) {
  return documents.map((doc) => {
    if (doc.doc_id !== docId) {
      return doc;
    }
    return {
      ...doc,
      rebuilding: true,
      taskId,
      uploadProgress: { ...DEFAULT_PROGRESS },
    };
  });
}

export function markDocumentsRebuildStarted(documents, docIds, taskId) {
  const rebuildIds = new Set(docIds);
  return documents.map((doc) => {
    if (!rebuildIds.has(doc.doc_id)) {
      return doc;
    }
    return {
      ...doc,
      rebuilding: true,
      selectable: false,
      taskId,
      uploadProgress: { ...DEFAULT_PROGRESS },
    };
  });
}

export function applyDocumentTaskProgress(documents, taskId, progress = {}) {
  const normalizedProgress = normalizeProgress(progress);
  const fileIndex = toNumber(progress.file_index, 0);

  return documents.map((doc) => {
    if (doc.taskId !== taskId) {
      return doc;
    }
    if (doc.rebuilding) {
      return {
        ...doc,
        uploadProgress: normalizedProgress,
      };
    }
    if (!doc.uploading || getUploadPlaceholderIndex(doc) !== fileIndex) {
      return doc;
    }
    return {
      ...doc,
      uploadProgress: normalizedProgress,
    };
  });
}

export function clearDocumentTaskState(documents, taskId) {
  return documents.flatMap((doc) => {
    if (doc.taskId !== taskId) {
      return [doc];
    }
    if (doc.uploading) {
      return [];
    }
    const nextDoc = { ...doc };
    delete nextDoc.rebuilding;
    delete nextDoc.taskId;
    delete nextDoc.uploadProgress;
    return [nextDoc];
  });
}

export function applyActiveRebuildState(loadedDocuments, currentDocuments) {
  const activeRebuilds = new Map(
    currentDocuments
      .filter((doc) => doc.rebuilding && doc.taskId)
      .map((doc) => [
        doc.doc_id,
        {
          taskId: doc.taskId,
          uploadProgress: doc.uploadProgress || { ...DEFAULT_PROGRESS },
        },
      ]),
  );

  return loadedDocuments.map((doc) => {
    const activeState = activeRebuilds.get(doc.doc_id);
    if (!activeState) {
      return doc;
    }
    return {
      ...doc,
      rebuilding: true,
      taskId: activeState.taskId,
      uploadProgress: activeState.uploadProgress,
    };
  });
}

export const formatTitlePath = (titlePath) =>
  Array.isArray(titlePath) && titlePath.length > 0
    ? titlePath.filter(Boolean).join(" > ")
    : "";

export function buildRetrievalSourceChips(source = {}) {
  if (!source) return [];
  const chips = [];
  const titlePath = formatTitlePath(source.title_path);
  if (titlePath) {
    chips.push({
      key: "title",
      icon: "mdi-format-header-pound",
      label: titlePath,
    });
  }
  if (source.page_number !== null && source.page_number !== undefined) {
    chips.push({
      key: "page",
      icon: "mdi-book-open-page-variant",
      labelKey: "retrieval.sourcePage",
      params: { page: source.page_number },
    });
  }
  if (source.section_index !== null && source.section_index !== undefined) {
    chips.push({
      key: "section",
      icon: "mdi-file-tree",
      labelKey: "retrieval.sourceSection",
      params: { index: source.section_index },
    });
  }
  if (source.parent_chunk_id) {
    chips.push({
      key: "parent",
      icon: "mdi-family-tree",
      labelKey: "retrieval.sourceParentChunk",
      params: { id: source.parent_chunk_id },
    });
  }
  return chips;
}

const SCORE_FIELDS = [
  { key: "dense_score", labelKey: "retrieval.traceDenseScore" },
  { key: "sparse_score", labelKey: "retrieval.traceSparseScore" },
  { key: "rrf_score", labelKey: "retrieval.traceRrfScore" },
  { key: "rerank_score", labelKey: "retrieval.traceRerankScore" },
];

const isFiniteScore = (value) =>
  typeof value === "number" && Number.isFinite(value);

export function buildTraceScoreChips(item = {}) {
  return SCORE_FIELDS.filter(({ key }) => isFiniteScore(item[key])).map(
    ({ key, labelKey }) => ({
      key,
      labelKey,
      value: item[key],
    }),
  );
}
