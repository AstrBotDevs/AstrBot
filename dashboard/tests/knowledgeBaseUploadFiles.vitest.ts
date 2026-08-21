import { describe, expect, it } from 'vitest';
import {
  collectDroppedKnowledgeBaseFiles,
  collectFilesFromEntry,
  collectFilesFromFileList,
  isSupportedKnowledgeBaseUploadFile,
  withUploadRelativeName,
  type FileSystemEntryLike,
} from '@/utils/knowledgeBaseUploadFiles';

function makeFile(name: string, content = 'body'): File {
  return new File([content], name, { type: 'text/plain' });
}

function fileEntry(name: string, file: File): FileSystemEntryLike {
  return {
    isFile: true,
    isDirectory: false,
    name,
    file: (success) => success(file),
  };
}

function directoryEntry(
  name: string,
  children: FileSystemEntryLike[],
): FileSystemEntryLike {
  let remaining = [...children];
  return {
    isFile: false,
    isDirectory: true,
    name,
    createReader: () => ({
      readEntries: (success) => {
        const batch = remaining;
        remaining = [];
        success(batch);
      },
    }),
  };
}

describe('knowledgeBaseUploadFiles', () => {
  it('accepts markdown and other knowledge-base formats', () => {
    expect(isSupportedKnowledgeBaseUploadFile('阿米娅.md')).toBe(true);
    expect(isSupportedKnowledgeBaseUploadFile('notes.markdown')).toBe(true);
    expect(isSupportedKnowledgeBaseUploadFile('guide.PDF')).toBe(true);
    expect(isSupportedKnowledgeBaseUploadFile('index.json')).toBe(false);
    expect(isSupportedKnowledgeBaseUploadFile('README')).toBe(false);
  });

  it('keeps nested relative names for dropped markdown trees', () => {
    const original = makeFile('阿米娅.md');
    const renamed = withUploadRelativeName(
      original,
      'markdown/operators/阿米娅.md',
    );
    expect(renamed.name).toBe('markdown/operators/阿米娅.md');
  });

  it('filters a file list and applies webkitRelativePath', () => {
    const markdown = makeFile('阿米娅.md');
    Object.defineProperty(markdown, 'webkitRelativePath', {
      value: 'markdown/operators/阿米娅.md',
    });
    const skipped = makeFile('index.json');
    const collected = collectFilesFromFileList([markdown, skipped]);
    expect(collected).toHaveLength(1);
    expect(collected[0]?.name).toBe('markdown/operators/阿米娅.md');
  });

  it('recursively collects supported files from a directory entry', async () => {
    const entry = directoryEntry('markdown', [
      directoryEntry('operators', [
        fileEntry('阿米娅.md', makeFile('阿米娅.md')),
        fileEntry('skip.json', makeFile('skip.json')),
      ]),
      directoryEntry('items', [fileEntry('源石.md', makeFile('源石.md'))]),
    ]);

    const collected = await collectFilesFromEntry(entry);
    expect(collected.map((file) => file.name).sort()).toEqual([
      'markdown/items/源石.md',
      'markdown/operators/阿米娅.md',
    ]);
  });

  it('prefers directory entries over a top-level FileList when dropping a folder', async () => {
    const entry = directoryEntry('markdown', [
      directoryEntry('operators', [
        fileEntry('阿米娅.md', makeFile('阿米娅.md')),
      ]),
    ]);
    const dataTransfer = {
      items: [
        {
          webkitGetAsEntry: () => entry,
        },
      ],
      files: [] as unknown as FileList,
    } as unknown as DataTransfer;

    const collected = await collectDroppedKnowledgeBaseFiles(dataTransfer);
    expect(collected.map((file) => file.name)).toEqual([
      'markdown/operators/阿米娅.md',
    ]);
  });

  it('falls back to FileList when the browser does not expose directory entries', async () => {
    const dataTransfer = {
      items: [],
      files: [
        makeFile('阿米娅.md'),
        makeFile('skip.json'),
      ] as unknown as FileList,
    } as unknown as DataTransfer;

    const collected = await collectDroppedKnowledgeBaseFiles(dataTransfer);
    expect(collected.map((file) => file.name)).toEqual(['阿米娅.md']);
  });
});
