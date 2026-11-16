import { onBeforeUnmount, ref } from "vue";

export const RECORDING_SAMPLE_INTERVAL_MS = 150;

export function useRecording() {
  const isRecording = ref(false);
  const isStarting = ref(false);
  const levels = ref<number[]>(Array(256).fill(0));
  const error = ref<Error | null>(null);
  let recorder: MediaRecorder | null = null;
  let stream: MediaStream | null = null;
  let context: AudioContext | null = null;
  let chunks: Blob[] = [];
  let frame: number | null = null;
  let generation = 0;
  let rejectStop: ((reason: Error) => void) | null = null;

  // Shared by cancellation, normal completion, and recording failures.
  function releaseMicrophone() {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    stream?.getTracks().forEach((track) => track.stop());
    stream = null;
    if (context) void context.close().catch(() => {});
    context = null;
    recorder = null;
    isRecording.value = false;
  }

  function cancelRecording() {
    generation += 1;
    if (recorder) {
      recorder.ondataavailable = null;
      recorder.onstop = null;
      recorder.onerror = null;
      if (recorder.state !== "inactive") recorder.stop();
    }
    rejectStop?.(new DOMException("Recording cancelled", "AbortError"));
    rejectStop = null;
    chunks = [];
    isStarting.value = false;
    releaseMicrophone();
    levels.value = Array(256).fill(0);
  }

  async function startRecording(): Promise<boolean> {
    if (isStarting.value || isRecording.value) return false;
    const current = ++generation;
    isStarting.value = true;
    error.value = null;
    chunks = [];
    levels.value = Array(256).fill(0);
    try {
      if (
        !navigator.mediaDevices?.getUserMedia ||
        typeof MediaRecorder === "undefined"
      ) {
        throw new Error("Audio recording is not supported in this browser");
      }
      const acquired = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });
      if (current !== generation) {
        acquired.getTracks().forEach((track) => track.stop());
        return false;
      }
      stream = acquired;
      const mimeType = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/ogg;codecs=opus",
        "audio/ogg",
        "audio/mp4",
        "audio/wav",
      ].find((type) => MediaRecorder.isTypeSupported(type));
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data);
      };
      recorder.onerror = () => {
        error.value = new Error("Audio recording failed");
        cancelRecording();
      };
      context = new AudioContext();
      const analyser = context.createAnalyser();
      analyser.fftSize = 256;
      context.createMediaStreamSource(stream).connect(analyser);
      await context.resume();
      if (current !== generation) return false;
      const samples = new Uint8Array(analyser.fftSize);
      let lastSample = 0;
      const sample = (time: number) => {
        if (current !== generation) return;
        if (time - lastSample >= RECORDING_SAMPLE_INTERVAL_MS) {
          analyser.getByteTimeDomainData(samples);
          let power = 0;
          for (const value of samples) power += ((value - 128) / 128) ** 2;
          const amplitude = Math.min(1, Math.sqrt(power / samples.length) * 4);
          levels.value = [...levels.value.slice(1), amplitude];
          lastSample = time;
        }
        frame = requestAnimationFrame(sample);
      };
      recorder.start();
      isRecording.value = true;
      frame = requestAnimationFrame(sample);
      return true;
    } catch (cause) {
      if (current !== generation) return false;
      releaseMicrophone();
      throw cause;
    } finally {
      if (current === generation) isStarting.value = false;
    }
  }

  async function stopRecording(): Promise<File> {
    const active = recorder;
    if (!active || active.state === "inactive")
      throw new Error("No active recording");
    isRecording.value = false;
    return new Promise((resolve, reject) => {
      rejectStop = reject;
      active.onstop = () => {
        const type =
          chunks.find((chunk) => chunk.type)?.type ||
          active.mimeType ||
          "audio/webm";
        const blob = new Blob(chunks, { type });
        chunks = [];
        rejectStop = null;
        releaseMicrophone();
        if (!blob.size) {
          reject(new Error("Recording is empty"));
          return;
        }
        const subtype = type.split("/")[1]?.split(";")[0];
        const extension = subtype === "mp4" ? "m4a" : subtype || "webm";
        resolve(
          new File([blob], `${crypto.randomUUID()}.${extension}`, { type }),
        );
      };
      active.onerror = () => {
        rejectStop = null;
        releaseMicrophone();
        reject(new Error("Audio recording failed"));
      };
      try {
        active.stop();
      } catch (cause) {
        rejectStop = null;
        releaseMicrophone();
        reject(cause);
      }
    });
  }

  onBeforeUnmount(cancelRecording);
  return {
    isRecording,
    isStarting,
    levels,
    error,
    startRecording,
    stopRecording,
    cancelRecording,
  };
}
