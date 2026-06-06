import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  applyActiveRebuildState,
  applyDocumentTaskProgress,
  buildDocumentDisplayTotals,
  buildDocumentFailureText,
  buildDocumentListParams,
  canRebuildDocument,
  clearDocumentTaskState,
  countUploadingDocuments,
  createDocumentChunkRouteLocation,
  getBatchDeleteState,
  getBatchRebuildState,
  getDocumentFailureSummary,
  getFocusedChunkId,
  getSelectableDocumentIds,
  hasRebuildableSource,
  isBatchSelectableDocument,
  isFailedDocument,
  markDocumentRebuildStarted,
  markDocumentsRebuildStarted,
  normalizeSelectedDocumentIds,
  removeFocusedChunkQuery,
  DEFAULT_BULK_PAGE_SIZE,
  DEFAULT_CHUNK_PAGE_SIZE_OPTIONS,
  DEFAULT_DOCUMENT_PAGE_SIZE_OPTIONS,
  DEFAULT_KB_PAGE_SIZE,
  buildRetrievalSourceChips,
  buildTraceScoreChips,
  buildKnowledgeBaseListParams,
  fetchAllPaginatedItems,
  formatTitlePath,
  getKnowledgeBaseListStats,
  getKnowledgeBasePaginationConfig,
  getKnowledgeBaseTaskErrorText,
  getKnowledgeBaseTaskProgress,
  getKnowledgeBaseTaskStatusColor,
  getKnowledgeBaseTaskTypeIcon,
  getRepairableConsistencyTypes,
  hasRepairableConsistencyIssues,
  isKnowledgeBaseFeatureEnabled,
  loadKnowledgeBaseListPages,
  normalizePaginatedPayload,
} from "../src/views/knowledge-base/knowledgeBaseUi.mjs";

test("canRebuildDocument accepts ready persistent documents", () => {
  assert.equal(
    canRebuildDocument({
      doc_id: "doc-1",
      source_type: "file",
      file_path: "/kb/files/doc-1/source.md",
    }),
    true,
  );
});

test("canRebuildDocument requires the rebuild capability", () => {
  assert.equal(
    canRebuildDocument(
      {
        doc_id: "doc-1",
        source_type: "file",
        file_path: "/kb/files/doc-1/source.md",
      },
      { supportsDocumentRebuild: false },
    ),
    false,
  );
});

test("canRebuildDocument rejects transient document states", () => {
  assert.equal(
    canRebuildDocument({
      doc_id: "uploading",
      uploading: true,
      source_type: "file",
      file_path: "/kb/files/uploading/source.md",
    }),
    false,
  );
  assert.equal(
    canRebuildDocument({
      doc_id: "rebuilding",
      rebuilding: true,
      source_type: "url",
      source_uri: "https://example.com",
    }),
    false,
  );
  assert.equal(canRebuildDocument({ doc_id: "" }), false);
  assert.equal(canRebuildDocument(null), false);
});

test("canRebuildDocument rejects documents already tracked as rebuilding", () => {
  assert.equal(
    canRebuildDocument(
      {
        doc_id: "doc-1",
        source_type: "file",
        file_path: "/kb/files/doc-1/source.md",
      },
      { rebuildingDocIds: new Set(["doc-1"]) },
    ),
    false,
  );
  assert.equal(
    canRebuildDocument(
      {
        doc_id: "doc-2",
        source_type: "url",
        source_uri: "https://example.com",
      },
      { rebuildingDocIds: ["doc-2"] },
    ),
    false,
  );
});

test("canRebuildDocument requires a rebuildable source", () => {
  assert.equal(
    canRebuildDocument({
      doc_id: "missing-file",
      source_type: "file",
      file_path: "",
    }),
    false,
  );
  assert.equal(
    canRebuildDocument({
      doc_id: "missing-url",
      source_type: "url",
      source_uri: "",
    }),
    false,
  );
  assert.equal(
    canRebuildDocument({
      doc_id: "empty-import",
      source_type: "import",
      chunk_count: 0,
    }),
    false,
  );
  assert.equal(
    canRebuildDocument({ doc_id: "unknown", source_type: "database" }),
    false,
  );
});

test("hasRebuildableSource accepts supported source strategies", () => {
  assert.equal(
    hasRebuildableSource({
      source_type: "file",
      file_path: "/kb/files/doc-1/source.md",
    }),
    true,
  );
  assert.equal(
    hasRebuildableSource({
      source_type: "url",
      source_uri: "https://example.com",
    }),
    true,
  );
  assert.equal(
    hasRebuildableSource({
      source_type: "import",
      chunk_count: 2,
    }),
    true,
  );
});

test("getBatchRebuildState enforces capability limit and busy state", () => {
  assert.deepEqual(
    getBatchRebuildState({
      selectedIds: ["doc-1", "doc-2", "doc-2"],
      maxDocuments: 1,
    }),
    {
      selectedIds: ["doc-1", "doc-2"],
      selectedCount: 2,
      limit: 1,
      exceedsLimit: true,
      hasSelection: true,
      canRebuild: false,
    },
  );

  assert.equal(
    getBatchRebuildState({
      selectedIds: ["doc-1"],
      maxDocuments: 1,
      busy: true,
    }).canRebuild,
    false,
  );
});

test("getBatchRebuildState filters selected documents without rebuildable sources", () => {
  assert.deepEqual(
    getBatchRebuildState({
      selectedIds: ["file-doc", "url-doc", "empty-import", "unknown-doc"],
      documents: [
        {
          doc_id: "file-doc",
          source_type: "file",
          file_path: "/kb/files/file-doc/source.md",
        },
        {
          doc_id: "url-doc",
          source_type: "url",
          source_uri: "https://example.com",
        },
        {
          doc_id: "empty-import",
          source_type: "import",
          chunk_count: 0,
        },
        {
          doc_id: "unknown-doc",
          source_type: "database",
        },
      ],
    }),
    {
      selectedIds: ["file-doc", "url-doc"],
      selectedCount: 2,
      limit: null,
      exceedsLimit: false,
      hasSelection: true,
      canRebuild: true,
    },
  );
});

test("getBatchRebuildState preserves ids when document details are unavailable", () => {
  assert.deepEqual(
    getBatchRebuildState({
      selectedIds: ["doc-1"],
      documents: [],
    }),
    {
      selectedIds: ["doc-1"],
      selectedCount: 1,
      limit: null,
      exceedsLimit: false,
      hasSelection: true,
      canRebuild: true,
    },
  );
});

test("getBatchRebuildState keeps selection visible when feature is disabled", () => {
  assert.deepEqual(
    getBatchRebuildState({
      selectedIds: ["doc-1"],
      enabled: false,
    }),
    {
      selectedIds: ["doc-1"],
      selectedCount: 1,
      limit: null,
      exceedsLimit: false,
      hasSelection: true,
      canRebuild: false,
    },
  );
});

test("isBatchSelectableDocument rejects transient document rows", () => {
  assert.equal(isBatchSelectableDocument({ doc_id: "ready" }), true);
  assert.equal(
    isBatchSelectableDocument({ doc_id: "uploading", uploading: true }),
    false,
  );
  assert.equal(
    isBatchSelectableDocument({ doc_id: "rebuilding", rebuilding: true }),
    false,
  );
  assert.equal(isBatchSelectableDocument({ doc_id: "" }), false);
});

test("normalizeSelectedDocumentIds keeps unique selectable ids", () => {
  const documents = [
    { doc_id: "doc-1" },
    { doc_id: "doc-2" },
    { doc_id: "uploading", uploading: true },
  ];

  assert.deepEqual(
    normalizeSelectedDocumentIds(
      ["doc-1", { doc_id: "doc-2" }, "doc-2", "uploading", "missing"],
      documents,
    ),
    ["doc-1", "doc-2"],
  );
});

test("getSelectableDocumentIds returns only persistent rows", () => {
  assert.deepEqual(
    getSelectableDocumentIds([
      { doc_id: "doc-1" },
      { doc_id: "doc-2", disabled: true },
      { doc_id: "doc-3", rebuilding: true },
      { doc_id: "doc-4", uploading: true },
    ]),
    ["doc-1"],
  );
});

test("getBatchDeleteState enforces capability limit and busy state", () => {
  const documents = [{ doc_id: "doc-1" }, { doc_id: "doc-2" }];

  assert.deepEqual(
    getBatchDeleteState({
      selected: ["doc-1", "doc-2"],
      documents,
      maxDocuments: 1,
    }),
    {
      selectedIds: ["doc-1", "doc-2"],
      selectedCount: 2,
      limit: 1,
      exceedsLimit: true,
      hasSelection: true,
      canDelete: false,
    },
  );

  assert.equal(
    getBatchDeleteState({
      selected: ["doc-1"],
      documents,
      maxDocuments: 1,
      busy: true,
    }).canDelete,
    false,
  );
});

test("getBatchDeleteState reports empty selections", () => {
  assert.deepEqual(
    getBatchDeleteState({
      selected: [],
      documents: [{ doc_id: "doc-1" }],
      maxDocuments: 10,
    }),
    {
      selectedIds: [],
      selectedCount: 0,
      limit: 10,
      exceedsLimit: false,
      hasSelection: false,
      canDelete: false,
    },
  );
});

test("getBatchDeleteState keeps selection visible when feature is disabled", () => {
  assert.deepEqual(
    getBatchDeleteState({
      selected: ["doc-1"],
      documents: [{ doc_id: "doc-1" }],
      enabled: false,
    }),
    {
      selectedIds: ["doc-1"],
      selectedCount: 1,
      limit: null,
      exceedsLimit: false,
      hasSelection: true,
      canDelete: false,
    },
  );
});

const labels = {
  document: "Document",
  documentId: "Document ID",
  stage: "Stage",
  message: "Message",
  unknownStage: "Unknown stage",
  noErrorMessage: "No error message",
};

test("isFailedDocument checks persistent failed document status", () => {
  assert.equal(isFailedDocument({ status: "failed" }), true);
  assert.equal(isFailedDocument({ status: "ready" }), false);
  assert.equal(isFailedDocument(null), false);
});

test("getDocumentFailureSummary combines stage and message", () => {
  assert.equal(
    getDocumentFailureSummary(
      {
        status: "failed",
        error_stage: "parsing",
        error_message: "cannot parse pdf",
      },
      labels,
    ),
    "parsing: cannot parse pdf",
  );
});

test("getDocumentFailureSummary falls back when diagnostics are missing", () => {
  assert.equal(
    getDocumentFailureSummary({ status: "failed" }, labels),
    "Unknown stage: No error message",
  );
  assert.equal(getDocumentFailureSummary({ status: "ready" }, labels), "");
});

test("buildDocumentFailureText includes stable copyable fields", () => {
  assert.equal(
    buildDocumentFailureText(
      {
        doc_name: "broken.pdf",
        doc_id: "doc-1",
        error_stage: "embedding",
        error_message: "provider failed",
      },
      labels,
    ),
    [
      "Document: broken.pdf",
      "Document ID: doc-1",
      "Stage: embedding",
      "Message: provider failed",
    ].join("\n"),
  );
});

test("buildDocumentFailureText falls back to no error message", () => {
  assert.equal(buildDocumentFailureText({}, labels), "No error message");
});

test("buildDocumentListParams includes active document filters", () => {
  assert.deepEqual(
    buildDocumentListParams({
      kbId: "kb-1",
      page: 2,
      pageSize: 25,
      search: " alpha ",
      status: "ready",
      sourceType: "file",
      allowedStatuses: ["ready", "failed"],
      allowedSourceTypes: ["file", "url"],
    }),
    {
      kb_id: "kb-1",
      page: 2,
      page_size: 25,
      search: "alpha",
      status: "ready",
      source_type: "file",
    },
  );
});

test("buildDocumentListParams omits empty document filters", () => {
  assert.deepEqual(
    buildDocumentListParams({
      kbId: "kb-1",
      page: 1,
      pageSize: 10,
      search: "   ",
      status: null,
      sourceType: undefined,
    }),
    {
      kb_id: "kb-1",
      page: 1,
      page_size: 10,
      search: undefined,
      status: undefined,
      source_type: undefined,
    },
  );
});

test("buildDocumentListParams drops stale values when capabilities are known", () => {
  assert.deepEqual(
    buildDocumentListParams({
      kbId: "kb-1",
      page: 1,
      pageSize: 10,
      status: "archived",
      sourceType: "api",
      allowedStatuses: ["ready", "failed"],
      allowedSourceTypes: ["file", "url"],
    }),
    {
      kb_id: "kb-1",
      page: 1,
      page_size: 10,
      search: undefined,
      status: undefined,
      source_type: undefined,
    },
  );
});

test("buildDocumentListParams keeps filters before capabilities load", () => {
  assert.deepEqual(
    buildDocumentListParams({
      kbId: "kb-1",
      page: 1,
      pageSize: 10,
      status: "ready",
      sourceType: "url",
    }),
    {
      kb_id: "kb-1",
      page: 1,
      page_size: 10,
      search: undefined,
      status: "ready",
      source_type: "url",
    },
  );
});

test("createDocumentChunkRouteLocation includes chunkId when available", () => {
  assert.deepEqual(
    createDocumentChunkRouteLocation({
      kbId: "kb-1",
      docId: "doc-1",
      chunkId: "chunk-1",
    }),
    {
      name: "NativeDocumentDetail",
      params: { kbId: "kb-1", docId: "doc-1" },
      query: { chunkId: "chunk-1" },
    },
  );
});

test("createDocumentChunkRouteLocation omits empty chunkId", () => {
  assert.deepEqual(
    createDocumentChunkRouteLocation({
      kbId: "kb-1",
      docId: "doc-1",
      chunkId: "",
    }),
    {
      name: "NativeDocumentDetail",
      params: { kbId: "kb-1", docId: "doc-1" },
    },
  );
});

test("getFocusedChunkId trims string query values and rejects arrays", () => {
  assert.equal(getFocusedChunkId({ chunkId: " chunk-1 " }), "chunk-1");
  assert.equal(getFocusedChunkId({ chunkId: ["chunk-1"] }), "");
  assert.equal(getFocusedChunkId({ chunkId: "   " }), "");
});

test("removeFocusedChunkQuery preserves unrelated query keys", () => {
  const query = { chunkId: "chunk-1", tab: "documents", page: "2" };

  assert.deepEqual(removeFocusedChunkQuery(query), {
    tab: "documents",
    page: "2",
  });
  assert.deepEqual(query, { chunkId: "chunk-1", tab: "documents", page: "2" });
});

test("countUploadingDocuments counts only active upload placeholders", () => {
  assert.equal(
    countUploadingDocuments([
      { doc_id: "ready" },
      { doc_id: "uploading-1", uploading: true },
      { doc_id: "failed", uploading: false },
      { doc_id: "uploading-2", uploading: true },
    ]),
    2,
  );
});

test("buildDocumentDisplayTotals adds upload placeholders to backend totals", () => {
  assert.deepEqual(
    buildDocumentDisplayTotals({
      matchedTotal: 4,
      documentCount: 10,
      uploadingCount: 3,
    }),
    {
      filteredTotal: 7,
      documentCount: 13,
    },
  );
});

test("buildDocumentDisplayTotals falls back to backend total metadata", () => {
  assert.deepEqual(
    buildDocumentDisplayTotals({
      total: 5,
      uploadingCount: 2,
    }),
    {
      filteredTotal: 7,
      documentCount: 7,
    },
  );
});

test("buildDocumentDisplayTotals clamps invalid totals instead of drifting", () => {
  assert.deepEqual(
    buildDocumentDisplayTotals({
      matchedTotal: -4,
      documentCount: Number.NaN,
      uploadingCount: 2.9,
    }),
    {
      filteredTotal: 2,
      documentCount: 2,
    },
  );
});

test("markDocumentRebuildStarted marks only the requested document", () => {
  assert.deepEqual(
    markDocumentRebuildStarted(
      [
        { doc_id: "doc-1", doc_name: "first.md" },
        { doc_id: "doc-2", doc_name: "second.md" },
      ],
      "doc-2",
      "task-1",
    ),
    [
      { doc_id: "doc-1", doc_name: "first.md" },
      {
        doc_id: "doc-2",
        doc_name: "second.md",
        rebuilding: true,
        taskId: "task-1",
        uploadProgress: {
          stage: "waiting",
          current: 0,
          total: 100,
        },
      },
    ],
  );
});

test("markDocumentsRebuildStarted marks selected documents with one task", () => {
  assert.deepEqual(
    markDocumentsRebuildStarted(
      [
        { doc_id: "doc-1", doc_name: "first.md", selectable: true },
        { doc_id: "doc-2", doc_name: "second.md", selectable: true },
        { doc_id: "doc-3", doc_name: "third.md", selectable: true },
      ],
      ["doc-1", "doc-3"],
      "task-1",
    ),
    [
      {
        doc_id: "doc-1",
        doc_name: "first.md",
        selectable: false,
        rebuilding: true,
        taskId: "task-1",
        uploadProgress: {
          stage: "waiting",
          current: 0,
          total: 100,
        },
      },
      { doc_id: "doc-2", doc_name: "second.md", selectable: true },
      {
        doc_id: "doc-3",
        doc_name: "third.md",
        selectable: false,
        rebuilding: true,
        taskId: "task-1",
        uploadProgress: {
          stage: "waiting",
          current: 0,
          total: 100,
        },
      },
    ],
  );
});

test("applyDocumentTaskProgress updates active rebuild documents", () => {
  assert.deepEqual(
    applyDocumentTaskProgress(
      [
        {
          doc_id: "doc-1",
          rebuilding: true,
          taskId: "task-1",
          uploadProgress: { stage: "waiting", current: 0, total: 100 },
        },
      ],
      "task-1",
      { stage: "embedding", current: 3, total: 8 },
    ),
    [
      {
        doc_id: "doc-1",
        rebuilding: true,
        taskId: "task-1",
        uploadProgress: { stage: "embedding", current: 3, total: 8 },
      },
    ],
  );
});

test("applyDocumentTaskProgress updates only the matching upload placeholder index", () => {
  assert.deepEqual(
    applyDocumentTaskProgress(
      [
        {
          doc_id: "uploading_task-1_0",
          uploading: true,
          taskId: "task-1",
          uploadProgress: { stage: "waiting", current: 0, total: 100 },
        },
        {
          doc_id: "uploading_task-1_1",
          uploading: true,
          taskId: "task-1",
          uploadProgress: { stage: "waiting", current: 0, total: 100 },
        },
      ],
      "task-1",
      { file_index: 1, stage: "chunking", current: 2, total: 5 },
    ),
    [
      {
        doc_id: "uploading_task-1_0",
        uploading: true,
        taskId: "task-1",
        uploadProgress: { stage: "waiting", current: 0, total: 100 },
      },
      {
        doc_id: "uploading_task-1_1",
        uploading: true,
        taskId: "task-1",
        uploadProgress: { stage: "chunking", current: 2, total: 5 },
      },
    ],
  );
});

test("clearDocumentTaskState removes upload placeholders but keeps rebuilt rows", () => {
  assert.deepEqual(
    clearDocumentTaskState(
      [
        {
          doc_id: "uploading_task-1_0",
          uploading: true,
          taskId: "task-1",
        },
        {
          doc_id: "doc-1",
          doc_name: "first.md",
          rebuilding: true,
          taskId: "task-1",
          uploadProgress: { stage: "embedding", current: 1, total: 2 },
        },
      ],
      "task-1",
    ),
    [
      {
        doc_id: "doc-1",
        doc_name: "first.md",
      },
    ],
  );
});

test("applyActiveRebuildState preserves rebuild state after list reload", () => {
  assert.deepEqual(
    applyActiveRebuildState(
      [{ doc_id: "doc-1", doc_name: "fresh.md", chunk_count: 3 }],
      [
        {
          doc_id: "doc-1",
          doc_name: "old.md",
          rebuilding: true,
          taskId: "task-1",
          uploadProgress: { stage: "rebuilding", current: 20, total: 100 },
        },
      ],
    ),
    [
      {
        doc_id: "doc-1",
        doc_name: "fresh.md",
        chunk_count: 3,
        rebuilding: true,
        taskId: "task-1",
        uploadProgress: { stage: "rebuilding", current: 20, total: 100 },
      },
    ],
  );
});

test("formatTitlePath joins non-empty title path segments", () => {
  assert.equal(
    formatTitlePath(["Guide", "", "Plugins", null]),
    "Guide > Plugins",
  );
});

test("buildRetrievalSourceChips exposes source metadata chips", () => {
  assert.deepEqual(
    buildRetrievalSourceChips({
      title_path: ["Guide", "Plugins"],
      page_number: 0,
      section_index: 0,
      parent_chunk_id: "parent-1",
    }),
    [
      {
        key: "title",
        icon: "mdi-format-header-pound",
        label: "Guide > Plugins",
      },
      {
        key: "page",
        icon: "mdi-book-open-page-variant",
        labelKey: "retrieval.sourcePage",
        params: { page: 0 },
      },
      {
        key: "section",
        icon: "mdi-file-tree",
        labelKey: "retrieval.sourceSection",
        params: { index: 0 },
      },
      {
        key: "parent",
        icon: "mdi-family-tree",
        labelKey: "retrieval.sourceParentChunk",
        params: { id: "parent-1" },
      },
    ],
  );
});

test("buildRetrievalSourceChips skips empty source metadata", () => {
  assert.deepEqual(buildRetrievalSourceChips({}), []);
  assert.deepEqual(buildRetrievalSourceChips(null), []);
});

test("buildTraceScoreChips exposes finite trace score fields", () => {
  assert.deepEqual(
    buildTraceScoreChips({
      dense_score: 0.91,
      sparse_score: 0,
      rrf_score: 0.032,
      rerank_score: 0.77,
    }),
    [
      {
        key: "dense_score",
        labelKey: "retrieval.traceDenseScore",
        value: 0.91,
      },
      {
        key: "sparse_score",
        labelKey: "retrieval.traceSparseScore",
        value: 0,
      },
      {
        key: "rrf_score",
        labelKey: "retrieval.traceRrfScore",
        value: 0.032,
      },
      {
        key: "rerank_score",
        labelKey: "retrieval.traceRerankScore",
        value: 0.77,
      },
    ],
  );
});

test("buildTraceScoreChips skips missing and invalid values", () => {
  assert.deepEqual(
    buildTraceScoreChips({
      dense_score: null,
      sparse_score: Number.NaN,
      rrf_score: "0.032",
      rerank_score: undefined,
    }),
    [],
  );
});

test("getRepairableConsistencyTypes includes orphan vectors", () => {
  const report = {
    summary: {
      orphan_vectors: 2,
      chunk_count_mismatches: 0,
    },
    issues: {
      orphan_vectors: [{ doc_id: "doc-gone" }],
      chunk_count_mismatches: [],
    },
  };

  assert.deepEqual(getRepairableConsistencyTypes(report), ["orphan_vectors"]);
  assert.equal(hasRepairableConsistencyIssues(report), true);
});

test("getRepairableConsistencyTypes includes only chunk mismatches with extra indexed chunks", () => {
  const report = {
    summary: {
      orphan_vectors: 0,
      chunk_count_mismatches: 2,
    },
    issues: {
      orphan_vectors: [],
      chunk_count_mismatches: [
        {
          doc_id: "doc-missing-index",
          expected_chunk_count: 3,
          actual_chunk_count: 1,
        },
        {
          doc_id: "doc-extra-indexed",
          expected_chunk_count: 1,
          actual_chunk_count: 2,
        },
      ],
    },
  };

  assert.deepEqual(getRepairableConsistencyTypes(report), [
    "chunk_count_mismatches",
  ]);
});

test("getRepairableConsistencyTypes ignores issues that require rebuild or manual action", () => {
  const report = {
    summary: {
      orphan_vectors: 0,
      missing_vectors: 1,
      chunk_count_mismatches: 1,
      missing_source_files: 1,
    },
    issues: {
      missing_vectors: [{ doc_id: "doc-missing-index" }],
      missing_source_files: [{ doc_id: "doc-missing-file" }],
      chunk_count_mismatches: [
        {
          doc_id: "doc-missing-index",
          expected_chunk_count: 3,
          actual_chunk_count: 0,
        },
      ],
    },
  };

  assert.deepEqual(getRepairableConsistencyTypes(report), []);
  assert.equal(hasRepairableConsistencyIssues(report), false);
});

test("isKnowledgeBaseFeatureEnabled keeps features enabled before capabilities load", () => {
  assert.equal(isKnowledgeBaseFeatureEnabled(null, "url_import"), true);
  assert.equal(isKnowledgeBaseFeatureEnabled({}, "document_rebuild"), true);
});

test("isKnowledgeBaseFeatureEnabled follows explicit backend feature flags", () => {
  const capabilities = {
    features: {
      url_import: false,
      document_rebuild: true,
    },
  };

  assert.equal(
    isKnowledgeBaseFeatureEnabled(capabilities, "url_import"),
    false,
  );
  assert.equal(
    isKnowledgeBaseFeatureEnabled(capabilities, "document_rebuild"),
    true,
  );
});

test("isKnowledgeBaseFeatureEnabled treats missing feature keys as compatible", () => {
  const capabilities = {
    features: {
      url_import: false,
    },
  };

  assert.equal(isKnowledgeBaseFeatureEnabled(capabilities, "kb_rebuild"), true);
});

test("getKnowledgeBaseListStats prefers refreshed backend statistics", () => {
  assert.deepEqual(
    getKnowledgeBaseListStats({
      doc_count: 1,
      chunk_count: 2,
      document_count: 3,
      indexed_chunk_count: 4,
    }),
    {
      documentCount: 3,
      chunkCount: 4,
    },
  );
});

test("getKnowledgeBaseListStats preserves zero refreshed values", () => {
  assert.deepEqual(
    getKnowledgeBaseListStats({
      doc_count: 8,
      chunk_count: 9,
      document_count: 0,
      indexed_chunk_count: 0,
    }),
    {
      documentCount: 0,
      chunkCount: 0,
    },
  );
});

test("getKnowledgeBaseListStats falls back to legacy counters", () => {
  assert.deepEqual(
    getKnowledgeBaseListStats({
      doc_count: 5,
      chunk_count: 12,
    }),
    {
      documentCount: 5,
      chunkCount: 12,
    },
  );
});

test("buildKnowledgeBaseListParams includes refresh stats only when requested", () => {
  assert.deepEqual(
    buildKnowledgeBaseListParams({
      page: 2,
      pageSize: 20,
      refreshStats: true,
    }),
    {
      page: 2,
      page_size: 20,
      refresh_stats: "true",
    },
  );
  assert.deepEqual(
    buildKnowledgeBaseListParams({
      page: 1,
      pageSize: 20,
      refreshStats: false,
    }),
    {
      page: 1,
      page_size: 20,
    },
  );
});

test("loadKnowledgeBaseListPages loads every page and preserves request params", async () => {
  const requests = [];
  const allItems = [
    { kb_id: "kb-1" },
    { kb_id: "kb-2" },
    { kb_id: "kb-3" },
    { kb_id: "kb-4" },
    { kb_id: "kb-5" },
  ];

  const items = await loadKnowledgeBaseListPages({
    fetchPage: async (params) => {
      requests.push(params);
      const start = (params.page - 1) * params.page_size;
      return {
        status: "ok",
        data: {
          items: allItems.slice(start, start + params.page_size),
          page: params.page,
          page_size: params.page_size,
          total: allItems.length,
        },
      };
    },
    pageSize: 2,
    refreshStats: true,
  });

  assert.deepEqual(items, allItems);
  assert.deepEqual(requests, [
    { page: 1, page_size: 2, refresh_stats: "true" },
    { page: 2, page_size: 2, refresh_stats: "true" },
    { page: 3, page_size: 2, refresh_stats: "true" },
  ]);
});

test("loadKnowledgeBaseListPages raises backend errors", async () => {
  await assert.rejects(
    () =>
      loadKnowledgeBaseListPages({
        fetchPage: async () => ({
          status: "error",
          message: "database unavailable",
        }),
        pageSize: 20,
      }),
    /database unavailable/,
  );
});

test("normalizePaginatedPayload keeps items and backend pagination metadata", () => {
  assert.deepEqual(
    normalizePaginatedPayload({
      items: ["a", "b"],
      page: 2,
      page_size: 50,
      total: 120,
    }),
    {
      items: ["a", "b"],
      page: 2,
      pageSize: 50,
      total: 120,
    },
  );
});

test("fetchAllPaginatedItems loads every backend page until total is reached", async () => {
  const requests = [];
  const items = await fetchAllPaginatedItems(
    async ({ page, pageSize }) => {
      requests.push({ page, pageSize });
      const allItems = ["a", "b", "c", "d", "e"];
      const start = (page - 1) * pageSize;
      return {
        items: allItems.slice(start, start + pageSize),
        page,
        page_size: pageSize,
        total: allItems.length,
      };
    },
    { pageSize: 2 },
  );

  assert.deepEqual(items, ["a", "b", "c", "d", "e"]);
  assert.deepEqual(requests, [
    { page: 1, pageSize: 2 },
    { page: 2, pageSize: 2 },
    { page: 3, pageSize: 2 },
  ]);
});

test("fetchAllPaginatedItems stops after one page when total is omitted", async () => {
  const items = await fetchAllPaginatedItems(async () => ({
    items: ["a", "b"],
    page: 1,
    page_size: 100,
  }));

  assert.deepEqual(items, ["a", "b"]);
});

test("fetchAllPaginatedItems fails when backend pagination does not advance", async () => {
  await assert.rejects(
    () =>
      fetchAllPaginatedItems(async ({ page, pageSize }) => ({
        items: [`item-${page}`],
        page: 1,
        page_size: pageSize,
        total: 100,
      })),
    /Pagination did not advance/,
  );
});

test("getKnowledgeBasePaginationConfig reads backend pagination capabilities", () => {
  assert.deepEqual(
    getKnowledgeBasePaginationConfig({
      pagination: {
        document_page_size_options: [15, 30],
        chunk_page_size_options: [20, 40],
        default_kb_page_size: 25,
        default_document_page_size: 30,
        default_chunk_page_size: 20,
        bulk_page_size: 250,
      },
    }),
    {
      documentPageSizeOptions: [15, 30],
      chunkPageSizeOptions: [20, 40],
      defaultKbPageSize: 25,
      defaultDocumentPageSize: 30,
      defaultChunkPageSize: 20,
      bulkPageSize: 250,
    },
  );
});

test("getKnowledgeBasePaginationConfig falls back to centralized defaults", () => {
  assert.deepEqual(getKnowledgeBasePaginationConfig(null), {
    documentPageSizeOptions: DEFAULT_DOCUMENT_PAGE_SIZE_OPTIONS,
    chunkPageSizeOptions: DEFAULT_CHUNK_PAGE_SIZE_OPTIONS,
    defaultKbPageSize: DEFAULT_KB_PAGE_SIZE,
    defaultDocumentPageSize: DEFAULT_DOCUMENT_PAGE_SIZE_OPTIONS[0],
    defaultChunkPageSize: DEFAULT_CHUNK_PAGE_SIZE_OPTIONS[0],
    bulkPageSize: DEFAULT_BULK_PAGE_SIZE,
  });
});

test("getKnowledgeBasePaginationConfig sanitizes invalid backend values", () => {
  assert.deepEqual(
    getKnowledgeBasePaginationConfig({
      pagination: {
        document_page_size_options: [0, 25, 25, "50", -1],
        chunk_page_size_options: [],
        default_kb_page_size: "bad",
        default_document_page_size: "bad",
        default_chunk_page_size: 0,
        bulk_page_size: -10,
      },
    }),
    {
      documentPageSizeOptions: [25, 50],
      chunkPageSizeOptions: DEFAULT_CHUNK_PAGE_SIZE_OPTIONS,
      defaultKbPageSize: DEFAULT_KB_PAGE_SIZE,
      defaultDocumentPageSize: 25,
      defaultChunkPageSize: DEFAULT_CHUNK_PAGE_SIZE_OPTIONS[0],
      bulkPageSize: DEFAULT_BULK_PAGE_SIZE,
    },
  );
});

test("getKnowledgeBasePaginationConfig keeps defaults inside option lists", () => {
  assert.deepEqual(
    getKnowledgeBasePaginationConfig({
      pagination: {
        document_page_size_options: [20, 40],
        chunk_page_size_options: [25, 50],
        default_document_page_size: 10,
        default_chunk_page_size: 10,
      },
    }),
    {
      documentPageSizeOptions: [20, 40],
      chunkPageSizeOptions: [25, 50],
      defaultKbPageSize: DEFAULT_KB_PAGE_SIZE,
      defaultDocumentPageSize: 20,
      defaultChunkPageSize: 25,
      bulkPageSize: DEFAULT_BULK_PAGE_SIZE,
    },
  );
});

test("getKnowledgeBaseTaskTypeIcon maps known task types", () => {
  assert.equal(getKnowledgeBaseTaskTypeIcon("upload"), "mdi-upload");
  assert.equal(getKnowledgeBaseTaskTypeIcon("document_rebuild"), "mdi-refresh");
  assert.equal(
    getKnowledgeBaseTaskTypeIcon("document_batch_rebuild"),
    "mdi-refresh",
  );
  assert.equal(getKnowledgeBaseTaskTypeIcon("kb_rebuild"), "mdi-database-sync");
  assert.equal(getKnowledgeBaseTaskTypeIcon("custom"), "mdi-progress-clock");
});

test("getKnowledgeBaseTaskStatusColor maps known statuses", () => {
  assert.equal(getKnowledgeBaseTaskStatusColor("pending"), "grey");
  assert.equal(getKnowledgeBaseTaskStatusColor("processing"), "warning");
  assert.equal(getKnowledgeBaseTaskStatusColor("completed"), "success");
  assert.equal(getKnowledgeBaseTaskStatusColor("partial_failed"), "warning");
  assert.equal(getKnowledgeBaseTaskStatusColor("failed"), "error");
  assert.equal(getKnowledgeBaseTaskStatusColor("custom"), "grey");
});

test("getKnowledgeBaseTaskProgress prefers nested persisted progress", () => {
  assert.deepEqual(
    getKnowledgeBaseTaskProgress({
      progress_stage: "waiting",
      progress_current: 0,
      progress_total: 100,
      progress: {
        stage: "embedding",
        current: 4,
        total: 10,
      },
    }),
    {
      stage: "embedding",
      current: 4,
      total: 10,
    },
  );
});

test("getKnowledgeBaseTaskProgress falls back to flattened task progress", () => {
  assert.deepEqual(
    getKnowledgeBaseTaskProgress({
      progress_stage: "rebuilding",
      progress_current: 0,
      progress_total: 0,
    }),
    {
      stage: "rebuilding",
      current: 0,
      total: 1,
    },
  );
});

test("getKnowledgeBaseTaskErrorText handles strings, objects, and fallbacks", () => {
  assert.equal(getKnowledgeBaseTaskErrorText("boom"), "boom");
  assert.equal(
    getKnowledgeBaseTaskErrorText({ message: "parse failed" }),
    "parse failed",
  );
  assert.equal(
    getKnowledgeBaseTaskErrorText({ stage: "embedding" }),
    '{"stage":"embedding"}',
  );
  assert.equal(getKnowledgeBaseTaskErrorText(null, "none"), "none");
});

const currentDir = dirname(fileURLToPath(import.meta.url));
const localeRoot = join(currentDir, "../src/i18n/locales");
const knowledgeBaseViewRoot = join(currentDir, "../src/views/knowledge-base");

const locales = ["zh-CN", "en-US", "ru-RU"];
const knowledgeBaseModules = [
  "features/knowledge-base/index.json",
  "features/knowledge-base/detail.json",
  "features/knowledge-base/document.json",
  "features/alkaid/knowledge-base.json",
];

const allowedRussianEnglishOnlyValues = new Set([
  "API",
  "Context Recall",
  "MRR",
  "nDCG",
  "Precision",
  "Recall",
  "Rerank",
  "Tavily API Key",
  "URL",
  "tvly-...",
]);

function readJson(relativePath) {
  const content = readFileSync(relativePath, "utf8").replace(/^\uFEFF/, "");
  return JSON.parse(content);
}

function flattenKeys(value, prefix = "") {
  return Object.entries(value).flatMap(([key, nestedValue]) => {
    const nextKey = prefix ? `${prefix}.${key}` : key;
    if (
      nestedValue &&
      typeof nestedValue === "object" &&
      !Array.isArray(nestedValue)
    ) {
      return flattenKeys(nestedValue, nextKey);
    }
    return [nextKey];
  });
}

function flattenStringValues(value, prefix = "") {
  return Object.entries(value).flatMap(([key, nestedValue]) => {
    const nextKey = prefix ? `${prefix}.${key}` : key;
    if (
      nestedValue &&
      typeof nestedValue === "object" &&
      !Array.isArray(nestedValue)
    ) {
      return flattenStringValues(nestedValue, nextKey);
    }
    return [{ key: nextKey, value: nestedValue }];
  });
}

function collectVueFiles(directory) {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    const stat = statSync(path);
    if (stat.isDirectory()) {
      return collectVueFiles(path);
    }
    return path.endsWith(".vue") ? [path] : [];
  });
}

test("knowledge base locale modules keep matching key sets", () => {
  for (const modulePath of knowledgeBaseModules) {
    const localeKeys = new Map(
      locales.map((locale) => {
        const data = readJson(join(localeRoot, locale, modulePath));
        return [locale, new Set(flattenKeys(data))];
      }),
    );
    const allKeys = new Set(
      [...localeKeys.values()].flatMap((keys) => [...keys]),
    );

    for (const locale of locales) {
      const missingKeys = [...allKeys].filter(
        (key) => !localeKeys.get(locale).has(key),
      );
      assert.deepEqual(
        missingKeys,
        [],
        `${locale} is missing keys in ${modulePath}`,
      );
    }
  }
});

test("Russian knowledge base locale has no untranslated English-only UI phrases", () => {
  const violations = [];

  for (const modulePath of knowledgeBaseModules) {
    const data = readJson(join(localeRoot, "ru-RU", modulePath));
    for (const { key, value } of flattenStringValues(data)) {
      if (typeof value !== "string") {
        continue;
      }
      const hasLatin = /[A-Za-z]/.test(value);
      const hasCyrillic = /[\u0400-\u04FF]/.test(value);
      if (
        hasLatin &&
        !hasCyrillic &&
        !allowedRussianEnglishOnlyValues.has(value)
      ) {
        violations.push(`${modulePath}:${key}=${value}`);
      }
    }
  }

  assert.deepEqual(violations, []);
});

test("knowledge base Vue templates avoid hardcoded visible UI attributes", () => {
  const violations = [];
  const visibleAttributePattern =
    /\s(?<![:@#\w-])(label|placeholder|title|text|message)="([^"]*[A-Za-z][^"]*)"/g;

  for (const vueFile of collectVueFiles(knowledgeBaseViewRoot)) {
    const content = readFileSync(vueFile, "utf8");
    for (const match of content.matchAll(visibleAttributePattern)) {
      violations.push(`${vueFile}:${match[1]}="${match[2]}"`);
    }
  }

  assert.deepEqual(violations, []);
});
