<template>
  <v-menu v-bind="$attrs" :close-on-content-click="closeOnContentClick">
    <template #activator="{ props: activatorProps }">
      <slot name="activator" :props="activatorProps"></slot>
    </template>

    <v-card
      class="styled-menu-card"
      :class="{ 'styled-menu-card-borderless': noBorder }"
      elevation="4"
      rounded="md"
    >
      <v-list density="compact" class="styled-menu-list pa-1">
        <slot></slot>
      </v-list>
    </v-card>
  </v-menu>
</template>

<script setup lang="ts">
defineOptions({
  inheritAttrs: false,
});

withDefaults(
  defineProps<{
    closeOnContentClick?: boolean;
    noBorder?: boolean;
  }>(),
  {
    closeOnContentClick: true,
    noBorder: false,
  },
);
</script>

<style>
.styled-menu-card {
  min-width: 100px;
  width: fit-content;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  background: rgb(var(--v-theme-surface));
}

.styled-menu-card-borderless {
  border: 0;
}

.styled-menu-list {
  background: transparent;
}

.styled-menu-item {
  margin: 4px 0;
  border-radius: 6px;
  transition: background-color 0.2s ease;
}

.styled-menu-item:hover {
  background: rgb(var(--v-theme-surface-variant));
}

.styled-menu-item-active {
  background: rgb(var(--v-theme-surface-variant));
  font-weight: 500;
}

.styled-menu-item-active:hover {
  background: rgb(var(--v-theme-surface-variant));
}
</style>
