<template>
  <div
    class="bg"
    ref="bgEl"
    @mousemove="onMouseMove"
    @mouseleave="onMouseLeave"
  >
    <canvas ref="canvasEl" class="bg-canvas"></canvas>
    <div class="gravity-well"></div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed } from "vue";
import { useCustomizerStore } from "@/stores/customizer";

const customizer = useCustomizerStore();
const isDark = computed(() => customizer.isDarkTheme);

const bgEl = ref<HTMLElement | null>(null);
const canvasEl = ref<HTMLCanvasElement | null>(null);

const GRID = 24; // grid cell size in px
const CROSS_SIZE = 5; // crosshair half-length
const SOCKET_RADIUS = 1.5; // recessed socket dot radius
const ENERGY_RADIUS = 150; // mouse energy field radius
const LERP = 0.1; // follow speed
const SINK_DEPTH = 0.4; // how much crosses shrink when pressed

// mouse tracking with lerp
const targetX = ref(-9999);
const targetY = ref(-9999);
const smoothX = ref(-9999);
const smoothY = ref(-9999);

let ctx: CanvasRenderingContext2D | null = null;
let animId: number | null = null;
let width = 0;
let height = 0;

const onMouseMove = (e: MouseEvent) => {
  targetX.value = e.clientX;
  targetY.value = e.clientY;
};

const onMouseLeave = () => {
  targetX.value = -9999;
  targetY.value = -9999;
};

function draw() {
  if (!ctx || !canvasEl.value) return;

  const W = width;
  const H = height;
  const dark = isDark.value;

  // clear
  ctx.fillStyle = dark ? "#0A0A0C" : "#FFFFFF";
  ctx.fillRect(0, 0, W, H);

  const cols = Math.ceil(W / GRID) + 1;
  const rows = Math.ceil(H / GRID) + 1;

  const mx = smoothX.value;
  const my = smoothY.value;

  // draw static base grid (very faint)
  ctx.strokeStyle = dark
    ? "rgba(255, 255, 255, 0.03)"
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

  // draw crosshairs + sockets with interaction
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const cx = c * GRID;
      const cy = r * GRID;

      const dx = mx - cx;
      const dy = my - cy;
      const dist = Math.sqrt(dx * dx + dy * dy);

      // socket dot at intersection (always visible, very subtle)
      const socketAlpha = 0.08;
      ctx.fillStyle = `rgba(5, 5, 8, ${socketAlpha})`;
      ctx.beginPath();
      ctx.arc(cx, cy, SOCKET_RADIUS, 0, Math.PI * 2);
      ctx.fill();

      // crosshair
      let crossAlpha = 0.05;
      let crossScale = 1.0;
      let crossBlue = 0;

      if (dist < ENERGY_RADIUS) {
        const t = 1 - dist / ENERGY_RADIUS;
        const eased = t * t * (3 - 2 * t);
        crossAlpha = dark ? 0.05 + eased * 0.35 : 0.04 + eased * 0.4;
        crossScale = 1.0 - eased * SINK_DEPTH;
        crossBlue = dark ? Math.floor(eased * 180) : 0;
      }

      if (crossAlpha < 0.01) continue;

      const halfLen = CROSS_SIZE * crossScale;
      const strokeColor =
        crossBlue > 0
          ? `rgba(${crossBlue * 0.3}, ${crossBlue * 0.8}, ${crossBlue}, ${crossAlpha})`
          : dark
            ? `rgba(255, 255, 255, ${crossAlpha})`
            : `rgba(26, 46, 60, ${crossAlpha})`;

      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 0.4;
      ctx.beginPath();
      ctx.moveTo(cx - halfLen, cy);
      ctx.lineTo(cx + halfLen, cy);
      ctx.moveTo(cx, cy - halfLen);
      ctx.lineTo(cx, cy + halfLen);
      ctx.stroke();
    }
  }

  // core mouse dot at exact mouse position
  if (mx > 0 && my > 0 && mx < W && my < H) {
    if (dark) {
      const grad = ctx.createRadialGradient(mx, my, 0, mx, my, 6);
      grad.addColorStop(0, "rgba(0, 242, 255, 0.95)");
      grad.addColorStop(0.3, "rgba(0, 210, 255, 0.6)");
      grad.addColorStop(1, "rgba(0, 180, 255, 0)");
      ctx.fillStyle = grad;
    } else {
      const grad = ctx.createRadialGradient(mx, my, 0, mx, my, 6);
      grad.addColorStop(0, "rgba(0, 49, 83, 0.4)");
      grad.addColorStop(0.3, "rgba(0, 49, 83, 0.15)");
      grad.addColorStop(1, "rgba(0, 49, 83, 0)");
      ctx.fillStyle = grad;
    }
    ctx.beginPath();
    ctx.arc(mx, my, 6, 0, Math.PI * 2);
    ctx.fill();
  }
}

function loop() {
  // lerp follow
  if (targetX.value !== -9999) {
    smoothX.value += (targetX.value - smoothX.value) * LERP;
    smoothY.value += (targetY.value - smoothY.value) * LERP;
  }
  draw();
  animId = requestAnimationFrame(loop);
}

function resize() {
  if (!canvasEl.value || !bgEl.value) return;
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
  loop();
});

onUnmounted(() => {
  window.removeEventListener("resize", resize);
  if (animId) cancelAnimationFrame(animId);
});
</script>

<style scoped>
.bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  background: #0a0a0c;
}

/* Light mode: clean white */
.v-theme--bluebusinesstheme .bg {
  background: #ffffff;
}

.bg-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.gravity-well {
  position: fixed;
  bottom: -200px;
  left: 50%;
  transform: translateX(-50%);
  width: 600px;
  height: 400px;
  background: radial-gradient(
    ellipse 50% 40% at 50% 100%,
    rgba(0, 26, 51, 0.7) 0%,
    rgba(0, 40, 60, 0.3) 40%,
    transparent 70%
  );
  pointer-events: none;
  z-index: 1;
}
</style>
