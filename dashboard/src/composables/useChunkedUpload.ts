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
    // Bumped on every start/resume/cancel; stale completions from a
    // previous run must not count toward the current run's progress.
    let runGeneration = 0;

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

    // sessionId is pinned per run: retries must keep writing to the
    // session they started in, even if a newer run re-initialized one.
    async function uploadOneChunk(chunkIndex: number, sessionId: string, generation: number) {
        const start = chunkIndex * chunkSize;
        const chunk = file!.slice(start, start + chunkSize);
        let lastError: any;
        for (let attempt = 0; attempt < CHUNK_MAX_ATTEMPTS; attempt++) {
            if (cancelled) throw new Error('cancelled');
            try {
                envelopeData(
                    await api.uploadChunk({
                        upload_id: sessionId,
                        chunk_index: chunkIndex,
                        chunk,
                    }),
                );
                if (generation === runGeneration) {
                    uploadedBytes.value += chunkSizes[chunkIndex];
                }
                return;
            } catch (err) {
                lastError = err;
            }
        }
        throw lastError;
    }

    async function runPool(indexes: number[], sessionId: string, generation: number) {
        const pending = [...indexes];
        const active: Promise<void>[] = [];
        let failure: any = null;
        while (!failure && !cancelled && (pending.length > 0 || active.length > 0)) {
            while (pending.length > 0 && active.length < CONCURRENT_UPLOADS) {
                const chunkIndex = pending.shift()!;
                const promise = uploadOneChunk(chunkIndex, sessionId, generation).finally(() => {
                    const idx = active.indexOf(promise);
                    if (idx > -1) active.splice(idx, 1);
                });
                active.push(promise);
            }
            if (active.length > 0) {
                try {
                    await Promise.race(active);
                } catch (err) {
                    // Stop scheduling; already-issued requests are drained
                    // below so a later resume never races them on a chunk.
                    failure = err;
                }
            }
        }
        if (active.length > 0) await Promise.allSettled(active);
        if (cancelled) throw new Error('cancelled');
        if (failure) throw failure;
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
        const result = envelopeData(await api.completeUpload({ upload_id: uploadId }));
        // The request was in flight when the user cancelled; a late success
        // must not flip the state back to done or hand a result to the caller.
        if (cancelled) throw new Error('cancelled');
        return result;
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
            await runPool(
                Array.from({ length: totalChunks }, (_, i) => i),
                uploadId,
                ++runGeneration,
            );
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
            await runPool(missing, uploadId, ++runGeneration);
            const result = await completeSession();
            status.value = 'done';
            return result;
        } catch (err) {
            return handleFailure(err);
        }
    }

    function handleFailure(err: any): undefined {
        // Cancel wins over any late resolution: a run cancelled while its
        // init request was still in flight lands here once init returns,
        // and its freshly created session must not leak server-side.
        if (cancelled || err?.message === 'cancelled') {
            const id = uploadId;
            reset();
            if (id) {
                void api.abortUpload({ upload_id: id }).catch(e =>
                    console.error('Failed to abort upload:', e),
                );
            }
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
        runGeneration++;
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
