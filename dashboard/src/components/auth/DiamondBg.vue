<template>
  <div class="bg" ref="bgEl" @mousemove="onMouseMove" @mouseleave="onMouseLeave">
    <div class="torch" :style="torchStyle"></div>
    <div class="grid">
      <div class="cell" v-for="i in total" :key="i" :style="getCellStyle(i - 1)">
        <div class="socket">
          <svg viewBox="0 0 20 20" class="etch">
            <rect x="5" y="5" width="10" height="10" />
            <line x1="10" y1="5" x2="10" y2="15" />
            <line x1="5" y1="10" x2="15" y2="10" />
          </svg>
        </div>
      </div>
    </div>
    <div class="core" :style="coreStyle"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";

const bgEl = ref<HTMLElement | null>(null);
const cols = 40;
const rows = 22;
const total = computed(() => cols * rows);

const targetX = ref(-9999);
const targetY = ref(-9999);
const smoothX = ref(-9999);
const smoothY = ref(-9999);
const LERP = 0.12;

const torchStyle = computed(() => ({
  "--x": `${smoothX.value}px`,
  "--y": `${smoothY.value}px`,
}));

const coreStyle = computed(() => ({
  left: `${smoothX.value}px`,
  top: `${smoothY.value}px`,
}));

const onMouseMove = (e: MouseEvent) => {
  targetX.value = e.clientX;
  targetY.value = e.clientY;
};

const onMouseLeave = () => {
  targetX.value = -9999;
  targetY.value = -9999;
};

const getCellStyle = (idx: number) => {
  const col = idx % cols;
  const row = Math.floor(idx / cols);
  const cellW = window.innerWidth / cols;
  const cellH = window.innerHeight / rows;
  const cx = col * cellW + cellW / 2;
  const cy = row * cellH + cellH / 2;

  const dx = smoothX.value - cx;
  const dy = smoothY.value - cy;
  const dist = Math.sqrt(dx * dx + dy * dy);
  const maxDist = 180;

  if (dist > maxDist) {
    return { opacity: "0" };
  }

  const reveal = 1 - dist / maxDist;
  return {
    opacity: String(reveal * 0.4),
    transform: `scale(${0.9 + reveal * 0.1})`,
  };
};

let animId: number | null = null;
const loop = () => {
  smoothX.value += (targetX.value - smoothX.value) * LERP;
  smoothY.value += (targetY.value - smoothY.value) * LERP;
  animId = requestAnimationFrame(loop);
};

onMounted(() => { loop(); });
onUnmounted(() => { if (animId) cancelAnimationFrame(animId); });
</script>

<style scoped>
.bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  background: #050505;
  cursor: none;
  overflow: hidden;
}

.torch {
  position: fixed;
  inset: 0;
  z-index: 5;
  background: radial-gradient(
    circle at var(--x) var(--y),
    rgba(0, 200, 255, 0.08) 0%,
    rgba(0, 150, 255, 0.03) 80px,
    transparent 180px
  );
  pointer-events: none;
}

.grid {
  position: relative;
  z-index: 0;
  display: grid;
  grid-template-columns: repeat(v-bind(cols), 1fr);
  grid-template-rows: repeat(v-bind(rows), 1fr);
  width: 100%;
  height: 100vh;
}

.cell {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.15s ease;
}

.socket {
  width: 70%;
  height: 70%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.etch {
  width: 100%;
  height: 100%;
  opacity: 0.6;
}

.etch rect,
.etch line {
  stroke: #1a1a1a;
  stroke-width: 0.3;
  fill: none;
}

.core {
  position: fixed;
  width: 2px;
  height: 2px;
  z-index: 10;
  pointer-events: none;
  transform: translate(-50%, -50%);
  background: rgba(0, 220, 255, 0.95);
  box-shadow:
    0 0 4px 1px rgba(0, 200, 255, 0.8),
    0 0 10px 2px rgba(0, 200, 255, 0.3);
}
</style>
