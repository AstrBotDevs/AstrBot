<script setup>
const props = defineProps({
  title: {
    type: String,
    required: true,
  },
  items: {
    type: Array,
    default: () => [],
  },
  emptyText: {
    type: String,
    required: true,
  },
  inactiveText: {
    type: String,
    required: true,
  },
  configureText: {
    type: String,
    default: "",
  },
  readonly: {
    type: Boolean,
    default: false,
  },
  saving: {
    type: Boolean,
    default: false,
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

defineEmits(["toggle", "configure"]);
</script>

<template>
  <div class="capability-list" role="group" :aria-label="title">
    <div v-if="loading || items.length === 0" class="capability-list__empty">
      <v-progress-circular v-if="loading" indeterminate size="18" width="2" />
      <span v-else>{{ emptyText }}</span>
    </div>

    <v-list v-else class="capability-list__items" density="compact">
      <v-list-item
        v-for="item in items"
        :key="item.key || item.name"
        :disabled="readonly || saving || item.disabled"
        class="capability-list__item"
        @click="$emit('toggle', item)"
      >
        <template #prepend>
          <v-checkbox-btn
            :model-value="item.selected"
            :indeterminate="item.indeterminate || false"
            :disabled="readonly || saving || item.disabled"
            :aria-label="item.name"
            density="compact"
            @click.stop="$emit('toggle', item)"
          />
        </template>

        <v-list-item-title class="capability-list__item-title">
          <span>{{ item.name }}</span>
          <v-chip v-if="item.badge" size="x-small" variant="tonal">
            {{ item.badge }}
          </v-chip>
        </v-list-item-title>
        <v-list-item-subtitle v-if="item.meta || item.description">
          <span v-if="item.meta">{{ item.meta }}</span>
          <span v-if="item.meta && item.description"> · </span>
          <span v-if="item.description">{{ item.description }}</span>
        </v-list-item-subtitle>

        <template v-if="item.disabled || item.configurable" #append>
          <div class="capability-list__actions">
            <v-chip
              v-if="item.disabled"
              size="x-small"
              variant="tonal"
              color="warning"
            >
              {{ inactiveText }}
            </v-chip>
            <v-tooltip
              v-if="item.configurable"
              :text="configureText"
              location="top"
            >
              <template #activator="{ props: tooltipProps }">
                <v-btn
                  v-bind="tooltipProps"
                  icon="mdi-cog-outline"
                  size="small"
                  variant="text"
                  :aria-label="configureText"
                  :disabled="readonly || saving"
                  @click.stop="$emit('configure', item)"
                />
              </template>
            </v-tooltip>
          </div>
        </template>
      </v-list-item>
    </v-list>
  </div>
</template>

<style scoped>
.capability-list {
  min-width: 0;
  overflow: hidden;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
}

.capability-list__items {
  max-height: 380px;
  overflow-y: auto;
  padding: 4px;
}

.capability-list__item {
  min-height: 48px;
  border-radius: 6px;
}

.capability-list__item-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  font-size: 0.8rem;
  gap: 8px;
  white-space: normal;
}

.capability-list__actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.capability-list__item :deep(.v-list-item-subtitle) {
  display: -webkit-box;
  overflow: hidden;
  font-size: 0.72rem;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
}

.capability-list__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 96px;
  padding: 16px;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.76rem;
  opacity: 0.55;
  text-align: center;
}
</style>
