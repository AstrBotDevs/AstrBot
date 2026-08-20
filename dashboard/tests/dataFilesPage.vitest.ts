import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const page = readFileSync(
  resolve(process.cwd(), 'src/views/DataFilesPage.vue'),
  'utf8',
);
const api = readFileSync(
  resolve(process.cwd(), 'src/api/v1/dataFiles.ts'),
  'utf8',
);
const monacoLoader = readFileSync(
  resolve(process.cwd(), 'src/utils/monacoLoader.ts'),
  'utf8',
);

describe('DataFilesPage contract', () => {
  it('uses the shared Monaco loader and Dashboard theme mapping', () => {
    expect(page).toContain('@/utils/monacoLoader');
    expect(monacoLoader).toContain("from 'monaco-editor';");
    expect(page).toContain("customizer.isDark ? 'vs-dark' : 'vs-light'");
    expect(page).toContain('readOnly: !selectedEntry.value?.writable');
  });

  it('keeps unsaved and conflict states explicit', () => {
    expect(page).toContain('unsavedDialog');
    expect(page).toContain('errorStatus(error) === 409');
    expect(page).toContain("tm('keepLocal')");
    expect(page).toContain("tm('reload')");
  });

  it('wires step-up confirmation and keeps the file tree independently scrollable', () => {
    expect(page).toContain('@confirm="submitStepUp"');
    expect(page).not.toContain('@submit="submitStepUp"');
    expect(page).toContain('height: min(620px, calc(100vh - 180px))');
    expect(page).toContain('overflow-y: auto');
  });

  it('covers Phase 2 API operations without persistent file content state', () => {
    for (const operation of ['create', 'move', 'remove', 'upload', 'search']) {
      expect(api).toContain(`${operation}(`);
    }
    expect(page).toContain('dataFilesApi.upload');
    expect(page).toContain('dataFilesApi.search');
    expect(page).not.toContain('localStorage.setItem');
  });
});
