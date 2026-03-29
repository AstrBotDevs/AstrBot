<template>
  <div class="bg">
    <canvas ref="canvas"></canvas>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";

const canvas = ref<HTMLCanvasElement | null>(null);
let animId: number | null = null;

interface Cylinder {
  x: number;
  y: number;
  phase: number;
}

const createGrid = (w: number, h: number): Cylinder[] => {
  const grid: Cylinder[] = [];
  const sx = 44, sy = 38;
  const cols = Math.ceil(w / sx) + 2;
  const rows = Math.ceil(h / sy) + 2;

  for (let i = 0; i < cols; i++) {
    for (let j = 0; j < rows; j++) {
      grid.push({
        x: i * sx + (j % 2) * (sx / 2),
        y: j * sy,
        phase: (i + j * 0.5) * 0.3,
      });
    }
  }
  return grid;
};

const draw = (ctx: CanvasRenderingContext2D, w: number, h: number, t: number) => {
  ctx.fillStyle = "#0c0e12";
  ctx.fillRect(0, 0, w, h);

  const sx = 44, sy = 38;
  const cols = Math.ceil(w / sx) + 2;
  const rows = Math.ceil(h / sy) + 2;

  for (let i = 0; i < cols; i++) {
    for (let j = 0; j < rows; j++) {
      const x = i * sx + (j % 2) * (sx / 2);
      const y = j * sy;

      // Outer rim
      ctx.beginPath();
      ctx.arc(x, y, 8, 0, Math.PI * 2);
      ctx.fillStyle = "#1a1c22";
      ctx.fill();

      // Recessed cylinder body
      ctx.beginPath();
      ctx.arc(x, y, 7, 0, Math.PI * 2);
      const bodyGrad = ctx.createRadialGradient(x, y - 2, 0, x, y, 7);
      bodyGrad.addColorStop(0, "#14161c");
      bodyGrad.addColorStop(1, "#0a0b0e");
      ctx.fillStyle = bodyGrad;
      ctx.fill();

      // Sharp outer rim highlight
      ctx.beginPath();
      ctx.arc(x, y, 8, 0, Math.PI * 2);
      ctx.strokeStyle = "#2a2c34";
      ctx.lineWidth = 0.5;
      ctx.stroke();

      // Deep indigo glow from depth
      const depthPulse = 0.15 + 0.1 * Math.sin(t * 0.2);
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      const glowGrad = ctx.createRadialGradient(x, y, 0, x, y, 4);
      glowGrad.addColorStop(0, `rgba(60, 40, 120, ${depthPulse})`);
      glowGrad.addColorStop(1, "transparent");
      ctx.fillStyle = glowGrad;
      ctx.fill();

      // Starlight pinpoint at center
      const starPulse = 0.6 + 0.4 * Math.sin(t * 0.3 + (i + j) * 0.2);
      ctx.beginPath();
      ctx.arc(x, y, 1, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(220, 230, 255, ${starPulse})`;
      ctx.fill();
    }
  }
};

onMounted(() => {
  if (!canvas.value) return;
  const ctx = canvas.value.getContext("2d");
  if (!ctx) return;

  let t = 0;

  const resize = () => {
    if (!canvas.value) return;
    canvas.value.width = window.innerWidth;
    canvas.value.height = window.innerHeight;
  };

  const loop = () => {
    if (!canvas.value || !ctx) return;
    draw(ctx, canvas.value.width, canvas.value.height, t);
    t += 0.015;
    animId = requestAnimationFrame(loop);
  };

  resize();
  loop();
  window.addEventListener("resize", resize);
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
  background: #0c0e12;
}

canvas {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
