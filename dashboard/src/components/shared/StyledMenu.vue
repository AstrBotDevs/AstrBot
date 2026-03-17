<template>
  <v-menu v-bind="$attrs" :close-on-content-click="closeOnContentClick">
    <template v-slot:activator="{ props: activatorProps }">
      <slot name="activator" :props="activatorProps"></slot>
    </template>
    
    <v-card class="styled-menu-card" elevation="8" rounded="lg">
      <v-list density="compact" class="styled-menu-list pa-1">
        <slot></slot>
      </v-list>
    </v-card>
  </v-menu>
</template>

<script setup lang="ts">
defineOptions({
  inheritAttrs: false
})

withDefaults(defineProps<{
  closeOnContentClick?: boolean
}>(), {
  closeOnContentClick: true
})
</script>

<style scoped>
.styled-menu-card {
  min-width: 100px;
  width: fit-content;
  border: 1px solid rgba(94, 53, 177, 0.15) !important;
  background: #f8f6fc !important;
  backdrop-filter: blur(10px);
}

.styled-menu-list {
  background: transparent !important;
}

:deep(.styled-menu-item) {
  margin: 2px 0;
  transition: all 0.2s ease;
  border-radius: 6px;
}

:deep(.styled-menu-item:hover) {
  background: rgba(94, 53, 177, 0.08) !important;
}

:deep(.styled-menu-item-active) {
  background: rgba(94, 53, 177, 0.15) !important;
  font-weight: 500;
}

:deep(.styled-menu-item-active:hover) {
  background: rgba(94, 53, 177, 0.2) !important;
}
</style>

<style>
/* 深色模式下的下拉框样式 - 需要全局样式才能检测主题 */
.v-theme--PurpleThemeDark .styled-menu-card {
  background: #2a2733 !important;
  border: 1px solid rgba(110, 60, 180, 0.692) !important;
}

/* 深色模式下的列表项悬停效果 */
.v-theme--PurpleThemeDark .styled-menu-item:hover {
  background: rgba(114, 46, 209, 0.12) !important;
}

.v-theme--PurpleThemeDark .styled-menu-item-active {
  background: rgba(114, 46, 209, 0.2) !important;
}

.v-theme--PurpleThemeDark .styled-menu-item-active:hover {
  background: rgba(114, 46, 209, 0.25) !important;
}
</style>
