export const KNOWLEDGE_BASE_UPLOAD_EXTENSIONS = new Set([
  '.txt',
  '.md',
  '.markdown',
  '.rst',
  '.adoc',
  '.pdf',
  '.docx',
  '.epub',
  '.xls',
  '.xlsx',
]);

type DirectoryReaderLike = {
  readEntries: (
    successCallback: (entries: FileSystemEntryLike[]) => void,
    errorCallback?: (error: DOMException) => void,
  ) => void;
};

export type FileSystemEntryLike = {
  isFile: boolean;
  isDirectory: boolean;
  name: string;
  file?: (
    successCallback: (file: File) => void,
    errorCallback?: (error: DOMException) => void,
  ) => void;
  createReader?: () => DirectoryReaderLike;
};

export function knowledgeBaseUploadExtension(name: string): string {
  const base = name.replaceAll('\\', '/').split('/').pop() || name;
  const index = base.lastIndexOf('.');
  return index >= 0 ? base.slice(index).toLowerCase() : '';
}

export function isSupportedKnowledgeBaseUploadFile(name: string): boolean {
  return KNOWLEDGE_BASE_UPLOAD_EXTENSIONS.has(
    knowledgeBaseUploadExtension(name),
  );
}

export function withUploadRelativeName(file: File, relativePath: string): File {
  const normalized = relativePath.replaceAll('\\', '/').replace(/^\/+/, '');
  if (!normalized || normalized === file.name) {
    return file;
  }
  return new File([file], normalized, {
    type: file.type,
    lastModified: file.lastModified,
  });
}

function fileRelativePath(file: File): string {
  const relativePath =
    'webkitRelativePath' in file && typeof file.webkitRelativePath === 'string'
      ? file.webkitRelativePath
      : '';
  return relativePath || file.name;
}

export function collectFilesFromFileList(files: FileList | File[]): File[] {
  return Array.from(files)
    .filter((file) => isSupportedKnowledgeBaseUploadFile(file.name))
    .map((file) => withUploadRelativeName(file, fileRelativePath(file)));
}

async function readAllDirectoryEntries(
  reader: DirectoryReaderLike,
): Promise<FileSystemEntryLike[]> {
  const entries: FileSystemEntryLike[] = [];
  while (true) {
    const batch = await new Promise<FileSystemEntryLike[]>(
      (resolve, reject) => {
        reader.readEntries(resolve, reject);
      },
    );
    if (batch.length === 0) {
      return entries;
    }
    entries.push(...batch);
  }
}

export async function collectFilesFromEntry(
  entry: FileSystemEntryLike,
  prefix = '',
): Promise<File[]> {
  const relativePath = prefix ? `${prefix}${entry.name}` : entry.name;
  if (entry.isFile && entry.file) {
    const file = await new Promise<File>((resolve, reject) => {
      entry.file?.(resolve, reject);
    });
    if (!isSupportedKnowledgeBaseUploadFile(file.name)) {
      return [];
    }
    return [withUploadRelativeName(file, relativePath)];
  }
  if (!entry.isDirectory || !entry.createReader) {
    return [];
  }
  const children = await readAllDirectoryEntries(entry.createReader());
  const nested: File[] = [];
  const childPrefix = `${relativePath}/`;
  for (const child of children) {
    nested.push(...(await collectFilesFromEntry(child, childPrefix)));
  }
  return nested;
}

export async function collectDroppedKnowledgeBaseFiles(
  dataTransfer: DataTransfer,
): Promise<File[]> {
  const items = Array.from(dataTransfer.items ?? []);
  const collected: File[] = [];
  let usedEntries = false;
  for (const item of items) {
    const entry = item.webkitGetAsEntry?.() as FileSystemEntryLike | null;
    if (!entry) {
      continue;
    }
    usedEntries = true;
    collected.push(...(await collectFilesFromEntry(entry)));
  }
  if (usedEntries) {
    return collected;
  }
  return collectFilesFromFileList(dataTransfer.files);
}
