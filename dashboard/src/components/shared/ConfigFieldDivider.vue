<template>
  <v-divider
    class="config-field-divider"
    :class="{ 'config-field-divider--dark': theme.current.value.dark }"
  />
</template>

<script setup>
import { useTheme } from 'vuetify'

const theme = useTheme()
</script>

<style scoped>
.config-field-divider {
  margin: 0 16px;
  max-width: calc(100% - 32px);
  border-color: rgba(var(--v-theme-on-surface), 0.06);
  opacity: 1;
}

.config-field-divider--dark {
  border-color: rgba(var(--v-theme-on-surface), 0.14);
}

@media (max-width: 600px) {
  .config-field-divider {
    display: none;
  }
}
</style>
