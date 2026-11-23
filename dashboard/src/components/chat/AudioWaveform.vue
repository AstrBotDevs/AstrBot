<template>
  <div ref="element" class="audio-waveform" aria-hidden="true">
    <canvas ref="canvas" />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RECORDING_SAMPLE_INTERVAL_MS } from "@/composables/useRecording";

const props = defineProps<{ levels: number[]; active: boolean }>();
const element = ref<HTMLElement | null>(null);
const canvas = ref<HTMLCanvasElement | null>(null);
let observer: ResizeObserver | undefined;
let frame: number | null = null;
let sampleTime = 0;
let width = 0;
let offset = 0;
let reducedMotion: MediaQueryList | undefined;

// New samples move by one bar; interpolate the distance on display frames.
function draw(time: number) {
  frame = null;
  const target = canvas.value;
  const context = target?.getContext("2d");
  if (!target || !context || width <= 0) return;
  const ratio = window.devicePixelRatio || 1;
  if (target.width !== Math.round(width * ratio) || target.height !== Math.round(28 * ratio)) {
    target.width = Math.round(width * ratio);
    target.height = Math.round(28 * ratio);
  }
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, 28);
  context.strokeStyle = getComputedStyle(target).color;
  context.lineWidth = 3;
  context.lineCap = "round";
  const phase =
    props.active && !reducedMotion?.matches
      ? Math.min(1, Math.max(0, time - sampleTime) / RECORDING_SAMPLE_INTERVAL_MS)
      : 0;
  if (props.active) offset = phase * 6;
  context.beginPath();
  for (let index = 0; index < Math.ceil(width / 6) + 1; index += 1) {
    const level = props.levels[props.levels.length - 1 - index] || 0;
    const x = width - 1.5 - index * 6 - offset;
    const height = level * 21;
    context.moveTo(x, 14 - height / 2);
    context.lineTo(x, 14 + Math.max(0.01, height / 2));
  }
  context.stroke();
  if (props.active && !reducedMotion?.matches) frame = requestAnimationFrame(draw);
}

watch(
  () => props.levels,
  () => {
    sampleTime = performance.now();
    if (frame === null) frame = requestAnimationFrame(draw);
  },
);
watch(
  () => props.active,
  () => {
    if (frame === null) frame = requestAnimationFrame(draw);
  },
);
onMounted(() => {
  reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  sampleTime = performance.now();
  observer = new ResizeObserver(([entry]) => {
    width = entry.contentRect.width;
    if (frame === null) frame = requestAnimationFrame(draw);
  });
  if (element.value) observer.observe(element.value);
});
onBeforeUnmount(() => {
  observer?.disconnect();
  if (frame !== null) cancelAnimationFrame(frame);
});
</script>

<style scoped>
.audio-waveform {
  height: 28px;
  min-width: 0;
  overflow: hidden;
  color: rgba(var(--v-theme-on-surface), 0.55);
  mask-image: linear-gradient(
    to right,
    transparent,
    black 5%,
    black 95%,
    transparent
  );
}
.audio-waveform canvas {
  display: block;
  width: 100%;
  height: 28px;
  color: inherit;
}
</style>
