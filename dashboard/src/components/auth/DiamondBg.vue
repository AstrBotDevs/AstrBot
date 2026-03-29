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
        <div class="pin">
          <svg class="cross" viewBox="0 0 10 10">
            <line class="h" x1="0" y1="5" x2="10" y2="5" />
            <line class="v" x1="5" y1="0" x2="5" y2="10" />
          </svg>
        </div>
      </div>
    </div>
    <div class="focus" :style="focusStyle"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";

const bgEl = ref<HTMLElement | null>(null);
const cols = 32;
const rows = 18;
const total = computed(() => cols * rows);

// Mouse position (raw)
const mouseX = ref(0);
const mouseY = ref(0);
// Smooth position (lerped)
const smoothX = ref(0);
const smoothY = ref(0);
// Target position for lerp
const targetX = ref(0);
const targetY = ref(0);
const LERP = 0.08;

const focusStyle = computed(() => ({
  left: `${smoothX.value}px`,
  top: `${smoothY.value}px`,
}));

const onMouseMove = (e: MouseEvent) => {
  targetX.value = e.clientX;
  targetY.value = e.clientY;
};

const onMouseLeave = () => {
  targetX.value = -1000;
  targetY.value = -1000;
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
  const maxDist = Math.min(window.innerWidth, window.innerHeight) * 0.25;

  // Scale: 1 at edge, 0.7 at center
  const scale = 1 - Math.max(0, 1 - dist / maxDist) * 0.3;

  // Depth shadow: darker in center
  const depth = Math.max(0, 1 - dist / maxDist);

  return {
    transform: `scale(${scale})`,
    opacity: 0.7 + (1 - depth) * 0.3,
  };
};

let animId: number | null = null;

const loop = () => {
  // Lerp towards target
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
  background: #050709;
  filter: contrast(1.1) brightness(0.88);
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
  transition: transform 0.25s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

.pin {
  position: relative;
  width: 70%;
  height: 70%;
}

.pin::before {
  content: '';
  position: absolute;
  inset: 0;
  background: #0a0c14;
  box-shadow:
    inset 0 1px 1px rgba(255, 255, 255, 0.02),
    inset 0 -1px 1px rgba(0, 0, 0, 0.5);
}

.cross {
  position: absolute;
  inset: 15%;
  width: 70%;
  height: 70%;
  opacity: 0.4;
}

.cross line {
  stroke: #1a1e2a;
  stroke-width: 0.5;
  stroke-linecap: square;
  fill: none;
}

.focus {
  position: fixed;
  width: 4px;
  height: 4px;
  background: transparent;
  border-radius: 50%;
  pointer-events: none;
  z-index: 5;
  transform: translate(-50%, -50%);
  box-shadow:
    0 0 8px 2px rgba(60, 160, 255, 0.6),
    0 0 20px 4px rgba(60, 160, 255, 0.3),
    0 0 40px 8px rgba(60, 160, 255, 0.1);
}

.focus::after {
  content: '';
  position: absolute;
  inset: -2px;
  background: rgba(140, 210, 255, 0.9);
  border-radius: 50%;
  width: 8px;
  height: 8px;
  transform: translate(-50%, -50%);
  left: 50%;
  top: 50%;
}
</style>
