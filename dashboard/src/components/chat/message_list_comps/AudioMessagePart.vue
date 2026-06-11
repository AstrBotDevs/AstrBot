<template>
  <div class="audio-message">
    <div class="audio-message-part" :class="{ 'is-playing': isPlaying }">
      <button
        type="button"
        class="audio-play-btn"
        :disabled="!src || hasError"
        :aria-label="isPlaying ? 'Pause' : 'Play'"
        @click="togglePlay"
      >
        <v-icon :icon="isPlaying ? 'mdi-pause' : 'mdi-play'" size="20" />
      </button>

      <div
        ref="waveRef"
        class="audio-wave"
        role="slider"
        tabindex="0"
        :aria-valuemin="0"
        :aria-valuemax="Math.round(duration) || 0"
        :aria-valuenow="Math.round(currentTime)"
        aria-label="Seek"
        @pointerdown="onSeekStart"
        @keydown="onSeekKeydown"
      >
        <span
          v-for="(bar, index) in bars"
          :key="index"
          class="audio-wave-bar"
          :class="{ played: barPlayed(index) }"
          :style="{ height: `${bar}%` }"
        />
      </div>

      <span class="audio-time">{{ formatTime(displayTime) }}</span>

      <audio
        ref="audioRef"
        class="audio-native"
        preload="metadata"
        :src="src"
        @loadedmetadata="onLoadedMetadata"
        @timeupdate="onTimeUpdate"
        @play="isPlaying = true"
        @pause="isPlaying = false"
        @ended="onEnded"
        @error="hasError = true"
      />
    </div>

    <p v-if="text" class="audio-caption">{{ text }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue';

const props = defineProps<{
  src: string;
  text?: string;
  autoplay?: boolean;
}>();

const BAR_COUNT = 44;
const FALLBACK_BARS = Array.from({ length: BAR_COUNT }, (_, i) =>
  // A gentle, symmetric default shape so the control never looks empty.
  Math.round(28 + 52 * Math.abs(Math.sin((i / BAR_COUNT) * Math.PI * 3))),
);

const audioRef = ref<HTMLAudioElement | null>(null);
const waveRef = ref<HTMLElement | null>(null);

const isPlaying = ref(false);
const hasError = ref(false);
const currentTime = ref(0);
const duration = ref(0);
const seeking = ref(false);
const bars = ref<number[]>(FALLBACK_BARS);
const autoplayed = ref(false);

const src = computed(() => props.src);

const displayTime = computed(() =>
  isPlaying.value || currentTime.value > 0 ? currentTime.value : duration.value,
);

const progress = computed(() => {
  if (!duration.value || !Number.isFinite(duration.value)) return 0;
  return Math.min(1, Math.max(0, currentTime.value / duration.value));
});

function barPlayed(index: number): boolean {
  return index / bars.value.length < progress.value;
}

function formatTime(value: number): string {
  if (!Number.isFinite(value) || value < 0) return '0:00';
  const total = Math.floor(value);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

function togglePlay() {
  const el = audioRef.value;
  if (!el) return;
  if (el.paused) {
    void ensureWaveform();
    void el.play();
  } else {
    el.pause();
  }
}

function onLoadedMetadata() {
  const el = audioRef.value;
  if (el && Number.isFinite(el.duration)) {
    duration.value = el.duration;
  }
  maybeAutoplay();
}

function maybeAutoplay() {
  if (!props.autoplay || autoplayed.value) return;
  const el = audioRef.value;
  if (!el || !props.src || hasError.value) return;
  autoplayed.value = true;
  void ensureWaveform();
  // Browsers may reject autoplay without a gesture; sending a message counts as
  // one, but swallow any rejection so the player still works manually.
  void el.play().catch(() => {});
}

function onTimeUpdate() {
  if (seeking.value) return;
  const el = audioRef.value;
  if (el) currentTime.value = el.currentTime;
}

function onEnded() {
  isPlaying.value = false;
  currentTime.value = 0;
}

function seekToClientX(clientX: number) {
  const el = audioRef.value;
  const wave = waveRef.value;
  if (!el || !wave || !duration.value) return;
  const rect = wave.getBoundingClientRect();
  const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
  const time = ratio * duration.value;
  currentTime.value = time;
  el.currentTime = time;
}

function onSeekMove(event: PointerEvent) {
  seekToClientX(event.clientX);
}

function onSeekEnd() {
  seeking.value = false;
  window.removeEventListener('pointermove', onSeekMove);
  window.removeEventListener('pointerup', onSeekEnd);
}

function onSeekStart(event: PointerEvent) {
  if (!src.value || hasError.value) return;
  seeking.value = true;
  seekToClientX(event.clientX);
  window.addEventListener('pointermove', onSeekMove);
  window.addEventListener('pointerup', onSeekEnd);
}

const SEEK_STEP_SECONDS = 5;
function onSeekKeydown(event: KeyboardEvent) {
  const el = audioRef.value;
  if (!el || !duration.value || hasError.value) return;
  let next: number;
  switch (event.key) {
    case 'ArrowRight':
    case 'ArrowUp':
      next = Math.min(duration.value, currentTime.value + SEEK_STEP_SECONDS);
      break;
    case 'ArrowLeft':
    case 'ArrowDown':
      next = Math.max(0, currentTime.value - SEEK_STEP_SECONDS);
      break;
    case 'Home':
      next = 0;
      break;
    case 'End':
      next = duration.value;
      break;
    default:
      return;
  }
  event.preventDefault();
  currentTime.value = next;
  el.currentTime = next;
}

// One AudioContext shared by every player instance: browsers cap concurrent
// contexts, and decoding is the only thing we need it for.
let sharedAudioCtx: AudioContext | null = null;
function getSharedAudioContext(): AudioContext | null {
  if (sharedAudioCtx) return sharedAudioCtx;
  const AudioCtx =
    window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioCtx) return null;
  sharedAudioCtx = new AudioCtx();
  return sharedAudioCtx;
}

// Decode the audio once and compute amplitude peaks for the waveform. This
// downloads the full file, so it only runs lazily on first playback — a chat
// history full of voice messages must not fetch every clip on mount.
let decodeToken = 0;
let waveformStarted = false;
function ensureWaveform() {
  if (waveformStarted) return;
  waveformStarted = true;
  void buildWaveform(src.value);
}

async function buildWaveform(url: string) {
  if (!url) return;
  const token = ++decodeToken;
  const ctx = getSharedAudioContext();
  if (!ctx) return;
  try {
    const resp = await fetch(url);
    const arrayBuffer = await resp.arrayBuffer();
    const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
    if (token !== decodeToken) return;

    const channel = audioBuffer.getChannelData(0);
    const blockSize = Math.floor(channel.length / BAR_COUNT) || 1;
    const peaks: number[] = [];
    let max = 0;
    for (let i = 0; i < BAR_COUNT; i++) {
      let sum = 0;
      const start = i * blockSize;
      for (let j = 0; j < blockSize; j++) {
        sum += Math.abs(channel[start + j] || 0);
      }
      const avg = sum / blockSize;
      peaks.push(avg);
      if (avg > max) max = avg;
    }
    if (max === 0) return;
    bars.value = peaks.map((p) => {
      const norm = p / max;
      // Map to 12%–100% so quiet sections stay visible.
      return Math.round(12 + norm * 88);
    });
  } catch {
    // Keep the fallback bars on any decode/CORS failure.
  }
}

// On src change the <audio> element reloads and fires loadedmetadata again,
// which re-runs maybeAutoplay with the reset flag.
watch(src, () => {
  decodeToken++;
  bars.value = FALLBACK_BARS;
  waveformStarted = false;
  autoplayed.value = false;
  hasError.value = false;
  currentTime.value = 0;
  duration.value = 0;
});

onMounted(maybeAutoplay);

onBeforeUnmount(() => {
  decodeToken++;
  window.removeEventListener('pointermove', onSeekMove);
  window.removeEventListener('pointerup', onSeekEnd);
});
</script>

<style scoped>
.audio-message {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: min(340px, 100%);
  margin-top: 8px;
}

.audio-message-part {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 999px;
  background: rgba(var(--v-theme-surface), 0.95);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}

.audio-caption {
  margin: 0;
  padding: 0 4px;
  font-size: 14px;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), 0.88);
  white-space: pre-wrap;
  word-break: break-word;
}

.audio-native {
  display: none;
}

.audio-play-btn {
  display: grid;
  place-items: center;
  flex: 0 0 36px;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  color: rgb(var(--v-theme-on-primary, 255, 255, 255));
  background: rgb(var(--v-theme-primary));
  cursor: pointer;
  transition:
    transform 0.12s ease,
    box-shadow 0.15s ease,
    opacity 0.15s ease;
  box-shadow: 0 2px 6px rgba(var(--v-theme-primary), 0.35);
}

.audio-play-btn:hover:not(:disabled) {
  transform: scale(1.05);
  box-shadow: 0 4px 10px rgba(var(--v-theme-primary), 0.42);
}

.audio-play-btn:active:not(:disabled) {
  transform: scale(0.95);
}

.audio-play-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.audio-wave {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1 1 auto;
  min-width: 0;
  height: 32px;
  cursor: pointer;
  touch-action: none;
}

.audio-wave-bar {
  flex: 1 1 0;
  min-width: 2px;
  max-width: 4px;
  border-radius: 999px;
  background: rgba(var(--v-theme-on-surface), 0.22);
  transition: background-color 0.12s ease;
}

.audio-wave-bar.played {
  background: rgb(var(--v-theme-primary));
}

.audio-time {
  flex: 0 0 auto;
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  line-height: 1;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

:global(.is-dark) .audio-message-part {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  box-shadow: none;
}

@media (max-width: 600px) {
  .audio-message {
    width: 100%;
  }

  .audio-message-part {
    gap: 10px;
    padding: 8px 12px;
  }
}
</style>
