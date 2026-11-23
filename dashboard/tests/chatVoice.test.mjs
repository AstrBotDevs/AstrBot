import assert from "node:assert/strict";
import { flushPromises } from "@vue/test-utils";
import { createPinia } from "pinia";
import { onTestFinished, test, vi } from "vitest";
import { nextTick, ref } from "vue";
import { chatApi, fileApi, providerApi } from "../src/api/v1.ts";
import { useChatVoice } from "../src/composables/useChatVoice.ts";
import { installMediaDevices } from "./helpers/media.mjs";
import { mountComposable } from "./helpers/mountComposable.mjs";

function setupVoice(initialStorage = {}) {
  for (const [key, value] of Object.entries({ user: "alice", ...initialStorage })) localStorage.setItem(key, value);
  installMediaDevices();
  const draft = ref("Existing draft");
  const stagedFiles = ref([]);
  const contextKey = ref("chat-a");
  const calls = { transcriptions: [], uploads: [], sends: [], errors: [] };
  vi.spyOn(providerApi, "listByProviderType").mockResolvedValue({
    data: { status: "ok", data: [{ id: "first" }, { id: "second" }, { id: "disabled", enable: false }] },
  });
  vi.spyOn(chatApi, "transcribeAudio").mockImplementation(
    (...args) => new Promise((resolve) => calls.transcriptions.push({ args, resolve })),
  );
  vi.spyOn(fileApi, "upload").mockImplementation(
    (...args) => new Promise((resolve) => calls.uploads.push({ args, resolve })),
  );
  const objectUrlDescriptor = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
  onTestFinished(() => {
    if (objectUrlDescriptor) Object.defineProperty(URL, "createObjectURL", objectUrlDescriptor);
    else delete URL.createObjectURL;
  });
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    writable: true,
    value: vi.fn(() => "blob:preview"),
  });
  const app = mountComposable(
    () =>
      useChatVoice({
        draft,
        stagedFiles,
        contextKey: () => contextKey.value,
        send: async () => calls.sends.push([...stagedFiles.value]),
        configureStt: vi.fn(),
      }),
    { global: { plugins: [createPinia()] } },
  );
  return {
    voice: app.result,
    draft,
    stagedFiles,
    contextKey,
    calls,
    recorder: { isRecording: app.result.isRecording },
    get storage() {
      return new Map(Object.keys(localStorage).map((key) => [key, localStorage.getItem(key)]));
    },
    cleanup: app.unmount,
  };
}

const flush = flushPromises;

test("dictation uses selected STT, appends to the draft, and never sends audio", async () => {
  const h = setupVoice();
  try {
    await h.voice.start("transcribe");
    assert.equal(h.voice.selectedSttProvider.value, "first");
    assert.equal(h.voice.sttProviders.value.length, 2);
    h.voice.selectedSttProvider.value = "second";
    await nextTick();
    assert.equal(JSON.parse(h.storage.get("astrbot.chat.preferences")).users.alice.global.sttProvider, "second");
    assert.equal(h.storage.has("chat.sttProvider"), false);
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
      const pending = mode === "transcribe" ? h.calls.transcriptions[0] : h.calls.uploads[0];
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

for (const format of ["legacy", "consolidated"]) {
  test(`dictation restores the saved provider from ${format} preferences`, async () => {
    const h = setupVoice(
      format === "legacy"
        ? { "chat.sttProvider": "second" }
        : {
            "astrbot.chat.preferences": JSON.stringify({
              version: 1,
              users: {
                alice: { global: { sttProvider: "second" }, sessions: {} },
              },
            }),
          },
    );
    try {
      assert.equal(h.voice.selectedSttProvider.value, "second");
      await h.voice.start("transcribe");
      assert.equal(h.voice.selectedSttProvider.value, "second");
      assert.equal(JSON.parse(h.storage.get("astrbot.chat.preferences")).users.alice.global.sttProvider, "second");
      assert.equal(h.storage.has("chat.sttProvider"), false);
    } finally {
      h.cleanup();
    }
  });
}
