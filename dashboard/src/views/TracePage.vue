<script setup>
import TraceDisplayer from '@/components/shared/TraceDisplayer.vue';
import { useModuleI18n } from '@/i18n/composables';

const { tm } = useModuleI18n('features/trace');
</script>

<template>
  <div style="height: 100%;">
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
