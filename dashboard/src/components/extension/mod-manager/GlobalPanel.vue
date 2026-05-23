<script setup lang="ts">
// Reserved area panel — placeholder for future plugin workspace features.
</script>

<template>
  <div class="h-100 d-flex flex-column global-panel">
    <div class="global-panel__body d-flex flex-column align-center justify-center pa-6">
      <div class="reserved-icon mb-4">
        <v-icon size="48" color="grey-lighten-1">mdi-puzzle-plus-outline</v-icon>
      </div>

      <div class="text-subtitle-1 font-weight-medium text-medium-emphasis mb-2">
        预留功能区
      </div>

      <div class="text-body-2 text-center text-disabled reserved-desc">
        待后续开发，考虑用于：
      </div>

      <div class="reserved-features mt-4">
        <div class="reserved-feature d-flex align-center ga-3 pa-3">
          <v-icon size="20" color="primary">mdi-application-outline</v-icon>
          <span class="text-body-2">插件自带 UI 的 iframe 嵌入展示</span>
        </div>
        <div class="reserved-feature d-flex align-center ga-3 pa-3">
          <v-icon size="20" color="info">mdi-text-box-search-outline</v-icon>
          <span class="text-body-2">仅跟踪当前插件的相关日志信息</span>
        </div>
        <div class="reserved-feature d-flex align-center ga-3 pa-3">
          <v-icon size="20" color="success">mdi-chart-timeline-variant</v-icon>
          <span class="text-body-2">插件运行状态与调用统计</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.global-panel {
  min-height: 0;
  overflow: hidden;
}

.global-panel__body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
}

.reserved-icon {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(
    135deg,
    rgba(var(--v-theme-primary), 0.06),
    rgba(var(--v-theme-info), 0.06)
  );
  border: 2px dashed rgba(var(--v-theme-on-surface), 0.1);
}

.reserved-desc {
  max-width: 280px;
}

.reserved-features {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  max-width: 340px;
}

.reserved-feature {
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.02);
  transition: background 0.2s ease;
}

.reserved-feature:hover {
  background: rgba(var(--v-theme-on-surface), 0.05);
}
</style>