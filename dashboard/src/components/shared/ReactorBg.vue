<template>
  <canvas ref="canvasEl" class="reactor-bg-canvas" />
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { useCustomizerStore } from "@/stores/customizer";

const canvasEl = ref<HTMLCanvasElement | null>(null);
const customizer = useCustomizerStore();

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
  const isDark = customizer.isDarkTheme;

  // Background
  ctx.fillStyle = isDark ? "#050507" : "#FFFFFF";
  ctx.fillRect(0, 0, W, H);

  const cols = Math.ceil(W / GRID) + 1;
  const rows = Math.ceil(H / GRID) + 1;

  const mx = smoothX;
  const my = smoothY;

  // Grid lines — dark mode: faint white, light mode: nearly invisible
  ctx.strokeStyle = isDark
    ? "rgba(255, 255, 255, 0.025)"
    : "rgba(0, 49, 83, 0.03)";
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

  // Crosshairs + sockets with energy interaction
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const cx = c * GRID;
      const cy = r * GRID;

      const dx = mx - cx;
      const dy = my - cy;
      const dist = Math.sqrt(dx * dx + dy * dy);

      // Socket dot — dark: deeper black, light: deeper white
      ctx.fillStyle = isDark
        ? "rgba(5, 5, 8, 0.1)"
        : "rgba(240, 244, 248, 0.6)";
      ctx.beginPath();
      ctx.arc(cx, cy, SOCKET_RADIUS, 0, Math.PI * 2);
      ctx.fill();

      let crossAlpha = isDark ? 0.04 : 0.06;
      let crossScale = 1.0;
      let accent = 0; // 0=neutral, 1=cyan dark, 2=blue light
      let eased = 0;

      if (dist < ENERGY_RADIUS) {
        const t = 1 - dist / ENERGY_RADIUS;
        eased = t * t * (3 - 2 * t);

        if (isDark) {
          // Dark mode: crosses glow cyan (Cherenkov)
          crossAlpha = 0.04 + eased * 0.4;
          crossScale = 1.0 - eased * 0.35;
          accent = 1;
        } else {
          // Light mode: crosses darken + depress (ink shadow)
          crossAlpha = 0.06 + eased * 0.5;
          crossScale = 1.0 - eased * 0.3;
          accent = 2;
        }
      }

      if (crossAlpha < 0.01) continue;

      const halfLen = CROSS_SIZE * crossScale;
      let strokeColor: string;

      if (accent === 1) {
        // Dark mode: cyan glow
        const b = Math.floor(eased * 200);
        strokeColor = `rgba(${Math.floor(b * 0.3)}, ${Math.floor(b * 0.85)}, ${b}, ${crossAlpha})`;
      } else if (accent === 2) {
        // Light mode: deep indigo ink
        const ink = Math.floor(80 + eased * 100);
        strokeColor = `rgba(${ink}, ${Math.floor(ink * 0.6)}, ${Math.floor(ink * 0.4)}, ${crossAlpha})`;
      } else {
        // Idle: neutral gray
        strokeColor = isDark
          ? `rgba(255, 255, 255, ${crossAlpha})`
          : `rgba(26, 46, 60, ${crossAlpha})`;
      }

      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = isDark ? 0.35 : 0.4;
      ctx.beginPath();
      ctx.moveTo(cx - halfLen, cy);
      ctx.lineTo(cx + halfLen, cy);
      ctx.moveTo(cx, cy - halfLen);
      ctx.lineTo(cx, cy + halfLen);
      ctx.stroke();
    }
  }

  // Mouse ink-drop radial gradient (light mode) / Cherenkov glow (dark mode)
  if (mx > 0 && my > 0 && mx < W && my < H) {
    if (isDark) {
      // Cherenkov glow
      const grad = ctx.createRadialGradient(mx, my, 0, mx, my, 80);
      grad.addColorStop(0, "rgba(0, 242, 255, 0.1)");
      grad.addColorStop(0.5, "rgba(0, 180, 255, 0.04)");
      grad.addColorStop(1, "rgba(0, 100, 200, 0)");
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(mx, my, 80, 0, Math.PI * 2);
      ctx.fill();
    } else {
      // Light mode: soft indigo ink-drop shadow
      const grad = ctx.createRadialGradient(mx, my, 0, mx, my, 100);
      grad.addColorStop(0, "rgba(26, 46, 80, 0.06)");
      grad.addColorStop(0.6, "rgba(26, 46, 80, 0.02)");
      grad.addColorStop(1, "rgba(26, 46, 80, 0)");
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(mx, my, 100, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

function loop() {
  if (targetX !== -9999) {
    smoothX += (targetX - smoothX) * LERP;
    smoothY += (targetY - smoothY) * LERP;
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
  window.addEventListener("mousemove", onMouseMove);
  window.addEventListener("mouseleave", onMouseLeave);
  loop();
});

onUnmounted(() => {
  window.removeEventListener("resize", resize);
  window.removeEventListener("mousemove", onMouseMove);
  window.removeEventListener("mouseleave", onMouseLeave);
  if (animId) cancelAnimationFrame(animId);
});

function onMouseMove(e: MouseEvent) {
  targetX = e.clientX;
  targetY = e.clientY;
}

function onMouseLeave() {
  targetX = -9999;
  targetY = -9999;
}
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
