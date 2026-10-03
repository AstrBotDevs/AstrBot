<script setup lang="ts">
import McpServersSection from "@/components/extension/McpServersSection.vue";
import { useI18n, useModuleI18n } from "@/i18n/composables";

const { t } = useI18n();
const { tm } = useModuleI18n("features/extension");
</script>

<template>
  <div class="plugin-section-page">
    <div class="mb-4 pt-4 pb-4">
      <div class="d-flex flex-column" style="gap: 6px">
        <h2 class="text-h2 mb-0">{{ tm("tabs.installedMcpServers") }}</h2>
        <div class="text-body-2 text-medium-emphasis">
          {{ t("features.tooluse.mcpServers.description") }}
        </div>
      </div>
    </div>
    <McpServersSection />
  </div>
</template>

<style scoped>
.plugin-section-page {
  margin: 0 auto;
  max-width: 1200px;
  padding: 0 12px;
  width: 100%;
}
</style>
