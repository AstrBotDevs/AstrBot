import type { Locale } from '@/i18n/types';

import {
  generatedFormData,
  generatedOptions,
  generatedQuery,
  openApiV1,
  typed,
} from './shared';
import type {
  BackupChunkUploadRequest,
  BackupExportRequest,
  BackupImportRequest,
  BackupRenameRequest,
  BackupUploadInitRequest,
  BackupUploadRequest,
  BackupUploadSessionRequest,
  GhproxyTestRequest,
  PipInstallRequest,
  TraceSettingsRequest,
  UpdateRequest,
} from './shared';
import type { AxiosRequestConfig } from './shared';
import type { AxiosResponse } from './shared';
import type {
  BackupListParams,
  BaseStatsData,
  OpenConfig,
  ProviderTokenStatsData,
  PublicVersionData,
  ReleaseItemData,
  T2iRuntimeStatsData,
  UpdateCheckData,
  UpdateProgressData,
  VersionData,
} from './types';

type StartTimeData = {
  start_time?: number | string | null;
};

export const traceApi = {
  getSettings() {
    return typed<TraceSettingsRequest>(openApiV1.getTraceSettings());
  },
  updateSettings(settings: TraceSettingsRequest) {
    return typed<OpenConfig>(openApiV1.updateTraceSettings({ body: settings }));
  },
};

export const updatesApi = {
  check() {
    return typed<UpdateCheckData>(openApiV1.checkUpdate());
  },
  releases() {
    return typed<ReleaseItemData[]>(openApiV1.listReleases());
  },
  core(payload?: UpdateRequest, requestConfig?: AxiosRequestConfig) {
    return typed<OpenConfig>(
      openApiV1.updateCore(generatedOptions({ body: payload }, requestConfig)),
    );
  },
  progress(taskId: string) {
    return typed<UpdateProgressData>(
      openApiV1.getUpdateProgress({ path: { task_id: taskId } }),
    );
  },
  installPip(payload: PipInstallRequest, requestConfig?: AxiosRequestConfig) {
    return typed<OpenConfig>(
      openApiV1.installPipPackage(
        generatedOptions({ body: payload }, requestConfig),
      ),
    );
  },
};

export const backupApi = {
  list(params?: BackupListParams) {
    return typed<OpenConfig>(
      openApiV1.listBackups({ query: generatedQuery(params) }),
    );
  },
  create(payload?: BackupExportRequest) {
    return typed<OpenConfig>(openApiV1.createBackup({ body: payload }));
  },
  progress(taskId: string) {
    return typed<OpenConfig>(
      openApiV1.getBackupProgress({ path: { task_id: taskId } }),
    );
  },
  upload(formData: FormData | BackupUploadRequest) {
    return typed<OpenConfig>(
      openApiV1.uploadBackup({
        body: generatedFormData(formData) as unknown as BackupUploadRequest,
      }),
    );
  },
  initUpload(payload: BackupUploadInitRequest) {
    return typed<OpenConfig>(openApiV1.initBackupUpload({ body: payload }));
  },
  uploadChunk(formData: FormData | BackupChunkUploadRequest) {
    return typed<OpenConfig>(
      openApiV1.uploadBackupChunk({
        body: generatedFormData(
          formData,
        ) as unknown as BackupChunkUploadRequest,
      }),
    );
  },
  completeUpload(payload: BackupUploadSessionRequest) {
    return typed<OpenConfig>(openApiV1.completeBackupUpload({ body: payload }));
  },
  abortUpload(payload: BackupUploadSessionRequest) {
    return typed<OpenConfig>(openApiV1.abortBackupUpload({ body: payload }));
  },
  check(filename: string) {
    return typed<OpenConfig>(openApiV1.checkBackup({ path: { filename } }));
  },
  importBackup(filename: string, confirmed = true) {
    const payload: BackupImportRequest = { confirmed };
    return typed<OpenConfig>(
      openApiV1.importBackup({
        path: { filename },
        body: payload,
      }),
    );
  },
  delete(filename: string) {
    return typed<OpenConfig>(openApiV1.deleteBackup({ path: { filename } }));
  },
  rename(filename: string, payload: BackupRenameRequest) {
    return typed<OpenConfig>(
      openApiV1.renameBackup({ path: { filename }, body: payload }),
    );
  },
  download(filename: string) {
    return openApiV1.downloadBackup({
      path: { filename },
      responseType: 'blob',
    }) as Promise<AxiosResponse<Blob>>;
  },
};

export const statsApi = {
  get(offsetSec?: number) {
    return typed<BaseStatsData>(
      openApiV1.getStats({
        query: offsetSec === undefined ? undefined : { offset_sec: offsetSec },
      }),
    );
  },
  providerTokens(days?: number) {
    return typed<ProviderTokenStatsData>(
      openApiV1.getProviderTokenStats({
        query: days === undefined ? undefined : { days },
      }),
    );
  },
  version(requestConfig?: AxiosRequestConfig) {
    return typed<VersionData>(
      openApiV1.getVersion(generatedOptions({}, requestConfig)),
    );
  },
  firstNotice(locale?: Locale) {
    return typed<{ content?: string | null }>(
      openApiV1.getFirstNotice({
        query: locale ? { locale } : undefined,
      }),
    );
  },
  testGhproxy(payload: GhproxyTestRequest) {
    return typed<{ latency?: number }>(
      openApiV1.testGhproxyConnection({ body: payload }),
    );
  },
  startTime(requestConfig?: AxiosRequestConfig) {
    return typed<StartTimeData>(
      openApiV1.getStartTime(generatedOptions({}, requestConfig)),
    );
  },
  t2iRuntime() {
    return typed<T2iRuntimeStatsData>(openApiV1.getT2iRuntimeStats());
  },
  restart(requestConfig?: AxiosRequestConfig) {
    return typed<OpenConfig>(
      openApiV1.restartCore(generatedOptions({}, requestConfig)),
    );
  },
  storage() {
    return typed<OpenConfig>(openApiV1.getStorageStatus());
  },
  cleanupStorage(target?: string) {
    return typed<OpenConfig>(
      openApiV1.cleanupStorage({
        body: target ? { target } : undefined,
      }),
    );
  },
};

export const publicApi = {
  versions(requestConfig?: AxiosRequestConfig) {
    return typed<PublicVersionData>(
      openApiV1.getPublicVersions(generatedOptions({}, requestConfig)),
    );
  },
};

export const changelogApi = {
  listVersions() {
    return typed<{ versions?: string[] }>(openApiV1.listChangelogVersions());
  },
  get(version: string) {
    return typed<{ content?: string }>(
      openApiV1.getChangelog({ path: { version } }),
    );
  },
};
