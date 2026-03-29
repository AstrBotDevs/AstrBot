<template>
  <div class="bg" ref="bgEl" @mousemove="onMouseMove" @mouseleave="onMouseLeave">
    <svg class="noise">
      <filter id="grain">
        <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="4" stitchTiles="stitch" />
        <feColorMatrix type="saturate" values="0" />
      </filter>
      <rect width="100%" height="100%" filter="url(#grain)" opacity="0.035" />
    </svg>
    <div class="grid">
      <div
        class="cell"
        v-for="i in total"
        :key="i"
        :style="getCellStyle(i - 1)"
      >
        <div class="slot">
          <svg class="cross" viewBox="0 0 20 20">
            <rect x="4" y="4" width="12" height="12" />
            <line x1="10" y1="4" x2="10" y2="16" />
            <line x1="4" y1="10" x2="16" y2="10" />
          </svg>
        </div>
      </div>
    </div>
    <div class="glow" :style="glowStyle"></div>
    <div class="focus" :style="focusStyle"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";

const bgEl = ref<HTMLElement | null>(null);
const cols = 36;
const rows = 20;
const total = computed(() => cols * rows);

const loginX = 50;
const loginY = 50;
const loginW = 13;
const loginH = 20;

const targetX = ref(-9999);
const targetY = ref(-9999);
const smoothX = ref(-9999);
const smoothY = ref(-9999);
const LERP = 0.1;

const focusStyle = computed(() => ({
  left: `${smoothX.value}px`,
  top: `${smoothY.value}px`,
}));

const glowStyle = computed(() => ({
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

const isInLoginZone = (col: number, row: number) => {
  const colPct = (col / cols) * 100;
  const rowPct = (row / rows) * 100;
  const dx = Math.abs(colPct - loginX);
  const dy = Math.abs(rowPct - loginY);
  return (dx / loginW + dy / loginH) < 0.75;
};

const getCellStyle = (idx: number) => {
  const col = idx % cols;
  const row = Math.floor(idx / cols);

  const cellW = window.innerWidth / cols;
  const cellH = window.innerHeight / rows;
  const cx = col * cellW + cellW / 2;
  const cy = row * cellH + cellH / 2;

  const inLogin = isInLoginZone(col, row);

  const dx = smoothX.value - cx;
  const dy = smoothY.value - cy;
  const dist = Math.sqrt(dx * dx + dy * dy);
  const maxDist = Math.min(window.innerWidth, window.innerHeight) * 0.22;

  const proximity = Math.max(0, 1 - dist / maxDist);
  const scale = inLogin ? 0.82 : 1 - proximity * 0.22;

  return {
    transform: `scale(${scale})`,
  };
};

let animId: number | null = null;

const loop = () => {
  smoothX.value += (targetX.value - smoothX.value) * LERP;
  smoothY.value += (targetY.value - smoothY.value) * LERP;
  animId = requestAnimationFrame(loop);
};

onMounted(() => {
  loop();
});

onUnmounted(() => {
  if (animId !== null) cancelAnimationFrame(animId);
});
</script>

<style scoped>
.bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  background: #050505;
  filter: contrast(1.06) brightness(0.92);
  cursor: none;
}

.noise {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 10;
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
  transition: transform 0.28s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

.slot {
  position: relative;
  width: 82%;
  height: 82%;
  background: #070709;
  box-shadow:
    inset 0 1px 2px rgba(0, 0, 0, 0.95),
    inset 0 0 8px rgba(0, 0, 0, 0.7);
}

.cross {
  position: absolute;
  inset: 12%;
  width: 76%;
  height: 76%;
}

.cross rect,
.cross line {
  stroke: #181818;
  stroke-width: 0.35;
  fill: none;
}

.glow {
  position: fixed;
  width: 2px;
  height: 2px;
  pointer-events: none;
  z-index: 5;
  transform: translate(-50%, -50%);
  background: rgba(60, 180, 255, 1);
  box-shadow:
    0 0 4px 1px rgba(60, 160, 255, 0.9),
    0 0 8px 1px rgba(60, 160, 255, 0.4);
}

.focus {
  position: fixed;
  width: 2px;
  height: 2px;
  pointer-events: none;
  z-index: 5;
  transform: translate(-50%, -50%);
  background: rgba(160, 220, 255, 0.9);
}
</style>
