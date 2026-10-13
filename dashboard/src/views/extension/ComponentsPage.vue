<script setup lang="ts">
import ComponentPanel from "@/components/extension/componentPanel/index.vue";
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/extension");
</script>

<template>
  <div class="plugin-section-page">
    <div class="mb-4 pt-4 pb-4">
      <h2 class="text-h2 mb-0">{{ tm("tabs.handlersOperation") }}</h2>
    </div>
    <ComponentPanel :active="true" />
  </div>
</template>

<style scoped>
.plugin-section-page {
  padding: 0 12px;
  width: 100%;
}
</style>
