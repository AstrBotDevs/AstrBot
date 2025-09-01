<template>
  <div class="flex-grow-1" style="display: flex; flex-direction: column; height: 100%;">
    <div class="d-flex align-center justify-center"
      style="flex-grow: 1; width: 100%; border: 1px solid #eee; border-radius: 8px;">
      <span size="64">🌍</span>
      <p class="text-h6 text-grey ml-4">{{ tm('comingSoon') }}</p>
    </div>
  </div>
</template>

<script setup>
import { useModuleI18n } from '@/i18n/composables';

const { tm } = useModuleI18n('features/alkaid/index');
</script>
