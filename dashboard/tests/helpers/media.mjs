import { onTestFinished, vi } from "vitest";

export function installMediaDevices({ manualPermission = false, manualStop = false, mimeType = "audio/webm" } = {}) {
  let grant;
  let frameId = 0;
  const stats = { tracksStopped: 0, contextsClosed: 0, instances: [], streams: [] };
  const callbacks = new Map();
  const pendingStops = [];
  function createStream() {
    const record = { tracksStopped: 0 };
    const track = {
      stop: () => {
        record.tracksStopped++;
        stats.tracksStopped++;
      },
    };
    record.stream = { getTracks: () => [track] };
    stats.streams.push(record);
    return record.stream;
  }
  const original = Object.getOwnPropertyDescriptor(navigator, "mediaDevices");
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: vi.fn(() =>
        manualPermission
          ? new Promise((resolve) => {
              grant = () => resolve(createStream());
            })
          : Promise.resolve(createStream()),
      ),
    },
  });
  onTestFinished(() => {
    if (original) Object.defineProperty(navigator, "mediaDevices", original);
    else delete navigator.mediaDevices;
  });
  class Recorder {
    static isTypeSupported(type) {
      return type === mimeType;
    }
    constructor(_stream, options) {
      this.mimeType = options?.mimeType || mimeType;
      this.state = "inactive";
      stats.instances.push(this);
    }
    start() {
      this.state = "recording";
    }
    stop() {
      this.state = "inactive";
      const finish = () => {
        this.ondataavailable?.({ data: new Blob(["recorded audio"], { type: this.mimeType }) });
        this.onstop?.();
      };
      if (manualStop) pendingStops.push(finish);
      else queueMicrotask(finish);
    }
  }
  class AudioContext {
    createAnalyser() {
      return { fftSize: 256, getByteTimeDomainData: (array) => array.fill(150) };
    }
    createMediaStreamSource() {
      return { connect() {} };
    }
    async resume() {}
    async close() {
      stats.contextsClosed++;
    }
  }
  vi.stubGlobal("MediaRecorder", Recorder);
  vi.stubGlobal("AudioContext", AudioContext);
  vi.stubGlobal("requestAnimationFrame", (callback) => {
    callbacks.set(++frameId, callback);
    return frameId;
  });
  vi.stubGlobal("cancelAnimationFrame", (id) => callbacks.delete(id));
  vi.spyOn(crypto, "randomUUID").mockReturnValue("recording-id");
  return { stats, callbacks, grant: () => grant(), finishStop: () => pendingStops.shift()?.() };
}
