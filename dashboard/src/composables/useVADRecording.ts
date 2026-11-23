import { onBeforeUnmount, ref } from "vue";

interface VADOptions {
  onSpeechStart?: () => void;
  onSpeechRealStart?: () => void;
  onSpeechEnd: (audio: Float32Array) => void;
  onVADMisfire?: () => void;
  onFrameProcessed?: (probabilities: { isSpeech: number; notSpeech: number }, frame: Float32Array) => void;
  positiveSpeechThreshold?: number;
  negativeSpeechThreshold?: number;
  redemptionMs?: number;
  preSpeechPadMs?: number;
  minSpeechMs?: number;
  submitUserSpeechOnPause?: boolean;
  model?: "v5" | "legacy";
  startOnLoad?: boolean;
  baseAssetPath?: string;
  onnxWASMBasePath?: string;
}

interface VADInstance {
  start(): void | Promise<void>;
  pause(): void | Promise<void>;
  destroy?: () => void | Promise<void>;
  listening: boolean;
}

const VAD_BASE_ASSET_PATH = "https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.29/dist/";
const VAD_ONNX_WASM_BASE_PATH = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0/dist/";
const VAD_SCRIPT_URLS = [`${VAD_ONNX_WASM_BASE_PATH}ort.wasm.min.js`, `${VAD_BASE_ASSET_PATH}bundle.min.js`];

let vadScriptsPromise: Promise<void> | null = null;

/**
 * Lazily inject the VAD dependency scripts so they don't block the first paint.
 * Scripts must load sequentially because vad-web expects onnxruntime on window.
 */
function ensureVADScriptsLoaded(): Promise<void> {
  if (!vadScriptsPromise) {
    vadScriptsPromise = (async () => {
      for (const src of VAD_SCRIPT_URLS) {
        await new Promise<void>((resolve, reject) => {
          const script = document.createElement("script");
          script.src = src;
          script.onload = () => resolve();
          script.onerror = () => reject(new Error(`Failed to load VAD dependency: ${src}`));
          document.head.appendChild(script);
        });
      }
    })();
    // Allow retrying on the next init attempt if loading failed.
    vadScriptsPromise.catch(() => {
      vadScriptsPromise = null;
    });
  }
  return vadScriptsPromise;
}

declare global {
  interface Window {
    vad?: {
      MicVAD: {
        new: (options: VADOptions) => Promise<VADInstance>;
      };
    };
  }
}

/** Keep microphone operations ordered across start, stop, and unmount. */
export function useVADRecording() {
  const isRecording = ref(false);
  const isSpeaking = ref(false);
  const audioEnergy = ref(0);
  let vadInstance: VADInstance | null = null;
  let lifecycle: Promise<void> = Promise.resolve();
  let generation = 0;
  let activeGeneration = 0;
  let wantsRecording = false;
  let disposed = false;
  let onSpeechStartCallback: (() => void) | null = null;
  let onSpeechEndCallback: ((audio: Float32Array) => void) | null = null;

  function enqueue(operation: () => Promise<void>): Promise<void> {
    lifecycle = lifecycle.then(operation).catch((error) => {
      console.error("VAD lifecycle operation failed:", error);
    });
    return lifecycle;
  }

  function isCurrent(current: number) {
    return !disposed && wantsRecording && current === generation;
  }

  function acceptsEvents() {
    return isCurrent(activeGeneration);
  }

  function invalidateRecording() {
    generation += 1;
    activeGeneration = 0;
    wantsRecording = false;
    isRecording.value = false;
    isSpeaking.value = false;
    audioEnergy.value = 0;
    onSpeechStartCallback = null;
    onSpeechEndCallback = null;
  }

  async function destroyInstance(instance: VADInstance) {
    if (instance.destroy) await instance.destroy();
    else await instance.pause();
  }

  async function ensureInstance(current: number): Promise<VADInstance | null> {
    if (vadInstance) return vadInstance;
    await ensureVADScriptsLoaded();
    if (!isCurrent(current)) return null;
    const factory = window.vad?.MicVAD;
    if (!factory) throw new Error("VAD library not loaded.");

    const instance = await factory.new({
      startOnLoad: false,
      onSpeechStart: () => {
        if (!acceptsEvents()) return;
        isSpeaking.value = true;
        onSpeechStartCallback?.();
      },
      onSpeechRealStart: () => {
        if (acceptsEvents()) console.info("[VAD] Real speech started");
      },
      onSpeechEnd: (audio: Float32Array) => {
        if (!acceptsEvents()) return;
        isSpeaking.value = false;
        onSpeechEndCallback?.(audio);
      },
      onVADMisfire: () => {
        if (acceptsEvents()) isSpeaking.value = false;
      },
      onFrameProcessed: (_probabilities, frame) => {
        if (!acceptsEvents() || !frame.length) return;
        let sum = 0;
        for (const sample of frame) sum += sample * sample;
        const targetEnergy = Math.min(Math.sqrt(sum / frame.length) * 5, 1);
        audioEnergy.value = audioEnergy.value * 0.8 + targetEnergy * 0.2;
      },
      positiveSpeechThreshold: 0.3,
      negativeSpeechThreshold: 0.25,
      redemptionMs: 1400,
      preSpeechPadMs: 800,
      minSpeechMs: 400,
      submitUserSpeechOnPause: false,
      model: "v5",
      baseAssetPath: VAD_BASE_ASSET_PATH,
      onnxWASMBasePath: VAD_ONNX_WASM_BASE_PATH,
    });
    if (disposed) {
      await destroyInstance(instance);
      return null;
    }
    vadInstance = instance;
    return instance;
  }

  function startRecording(onSpeechStart: () => void, onSpeechEnd: (audio: Float32Array) => void): Promise<void> {
    if (disposed) return Promise.resolve();
    if (wantsRecording) return lifecycle;
    wantsRecording = true;
    const current = ++generation;
    onSpeechStartCallback = onSpeechStart;
    onSpeechEndCallback = onSpeechEnd;
    return enqueue(async () => {
      if (!isCurrent(current)) return;
      try {
        const instance = await ensureInstance(current);
        if (!instance || !isCurrent(current)) return;
        activeGeneration = current;
        await instance.start();
        if (isCurrent(current)) isRecording.value = true;
      } catch (error) {
        if (isCurrent(current)) {
          invalidateRecording();
          console.error("Failed to start VAD recording:", error);
        }
        // Finish releasing a failed start before the next queued operation.
        if (vadInstance) await vadInstance.pause();
      }
    });
  }

  function stopRecording(): Promise<void> {
    invalidateRecording();
    return enqueue(async () => {
      if (vadInstance) await vadInstance.pause();
    });
  }

  onBeforeUnmount(() => {
    disposed = true;
    invalidateRecording();
    void enqueue(async () => {
      const instance = vadInstance;
      vadInstance = null;
      if (instance) await destroyInstance(instance);
    });
  });

  return {
    isRecording,
    isSpeaking,
    audioEnergy,
    startRecording,
    stopRecording,
  };
}
