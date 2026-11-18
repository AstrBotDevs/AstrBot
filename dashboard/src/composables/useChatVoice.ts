import { chatPreferences } from "@/utils/chatPreferences";
import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
  type Ref,
} from "vue";
import { chatApi, fileApi, providerApi } from "@/api/v1";
import { useRecording } from "@/composables/useRecording";
import type { StagedFileInfo } from "@/composables/useMediaHandling";
import { useModuleI18n } from "@/i18n/composables";
import { useToast } from "@/utils/toast";

export function useChatVoice(options: {
  draft: Ref<string>;
  stagedFiles: Ref<StagedFileInfo[]>;
  contextKey: () => string;
  send: () => Promise<void>;
  configureStt: () => void;
}) {
  const { tm } = useModuleI18n("features/chat");
  const toast = useToast();
  const recording = useRecording();
  const mode = ref<"transcribe" | "audio" | null>(null);
  const processing = ref(false);
  const busy = computed(() => processing.value || recording.isStarting.value);
  const sttProviders = ref<{ title: string; value: string }[]>([]);
  const selectedSttProvider = ref(
    chatPreferences().global.sttProvider || "",
  );
  let epoch = 0;
  let request: AbortController | null = null;

  async function loadProviders() {
    try {
      const response = await providerApi.listByProviderType("speech_to_text");
      if (response.data.status !== "ok")
        throw new Error(response.data.message || "Failed to load providers");
      sttProviders.value = (response.data.data || [])
        .filter((provider) => provider.enable !== false)
        .map((provider) => ({
          title: String(provider.id),
          value: String(provider.id),
        }));
      if (
        !sttProviders.value.some(
          (provider) => provider.value === selectedSttProvider.value,
        )
      ) {
        selectedSttProvider.value = sttProviders.value[0]?.value || "";
      }
    } catch (error) {
      console.error("Failed to load transcription providers:", error);
    }
  }

  function cancel() {
    epoch += 1;
    request?.abort();
    request = null;
    recording.cancelRecording();
    mode.value = null;
    processing.value = false;
  }

  async function start(nextMode: "transcribe" | "audio") {
    if (mode.value || busy.value) return;
    const current = ++epoch;
    mode.value = nextMode;
    try {
      if (nextMode === "transcribe") {
        processing.value = true;
        await loadProviders();
        if (current !== epoch) return;
        processing.value = false;
        if (!selectedSttProvider.value) {
          toast.error(tm("voice.noSttProvider"), {
            timeout: 8000,
            action: { label: tm("voice.configure"), onClick: options.configureStt },
          });
          cancel();
          return;
        }
      }
      await recording.startRecording();
    } catch (error) {
      if (current !== epoch) return;
      console.error("Failed to start recording:", error);
      toast.error(tm("voice.error"));
      cancel();
    }
  }

  async function finish() {
    if (!mode.value || busy.value || !recording.isRecording.value) return;
    const current = epoch;
    const currentMode = mode.value;
    processing.value = true;
    request = new AbortController();
    const signal = request.signal;
    try {
      const file = await recording.stopRecording();
      if (current !== epoch) return;
      if (currentMode === "transcribe") {
        const response = await chatApi.transcribeAudio(
          file,
          selectedSttProvider.value,
          signal,
        );
        if (current !== epoch) return;
        if (response.data.status !== "ok" || !response.data.data?.text) {
          throw new Error(response.data.message || "Transcription failed");
        }
        const draft = options.draft.value;
        options.draft.value =
          draft +
          (draft && !/\s$/.test(draft) ? " " : "") +
          response.data.data.text;
      } else {
        const form = new FormData();
        form.append("file", file);
        const response = await fileApi.upload(form, signal);
        if (current !== epoch) return;
        const data = response.data.data;
        if (response.data.status !== "ok" || !data?.attachment_id) {
          throw new Error(response.data.message || "Audio upload failed");
        }
        options.stagedFiles.value.push({
          attachment_id: data.attachment_id,
          filename: data.filename,
          original_name: file.name,
          url: URL.createObjectURL(file),
          type: "record",
        });
        mode.value = null;
        processing.value = false;
        await options.send();
      }
    } catch (error) {
      if (current !== epoch || signal.aborted) return;
      console.error("Failed to finish voice input:", error);
      toast.error(
        tm(
          currentMode === "transcribe"
            ? "voice.transcriptionFailed"
            : "voice.error",
        ),
      );
    } finally {
      if (current === epoch) {
        mode.value = null;
        processing.value = false;
        request = null;
      }
    }
  }

  watch(selectedSttProvider, (value) =>
    chatPreferences((preferences) => { preferences.global.sttProvider = value; }),
  );
  watch(options.contextKey, cancel, { flush: "sync" });
  watch(recording.error, (error) => {
    if (error) {
      toast.error(tm("voice.error"));
      cancel();
    }
  });
  onMounted(loadProviders);
  onBeforeUnmount(cancel);
  return {
    mode,
    busy,
    sttProviders,
    selectedSttProvider,
    loadProviders,
    isRecording: recording.isRecording,
    levels: recording.levels,
    start,
    finish,
    cancel,
  };
}
