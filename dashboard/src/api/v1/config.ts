import { generatedOptions, openApiV1, typed } from './shared';
import type {
  ConfigRoutesReplaceRequest,
  ConfigRouteUpsertRequest,
} from './shared';
import type { AxiosRequestConfig } from './shared';
import type { OpenConfig } from './types';

export const configProfileApi = {
  schema() {
    return typed<OpenConfig>(openApiV1.getConfigProfileSchema());
  },
  list() {
    return typed<{ info_list: OpenConfig[] }>(openApiV1.listConfigProfiles());
  },
  create(
    payload: { name?: string | null; config?: OpenConfig | null },
    requestConfig?: AxiosRequestConfig,
  ) {
    return typed<{ conf_id: string }>(
      openApiV1.createConfigProfile(
        generatedOptions(
          {
            body: {
              name: payload.name ?? undefined,
              config: payload.config ?? undefined,
            },
          },
          requestConfig,
        ),
      ),
    );
  },
  get(configId: string) {
    return typed<OpenConfig>(
      openApiV1.getConfigProfile({ path: { config_id: configId } }),
    );
  },
  update(
    configId: string,
    config: OpenConfig,
    requestConfig?: AxiosRequestConfig,
  ) {
    return typed<OpenConfig>(
      openApiV1.updateConfigProfileContent(
        generatedOptions(
          {
            path: { config_id: configId },
            body: config,
          },
          requestConfig,
        ),
      ),
    );
  },
  rename(configId: string, name: string | null) {
    return typed<OpenConfig>(
      openApiV1.renameConfigProfile({
        path: { config_id: configId },
        body: { name: name ?? '' },
      }),
    );
  },
  delete(configId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteConfigProfile({ path: { config_id: configId } }),
    );
  },
};

export const systemConfigApi = {
  schema() {
    return typed<OpenConfig>(openApiV1.getSystemConfigSchema());
  },
  get() {
    return typed<OpenConfig>(openApiV1.getSystemConfig());
  },
  runtime() {
    return typed<OpenConfig>(openApiV1.getSystemConfigRuntime());
  },
  update(config: OpenConfig, requestConfig?: AxiosRequestConfig) {
    return typed<OpenConfig>(
      openApiV1.updateSystemConfig(
        generatedOptions({ body: config }, requestConfig),
      ),
    );
  },
};

export const configRouteApi = {
  list() {
    return typed<{ routing?: Record<string, string> }>(
      openApiV1.listConfigRoutes(),
    );
  },
  replace(payload: ConfigRoutesReplaceRequest) {
    return typed<OpenConfig>(openApiV1.replaceConfigRoutes({ body: payload }));
  },
  upsert(umo: string, payload: ConfigRouteUpsertRequest) {
    return typed<OpenConfig>(
      openApiV1.upsertConfigRoute({ path: { umo }, body: payload }),
    );
  },
  delete(umo: string) {
    return typed<OpenConfig>(openApiV1.deleteConfigRoute({ path: { umo } }));
  },
};
