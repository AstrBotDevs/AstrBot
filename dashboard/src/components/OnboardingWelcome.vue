<template>
  <div class="guide-welcome">
    <img :src="logo" width="72" height="72" alt="" />
    <h2 ref="heading" tabindex="-1">{{ tm('guide.welcomeTitle') }}</h2>
    <p class="text-body-1 text-medium-emphasis">{{ tm('guide.welcomeHint') }}</p>
    <canvas ref="canvas" class="welcome-confetti" aria-hidden="true" />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import confetti from 'canvas-confetti';
import { useModuleI18n } from '@/i18n/composables';
import logo from '/favicon.svg';

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
.welcome-confetti { position: fixed; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 20; }
</style>
