<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import { appearanceApi } from '@/api/v1';
import { fetchWithAuth } from '@/api/http';
import { useAppearanceStore } from '@/stores/appearance';

const appearance = useAppearanceStore();
const portrait = ref(false);
const activeLayer = ref(0);
const layers = ref(['', '']);

let mediaQuery: MediaQueryList | null = null;
let transitionTimer: number | null = null;
let requestVersion = 0;

const wallpaperId = computed(() => {
  const settings = appearance.settings;
  if (portrait.value) {
    return settings.portraitWallpaperId || settings.landscapeWallpaperId;
  }
  return settings.landscapeWallpaperId || settings.portraitWallpaperId;
});

const wallpaperUrl = computed(() => {
  if (!appearance.active || !wallpaperId.value) return '';
  return appearanceApi.imageUrl(wallpaperId.value);
});

const layerStyle = (url: string) => ({
  backgroundImage: url ? `url("${url}")` : 'none',
});

function updateOrientation(event?: MediaQueryListEvent): void {
  portrait.value = event?.matches ?? mediaQuery?.matches ?? false;
}

async function decodeImage(url: string): Promise<void> {
  const image = new Image();
  image.src = url;
  await new Promise<void>((resolve, reject) => {
    image.onload = () => void resolve();
    image.onerror = () =>
      void reject(new Error('Wallpaper could not be decoded'));
  });
  await image.decode?.().catch(() => undefined);
}

function revokeLayer(index: number): void {
  const url = layers.value[index];
  if (url.startsWith('blob:')) URL.revokeObjectURL(url);
  layers.value[index] = '';
}

async function applyWallpaper(url: string): Promise<void> {
  const version = ++requestVersion;
  if (!url) {
    if (transitionTimer !== null) window.clearTimeout(transitionTimer);
    revokeLayer(0);
    revokeLayer(1);
    activeLayer.value = 0;
    return;
  }

  try {
    const response = await fetchWithAuth(url, { cache: 'no-store' });
    if (!response.ok) throw new Error('Wallpaper request failed');
    const objectUrl = URL.createObjectURL(await response.blob());
    await decodeImage(objectUrl);
    if (version !== requestVersion) {
      URL.revokeObjectURL(objectUrl);
      return;
    }

    const nextLayer = activeLayer.value === 0 ? 1 : 0;
    revokeLayer(nextLayer);
    layers.value[nextLayer] = objectUrl;
    requestAnimationFrame(() => {
      if (version !== requestVersion) return;
      const previousLayer = activeLayer.value;
      activeLayer.value = nextLayer;
      if (transitionTimer !== null) window.clearTimeout(transitionTimer);
      transitionTimer = window.setTimeout(
        () => void revokeLayer(previousLayer),
        700,
      );
    });
  } catch {
    // Keep the previous layer and preference intact. A transient request failure
    // should not silently disable the user's selected appearance.
  }
}

watch(
  wallpaperUrl,
  (url) => {
    void applyWallpaper(url);
  },
  { immediate: true },
);

onMounted(() => {
  mediaQuery = window.matchMedia('(orientation: portrait)');
  updateOrientation();
  mediaQuery.addEventListener('change', updateOrientation);
});

onBeforeUnmount(() => {
  requestVersion += 1;
  if (mediaQuery) mediaQuery.removeEventListener('change', updateOrientation);
  if (transitionTimer !== null) window.clearTimeout(transitionTimer);
  revokeLayer(0);
  revokeLayer(1);
});
</script>

<template>
  <div
    v-if="appearance.active && wallpaperId"
    class="dashboard-wallpaper"
    aria-hidden="true"
  >
    <div
      v-for="(url, index) in layers"
      :key="index"
      class="dashboard-wallpaper__layer"
      :class="{ 'dashboard-wallpaper__layer--active': activeLayer === index }"
      :style="layerStyle(url)"
    />
  </div>
</template>

<style>
.dashboard-wallpaper {
  position: fixed;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
}

.dashboard-wallpaper::after {
  position: absolute;
  inset: 0;
  background: rgb(0 0 0 / var(--dashboard-wallpaper-dim, 0.5));
  content: '';
}

.dashboard-wallpaper__layer {
  position: absolute;
  inset: calc(-1 * var(--dashboard-wallpaper-blur, 0px));
  background-position: var(--dashboard-wallpaper-position, center center);
  background-repeat: no-repeat;
  background-size: var(--dashboard-wallpaper-fit, cover);
  filter: blur(var(--dashboard-wallpaper-blur, 0px))
    brightness(var(--dashboard-wallpaper-brightness, 1));
  opacity: 0;
  transition: opacity 650ms ease;
}

.dashboard-wallpaper__layer--active {
  opacity: 1;
}

.dashboard-appearance-active {
  --dashboard-wallpaper-surface: rgb(
    var(--v-theme-surface) / var(--dashboard-surface-opacity, 1)
  );
  background: transparent;
  isolation: isolate;
}

.dashboard-appearance-active .v-application__wrap {
  position: relative;
  z-index: 1;
  background: transparent;
}

.dashboard-appearance-active .v-main {
  background-color: transparent;
}

.dashboard-appearance-active .page-wrapper {
  background-color: var(--dashboard-wallpaper-surface);
}
</style>
