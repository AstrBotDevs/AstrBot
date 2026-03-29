<template>
  <canvas ref="canvasEl" class="reactor-bg-canvas" />
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { useReactorBg } from "@/composables/useReactorBg";

const canvasEl = ref<HTMLCanvasElement | null>(null);
const { mouseX, mouseY, onMouseMove, onMouseLeave } = useReactorBg();

const GRID = 24;
const CROSS_SIZE = 4;
const SOCKET_RADIUS = 1.2;
const ENERGY_RADIUS = 120;
const LERP = 0.08;

let ctx: CanvasRenderingContext2D | null = null;
let animId: number | null = null;
let width = 0;
let height = 0;

let smoothX = -9999;
let smoothY = -9999;
let targetX = -9999;
let targetY = -9999;

function draw() {
  if (!ctx || !canvasEl.value) return;

  const W = width;
  const H = height;

  ctx.fillStyle = "#0A0A0C";
  ctx.fillRect(0, 0, W, H);

  const cols = Math.ceil(W / GRID) + 1;
  const rows = Math.ceil(H / GRID) + 1;

  const mx = smoothX;
  const my = smoothY;

  // faint base grid
  ctx.strokeStyle = "rgba(255, 255, 255, 0.025)";
  ctx.lineWidth = 0.5;
  for (let x = 0; x <= W; x += GRID) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, H);
    ctx.stroke();
  }
  for (let y = 0; y <= H; y += GRID) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(W, y);
    ctx.stroke();
  }

  // crosshairs + sockets with energy interaction
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const cx = c * GRID;
      const cy = r * GRID;

      const dx = mx - cx;
      const dy = my - cy;
      const dist = Math.sqrt(dx * dx + dy * dy);

      // socket dot
      ctx.fillStyle = "rgba(5, 5, 8, 0.1)";
      ctx.beginPath();
      ctx.arc(cx, cy, SOCKET_RADIUS, 0, Math.PI * 2);
      ctx.fill();

      let crossAlpha = 0.04;
      let crossScale = 1.0;
      let crossBlue = 0;

      if (dist < ENERGY_RADIUS) {
        const t = 1 - dist / ENERGY_RADIUS;
        const eased = t * t * (3 - 2 * t);
        crossAlpha = 0.04 + eased * 0.4;
        crossScale = 1.0 - eased * 0.35;
        crossBlue = Math.floor(eased * 200);
      }

      if (crossAlpha < 0.01) continue;

      const halfLen = CROSS_SIZE * crossScale;
      const strokeColor = crossBlue > 0
        ? `rgba(${Math.floor(crossBlue * 0.3)}, ${Math.floor(crossBlue * 0.85)}, ${crossBlue}, ${crossAlpha})`
        : `rgba(255, 255, 255, ${crossAlpha})`;

      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 0.35;
      ctx.beginPath();
      ctx.moveTo(cx - halfLen, cy);
      ctx.lineTo(cx + halfLen, cy);
      ctx.moveTo(cx, cy - halfLen);
      ctx.lineTo(cx, cy + halfLen);
      ctx.stroke();
    }
  }
}

function loop() {
  if (targetX !== -9999) {
    smoothX += (targetX - smoothX) * LERP;
    smoothY += (targetY - smoothY) * LERP;
  }
  // Sync from global mouse tracking
  if (mouseX.value !== -9999) {
    targetX = mouseX.value;
    targetY = mouseY.value;
  } else {
    targetX = -9999;
    targetY = -9999;
  }
  draw();
  animId = requestAnimationFrame(loop);
}

function resize() {
  if (!canvasEl.value) return;
  width = window.innerWidth;
  height = window.innerHeight;
  canvasEl.value.width = width;
  canvasEl.value.height = height;
}

onMounted(() => {
  if (!canvasEl.value) return;
  ctx = canvasEl.value.getContext("2d");
  resize();
  window.addEventListener("resize", resize);
  // Track global mouse
  window.addEventListener("mousemove", onMouseMove as EventListener);
  window.addEventListener("mouseleave", onMouseLeave);
  loop();
});

onUnmounted(() => {
  window.removeEventListener("resize", resize);
  window.removeEventListener("mousemove", onMouseMove as EventListener);
  window.removeEventListener("mouseleave", onMouseLeave);
  if (animId) cancelAnimationFrame(animId);
});
</script>

<style scoped>
.reactor-bg-canvas {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  pointer-events: none;
}
</style>
