<template>
  <v-row :no-gutters="compact" align="center" :class="compact ? 'mb-2' : 'config-row'">
    <v-col
      :cols="compact || inline ? labelColumns : 12"
      :sm="labelColumns"
      :class="compact ? 'mb-2 mb-sm-0' : $slots.label ? 'config-input' : 'property-info'"
    >
      <slot name="label">
        <v-list-item density="compact" :class="{ 'pa-0': compact }">
          <v-list-item-title :class="compact ? 'text-caption font-weight-medium' : 'property-name'">
            <slot name="title" />
          </v-list-item-title>
          <v-list-item-subtitle v-if="$slots.hint" :class="compact ? 'text-caption text-grey' : 'property-hint'">
            <slot name="hint" />
          </v-list-item-subtitle>
        </v-list-item>
      </slot>
    </v-col>
    <v-col :cols="compact || inline ? 12 - labelColumns : 12" :sm="12 - labelColumns" :class="compact ? 'pl-2' : 'config-input'">
      <slot />
    </v-col>
  </v-row>
</template>

<script setup>
defineProps({
  compact: { type: Boolean, default: false },
  inline: { type: Boolean, default: false },
  labelColumns: { type: Number, default: 6 }
})
</script>

<style scoped>
.config-row {
  margin: 0;
  align-items: center;
  padding: 4px 8px;
  border-radius: 4px;
}

.config-row:hover {
  background-color: rgba(0, 0, 0, 0.03);
}

.property-info {
  padding: 0;
}

.property-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--v-theme-primaryText);
}

.property-hint {
  font-size: 0.75rem;
  color: var(--v-theme-secondaryText);
  margin-top: 2px;
}

.config-input {
  padding: 4px 8px;
}

@media (max-width: 600px) {
  .config-row {
    padding: 8px 0;
  }

  .property-info, .config-input {
    padding: 4px;
  }

  .property-info :deep(.v-list-item) {
    padding-inline: 0;
  }
}
</style>
