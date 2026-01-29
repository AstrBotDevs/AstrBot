<script setup>
import TraceDisplayer from '@/components/shared/TraceDisplayer.vue';
import { useModuleI18n } from '@/i18n/composables';

const { tm } = useModuleI18n('features/trace');
</script>

<template>
  <div style="height: 100%;">
    <div
      style="background-color: var(--v-theme-surface); padding: 8px 16px; border-radius: 8px; margin-bottom: 16px; display: flex; flex-direction: row; align-items: center; justify-content: space-between;">
      <h4>{{ tm('title') }}</h4>
    </div>
    <TraceDisplayer />
  </div>
</template>

<script>
export default {
  name: 'TracePage',
  components: {
    TraceDisplayer
  }
};
</script>
