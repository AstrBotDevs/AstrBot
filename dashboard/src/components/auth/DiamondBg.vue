<template>
  <div class="diamond-bg">
    <canvas ref="canvas"></canvas>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";

const canvas = ref<HTMLCanvasElement | null>(null);
let animationId: number | null = null;

interface Diamond {
  x: number;
  y: number;
  size: number;
  phase: number;
  speed: number;
}

const createDiamonds = (w: number, h: number): Diamond[] => {
  const diamonds: Diamond[] = [];
  const spacing = 48;
  const cols = Math.ceil(w / spacing) + 2;
  const rows = Math.ceil(h / spacing) + 2;

  for (let i = 0; i < cols; i++) {
    for (let j = 0; j < rows; j++) {
      const offset = (j % 2) * (spacing / 2);
      diamonds.push({
        x: i * spacing + offset,
        y: j * spacing * 0.75,
        size: 8 + Math.random() * 6,
        phase: (i + j * 0.5) * 0.8,
        speed: 0.4 + Math.random() * 0.3,
      });
    }
  }
  return diamonds;
};

const drawDiamond = (
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  size: number,
  alpha: number,
  raised: boolean
) => {
  const d = size / 2;
  const depth = raised ? 0 : size * 0.25;

  // Main body
  ctx.beginPath();
  ctx.moveTo(x, y - d + depth);
  ctx.lineTo(x + d + depth, y);
  ctx.lineTo(x, y + d - depth);
  ctx.lineTo(x - d - depth, y);
  ctx.closePath();

  // Fill with subtle gradient
  const grad = ctx.createLinearGradient(x - d, y - d, x + d, y + d);
  if (raised) {
    grad.addColorStop(0, `rgba(147, 197, 253, ${alpha})`);
    grad.addColorStop(1, `rgba(59, 130, 246, ${alpha * 0.8})`);
  } else {
    grad.addColorStop(0, `rgba(30, 64, 175, ${alpha * 0.6})`);
    grad.addColorStop(1, `rgba(30, 58, 138, ${alpha * 0.4})`);
  }
  ctx.fillStyle = grad;
  ctx.fill();

  // Top edge highlight
  ctx.strokeStyle = `rgba(255, 255, 255, ${alpha * (raised ? 0.5 : 0.2)})`;
  ctx.lineWidth = 0.8;
  ctx.beginPath();
  ctx.moveTo(x - d + depth, y);
  ctx.lineTo(x, y - d + depth);
  ctx.lineTo(x + d + depth, y);
  ctx.stroke();
};

onMounted(() => {
  if (!canvas.value) return;
  const ctx = canvas.value.getContext("2d");
  if (!ctx) return;

  let diamonds: Diamond[] = [];
  let t = 0;

  const resize = () => {
    if (!canvas.value) return;
    canvas.value.width = window.innerWidth;
    canvas.value.height = window.innerHeight;
    diamonds = createDiamonds(canvas.value.width, canvas.value.height);
  };

  const animate = () => {
    if (!canvas.value || !ctx) return;
    ctx.clearRect(0, 0, canvas.value.width, canvas.value.height);
    t += 0.015;

    diamonds.forEach((d) => {
      const floatY = Math.sin(t * d.speed + d.phase) * 5;
      const raised = Math.sin(t * d.speed + d.phase) > 0;
      const alpha = 0.25 + Math.abs(Math.sin(t * d.speed + d.phase)) * 0.35;
      drawDiamond(ctx, d.x, d.y + floatY, d.size, alpha, raised);
    });

    animationId = requestAnimationFrame(animate);
  };

  resize();
  animate();
  window.addEventListener("resize", resize);
});

onUnmounted(() => {
  if (animationId !== null) cancelAnimationFrame(animationId);
});
</script>

<style scoped>
.diamond-bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  background: linear-gradient(145deg, #0c1322 0%, #1a2744 40%, #0c1322 100%);
}

canvas {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
