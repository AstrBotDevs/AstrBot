<template>
  <div class="star-bg">
    <canvas ref="canvas"></canvas>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";

const canvas = ref<HTMLCanvasElement | null>(null);
let animId: number | null = null;

interface Star {
  x: number;
  y: number;
  s: number;
  phase: number;
  spd: number;
}

const createGrid = (w: number, h: number): Star[] => {
  const stars: Star[] = [];
  const s = 28;
  const hStep = s * 0.866;
  const cols = Math.ceil(w / s) + 2;
  const rows = Math.ceil(h / hStep) + 2;

  for (let i = 0; i < cols; i++) {
    for (let j = 0; j < rows; j++) {
      stars.push({
        x: i * s + (j % 2) * (s / 2),
        y: j * hStep,
        s: 5 + Math.random() * 3,
        phase: Math.random() * Math.PI * 2,
        spd: 0.3 + Math.random() * 0.4,
      });
    }
  }
  return stars;
};

const draw = (
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  s: number,
  a: number,
  up: boolean
) => {
  const h = s * 0.5;
  const d = up ? 0 : h * 0.4;

  ctx.beginPath();
  ctx.moveTo(x, y - h + d);
  ctx.lineTo(x + s * 0.5 + d, y);
  ctx.lineTo(x, y + h - d);
  ctx.lineTo(x - s * 0.5 - d, y);
  ctx.closePath();

  const g = ctx.createLinearGradient(x, y - h, x, y + h);
  g.addColorStop(0, `rgba(180, 210, 255, ${a})`);
  g.addColorStop(1, `rgba(80, 140, 220, ${a * 0.6})`);
  ctx.fillStyle = g;
  ctx.fill();

  ctx.strokeStyle = `rgba(220, 240, 255, ${a * 0.4})`;
  ctx.lineWidth = 0.5;
  ctx.stroke();
};

onMounted(() => {
  if (!canvas.value) return;
  const ctx = canvas.value.getContext("2d");
  if (!ctx) return;

  let stars: Star[] = [];
  let t = 0;

  const resize = () => {
    if (!canvas.value) return;
    canvas.value.width = window.innerWidth;
    canvas.value.height = window.innerHeight;
    stars = createGrid(canvas.value.width, canvas.value.height);
  };

  const loop = () => {
    if (!canvas.value || !ctx) return;
    ctx.clearRect(0, 0, canvas.value.width, canvas.value.height);
    t += 0.012;

    stars.forEach((st) => {
      const fy = Math.sin(t * st.spd + st.phase) * 3;
      const up = Math.sin(t * st.spd + st.phase) > 0;
      const a = 0.2 + Math.abs(Math.sin(t * st.spd + st.phase)) * 0.5;
      draw(ctx, st.x, st.y + fy, st.s, a, up);
    });

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
.star-bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  background: #0a0e1a;
}

canvas {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
