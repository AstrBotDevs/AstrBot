<template>
  <div class="proxy-selector">
    <h5 class="proxy-selector__title">
      {{ tm('network.proxySelector.title') }}
    </h5>
    <p class="proxy-selector__hint">
      {{ tm('network.proxySelector.disabledHint') }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { useModuleI18n } from '@/i18n/composables';

const { tm } = useModuleI18n('features/settings');
</script>

<style scoped>
.proxy-selector {
  width: 100%;
  min-width: 0;
}

.proxy-selector__title {
  margin: 0;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.88rem;
  font-weight: 700;
  line-height: 1.4;
}

.proxy-selector__hint {
  margin: 8px 0 0;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.8rem;
  line-height: 1.4;
}
</style>
