<template>
  <div class="bg">
    <svg class="noise">
      <filter id="grain">
        <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="4" stitchTiles="stitch" />
        <feColorMatrix type="saturate" values="0" />
      </filter>
      <rect width="100%" height="100%" filter="url(#grain)" opacity="0.04" />
    </svg>
    <div class="grid">
      <div
        class="cell"
        v-for="i in total"
        :key="i"
        :class="{ recessed: isRecessed(i - 1) }"
      >
        <div class="socket">
          <svg class="cross" viewBox="0 0 10 10">
            <line class="h" x1="0" y1="5" x2="10" y2="5" />
            <line class="v" x1="5" y1="0" x2="5" y2="10" />
          </svg>
          <div class="star"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const cols = 28;
const rows = 16;
const total = computed(() => cols * rows);

// Center zone where login panel floats
const centerX = 50; // %
const centerY = 50; // %
const zoneW = 18; // %
const zoneH = 28; // %

const isRecessed = (idx: number) => {
  const col = idx % cols;
  const row = Math.floor(idx / cols);
  const colPct = (col / cols) * 100;
  const rowPct = (row / rows) * 100;

  const dx = Math.abs(colPct - centerX);
  const dy = Math.abs(rowPct - centerY);

  // Diamond/pit shape: |dx/zoneW| + |dy/zoneH| < 1
  return (dx / zoneW) + (dy / zoneH) < 0.85;
};
</script>

<style scoped>
.bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  background: #050709;
  filter: contrast(1.1) brightness(0.85);
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
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.socket {
  position: relative;
  width: 80%;
  height: 80%;
  background: #0a0c12;
  box-shadow:
    inset 0 1px 1px rgba(255, 255, 255, 0.02),
    inset 0 -1px 1px rgba(0, 0, 0, 0.6);
}

.cell.recessed .socket {
  background: #060810;
  box-shadow:
    inset 0 3px 10px rgba(0, 0, 0, 0.95),
    inset 0 0 20px rgba(0, 30, 60, 0.6);
  transform: scale(0.88);
}

.cross {
  position: absolute;
  inset: 20%;
  width: 60%;
  height: 60%;
}

.cross line {
  stroke: #181b24;
  stroke-width: 0.5;
  stroke-linecap: square;
  fill: none;
  transition: stroke-dasharray 0.3s ease, stroke-dashoffset 0.3s ease;
}

.cell.recessed .cross line {
  stroke: #1c2030;
  stroke-dasharray: 2;
  stroke-dashoffset: 1;
}

.star {
  position: absolute;
  inset: 35%;
  background: transparent;
  transition: all 0.3s ease;
}

.cell.recessed .star {
  background: #0a2040;
  box-shadow:
    0 0 3px rgba(30, 120, 255, 0.6),
    0 0 6px rgba(30, 120, 255, 0.2);
}

.cell.recessed .star::after {
  content: '';
  position: absolute;
  inset: 30%;
  background: rgba(100, 200, 255, 0.9);
}
</style>
