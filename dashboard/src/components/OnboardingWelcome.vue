<template>
  <div class="guide-welcome">
    <div class="welcome-logo" aria-hidden="true">
      <svg class="welcome-star welcome-star--large" width="72" height="72" viewBox="0 0 512 512">
        <path class="welcome-trail" d="M204 278 L-180 670 L218 290 Z" />
        <g transform="translate(0.8 32.9)">
          <path d="m246.3 328.1-17.8 41.2c-6.4 14.8-26.9 14.8-33.3 0l-17.8-41.2c-14.9-34.2-41.8-61.4-75.3-76.3l-48.8-21.6c-14.7-6.5-14.7-27.9 0-34.4l47.2-21c34.4-15.3 61.7-43.5 76.4-78.8l18-43.7c6.3-15.2 27.3-15.2 33.6 0l18 43.7c14.7 35.3 42 63.6 76.4 78.8l47.2 21c14.7 6.5 14.7 27.9 0 34.4l-48.8 21.6c-33.5 14.8-60.4 42.1-75.3 76.2z" transform="translate(0 35)" />
        </g>
      </svg>
      <svg class="welcome-star welcome-star--small" width="72" height="72" viewBox="0 0 512 512">
        <path class="welcome-trail" d="M390 116 L760 -254 L402 128 Z" />
        <g transform="translate(0.8 32.9)">
          <path d="m402.2 449.3-5.3 12.2c-3.5 7.9-14.4 7.9-17.9 0l-5.3-12.2c-8.4-19.3-23.6-34.6-42.4-43l-15.4-6.9c-7.9-3.5-7.9-14.9 0-18.4l14.5-6.5c19.4-8.6 34.8-24.5 43.1-44.5l5.4-13.1c3.4-8.1 14.6-8.1 18 0l5.4 13.1c8.3 19.9 23.7 35.8 43.1 44.5l14.5 6.5c7.9 3.5 7.9 14.9 0 18.4l-15.4 6.9c-19 8.3-34.1 23.7-42.5 43z" transform="matrix(0.95 0 0 0.95 22 -278)" />
        </g>
      </svg>
    </div>
    <h2 ref="heading" tabindex="-1">{{ tm('guide.welcomeTitle') }}</h2>
    <p class="text-body-1 text-medium-emphasis">{{ tm('guide.welcomeHint') }}</p>
    <canvas ref="canvas" class="welcome-confetti" aria-hidden="true" />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import confetti from 'canvas-confetti';
import { useModuleI18n } from '@/i18n/composables';

const { tm } = useModuleI18n('features/welcome');
const canvas = ref<HTMLCanvasElement>();
const heading = ref<HTMLElement>();
let celebrate: ReturnType<typeof confetti.create> | undefined;

onMounted(() => {
  heading.value?.focus({ preventScroll: true });
  if (!canvas.value) return;
  celebrate = confetti.create(canvas.value, { resize: true, disableForReducedMotion: true });
  const options = {
    particleCount: 100, spread: 60, startVelocity: 55, ticks: 200,
    colors: ['#5B8DEF', '#47BFA8', '#F3C969', '#E88BA4'],
  };
  void celebrate({ ...options, angle: 60, origin: { x: 0, y: 0.68 } });
  void celebrate({ ...options, angle: 120, origin: { x: 1, y: 0.68 } });
});

onBeforeUnmount(() => celebrate?.reset());
</script>

<style scoped>
.guide-welcome { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 20px; width: 100%; min-height: 360px; padding: 48px 0; text-align: center; overflow-wrap: anywhere; }
.guide-welcome h2 { font-size: 28px; line-height: 1.4; font-weight: 600; letter-spacing: 0; }
.guide-welcome h2:focus-visible { outline: 2px solid rgb(var(--v-theme-primary)); outline-offset: 6px; }
.guide-welcome h2, .guide-welcome p { animation: welcome-copy-in .35s ease-out .65s both; }
.welcome-logo { position: relative; flex-shrink: 0; width: 72px; height: 72px; --flight-distance: clamp(96px, 18vw, 220px); }
.welcome-star { position: absolute; inset: 0; overflow: visible; fill: #2f86bd; pointer-events: none; animation: welcome-star-arrive 1.1s cubic-bezier(.16, .8, .22, 1) both; }
.welcome-star--large { --from-x: calc(-1 * var(--flight-distance)); --from-y: var(--flight-distance); }
.welcome-star--small { --from-x: var(--flight-distance); --from-y: calc(-1 * var(--flight-distance)); animation-delay: 140ms; }
.welcome-trail { opacity: 0; animation: welcome-trail-fade 1.1s ease-out both; }
.welcome-star--small .welcome-trail { animation-delay: 140ms; }
@keyframes welcome-star-arrive {
  0% { opacity: 0; transform: translate(var(--from-x), var(--from-y)) scale(.75); }
  15% { opacity: 1; }
  100% { opacity: 1; transform: translate(0, 0) scale(1); }
}
@keyframes welcome-trail-fade {
  0%, 75%, 100% { opacity: 0; }
  15% { opacity: .35; }
}
@keyframes welcome-copy-in {
  from { opacity: 0; }
  to { opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .welcome-star, .welcome-trail, .guide-welcome h2, .guide-welcome p { animation: none; }
}
.welcome-confetti { position: fixed; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 20; }
</style>
