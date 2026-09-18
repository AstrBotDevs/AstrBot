import { ref, shallowRef, computed } from 'vue';
import { fileApi } from '@/api/v1';
import { useChunkedUpload } from '@/composables/useChunkedUpload';

// Files at or above this size use resumable chunked upload instead of a
// single multipart POST.
const CHUNKED_UPLOAD_THRESHOLD = 32 * 1024 * 1024;

export interface StagedFileInfo {
    attachment_id: string;
    filename: string;
    original_name: string;
    url: string;  // blob URL for preview
    type: string;  // image, record, file, video
    signature?: string;
}

export interface FailedUploadView {
    name: string;
    size: number;
    error: string;
}

export interface ActiveUploadView {
    name: string;
    size: number;
    percent: number;
}

interface UploadEntry {
    file: File;
    signature: string;
    uploader: ReturnType<typeof useChunkedUpload>;
}

export function useMediaHandling() {
    const stagedFiles = ref<StagedFileInfo[]>([]);
    const mediaCache = ref<Record<string, string>>({});
    const pendingFileSignatures = new Set<string>();
    // shallowRef: entries hold uploader instances whose internal refs must
    // stay intact (a deep ref() would unwrap them), so updates reassign.
    const failedUploads = shallowRef<UploadEntry[]>([]);
    const activeUploads = shallowRef<UploadEntry[]>([]);

    // Display-only projection of failed uploads for the input area.
    const failedUploadViews = computed<FailedUploadView[]>(() =>
        failedUploads.value.map(entry => ({
            name: entry.file.name,
            size: entry.file.size,
            error: entry.uploader.errorMessage.value
        }))
    );

    // Display-only projection of in-flight uploads (progress chips).
    const activeUploadViews = computed<ActiveUploadView[]>(() =>
        activeUploads.value.map(entry => ({
            name: entry.file.name,
            size: entry.file.size,
            percent: entry.uploader.percent.value
        }))
    );

    async function getFileSignature(file: File): Promise<string> {
        if (crypto?.subtle) {
            // Digest per block, then digest the concatenated block digests.
            // The signature is only used for in-session dedup and never
            // leaves the browser, so it does not need to be the canonical
            // SHA-256 of the whole file — only stable per file. This keeps
            // memory bounded at BLOCK bytes regardless of file size.
            const BLOCK = 8 * 1024 * 1024;
            const blockHashes: Uint8Array[] = [];
            for (let offset = 0; offset < file.size; offset += BLOCK) {
                const buf = await file.slice(offset, offset + BLOCK).arrayBuffer();
                blockHashes.push(new Uint8Array(await crypto.subtle.digest('SHA-256', buf)));
            }
            const combined = new Uint8Array(blockHashes.length * 32);
            blockHashes.forEach((h, i) => combined.set(h, i * 32));
            const digest = await crypto.subtle.digest('SHA-256', combined);
            const hash = Array.from(new Uint8Array(digest))
                .map(byte => byte.toString(16).padStart(2, '0'))
                .join('');
            return `sha256m:${hash}`;
        }

        return `meta:${file.name}:${file.size}:${file.type}:${file.lastModified}`;
    }

    function isDuplicateFile(signature: string) {
        return (
            pendingFileSignatures.has(signature) ||
            stagedFiles.value.some(file => file.signature === signature) ||
            failedUploads.value.some(entry => entry.signature === signature)
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

    function stageUploaded(file: File, data: any, signature: string): StagedFileInfo {
        const stagedFile = {
            attachment_id: data.attachment_id,
            filename: data.filename,
            original_name: file.name,
            url: URL.createObjectURL(file),
            type: data.type,
            signature
        };
        stagedFiles.value.push(stagedFile);
        return stagedFile;
    }

    async function uploadStagedFile(file: File): Promise<StagedFileInfo | undefined> {
        const signature = await getFileSignature(file);
        if (isDuplicateFile(signature)) return undefined;

        pendingFileSignatures.add(signature);
        try {
            if (file.size >= CHUNKED_UPLOAD_THRESHOLD) {
                return await uploadChunkedStagedFile(file, signature);
            }
            const formData = new FormData();
            formData.append('file', file);
            const response = await fileApi.upload(formData);
            return stageUploaded(file, response.data.data, signature);
        } catch (err) {
            console.error('Error uploading file:', err);
            return undefined;
        } finally {
            pendingFileSignatures.delete(signature);
        }
    }

    // Large files go through the resumable chunked upload endpoints; a
    // failure keeps the session entry so the user can resume from the
    // last received chunk instead of starting over.
    async function uploadChunkedStagedFile(file: File, signature: string): Promise<StagedFileInfo | undefined> {
        const uploader = useChunkedUpload({
            initUpload: ({ filename, total_size }) =>
                fileApi.initUpload({ filename, total_size, content_type: file.type }),
            uploadChunk: fileApi.uploadChunk,
            completeUpload: fileApi.completeUpload,
            abortUpload: fileApi.abortUpload,
            statusUpload: fileApi.statusUpload
        });
        const entry: UploadEntry = { file, signature, uploader };
        activeUploads.value = [...activeUploads.value, entry];
        const result = await uploader.start(file);
        activeUploads.value = activeUploads.value.filter(e => e !== entry);
        if (result) {
            return stageUploaded(file, result, signature);
        }
        if (uploader.status.value === 'error') {
            failedUploads.value = [...failedUploads.value, entry];
        }
        return undefined;
    }

    function cancelActiveUpload(index: number) {
        const entry = activeUploads.value[index];
        if (!entry) return;
        // The start() promise settles as cancelled; the entry is removed by
        // the settle path in uploadChunkedStagedFile.
        void entry.uploader.cancel();
    }

    async function retryFailedUpload(index: number): Promise<StagedFileInfo | undefined> {
        const entry = failedUploads.value[index];
        if (!entry) return undefined;
        // Move to active: blocks a second click from running resume()
        // concurrently on the same session and shows live progress.
        failedUploads.value = failedUploads.value.filter(e => e !== entry);
        activeUploads.value = [...activeUploads.value, entry];
        const result = await entry.uploader.resume();
        activeUploads.value = activeUploads.value.filter(e => e !== entry);
        if (!result) {
            if (entry.uploader.status.value === 'error') {
                failedUploads.value = [...failedUploads.value, entry];
            }
            return undefined;
        }
        return stageUploaded(entry.file, result, entry.signature);
    }

    async function discardFailedUpload(index: number) {
        const entry = failedUploads.value[index];
        if (!entry) return;
        failedUploads.value = failedUploads.value.filter(e => e !== entry);
        await entry.uploader.cancel();
    }

    async function processAndUploadImage(file: File) {
        return uploadStagedFile(file);
    }

    async function processAndUploadFile(file: File) {
        return uploadStagedFile(file);
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
        failedUploadViews,
        activeUploadViews,
        getMediaFile,
        processAndUploadImage,
        processAndUploadFile,
        handlePaste,
        removeImage,
        removeAudio,
        removeFile,
        retryFailedUpload,
        discardFailedUpload,
        cancelActiveUpload,
        clearStaged,
        cleanupMediaCache
    };
}
