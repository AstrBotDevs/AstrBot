import assert from "node:assert/strict";
import { File } from "node:buffer";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/composables/useChunkedUpload.ts", import.meta.url),
  "utf8",
);
const context = vm.createContext({
  exports: {},
  require: createRequire(import.meta.url),
  console,
});
vm.runInContext(
  ts.transpile(source, {
    target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.CommonJS,
  }),
  context,
);
const { useChunkedUpload } = context.exports;
const ok = (data) => ({ data: { status: "ok", data } });

for (const scenario of [
  "missing chunk",
  "all chunks received",
  "expired session",
  "status request rejected",
]) {
  test(`resume handles ${scenario}`, async () => {
    let sessions = 0;
    let failing = true;
    const uploads = [];
    const completions = [];
    const queries = [];
    const uploader = useChunkedUpload({
      async initUpload() {
        return ok({
          upload_id: `session-${++sessions}`,
          chunk_size: 4,
          total_chunks: 4,
        });
      },
      async uploadChunk({ upload_id, chunk_index, chunk }) {
        uploads.push({ upload_id, chunk_index, size: chunk.size });
        if (failing && chunk_index === 3) throw new Error("Network error");
        if (!failing && scenario === "missing chunk") {
          assert.equal(uploader.uploadedBytes.value, 12);
          assert.equal(uploader.percent.value, 86);
        }
        return ok({});
      },
      async statusUpload({ upload_id }) {
        queries.push(upload_id);
        if (scenario === "status request rejected")
          throw new Error("Network error");
        if (scenario === "expired session") {
          return {
            data: { status: "error", message: "Upload session expired" },
          };
        }
        return ok({
          received_chunks:
            scenario === "all chunks received" ? [0, 1, 2, 3] : [0, 1, 2],
        });
      },
      async completeUpload({ upload_id }) {
        completions.push(upload_id);
        assert.equal(uploader.uploadedBytes.value, 14);
        assert.equal(uploader.percent.value, 100);
        return ok({ attachment_id: "attachment-1" });
      },
      async abortUpload() {
        return ok({});
      },
    });

    await uploader.start(new File([new Uint8Array(14)], "upload.bin"));
    assert.equal(uploader.status.value, "error");
    assert.equal(uploader.canResume.value, true);
    assert.equal(uploader.uploadedBytes.value, 12);
    failing = false;
    uploads.length = 0;

    const result = await uploader.resume();
    const freshSession =
      scenario === "expired session" || scenario === "status request rejected";
    const expectedSession = freshSession ? "session-2" : "session-1";
    const expectedChunks = freshSession
      ? [0, 1, 2, 3]
      : scenario === "missing chunk"
      ? [3]
      : [];
    assert.deepEqual(queries, ["session-1"]);
    assert.equal(sessions, freshSession ? 2 : 1);
    assert.deepEqual(
      uploads.map(({ chunk_index }) => chunk_index),
      expectedChunks,
    );
    assert.ok(uploads.every(({ upload_id }) => upload_id === expectedSession));
    if (scenario === "missing chunk") assert.equal(uploads[0].size, 2);
    assert.deepEqual(completions, [expectedSession]);
    assert.equal(result.attachment_id, "attachment-1");
    assert.equal(uploader.status.value, "done");
    assert.equal(uploader.canResume.value, false);
    assert.equal(uploader.errorMessage.value, "");
  });
}
