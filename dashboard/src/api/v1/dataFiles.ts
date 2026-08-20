import {
  generatedOptions,
  openApiV1,
  typed,
  type AxiosRequestConfig,
} from './shared';
import type { ApiEnvelope } from './types';

export type DataFileEntry = {
  name: string;
  path: string;
  type: 'file' | 'directory' | 'symlink' | 'other';
  size: number;
  modified_at: string;
  category: 'text' | 'binary' | 'database' | 'system' | 'temporary';
  language: string | null;
  readable: boolean;
  writable: boolean;
  deletable: boolean;
  downloadable: boolean;
  protected: boolean;
  etag?: string | null;
  mime_type?: string;
};

type Envelope<T> = Promise<{ data: ApiEnvelope<T> }>;

export const dataFilesApi = {
  tree(
    path = '',
  ): Envelope<{ path: string; entries: DataFileEntry[]; truncated: boolean }> {
    return typed(
      openApiV1.listDataFileTree({ query: path ? { path } : undefined }),
    );
  },
  metadata(path: string): Envelope<DataFileEntry> {
    return typed(openApiV1.getDataFileMetadata({ query: { path } }));
  },
  content(path: string): Envelope<{
    path: string;
    content: string;
    etag: string;
    language: string | null;
    writable: boolean;
    protected: boolean;
    runtime_reload?: 'not_guaranteed' | 'reloaded';
  }> {
    return typed(openApiV1.getDataFileContent({ path: { path } }));
  },
  save(
    path: string,
    content: string,
    expected_etag: string,
    requestConfig?: AxiosRequestConfig,
  ): Envelope<{
    path: string;
    etag: string;
    size: number;
    runtime_reload?: 'not_guaranteed' | 'reloaded';
  }> {
    return typed(
      openApiV1.updateDataFileContent(
        generatedOptions(
          {
            path: { path },
            body: { content, expected_etag, encoding: 'utf-8' },
          },
          requestConfig,
        ),
      ),
    );
  },
  create(
    path: string,
    type: 'file' | 'directory',
    content = '',
    requestConfig?: AxiosRequestConfig,
  ) {
    return typed(
      openApiV1.createDataFileEntry(
        generatedOptions({ body: { path, type, content } }, requestConfig),
      ),
    );
  },
  move(
    source_path: string,
    target_path: string,
    requestConfig?: AxiosRequestConfig,
  ) {
    return typed(
      openApiV1.moveDataFileEntry(
        generatedOptions({ body: { source_path, target_path } }, requestConfig),
      ),
    );
  },
  remove(path: string, recursive = false, requestConfig?: AxiosRequestConfig) {
    return typed(
      openApiV1.deleteDataFileEntry(
        generatedOptions(
          { path: { path }, body: { path, recursive } },
          requestConfig,
        ),
      ),
    );
  },
  upload(path: string, file: File, requestConfig?: AxiosRequestConfig) {
    return typed(
      openApiV1.uploadDataFile(
        generatedOptions({ body: { path, file } }, requestConfig),
      ),
    );
  },
  search(
    q: string,
    path = '',
  ): Envelope<{ path: string; results: DataFileEntry[]; truncated: boolean }> {
    return typed(
      openApiV1.searchDataFiles({ query: { q, ...(path ? { path } : {}) } }),
    );
  },
  download(
    path: string,
    requestConfig?: AxiosRequestConfig,
  ): Promise<{ data: Blob }> {
    return openApiV1.downloadDataFile(
      generatedOptions({ path: { path }, responseType: 'blob' }, requestConfig),
    ) as Promise<{ data: Blob }>;
  },
};
