<template>
  <div class="input-area fade-in">
    <div class="input-shell">
      <textarea
        ref="inputRef"
        v-model="prompt"
        :disabled="disabled"
        :placeholder="placeholder"
        class="input-textarea"
        @keydown="onKeydown"
      />
      <div class="input-actions">
        <div class="left">
          <ProviderModelSelector ref="providerModelSelector" />
        </div>
        <div class="right">
          <input type="file" ref="imageInput" @change="handleFileSelect" accept="image/*" style="display: none" multiple />
          <v-progress-circular v-if="disabled" indeterminate size="16" class="mr-1" width="1.5" />
          <v-btn @click="triggerImageInput" icon="mdi-plus" variant="text" color="deep-purple" class="add-btn" size="small" />
          <v-btn @click="isRecording ? stopRecording() : startRecording()" :icon="isRecording ? 'mdi-stop-circle' : 'mdi-microphone'" variant="text" :color="isRecording ? 'error' : 'deep-purple'" class="record-btn" size="small" />
          <v-btn @click="emitSend" icon="mdi-send" variant="text" color="deep-purple" :disabled="!canSend" class="send-btn" size="small" />
        </div>
      </div>
    </div>

    <AttachmentsPreview
      :images="stagedImagesUrl"
      :audio="stagedAudioUrl"
      :recordingText="tm('voice.recording')"
      @remove:image="removeImage"
      @remove:audio="removeAudio"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed } from 'vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import ProviderModelSelector from '@/components/chat/ProviderModelSelector.vue';
import AttachmentsPreview from '@/components/chat/AttachmentsPreview.vue';
import { postImage as apiPostImage, postFile as apiPostFile } from '@/services/chat.api';

const props = defineProps<{ disabled: boolean }>();
const emit = defineEmits<{
  (e: 'send', payload: { text: string; imageNames: string[]; audioName: string | null; selection: { providerId: string; modelName: string } }): void
}>();

const { t } = useI18n();
const { tm } = useModuleI18n('features/chat');

const prompt = ref('');
const stagedImagesName = ref<string[]>([]);
const stagedImagesUrl = ref<string[]>([]);
const stagedAudioUrl = ref<string | null>(null);

const isRecording = ref(false);
const audioChunks: BlobPart[] = [];
let mediaRecorder: MediaRecorder | null = null;

const ctrlKeyDown = ref(false);
let ctrlKeyTimer: number | null = null;
const ctrlKeyLongPressThreshold = 300;

const providerModelSelector = ref<InstanceType<typeof ProviderModelSelector> | null>(null);
const imageInput = ref<HTMLInputElement | null>(null);
const inputRef = ref<HTMLTextAreaElement | null>(null);

const placeholder = computed(() => 'Ask AstrBot...');
const canSend = computed(() => !!prompt.value.trim() || stagedImagesName.value.length > 0 || !!stagedAudioUrl.value);

function triggerImageInput() {
  imageInput.value?.click();
}

async function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement;
  const files = target.files;
  if (files) {
    for (const file of Array.from(files)) {
      await processAndUploadImage(file);
    }
  }
  // Reset the input value to allow selecting the same file again
  if (target) target.value = '';
}

async function processAndUploadImage(file: File) {
  try {
    const res = await apiPostImage(file);
    const img = res.filename as string;
    stagedImagesName.value.push(img);
    stagedImagesUrl.value.push(URL.createObjectURL(file));
  } catch (err) {
    console.error('Error uploading image:', err);
  }
}

async function startRecording() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaRecorder = new MediaRecorder(stream);
  mediaRecorder.ondataavailable = (event) => {
    audioChunks.push(event.data);
  };
  mediaRecorder.start();
  isRecording.value = true;
}

async function stopRecording() {
  isRecording.value = false;
  mediaRecorder?.stop();
  if (!mediaRecorder) return;
  mediaRecorder.onstop = async () => {
    const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
    audioChunks.splice(0, audioChunks.length);
    mediaRecorder?.stream.getTracks().forEach((track) => track.stop());
    try {
      const res = await apiPostFile(audioBlob);
      const audio = res.filename as string;
      stagedAudioUrl.value = audio;
    } catch (err) {
      console.error('Error uploading audio:', err);
    }
  };
}

function removeAudio() {
  stagedAudioUrl.value = null;
}

function removeImage(index: number) {
  const urlToRevoke = stagedImagesUrl.value[index];
  if (urlToRevoke && urlToRevoke.startsWith('blob:')) URL.revokeObjectURL(urlToRevoke);
  stagedImagesName.value.splice(index, 1);
  stagedImagesUrl.value.splice(index, 1);
}

function handlePaste(event: ClipboardEvent) {
  const items = event.clipboardData?.items;
  if (!items) return;
  for (let i = 0; i < items.length; i++) {
    if (items[i].type.indexOf('image') !== -1) {
      const file = items[i].getAsFile();
      if (file) processAndUploadImage(file);
    }
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (canSend.value) emitSend();
    return;
  }
  if (e.ctrlKey && (e.key === 'b' || e.key === 'B')) {
    e.preventDefault();
    if (ctrlKeyDown.value) return;
    ctrlKeyDown.value = true;
    ctrlKeyTimer = window.setTimeout(() => {
      if (ctrlKeyDown.value && !isRecording.value) startRecording();
    }, ctrlKeyLongPressThreshold);
  }
}

function onKeyup(e: KeyboardEvent) {
  if (e.key === 'b' || e.key === 'B') {
    ctrlKeyDown.value = false;
    if (ctrlKeyTimer) {
      clearTimeout(ctrlKeyTimer);
      ctrlKeyTimer = null;
    }
    if (isRecording.value) stopRecording();
  }
}

function emitSend() {
  if (!canSend.value) return;
  const selection = providerModelSelector.value?.getCurrentSelection?.() || { providerId: '', modelName: '' };
  emit('send', {
    text: prompt.value.trim(),
    imageNames: [...stagedImagesName.value],
    audioName: stagedAudioUrl.value,
    selection: { providerId: selection?.providerId || '', modelName: selection?.modelName || '' },
  });
  // clear local state
  prompt.value = '';
  stagedImagesName.value = [];
  stagedImagesUrl.value.forEach((u) => u.startsWith('blob:') && URL.revokeObjectURL(u));
  stagedImagesUrl.value = [];
  stagedAudioUrl.value = null;
}

onMounted(() => {
  inputRef.value?.addEventListener('paste', handlePaste as any);
  window.addEventListener('keyup', onKeyup);
});

onBeforeUnmount(() => {
  inputRef.value?.removeEventListener('paste', handlePaste as any);
  window.removeEventListener('keyup', onKeyup);
});

defineExpose({ startRecording, stopRecording });
</script>

<style scoped>
.input-area {
  padding: 16px;
  background-color: var(--v-theme-surface);
  position: relative;
  border-top: 1px solid var(--v-theme-border);
  flex-shrink: 0;
}
.input-shell {
  width: 85%;
  max-width: 900px;
  margin: 0 auto;
  border: 1px solid #e0e0e0;
  border-radius: 24px;
}
.input-textarea {
  width: 100%;
  resize: none;
  outline: none;
  border: 1px solid var(--v-theme-border);
  border-radius: 12px;
  padding: 8px 16px;
  min-height: 40px;
  font-family: inherit;
  font-size: 16px;
  background-color: var(--v-theme-surface);
}
.input-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0px 8px;
}
.left {
  display: flex;
  justify-content: flex-start;
  margin-top: 4px;
}
.right {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
  align-items: center;
}
</style>
