import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { File } from "node:buffer";
import { ref, computed, watch, nextTick, effectScope } from "vue";
import ts from "typescript";

function setupVoice() {
  const draft = ref("Existing draft");
  const stagedFiles = ref([]);
  const contextKey = ref("chat-a");
  const calls = { transcriptions: [], uploads: [], sends: [], errors: [] };
  const mounted = [];
  const stopped = [];
  const storage = new Map();
  const recorder = {
    isRecording: ref(false),
    isStarting: ref(false),
    levels: ref([]),
    error: ref(null),
    async startRecording() {
      this.isRecording.value = true;
      return true;
    },
    async stopRecording() {
      this.isRecording.value = false;
      return new File(["audio"], "voice.webm", { type: "audio/webm" });
    },
    cancelRecording() {
      this.isRecording.value = false;
    },
  };
  const sandbox = vm.createContext({
    ref,
    computed,
    watch,
    onMounted: (fn) => mounted.push(fn),
    onBeforeUnmount: (fn) => stopped.push(fn),
    useModuleI18n: () => ({ tm: (key) => key }),
    useToast: () => ({ error: (error) => calls.errors.push(error) }),
    useRecording: () => recorder,
    localStorage: {
      getItem: (key) => storage.get(key),
      setItem: (key, value) => storage.set(key, value),
    },
    providerApi: {
      listByProviderType: async () => ({
        data: {
          status: "ok",
          data: [
            { id: "first" },
            { id: "second" },
            { id: "disabled", enable: false },
          ],
        },
      }),
    },
    chatApi: {
      transcribeAudio: (...args) =>
        new Promise((resolve) => calls.transcriptions.push({ args, resolve })),
    },
    fileApi: {
      upload: (...args) =>
        new Promise((resolve) => calls.uploads.push({ args, resolve })),
    },
    FormData,
    AbortController,
    URL: { createObjectURL: () => "blob:preview" },
    console: { error() {} },
  });
  const source = readFileSync(
    new URL("../src/composables/useChatVoice.ts", import.meta.url),
    "utf8",
  );
  const parsed = ts.createSourceFile(
    "voice.ts",
    source,
    ts.ScriptTarget.Latest,
    true,
  );
  const code = parsed.statements
    .filter((node) => !ts.isImportDeclaration(node))
    .map((node) => node.getText(parsed))
    .join("\n")
    .replace("export function", "function");
  vm.runInContext(ts.transpile(code), sandbox);
  const scope = effectScope();
  const voice = scope.run(() =>
    sandbox.useChatVoice({
      draft,
      stagedFiles,
      contextKey: () => contextKey.value,
      send: async () => calls.sends.push([...stagedFiles.value]),
      configureStt: () => {},
    }),
  );
  return {
    voice,
    draft,
    stagedFiles,
    contextKey,
    calls,
    recorder,
    storage,
    cleanup() {
      stopped.forEach((fn) => fn());
      scope.stop();
    },
  };
}

async function flush() {
  await new Promise(setImmediate);
}

test("dictation uses selected STT, appends to the draft, and never sends audio", async () => {
  const h = setupVoice();
  try {
    await h.voice.start("transcribe");
    assert.equal(h.voice.selectedSttProvider.value, "first");
    assert.equal(h.voice.sttProviders.value.length, 2);
    h.voice.selectedSttProvider.value = "second";
    await nextTick();
    assert.equal(h.storage.get("chat.sttProvider"), "second");
    const finished = h.voice.finish();
    await flush();
    assert.equal(h.calls.transcriptions[0].args[1], "second");
    h.calls.transcriptions[0].resolve({
      data: { status: "ok", data: { text: "recognized speech" } },
    });
    await finished;
    assert.equal(h.draft.value, "Existing draft recognized speech");
    assert.equal(h.voice.mode.value, null);
    assert.equal(h.calls.uploads.length, 0);
    assert.equal(h.calls.sends.length, 0);
  } finally {
    h.cleanup();
  }
});

test("audio mode uploads once and sends the recording without transcribing", async () => {
  const h = setupVoice();
  try {
    await h.voice.start("audio");
    const finished = h.voice.finish();
    await h.voice.finish();
    await flush();
    assert.equal(h.calls.uploads.length, 1);
    h.calls.uploads[0].resolve({
      data: {
        status: "ok",
        data: { attachment_id: "audio-id", filename: "voice.webm" },
      },
    });
    await finished;
    assert.equal(h.calls.sends.length, 1);
    assert.equal(h.calls.sends[0][0].type, "record");
    assert.equal(h.calls.transcriptions.length, 0);
    assert.equal(h.draft.value, "Existing draft");
  } finally {
    h.cleanup();
  }
});

for (const mode of ["transcribe", "audio"]) {
  test(`cancelling or switching conversations discards a late ${mode} result`, async () => {
    const h = setupVoice();
    try {
      await h.voice.start(mode);
      const finished = h.voice.finish();
      await flush();
      const pending =
        mode === "transcribe" ? h.calls.transcriptions[0] : h.calls.uploads[0];
      if (mode === "transcribe") h.voice.cancel();
      else h.contextKey.value = "chat-b";
      const signal = pending.args[mode === "transcribe" ? 2 : 1];
      assert.equal(signal.aborted, true);
      pending.resolve({
        data: {
          status: "ok",
          data: { text: "late result", attachment_id: "late-audio" },
        },
      });
      await finished;
      assert.equal(h.draft.value, "Existing draft");
      assert.equal(h.calls.sends.length, 0);
      assert.equal(h.stagedFiles.value.length, 0);
      assert.equal(h.voice.mode.value, null);
    } finally {
      h.cleanup();
    }
  });
}

test("cancelling active capture discards the recording without an upload", async () => {
  const h = setupVoice();
  try {
    await h.voice.start("audio");
    h.voice.cancel();
    await h.voice.finish();
    assert.equal(h.recorder.isRecording.value, false);
    assert.equal(h.calls.uploads.length, 0);
    assert.equal(h.calls.sends.length, 0);
  } finally {
    h.cleanup();
  }
});
