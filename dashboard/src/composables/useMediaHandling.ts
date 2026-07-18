import { ref, computed } from 'vue';
import { fileApi, pluginExtensionApi } from '@/api/v1';

export interface StagedFileInfo {
    attachment_id: string;
    filename: string;
    original_name: string;
    url: string;  // blob URL for preview
    type: string;  // image, record, file, video
    signature?: string;
}

/**
 * 2026-07-18 drag-to-chat (elecvoid243): the inner payload of
 * GET /spcode/file-browser for a file. pluginExtensionApi.get
 * returns the response wrapped in `ApiEnvelope<{ status, data }>`,
 * and we want to type-check the inner `data` shape — same pattern
 * as `useSpcodeNewFileLineCounts.ts:FileBrowserFilePayload`. We
 * only model the file-relevant fields; the rest (directory /
 * symlink snapshots, meta blocks) are ignored.
 */
interface FileBrowserFilePayload {
    type?: string | null;
    is_binary?: boolean | null;
    content?: string | null;
    reason?: string | null;
}

export function useMediaHandling() {
    const stagedFiles = ref<StagedFileInfo[]>([]);
    const mediaCache = ref<Record<string, string>>({});
    const pendingFileSignatures = new Set<string>();

    async function getFileSignature(file: File): Promise<string> {
        if (crypto?.subtle) {
            const buffer = await file.arrayBuffer();
            const digest = await crypto.subtle.digest('SHA-256', buffer);
            const hash = Array.from(new Uint8Array(digest))
                .map(byte => byte.toString(16).padStart(2, '0'))
                .join('');
            return `sha256:${hash}`;
        }

        return `meta:${file.name}:${file.size}:${file.type}:${file.lastModified}`;
    }

    function isDuplicateFile(signature: string) {
        return (
            pendingFileSignatures.has(signature) ||
            stagedFiles.value.some(file => file.signature === signature)
        );
    }

    async function getMediaFile(filename: string): Promise<string> {
        if (mediaCache.value[filename]) {
            return mediaCache.value[filename];
        }

        try {
            const response = await fileApi.getByName(filename);

            const blobUrl = URL.createObjectURL(response.data);
            mediaCache.value[filename] = blobUrl;
            return blobUrl;
        } catch (error) {
            console.error('Error fetching media file:', error);
            return '';
        }
    }

    async function uploadStagedFile(file: File): Promise<StagedFileInfo | undefined> {
        const signature = await getFileSignature(file);
        if (isDuplicateFile(signature)) return undefined;

        pendingFileSignatures.add(signature);
        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fileApi.upload(formData);

            const { attachment_id, filename, type } = response.data.data;
            const stagedFile = {
                attachment_id,
                filename,
                original_name: file.name,
                url: URL.createObjectURL(file),
                type,
                signature
            };
            stagedFiles.value.push(stagedFile);
            return stagedFile;
        } catch (err) {
            console.error('Error uploading file:', err);
            return undefined;
        } finally {
            pendingFileSignatures.delete(signature);
        }
    }

    async function processAndUploadImage(file: File) {
        return uploadStagedFile(file);
    }

    async function processAndUploadFile(file: File) {
        return uploadStagedFile(file);
    }

    /**
     * 2026-07-18 drag-to-chat (elecvoid243): upload a file by its
     * server-side path instead of a browser `File` object. Used by
     * the sidebar file-browser drop flow — the user drags a row
     * from the workspace / document-manager tree directly onto the
     * chat input, and the chat input forwards `{ path, name }` to
     * the parent, which calls this helper.
     *
     * Pipeline:
     *   1. GET /spcode/file-browser?path=<path> — fetch the file
     *      content. The endpoint is stateless and worktree-scoped
     *      implicitly via the agent's loaded project, so we don't
     *      need to pass umo / worktree.
     *   2. If the response is `is_binary: true` (or `content` is
     *      null for any reason), short-circuit with `undefined`
     *      and let the caller show a toast. The "+ → Upload Files"
     *      button accepts binary files because the user can pick
     *      them from disk, but our drop flow is text-only (the
     *      file-browser endpoint never returns binary blobs).
     *   3. Wrap the content in a `File` and delegate to the
     *      existing `uploadStagedFile` so signature dedup, blob
     *      URL, and the upload POST all behave identically to the
     *      regular click-to-upload path.
     *
     * The signature is computed against the wrapped `File` (same
     * as the click path), so dropping the same file twice via
     * either entry point is deduped against the same hash bucket.
     */
    async function processAndUploadFileFromPath(
        path: string,
        name: string,
    ): Promise<StagedFileInfo | undefined> {
        if (!path || !name) return undefined;
        try {
            const resp = await pluginExtensionApi.get<FileBrowserFilePayload>(
                'spcode/file-browser',
                { params: { path } },
            );
            const data = resp.data?.data;
            if (!data || data.type !== 'file' || data.is_binary === true) {
                return undefined;
            }
            if (typeof data.content !== 'string') {
                return undefined;
            }
            // Build a File object from the text content. The MIME
            // type is left empty so the backend's own type-detection
            // (used in fileApi.upload) drives the final StagedFileInfo
            // type field — matching how the regular click-upload path
            // behaves for files with no extension / unknown MIME.
            const file = new File([data.content], name, { type: '' });
            return uploadStagedFile(file);
        } catch (err) {
            console.error('Error fetching file from path:', err);
            return undefined;
        }
    }

    async function handlePaste(event: ClipboardEvent) {
        const items = event.clipboardData?.items;
        if (!items) return;

        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                const file = items[i].getAsFile();
                if (file) {
                    await processAndUploadImage(file);
                }
            }
        }
    }

    function removeImage(index: number) {
        // 找到第 index 个图片类型的文件
        let imageCount = 0;
        for (let i = 0; i < stagedFiles.value.length; i++) {
            if (stagedFiles.value[i].type === 'image') {
                if (imageCount === index) {
                    const fileToRemove = stagedFiles.value[i];
                    if (fileToRemove.url.startsWith('blob:')) {
                        URL.revokeObjectURL(fileToRemove.url);
                    }
                    stagedFiles.value.splice(i, 1);
                    return;
                }
                imageCount++;
            }
        }
    }

    function removeAudio() {
        for (let i = stagedFiles.value.length - 1; i >= 0; i--) {
            if (stagedFiles.value[i].type !== 'record') continue;

            const fileToRemove = stagedFiles.value[i];
            if (fileToRemove.url.startsWith('blob:')) {
                URL.revokeObjectURL(fileToRemove.url);
            }
            stagedFiles.value.splice(i, 1);
        }
    }

    function removeFile(index: number) {
        // Find the requested non-image, non-audio attachment.
        let fileCount = 0;
        for (let i = 0; i < stagedFiles.value.length; i++) {
            if (
                stagedFiles.value[i].type !== 'image' &&
                stagedFiles.value[i].type !== 'record'
            ) {
                if (fileCount === index) {
                    const fileToRemove = stagedFiles.value[i];
                    if (fileToRemove.url.startsWith('blob:')) {
                        URL.revokeObjectURL(fileToRemove.url);
                    }
                    stagedFiles.value.splice(i, 1);
                    return;
                }
                fileCount++;
            }
        }
    }

    function clearStaged(options: { revokeUrls?: boolean } = {}) {
        const { revokeUrls = true } = options;
        if (revokeUrls) {
            // 清理文件的 blob URLs
            stagedFiles.value.forEach(file => {
                if (file.url.startsWith('blob:')) {
                    URL.revokeObjectURL(file.url);
                }
            });
        }
        stagedFiles.value = [];
    }

    function cleanupMediaCache() {
        Object.values(mediaCache.value).forEach(url => {
            if (url.startsWith('blob:')) {
                URL.revokeObjectURL(url);
            }
        });
        mediaCache.value = {};
    }

    // 计算属性：获取图片的 URL 列表（用于预览）
    const stagedImagesUrl = computed(() => 
        stagedFiles.value.filter(f => f.type === 'image').map(f => f.url)
    );

    const stagedAudioUrl = computed(() =>
        stagedFiles.value.find(f => f.type === 'record')?.url || ''
    );

    // 计算属性：获取非图片文件列表
    const stagedNonImageFiles = computed(() => 
        stagedFiles.value.filter(f => f.type !== 'image' && f.type !== 'record')
    );

    return {
        stagedImagesUrl,
        stagedAudioUrl,
        stagedFiles,
        stagedNonImageFiles,
        getMediaFile,
        processAndUploadImage,
        processAndUploadFile,
        // 2026-07-18 drag-to-chat (elecvoid243): sidebar file-browser
        // drop upload. See helper docstring above for the full flow.
        processAndUploadFileFromPath,
        handlePaste,
        removeImage,
        removeAudio,
        removeFile,
        clearStaged,
        cleanupMediaCache
    };
}
