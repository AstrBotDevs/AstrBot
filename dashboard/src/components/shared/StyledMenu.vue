<template>
  <v-menu
    v-bind="$attrs"
    :close-on-content-click="closeOnContentClick"
  >
    <template #activator="{ props: activatorProps }">
      <slot
        name="activator"
        :props="activatorProps"
      />
    </template>
    
    <v-card
      class="styled-menu-card"
      elevation="8"
      rounded="lg"
    >
      <v-list
        density="compact"
        class="styled-menu-list pa-1"
      >
        <slot />
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

<style>
.styled-menu-card {
  min-width: 100px;
  width: fit-content;
  border: 1px solid rgba(var(--v-theme-primary), 0.15) !important;
  background: rgba(var(--v-theme-surface), 0.98) !important;
  backdrop-filter: blur(10px);
}

.styled-menu-list {
  background: transparent !important;
}

.styled-menu-item {
  margin: 2px 0;
  transition: all 0.2s ease;
  border-radius: 6px;
}

.styled-menu-item:hover {
  background: rgba(var(--v-theme-primary), 0.08) !important;
}

.styled-menu-item-active {
  background: rgba(var(--v-theme-primary), 0.15) !important;
  font-weight: 500;
}

.styled-menu-item-active:hover {
  background: rgba(var(--v-theme-primary), 0.2) !important;
}

/* 深色模式下的下拉框样式 - 需要全局样式才能检测主题 */
.v-theme--PurpleThemeDark .styled-menu-card {
  background: rgba(var(--v-theme-surface), 0.98) !important;
  border: 1px solid rgba(var(--v-theme-primary), 0.2) !important;
}

/* 深色模式下的列表项悬停效果 */
.v-theme--PurpleThemeDark .styled-menu-item:hover {
  background: rgba(var(--v-theme-primary), 0.12) !important;
}

.v-theme--PurpleThemeDark .styled-menu-item-active {
  background: rgba(var(--v-theme-primary), 0.2) !important;
}

.v-theme--PurpleThemeDark .styled-menu-item-active:hover {
  background: rgba(var(--v-theme-primary), 0.25) !important;
}
</style>
