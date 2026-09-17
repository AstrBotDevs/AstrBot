<script setup lang="ts">
import SkillsSection from "@/components/extension/SkillsSection.vue";
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/extension");
</script>

<template>
  <div class="plugin-section-page">
    <div class="mb-4 pt-4 pb-4">
      <div class="d-flex flex-column" style="gap: 6px">
        <h2 class="text-h2 mb-0">{{ tm("tabs.skills") }}</h2>
        <div class="text-body-2 text-medium-emphasis">
          {{ tm("skills.runtimeHint") }}
        </div>
      </div>
    </div>
    <SkillsSection />
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
