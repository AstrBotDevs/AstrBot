import { generatedQuery, openApiV1, providerConfig, typed } from './shared';
import type { AxiosResponse, EnabledPatch } from './shared';
import type {
  ApiEnvelope,
  OpenConfig,
  ProviderByIdData,
  ProviderByTypeEnvelope,
  ProviderEmbeddingDimensionData,
  ProviderListData,
  ProviderListParams,
  ProviderSchemaData,
  ProviderSourceModelsData,
  ProviderTestData,
} from './types';

type ProviderTypeList = NonNullable<ProviderListParams['provider_type']>;

export const providerApi = {
  schema() {
    return typed<ProviderSchemaData>(openApiV1.getProviderSchema());
  },
  sources() {
    return typed<{ provider_sources: OpenConfig[] }>(
      openApiV1.listProviderSources(),
    );
  },
  upsertSource(sourceId: string, config: OpenConfig, stepUp?: string) {
    return typed<OpenConfig>(
      openApiV1.upsertProviderSource({
        path: { source_id: sourceId },
        body: { config },
        headers: stepUp ? { 'X-AstrBot-Step-Up': stepUp } : undefined,
      }),
    );
  },
  deleteSource(sourceId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteProviderSource({ path: { source_id: sourceId } }),
    );
  },
  sourceModels(sourceId: string) {
    return typed<ProviderSourceModelsData>(
      openApiV1.listProviderSourceModels({
        path: { source_id: sourceId },
      }),
    );
  },
  list(params?: ProviderListParams) {
    return typed<ProviderListData>(
      openApiV1.listProviders({ query: generatedQuery(params) }),
    );
  },
  async listByProviderType(
    providerType: string,
  ): Promise<AxiosResponse<ProviderByTypeEnvelope>> {
    const providerTypes = normalizeProviderTypes(providerType);
    if (providerTypes.length === 0) {
      const response = await providerApi.list();
      return {
        ...response,
        data: {
          ...response.data,
          data: response.data.data.providers || [],
          model_metadata: response.data.data.model_metadata || {},
        },
      };
    }

    const responses = await Promise.all(
      providerTypes.map((type) => providerApi.list({ provider_type: type })),
    );
    const first = responses[0];
    const modelMetadata = responses.reduce<Record<string, unknown>>(
      (
        acc: Record<string, unknown>,
        response: AxiosResponse<ApiEnvelope<ProviderListData>>,
      ) => ({
        ...acc,
        ...(response.data.data.model_metadata || {}),
      }),
      {},
    );
    return {
      ...first,
      data: {
        ...first.data,
        data: responses.flatMap(
          (response: AxiosResponse<ApiEnvelope<ProviderListData>>) =>
            response.data.data.providers || [],
        ),
        model_metadata: modelMetadata,
      },
    };
  },
  create(config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.createProvider({ body: providerConfig(config) }),
    );
  },
  listBySource(
    sourceId: string,
    params?: Pick<ProviderListParams, 'provider_type'>,
  ) {
    return typed<{ providers: OpenConfig[] }>(
      openApiV1.listProvidersBySource({
        path: { source_id: sourceId },
        query: generatedQuery(params),
      }),
    );
  },
  createInSource(sourceId: string, config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.createProviderInSource({
        path: { source_id: sourceId },
        body: { config },
      }),
    );
  },
  get(providerId: string, merged = false) {
    return typed<ProviderByIdData>(
      openApiV1.getProvider({
        path: { provider_id: providerId },
        query: { merged },
      }),
    );
  },
  update(providerId: string, config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updateProvider({
        path: { provider_id: providerId },
        body: { config },
      }),
    );
  },
  setEnabled(providerId: string, payload: EnabledPatch) {
    return typed<OpenConfig>(
      openApiV1.setProviderEnabled({
        path: { provider_id: providerId },
        body: payload,
      }),
    );
  },
  delete(providerId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteProvider({ path: { provider_id: providerId } }),
    );
  },
  test(providerId: string) {
    return typed<ProviderTestData>(
      openApiV1.testProvider({ path: { provider_id: providerId } }),
    );
  },
  embeddingDimension(providerId: string, providerConfig?: OpenConfig) {
    return typed<ProviderEmbeddingDimensionData>(
      openApiV1.getProviderEmbeddingDimension({
        path: { provider_id: providerId },
        body: {
          ...(providerConfig ? { config: providerConfig } : {}),
        },
      }),
    );
  },
};

function normalizeProviderTypes(providerType: string): ProviderTypeList[] {
  return providerType
    .split(',')
    .map((value) => value.trim())
    .filter((value): value is ProviderTypeList => value.length > 0);
}
