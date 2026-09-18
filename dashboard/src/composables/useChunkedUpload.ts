import { ref, computed } from 'vue';

/**
 * Business-agnostic chunked upload scheduler.
 *
 * Owns slicing, bounded concurrency, silent per-chunk retries and
 * session resume. Pages wire in the five endpoint calls of their
 * business and render from the exposed state only.
 */

export interface ChunkedUploadApi {
    initUpload(payload: { filename: string; total_size: number }): Promise<any>;
    uploadChunk(payload: { upload_id: string; chunk_index: number; chunk: Blob }): Promise<any>;
    completeUpload(payload: { upload_id: string }): Promise<any>;
    abortUpload(payload: { upload_id: string }): Promise<any>;
    statusUpload(payload: { upload_id: string }): Promise<any>;
}

export type ChunkedUploadStatus = 'idle' | 'uploading' | 'error' | 'done';
export type ChunkedUploadPhase = 'init' | 'chunks' | 'complete';

const CONCURRENT_UPLOADS = 5;
// Silent retries per chunk before the whole run is considered failed.
const CHUNK_MAX_ATTEMPTS = 3;

export function useChunkedUpload(api: ChunkedUploadApi) {
    const status = ref<ChunkedUploadStatus>('idle');
    const phase = ref<ChunkedUploadPhase>('init');
    const uploadedBytes = ref(0);
    const totalBytes = ref(0);
    const errorMessage = ref('');

    const percent = computed(() =>
        totalBytes.value > 0 ? Math.round((uploadedBytes.value / totalBytes.value) * 100) : 0,
    );
    // Resume is only meaningful after a failed run while the file is known.
    const canResume = computed(() => status.value === 'error');

    // Session state kept across a failure so resume() can continue it.
    let file: File | null = null;
    let uploadId = '';
    let chunkSize = 0;
    let totalChunks = 0;
    let chunkSizes: number[] = [];
    let cancelled = false;

    function envelopeData(response: any): any {
        if (response.data?.status !== 'ok') {
            throw new Error(response.data?.message || 'Upload failed');
        }
        return response.data.data;
    }

    function toMessage(err: any): string {
        return err?.response?.data?.message || err?.message || 'Upload failed';
    }

    function planChunks() {
        chunkSizes = [];
        for (let i = 0; i < totalChunks; i++) {
            const start = i * chunkSize;
            chunkSizes[i] = Math.min(start + chunkSize, file!.size) - start;
        }
    }

    async function uploadOneChunk(chunkIndex: number) {
        const start = chunkIndex * chunkSize;
        const chunk = file!.slice(start, start + chunkSize);
        let lastError: any;
        for (let attempt = 0; attempt < CHUNK_MAX_ATTEMPTS; attempt++) {
            if (cancelled) throw new Error('cancelled');
            try {
                envelopeData(
                    await api.uploadChunk({
                        upload_id: uploadId,
                        chunk_index: chunkIndex,
                        chunk,
                    }),
                );
                uploadedBytes.value += chunkSizes[chunkIndex];
                return;
            } catch (err) {
                lastError = err;
            }
        }
        throw lastError;
    }

    async function runPool(indexes: number[]) {
        const pending = [...indexes];
        const active: Promise<void>[] = [];
        while (pending.length > 0 || active.length > 0) {
            while (!cancelled && pending.length > 0 && active.length < CONCURRENT_UPLOADS) {
                const chunkIndex = pending.shift()!;
                const promise = uploadOneChunk(chunkIndex).then(() => {
                    const idx = active.indexOf(promise);
                    if (idx > -1) active.splice(idx, 1);
                });
                active.push(promise);
            }
            if (active.length > 0) await Promise.race(active);
            if (cancelled) throw new Error('cancelled');
        }
    }

    async function initSession() {
        phase.value = 'init';
        const data = envelopeData(
            await api.initUpload({ filename: file!.name, total_size: file!.size }),
        );
        uploadId = data.upload_id;
        chunkSize = data.chunk_size;
        totalChunks = data.total_chunks;
        planChunks();
        uploadedBytes.value = 0;
    }

    async function completeSession() {
        phase.value = 'complete';
        return envelopeData(await api.completeUpload({ upload_id: uploadId }));
    }

    async function start(f: File): Promise<any> {
        file = f;
        cancelled = false;
        status.value = 'uploading';
        errorMessage.value = '';
        totalBytes.value = f.size;
        try {
            await initSession();
            phase.value = 'chunks';
            await runPool(Array.from({ length: totalChunks }, (_, i) => i));
            const result = await completeSession();
            status.value = 'done';
            return result;
        } catch (err) {
            return handleFailure(err);
        }
    }

    async function resume(): Promise<any> {
        if (!file) return undefined;
        cancelled = false;
        status.value = 'uploading';
        errorMessage.value = '';
        try {
            let received: number[] = [];
            if (uploadId) {
                try {
                    const data = await envelopeData(api.statusUpload({ upload_id: uploadId }));
                    received = data.received_chunks;
                } catch {
                    // Session expired or unknown: fall back to a fresh one.
                    uploadId = '';
                }
            }
            if (!uploadId) {
                await initSession();
            } else {
                uploadedBytes.value = received.reduce((sum, i) => sum + chunkSizes[i], 0);
            }
            phase.value = 'chunks';
            const missing = Array.from({ length: totalChunks }, (_, i) => i).filter(
                i => !received.includes(i),
            );
            await runPool(missing);
            const result = await completeSession();
            status.value = 'done';
            return result;
        } catch (err) {
            return handleFailure(err);
        }
    }

    function handleFailure(err: any): undefined {
        if (err?.message === 'cancelled') {
            reset();
            return undefined;
        }
        // A failed complete() means the merged result was rejected; the
        // session cannot be trusted to succeed on retry, so drop it and let
        // resume() start a fresh one.
        if (phase.value === 'complete') uploadId = '';
        status.value = 'error';
        errorMessage.value = toMessage(err);
        return undefined;
    }

    async function cancel() {
        cancelled = true;
        const id = uploadId;
        reset();
        if (id) {
            try {
                await api.abortUpload({ upload_id: id });
            } catch (err) {
                console.error('Failed to abort upload:', err);
            }
        }
    }

    function reset() {
        status.value = 'idle';
        phase.value = 'init';
        uploadedBytes.value = 0;
        totalBytes.value = 0;
        errorMessage.value = '';
        file = null;
        uploadId = '';
        chunkSize = 0;
        totalChunks = 0;
        chunkSizes = [];
    }

    return {
        status,
        phase,
        percent,
        uploadedBytes,
        totalBytes,
        errorMessage,
        canResume,
        start,
        resume,
        cancel,
        reset,
    };
}
