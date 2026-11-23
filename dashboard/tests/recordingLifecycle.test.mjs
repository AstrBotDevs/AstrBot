import assert from "node:assert/strict";
import { flushPromises } from "@vue/test-utils";
import { test, vi } from "vitest";
import { useRecording } from "../src/composables/useRecording.ts";
import { useVADRecording } from "../src/composables/useVADRecording.ts";
import { installMediaDevices } from "./helpers/media.mjs";
import { mountComposable } from "./helpers/mountComposable.mjs";

function setupRecorder() {
  const media = installMediaDevices({ manualPermission: true, mimeType: "audio/mp4" });
  const app = mountComposable(useRecording);
  return { recording: app.result, ...media, unmount: app.unmount };
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

test("finishing an older capture cannot release a new capture or leak its own tracks", async () => {
  const media = installMediaDevices({ manualStop: true });
  const app = mountComposable(useRecording);
  const recording = app.result;
  assert.equal(await recording.startRecording(), true);
  const finished = recording.stopRecording();
  const restarted = await recording.startRecording();
  media.finishStop();
  const file = await finished;
  assert.ok(file.size > 0);
  assert.equal(media.stats.streams[0].tracksStopped, 1);
  if (!restarted) {
    assert.equal(media.stats.instances.length, 1, "a serialized restart must not allocate another recorder early");
    assert.equal(await recording.startRecording(), true);
  }
  assert.equal(recording.isRecording.value, true);
  assert.equal(media.stats.streams.length, 2);
  assert.equal(media.stats.streams[1].tracksStopped, 0);
  app.unmount();
  assert.deepEqual(
    media.stats.streams.map((stream) => stream.tracksStopped),
    [1, 1],
  );
  assert.equal(media.stats.contextsClosed, 2);
  assert.equal(media.callbacks.size, 0);
});

test("VAD initialization that finishes after unmount never starts capture or invokes stale callbacks", async () => {
  let resolveInstance;
  let options;
  const instance = { start: vi.fn(), pause: vi.fn(), destroy: vi.fn(), listening: false };
  vi.stubGlobal("vad", {
    MicVAD: {
      new: vi.fn((input) => {
        options = input;
        return new Promise((resolve) => {
          resolveInstance = resolve;
        });
      }),
    },
  });
  const scripts = [];
  const nativeAppend = document.head.appendChild.bind(document.head);
  vi.spyOn(document.head, "appendChild").mockImplementation((node) => {
    if (node.tagName === "SCRIPT") {
      scripts.push(node);
      queueMicrotask(() => node.dispatchEvent(new Event("load")));
      return node;
    }
    return nativeAppend(node);
  });
  const app = mountComposable(useVADRecording);
  const onSpeechStart = vi.fn();
  const onSpeechEnd = vi.fn();
  const started = app.result.startRecording(onSpeechStart, onSpeechEnd);
  await flushPromises();
  assert.equal(scripts.length, 2, "the lazy runtime dependencies load through the controlled script boundary");
  assert.equal(typeof resolveInstance, "function");
  app.unmount();
  resolveInstance(instance);
  await started;
  assert.equal(instance.start.mock.calls.length, 0);
  assert.equal(app.result.isRecording.value, false);
  assert.ok(instance.pause.mock.calls.length + instance.destroy.mock.calls.length >= 1);
  options.onSpeechStart();
  options.onSpeechEnd(new Float32Array([0.1]));
  assert.equal(onSpeechStart.mock.calls.length, 0);
  assert.equal(onSpeechEnd.mock.calls.length, 0);
});
