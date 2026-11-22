import { shallowRef } from "vue";

import { providerApi } from "@/api/v1";
import type {
  ProviderMetadataSource,
  ProviderModelMetadata,
} from "@/utils/providerMetadata";

export interface ProviderConfig extends ProviderMetadataSource {
  id: string;
  type?: string;
  provider_type?: string;
  provider_source_id?: string;
  enable?: boolean;
  api_base?: string;
  embedding_api_base?: string;
  rerank_api_base?: string;
  gemini_tts_api_base?: string;
}

export function useProviderCatalog() {
  const providers = shallowRef<ProviderConfig[]>([]);
  const modelMetadata = shallowRef<Record<string, ProviderModelMetadata>>({});
  let requestId = 0;

  async function load(providerType: string) {
    const id = ++requestId;
    const { data } = await providerApi.listByProviderType(providerType);
    if (id !== requestId || data.status !== "ok") return false;

    providers.value = ((data.data || []) as unknown as ProviderConfig[]).filter(
      (provider) => provider.enable !== false,
    );
    modelMetadata.value = (data.model_metadata || {}) as Record<
      string,
      ProviderModelMetadata
    >;
    return true;
  }

  function reset() {
    ++requestId;
    providers.value = [];
    modelMetadata.value = {};
  }

  return { providers, modelMetadata, load, reset };
}
