<template>
  <div class="bg">
    <canvas ref="canvas"></canvas>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";

const canvas = ref<HTMLCanvasElement | null>(null);
let animId: number | null = null;

interface Cross {
  x: number;
  y: number;
  phase: number;
}

const createGrid = (w: number, h: number): Cross[] => {
  const grid: Cross[] = [];
  const s = 32;
  for (let i = 0; i < Math.ceil(w / s) + 2; i++) {
    for (let j = 0; j < Math.ceil(h / s) + 2; j++) {
      grid.push({
        x: i * s + (j % 2) * (s / 2),
        y: j * s * 0.75,
        phase: (i + j * 0.5) * 0.25,
      });
    }
  }
  return grid;
};

const draw = (ctx: CanvasRenderingContext2D, w: number, h: number, t: number) => {
  ctx.fillStyle = "#090a0d";
  ctx.fillRect(0, 0, w, h);

  const s = 32;
  const arm = 5;
  const barH = 2;
  const barW = 10;

  for (let i = 0; i < Math.ceil(w / s) + 2; i++) {
    for (let j = 0; j < Math.ceil(h / (s * 0.75)) + 2; j++) {
      const x = i * s + (j % 2) * (s / 2);
      const y = j * s * 0.75;
      const pulse = 0.4 + 0.4 * Math.sin(t * 0.15 + (i + j) * 0.3);

      // Recessed socket (square notch)
      ctx.strokeStyle = "#1a1c22";
      ctx.lineWidth = 0.5;
      ctx.strokeRect(x - 6, y - 6, 12, 12);

      // Cross arms
      ctx.strokeStyle = "#1e2028";
      ctx.lineWidth = barH;
      ctx.lineCap = "square";
      // Horizontal
      ctx.beginPath();
      ctx.moveTo(x - arm, y);
      ctx.lineTo(x + arm, y);
      ctx.stroke();
      // Vertical
      ctx.beginPath();
      ctx.moveTo(x, y - arm);
      ctx.lineTo(x, y + arm);
      ctx.stroke();

      // Diamond spark at center
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(Math.PI / 4);
      const sparkSize = 1 + pulse;
      ctx.fillStyle = `rgba(180, 210, 255, ${pulse})`;
      ctx.fillRect(-sparkSize / 2, -sparkSize / 2, sparkSize, sparkSize);
      ctx.restore();
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
    t += 0.01;
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
  background: #090a0d;
}
canvas {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
