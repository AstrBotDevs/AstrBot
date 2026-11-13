<template>
  <v-menu v-bind="$attrs" :close-on-content-click="closeOnContentClick">
    <template v-slot:activator="{ props: activatorProps }">
      <slot name="activator" :props="activatorProps"></slot>
    </template>
    
    <v-card
      class="styled-menu-card"
      :class="{ 'styled-menu-card-borderless': noBorder }"
      elevation="0"
      rounded="lg"
    >
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
  noBorder?: boolean
}>(), {
  closeOnContentClick: true,
  noBorder: false
})
</script>

<style>
.styled-menu-card {
  --astrbot-menu-shadow: 0 3px 10px rgba(0, 0, 0, 0.06);
  min-width: 100px;
  width: fit-content;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.09) !important;
  background: rgba(var(--v-theme-surface), 0.98) !important;
  backdrop-filter: blur(10px);
  box-shadow: var(--astrbot-menu-shadow) !important;
}

.v-overlay.v-menu .v-overlay__content > .styled-menu-card:not(.styled-menu-card-borderless) {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.09) !important;
  box-shadow: var(--astrbot-menu-shadow) !important;
}

.styled-menu-card-borderless {
  border: 0 !important;
}

.styled-menu-list {
  background: transparent !important;
}

.styled-menu-list .styled-menu-item {
  /* Avoid stacking Vuetify state overlays on the explicit backgrounds. */
  --v-hover-opacity: 0;
  --v-activated-opacity: 0;
  color: rgb(var(--v-theme-on-surface));
  margin: 2px 0;
  transition: all 0.2s ease;
  border-radius: 6px;
}

.styled-menu-item .v-list-item-title {
  font-size: 14px;
  line-height: 20px;
}

.styled-menu-item .v-list-item__prepend > .v-icon {
  font-size: 18px;
  width: 18px;
  height: 18px;
  opacity: 1;
}

.styled-menu-item .v-list-item__prepend > .v-icon ~ .v-list-item__spacer {
  width: 14px;
}

.styled-menu-item:hover,
.styled-menu-item[aria-haspopup="menu"][aria-expanded="true"] {
  background: rgba(var(--v-theme-on-surface), 0.05) !important;
}

.styled-menu-item-active,
.styled-menu-item.v-list-item--active {
  background: rgba(var(--v-theme-on-surface), 0.06) !important;
  font-weight: 500;
}

.styled-menu-item-active:hover,
.styled-menu-item.v-list-item--active:hover {
  background: rgba(var(--v-theme-on-surface), 0.09) !important;
}

/* 深色模式下的下拉框样式 - 需要全局样式才能检测主题 */
.v-theme--PurpleThemeDark .styled-menu-card {
  background: rgba(var(--v-theme-surface), 0.98) !important;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.09) !important;
}

.v-theme--PurpleThemeDark .styled-menu-card-borderless {
  border: 0 !important;
}
</style>
