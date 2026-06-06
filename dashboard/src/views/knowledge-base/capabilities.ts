import { ref } from "vue";
import axios from "axios";

export interface KnowledgeBaseCapabilities {
  upload: {
    allowed_extensions: string[];
    max_file_size_bytes: number;
    max_files_per_upload: number;
  };
  defaults: {
    chunk_size: number;
    chunk_overlap: number;
    batch_size: number;
    tasks_limit: number;
    max_retries: number;
    top_k_dense: number;
    top_k_sparse: number;
    top_m_final: number;
    index_type: string;
  };
  limits: {
    max_retrieve_top_k: number;
    max_batch_delete_documents: number;
    max_batch_rebuild_documents: number;
  };
  pagination: {
    document_page_size_options: number[];
    chunk_page_size_options: number[];
    default_kb_page_size: number;
    default_document_page_size: number;
    default_chunk_page_size: number;
    bulk_page_size: number;
  };
  document_filters: {
    statuses: string[];
    source_types: string[];
  };
  features: {
    sparse_retrieval: boolean;
    rerank: boolean;
    url_import: boolean;
    document_rebuild: boolean;
    kb_rebuild: boolean;
    consistency_check: boolean;
    consistency_repair: boolean;
    batch_delete: boolean;
    batch_rebuild: boolean;
  };
}

const capabilities = ref<KnowledgeBaseCapabilities | null>(null);
const loading = ref(false);
let pendingRequest: Promise<KnowledgeBaseCapabilities | null> | null = null;

export const useKnowledgeBaseCapabilities = () => {
  const loadCapabilities = async () => {
    if (capabilities.value) {
      return capabilities.value;
    }
    if (pendingRequest) {
      return pendingRequest;
    }

    loading.value = true;
    pendingRequest = axios
      .get("/api/kb/capabilities")
      .then((response) => {
        if (response.data.status === "ok") {
          capabilities.value = response.data.data;
          return capabilities.value;
        }
        console.warn(
          "Failed to load knowledge base capabilities:",
          response.data,
        );
        return null;
      })
      .catch((error) => {
        console.warn("Failed to load knowledge base capabilities:", error);
        return null;
      })
      .finally(() => {
        loading.value = false;
        pendingRequest = null;
      });

    return pendingRequest;
  };

  return {
    capabilities,
    capabilitiesLoading: loading,
    loadCapabilities,
  };
};
