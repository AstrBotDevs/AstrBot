<template>
  <v-menu
    v-model="menuOpen"
    :close-on-content-click="false"
    location="bottom start"
    :offset="10"
    transition="none"
  >
    <template #activator="{ props: menuProps }">
      <button
        v-bind="menuProps"
        type="button"
        class="config-profile-trigger"
        :disabled="disabled"
        :aria-label="tm('configSelection.selectConfig')"
      >
        <span class="config-profile-trigger__title">{{ selectedName }}</span>
        <v-icon class="config-profile-trigger__chevron" size="18">
          mdi-chevron-down
        </v-icon>
      </button>
    </template>

    <v-card class="config-profile-menu" elevation="0">
      <div class="config-profile-menu__body">
        <v-text-field
          v-if="items.length > 5"
          v-model="searchQuery"
          :placeholder="tm('configSelection.search')"
          hide-details
          variant="outlined"
          density="compact"
          prepend-inner-icon="mdi-magnify"
          class="config-profile-menu__search"
          clearable
        />

        <v-list density="compact" nav class="config-profile-menu__list">
          <v-list-item
            v-for="item in filteredItems"
            :key="item.id"
            :active="modelValue === item.id"
            rounded="lg"
            class="config-profile-menu__item"
            @click="selectProfile(item.id)"
          >
            <v-list-item-title class="config-profile-menu__item-title">
              {{ displayName(item) }}
            </v-list-item-title>
            <template #append>
              <v-icon
                v-if="modelValue === item.id"
                class="config-profile-menu__selected-icon"
                size="18"
              >
                mdi-check
              </v-icon>
            </template>
          </v-list-item>
        </v-list>

        <div
          v-if="filteredItems.length === 0"
          class="config-profile-menu__empty"
        >
          {{ tm('configSelection.noResults') }}
        </div>

        <v-divider class="config-profile-menu__divider" />
        <button
          type="button"
          class="config-profile-menu__manage"
          @click="openManager"
        >
          <v-icon size="17">mdi-cog-outline</v-icon>
          <span>{{ tm('configManagement.manageConfigs') }}</span>
        </button>
      </div>
    </v-card>
  </v-menu>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  items: {
    type: Array,
    default: () => [],
  },
  disabled: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['select', 'manage']);
const { tm } = useModuleI18n('features/config');
const menuOpen = ref(false);
const searchQuery = ref('');

function displayName(item) {
  if (item?.id === 'default') {
    return tm('configSelection.defaultConfig');
  }
  return item?.name || item?.id || tm('configSelection.selectConfig');
}

const selectedName = computed(() => {
  const selected = props.items.find((item) => item.id === props.modelValue);
  if (selected) {
    return displayName(selected);
  }
  if (props.modelValue === 'default') {
    return tm('configSelection.defaultConfig');
  }
  return props.modelValue || tm('configSelection.selectConfig');
});

const filteredItems = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  if (!query) {
    return props.items;
  }
  return props.items.filter(
    (item) =>
      displayName(item).toLowerCase().includes(query) ||
      String(item.id || '')
        .toLowerCase()
        .includes(query),
  );
});

watch(menuOpen, (isOpen) => {
  if (!isOpen) {
    searchQuery.value = '';
  }
});

function selectProfile(id) {
  emit('select', id);
  menuOpen.value = false;
}

function openManager() {
  emit('manage');
  menuOpen.value = false;
}
</script>

<style scoped>
.config-profile-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  max-width: min(280px, 38vw);
  min-width: 0;
  height: 24px;
  margin-top: 2px;
  padding: 0;
  border: 0;
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  cursor: pointer;
  font: inherit;
  letter-spacing: 0;
  text-align: left;
}

.config-profile-trigger:disabled {
  cursor: default;
  opacity: 0.55;
}

.config-profile-trigger:focus {
  outline: none;
}

.config-profile-trigger:focus-visible {
  border-radius: 6px;
  outline: 2px solid rgba(var(--v-theme-primary), 0.42);
  outline-offset: 3px;
}

.config-profile-trigger__title {
  min-width: 0;
  overflow: hidden;
  font-size: 17px;
  font-weight: 620;
  line-height: 24px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.config-profile-trigger__chevron {
  flex: 0 0 auto;
  opacity: 0.64;
}

.config-profile-menu {
  width: min(360px, calc(100vw - 24px));
  overflow: hidden;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.09) !important;
  border-radius: 14px !important;
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.07) !important;
}

:global(.v-overlay.v-menu .v-overlay__content > .config-profile-menu) {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.09) !important;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.07) !important;
}

.config-profile-menu__body {
  padding: 10px;
}

.config-profile-menu__search {
  margin-bottom: 8px;
}

.config-profile-menu__search :deep(.v-field) {
  border-radius: 10px;
  box-shadow: none;
}

.config-profile-menu__search :deep(.v-field__outline) {
  color: rgba(var(--v-theme-on-surface), 0.16);
}

.config-profile-menu__list {
  max-height: min(320px, 52vh);
  overflow-y: auto;
  padding: 0;
}

.config-profile-menu__item {
  min-height: 42px !important;
  margin-bottom: 2px;
  border-radius: 10px !important;
}

.config-profile-menu__item:hover {
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.config-profile-menu__item.v-list-item--active {
  background: rgba(var(--v-theme-primary), 0.08);
  color: rgb(var(--v-theme-on-surface));
}

.config-profile-menu__item-title {
  font-size: 14px;
  font-weight: 600;
  line-height: 18px;
}

.config-profile-menu__selected-icon {
  color: rgba(var(--v-theme-on-surface), 0.72);
}

.config-profile-menu__empty {
  padding: 16px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 12px;
  text-align: center;
}

.config-profile-menu__divider {
  margin: 8px 0;
  border-color: rgba(var(--v-theme-on-surface), 0.08);
}

.config-profile-menu__manage {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  min-height: 40px;
  padding: 8px 12px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.72);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  text-align: left;
}

.config-profile-menu__manage:hover {
  background: rgba(var(--v-theme-on-surface), 0.05);
  color: rgb(var(--v-theme-on-surface));
}

@media (max-width: 768px) {
  .config-profile-trigger {
    max-width: calc(100vw - 40px);
  }

  .config-profile-trigger__title {
    font-size: 16px;
  }
}
</style>
