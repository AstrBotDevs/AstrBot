import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { File } from "node:buffer";
import { ref } from "vue";
import ts from "typescript";

function setupRecorder() {
  let grant;
  const stats = { tracksStopped: 0, contextsClosed: 0, instances: [] };
  const callbacks = new Map();
  const unmounts = [];
  const stream = { getTracks: () => [{ stop: () => stats.tracksStopped++ }] };
  class Recorder {
    static isTypeSupported(type) {
      return type === "audio/mp4";
    }
    constructor(_stream, options) {
      this.mimeType = options.mimeType;
      this.state = "inactive";
      stats.instances.push(this);
    }
    start() {
      this.state = "recording";
    }
    stop() {
      this.state = "inactive";
      queueMicrotask(() => {
        this.ondataavailable?.({
          data: new Blob(["recorded audio"], { type: this.mimeType }),
        });
        this.onstop?.();
      });
    }
  }
  class AudioContext {
    createAnalyser() {
      return {
        fftSize: 256,
        getByteTimeDomainData: (array) => array.fill(150),
      };
    }
    createMediaStreamSource() {
      return { connect() {} };
    }
    async resume() {}
    async close() {
      stats.contextsClosed++;
    }
  }
  const sandbox = vm.createContext({
    ref,
    onBeforeUnmount: (fn) => unmounts.push(fn),
    MediaRecorder: Recorder,
    AudioContext,
    navigator: {
      mediaDevices: {
        getUserMedia: () =>
          new Promise((resolve) => {
            grant = resolve;
          }),
      },
    },
    requestAnimationFrame: (fn) => {
      const id = callbacks.size + 1;
      callbacks.set(id, fn);
      return id;
    },
    cancelAnimationFrame: (id) => callbacks.delete(id),
    Blob,
    File,
    Uint8Array,
    DOMException,
    crypto: { randomUUID: () => "recording-id" },
  });
  const source = readFileSync(
    new URL("../src/composables/useRecording.ts", import.meta.url),
    "utf8",
  );
  const code = source
    .replace(/import[^;]+;/, "")
    .replace("export function", "function")
    .replace("export const", "const");
  vm.runInContext(ts.transpile(code), sandbox);
  return {
    recording: sandbox.useRecording(),
    grant: () => grant(stream),
    stats,
    callbacks,
    unmount: () => unmounts.forEach((fn) => fn()),
  };
}

test("permission granted after cancellation immediately releases the microphone", async () => {
  const h = setupRecorder();
  const started = h.recording.startRecording();
  assert.equal(h.recording.isStarting.value, true);
  h.recording.cancelRecording();
  h.grant();
  assert.equal(await started, false);
  assert.equal(h.stats.tracksStopped, 1);
  assert.equal(h.stats.instances.length, 0);
  assert.equal(h.recording.isRecording.value, false);
});

test("finishing capture returns correctly typed audio and releases resources", async () => {
  const h = setupRecorder();
  const started = h.recording.startRecording();
  h.grant();
  await started;
  const file = await h.recording.stopRecording();
  assert.equal(file.name, "recording-id.m4a");
  assert.equal(file.type, "audio/mp4");
  assert.ok(file.size > 0);
  assert.equal(h.stats.tracksStopped, 1);
  assert.equal(h.stats.contextsClosed, 1);
  assert.equal(h.callbacks.size, 0);
  assert.equal(h.recording.isRecording.value, false);
});

test("unmounting during capture stops audio, analysis, and callbacks", async () => {
  const h = setupRecorder();
  const started = h.recording.startRecording();
  h.grant();
  await started;
  h.unmount();
  assert.equal(h.stats.instances[0].state, "inactive");
  assert.equal(h.stats.tracksStopped, 1);
  assert.equal(h.stats.contextsClosed, 1);
  assert.equal(h.callbacks.size, 0);
  assert.equal(h.recording.isRecording.value, false);
});
