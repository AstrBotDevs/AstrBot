<script setup>
import { computed } from "vue";

const props = defineProps({
  title: {
    type: String,
    required: true,
  },
  icon: {
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

const emit = defineEmits(["toggle", "toggle-all", "configure"]);

const selectableItems = computed(() =>
  props.items.filter((item) => !item.disabled),
);
const selectedCount = computed(
  () => selectableItems.value.filter((item) => item.selected).length,
);
const allSelected = computed(
  () =>
    selectableItems.value.length > 0 &&
    selectedCount.value === selectableItems.value.length,
);
const partiallySelected = computed(
  () =>
    props.items.some((item) => item.indeterminate) ||
    (selectedCount.value > 0 && !allSelected.value),
);
</script>

<template>
  <div class="capability-list">
    <div class="capability-list__header">
      <v-checkbox-btn
        :model-value="allSelected"
        :indeterminate="partiallySelected"
        :disabled="readonly || saving || selectableItems.length === 0"
        :aria-label="title"
        density="compact"
        @click.stop="emit('toggle-all')"
      />
      <v-icon size="18">{{ icon }}</v-icon>
      <span class="capability-list__title">{{ title }}</span>
      <span class="capability-list__count">
        {{ selectedCount }}/{{ selectableItems.length }}
      </span>
    </div>

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
        @click="emit('toggle', item)"
      >
        <template #prepend>
          <v-checkbox-btn
            :model-value="item.selected"
            :indeterminate="item.indeterminate || false"
            :disabled="readonly || saving || item.disabled"
            :aria-label="item.name"
            density="compact"
            @click.stop="emit('toggle', item)"
          />
        </template>

        <v-list-item-title class="capability-list__item-title">
          <span>{{ item.name }}</span>
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
                  @click.stop="emit('configure', item)"
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

.capability-list__header {
  display: flex;
  align-items: center;
  min-height: 44px;
  padding: 2px 10px 2px 4px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  gap: 6px;
}

.capability-list__title {
  min-width: 0;
  overflow: hidden;
  font-size: 0.82rem;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.capability-list__count {
  margin-left: auto;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.74rem;
  opacity: 0.6;
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
