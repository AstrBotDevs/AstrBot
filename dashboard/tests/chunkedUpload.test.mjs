import { flushPromises } from "@vue/test-utils";
import { describe, expect, test, vi } from "vitest";
import { useChunkedUpload } from "../src/composables/useChunkedUpload.ts";

const ok = (data = {}) => ({ data: { status: "ok", data } });
const fileOfSize = (size) => new File([new Uint8Array(size)], "report.zip");
const metadata = (extra = {}) => ({ upload_id: "upload-1", chunk_size: 4, total_chunks: 3, ...extra });

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function fixture(data = metadata()) {
  const result = { filename: "uploaded.zip" };
  const api = {
    initUpload: vi.fn().mockResolvedValue(ok(data)),
    uploadChunk: vi.fn().mockResolvedValue(ok()),
    completeUpload: vi.fn().mockResolvedValue(ok(result)),
    abortUpload: vi.fn().mockResolvedValue(ok()),
    statusUpload: vi.fn().mockResolvedValue(ok({ received_chunks: [] })),
  };
  return { api, result, upload: useChunkedUpload(api) };
}

describe("chunked upload session contracts", () => {
  test("resumes a valid session after awaiting status without reinitializing or replaying received chunks", async () => {
    const { api, upload, result } = fixture();
    const failedAttempt = deferred();
    let attempts = 0;
    api.uploadChunk.mockImplementation(({ chunk_index }) => {
      if (chunk_index !== 2) return Promise.resolve(ok());
      attempts++;
      return attempts < 3 ? Promise.reject(new Error("offline")) : failedAttempt.promise;
    });
    const initial = upload.start(fileOfSize(9));
    await flushPromises();
    failedAttempt.reject(new Error("offline"));
    await initial;
    const initialStatus = upload.status.value;

    api.uploadChunk.mockClear().mockResolvedValue(ok());
    const progress = deferred();
    api.statusUpload.mockReturnValue(progress.promise);
    const resumed = upload.resume();
    await flushPromises();
    const initializationsBeforeStatus = api.initUpload.mock.calls.length;
    const chunksBeforeStatus = api.uploadChunk.mock.calls.length;
    progress.resolve(ok({ received_chunks: [0, 1], chunk_size: 4, total_chunks: 3 }));
    const completed = await resumed;

    expect(initialStatus).toBe("error");
    expect(attempts).toBe(3);
    expect(initializationsBeforeStatus).toBe(1);
    expect(chunksBeforeStatus).toBe(0);
    expect(api.initUpload).toHaveBeenCalledTimes(1);
    expect(api.statusUpload).toHaveBeenCalledExactlyOnceWith({ upload_id: "upload-1" });
    expect(api.uploadChunk.mock.calls.map(([payload]) => payload.chunk_index)).toEqual([2]);
    expect(api.uploadChunk.mock.calls[0][0].chunk.size).toBe(1);
    expect(api.completeUpload).toHaveBeenCalledExactlyOnceWith({ upload_id: "upload-1" });
    expect(api.abortUpload).not.toHaveBeenCalled();
    expect(completed).toEqual(result);
    expect(upload.status.value).toBe("done");
    expect(upload.uploadedBytes.value).toBe(9);
    expect(upload.percent.value).toBe(100);
  });

  test.each([
    ["empty ID", metadata({ upload_id: "" }), null],
    ["non-string ID", metadata({ upload_id: 17 }), null],
    ["null data", null, null],
    ["missing geometry", { upload_id: "upload-1" }, "upload-1"],
    ["zero chunk size", metadata({ chunk_size: 0 }), "upload-1"],
    ["negative chunk size", metadata({ chunk_size: -4 }), "upload-1"],
    ["fractional chunk size", metadata({ chunk_size: 0.5 }), "upload-1"],
    ["string chunk size", metadata({ chunk_size: "4" }), "upload-1"],
    ["NaN chunk size", metadata({ chunk_size: Number.NaN }), "upload-1"],
    ["infinite chunk size", metadata({ chunk_size: Number.POSITIVE_INFINITY }), "upload-1"],
    ["unsafe chunk size", metadata({ chunk_size: Number.MAX_SAFE_INTEGER + 1, total_chunks: 1 }), "upload-1"],
    ["zero chunk count", metadata({ total_chunks: 0 }), "upload-1"],
    ["negative chunk count", metadata({ total_chunks: -1 }), "upload-1"],
    ["fractional chunk count", metadata({ total_chunks: 3.5 }), "upload-1"],
    ["string chunk count", metadata({ total_chunks: "3" }), "upload-1"],
    ["NaN chunk count", metadata({ total_chunks: Number.NaN }), "upload-1"],
    ["inconsistent chunk count", metadata({ total_chunks: 2 }), "upload-1"],
    ["unbounded total count: infinity", metadata({ total_chunks: Number.POSITIVE_INFINITY }), "upload-1"],
    ["unbounded total count: unsafe integer", metadata({ total_chunks: Number.MAX_SAFE_INTEGER + 1 }), "upload-1"],
  ])("rejects invalid metadata: %s", async (_label, data, abortId) => {
    const { api, upload } = fixture(data);
    const result = await upload.start(fileOfSize(9));
    expect(result).toBeUndefined();
    expect(upload.status.value).toBe("error");
    expect(upload.errorMessage.value).toBe("Invalid upload session");
    expect(api.uploadChunk).not.toHaveBeenCalled();
    expect(api.completeUpload).not.toHaveBeenCalled();
    expect(api.initUpload).toHaveBeenCalledTimes(1);
    if (abortId) expect(api.abortUpload).toHaveBeenCalledExactlyOnceWith({ upload_id: abortId });
    else expect(api.abortUpload).not.toHaveBeenCalled();
  });

  test("failed invalid-session cleanup keeps the validation error without automatically retrying", async () => {
    const { api, upload } = fixture(metadata({ chunk_size: 0 }));
    const cleanupError = new Error("cleanup unavailable");
    api.abortUpload.mockRejectedValue(cleanupError);
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    await upload.start(fileOfSize(9));
    await flushPromises();
    expect(upload.status.value).toBe("error");
    expect(upload.errorMessage.value).toBe("Invalid upload session");
    expect(api.abortUpload).toHaveBeenCalledExactlyOnceWith({ upload_id: "upload-1" });
    expect(log).toHaveBeenCalledWith("Failed to abort invalid upload session:", cleanupError);
    expect(api.uploadChunk).not.toHaveBeenCalled();
    expect(api.completeUpload).not.toHaveBeenCalled();
    expect(api.initUpload).toHaveBeenCalledTimes(1);
  });

  test("an empty file preserves the backend size rejection without creating another session", async () => {
    const { api, upload } = fixture();
    api.initUpload.mockResolvedValue({ data: { status: "error", message: "Invalid file size" } });
    expect(await upload.start(fileOfSize(0))).toBeUndefined();
    expect(upload.status.value).toBe("error");
    expect(upload.errorMessage.value).toBe("Invalid file size");
    expect(api.initUpload).toHaveBeenCalledExactlyOnceWith({ filename: "report.zip", total_size: 0 });
    expect(api.uploadChunk).not.toHaveBeenCalled();
    expect(api.completeUpload).not.toHaveBeenCalled();
    expect(api.abortUpload).not.toHaveBeenCalled();
  });

  test("an empty file cannot complete a malformed successful zero-chunk session", async () => {
    const { api, upload } = fixture(metadata({ total_chunks: 0 }));
    expect(await upload.start(fileOfSize(0))).toBeUndefined();
    expect(upload.status.value).toBe("error");
    expect(upload.errorMessage.value).toBe("Invalid upload session");
    expect(api.abortUpload).toHaveBeenCalledExactlyOnceWith({ upload_id: "upload-1" });
    expect(api.uploadChunk).not.toHaveBeenCalled();
    expect(api.completeUpload).not.toHaveBeenCalled();
  });

  test.each([
    [9, 4, 3, [4, 4, 1]],
    [3, 8, 1, [3]],
  ])("valid geometry uploads a %i-byte file with %i-byte chunks", async (size, chunkSize, totalChunks, sizes) => {
    const { api, upload, result } = fixture(metadata({ chunk_size: chunkSize, total_chunks: totalChunks }));
    expect(await upload.start(fileOfSize(size))).toEqual(result);
    expect(api.uploadChunk.mock.calls.map(([payload]) => payload.chunk.size)).toEqual(sizes);
    expect(api.uploadChunk.mock.calls.map(([payload]) => payload.chunk_index)).toEqual(sizes.map((_, index) => index));
    expect(upload.uploadedBytes.value).toBe(size);
    expect(upload.percent.value).toBe(100);
    expect(api.abortUpload).not.toHaveBeenCalled();
  });

  test("cancelling pending initialization cleans up its late session without sending chunks", async () => {
    const { api, upload } = fixture();
    const initialized = deferred();
    api.initUpload.mockReturnValue(initialized.promise);
    const started = upload.start(fileOfSize(9));
    await upload.cancel();
    initialized.resolve(ok(metadata()));
    expect(await started).toBeUndefined();
    await flushPromises();
    expect(api.abortUpload).toHaveBeenCalledExactlyOnceWith({ upload_id: "upload-1" });
    expect(api.uploadChunk).not.toHaveBeenCalled();
    expect(api.completeUpload).not.toHaveBeenCalled();
    expect(upload.status.value).toBe("idle");
    expect(upload.canResume.value).toBe(false);
  });

  test.each([
    ["an Error", new Error("chunk rejected"), "chunk rejected"],
    ["undefined", undefined, "Upload failed"],
    ["null", null, "Upload failed"],
    ["false", false, "Upload failed"],
    ["zero", 0, "Upload failed"],
    ["an empty string", "", "Upload failed"],
  ])("retains a concurrent failure with %s through draining without starting queued chunks", async (_label, reason, message) => {
    const { api, upload } = fixture(metadata({ total_chunks: 7 }));
    const gates = Array.from({ length: 5 }, () => deferred());
    const attempts = new Map();
    api.uploadChunk.mockImplementation(({ chunk_index }) => {
      const attempt = (attempts.get(chunk_index) ?? 0) + 1;
      attempts.set(chunk_index, attempt);
      if (chunk_index === 0 && attempt < 3) return Promise.reject(reason);
      return gates[chunk_index]?.promise ?? Promise.resolve(ok());
    });
    let settled = false;
    const started = upload.start(fileOfSize(25)).then((result) => {
      settled = true;
      return result;
    });
    await flushPromises();
    gates[1].resolve(ok());
    gates[0].reject(reason);
    await flushPromises();
    const requestedBeforeDrain = [...attempts.keys()];
    const settledBeforeDrain = settled;
    const completedBeforeDrain = api.completeUpload.mock.calls.length;
    for (const gate of gates.slice(2)) gate.resolve(ok());
    const result = await started;
    await flushPromises();

    expect(requestedBeforeDrain).toEqual([0, 1, 2, 3, 4]);
    expect(settledBeforeDrain).toBe(false);
    expect(completedBeforeDrain).toBe(0);
    expect(result).toBeUndefined();
    expect(upload.status.value).toBe("error");
    expect(upload.errorMessage.value).toBe(message);
    expect(upload.canResume.value).toBe(true);
    expect(attempts.get(0)).toBe(3);
    const retried = api.uploadChunk.mock.calls
      .map(([payload]) => payload)
      .filter((payload) => payload.chunk_index === 0);
    expect(retried).toHaveLength(3);
    for (const payload of retried) {
      expect(payload.upload_id).toBe("upload-1");
      expect(payload.chunk_index).toBe(0);
      expect(payload.chunk).toBe(retried[0].chunk);
      expect(payload.chunk.size).toBe(4);
    }
    for (const index of [1, 2, 3, 4]) expect(attempts.get(index)).toBe(1);
    expect(api.initUpload).toHaveBeenCalledTimes(1);
    expect(api.statusUpload).not.toHaveBeenCalled();
    expect(api.completeUpload).not.toHaveBeenCalled();
    expect(api.abortUpload).not.toHaveBeenCalled();
  });
});
