<script setup lang="ts">
import { computed } from 'vue';
import { useModuleI18n } from '@/i18n/composables';

const { tm } = useModuleI18n('features/command');

// Props
const props = defineProps<{
  availablePlugins: string[];
  hasSystemPluginConflict: boolean;
  effectiveShowSystemPlugins: boolean;
  pluginFilter: string;
  typeFilter: string;
  permissionFilter: string;
  statusFilter: string;
  showSystemPlugins: boolean;
  searchQuery: string;
}>();

// Emits
const emit = defineEmits<{
  (e: 'update:pluginFilter', value: string): void;
  (e: 'update:typeFilter', value: string): void;
  (e: 'update:permissionFilter', value: string): void;
  (e: 'update:statusFilter', value: string): void;
  (e: 'update:showSystemPlugins', value: boolean): void;
  (e: 'update:searchQuery', value: string): void;
}>();

// Computed items for selects
const pluginItems = computed(() => [
  { title: tm('filters.all'), value: 'all' },
  ...props.availablePlugins.map(p => ({ title: p, value: p }))
]);

const typeItems = [
  { title: tm('filters.all'), value: 'all' },
  { title: tm('type.group'), value: 'group' },
  { title: tm('type.command'), value: 'command' },
  { title: tm('type.subCommand'), value: 'sub_command' }
];

const permissionItems = [
  { title: tm('filters.all'), value: 'all' },
  { title: tm('permission.everyone'), value: 'everyone' },
  { title: tm('permission.admin'), value: 'admin' }
];

const statusItems = [
  { title: tm('filters.all'), value: 'all' },
  { title: tm('filters.enabled'), value: 'enabled' },
  { title: tm('filters.disabled'), value: 'disabled' },
  { title: tm('filters.conflict'), value: 'conflict' }
];
</script>

<template>
  <!-- 过滤器行 -->
  <v-row class="mb-4" align="center">
    <v-col cols="12" sm="6" md="3">
      <v-select
        :model-value="pluginFilter"
        @update:model-value="emit('update:pluginFilter', $event)"
        :items="pluginItems"
        :label="tm('filters.byPlugin')"
        density="compact"
        variant="outlined"
        hide-details
      />
    </v-col>
    <v-col cols="12" sm="6" md="2">
      <v-select
        :model-value="typeFilter"
        @update:model-value="emit('update:typeFilter', $event)"
        :items="typeItems"
        :label="tm('filters.byType')"
        density="compact"
        variant="outlined"
        hide-details
      />
    </v-col>
    <v-col cols="12" sm="6" md="2">
      <v-select
        :model-value="permissionFilter"
        @update:model-value="emit('update:permissionFilter', $event)"
        :items="permissionItems"
        :label="tm('filters.byPermission')"
        density="compact"
        variant="outlined"
        hide-details
      />
    </v-col>
    <v-col cols="12" sm="6" md="2">
      <v-select
        :model-value="statusFilter"
        @update:model-value="emit('update:statusFilter', $event)"
        :items="statusItems"
        :label="tm('filters.byStatus')"
        density="compact"
        variant="outlined"
        hide-details
      />
    </v-col>
  </v-row>

  <!-- 搜索栏 + 统计信息行 -->
  <div class="mb-4 d-flex flex-wrap align-center ga-4">
    <div style="min-width: 200px; max-width: 350px; flex: 1; border: 1px solid #B9B9B9; border-radius: 16px;">
      <v-text-field
        :model-value="searchQuery"
        @update:model-value="emit('update:searchQuery', $event)"
        density="compact"
        :label="tm('search.placeholder')"
        prepend-inner-icon="mdi-magnify"
        variant="solo-filled"
        flat
        hide-details
        single-line
      />
    </div>
    <div class="d-flex align-center ga-4">
      <slot name="stats"></slot>
      <v-divider vertical class="mx-1" style="height: 20px;" />
      <v-checkbox
        :model-value="effectiveShowSystemPlugins"
        @update:model-value="emit('update:showSystemPlugins', !!$event)"
        :label="tm('filters.showSystemPlugins')"
        density="compact"
        hide-details
        :disabled="hasSystemPluginConflict"
        class="system-plugin-checkbox"
      >
        <template v-slot:label>
          <span class="text-body-2">{{ tm('filters.showSystemPlugins') }}</span>
          <v-tooltip v-if="hasSystemPluginConflict" location="top">
            <template v-slot:activator="{ props: tooltipProps }">
              <v-icon v-bind="tooltipProps" size="16" color="warning" class="ml-1">mdi-alert-circle</v-icon>
            </template>
            {{ tm('filters.systemPluginConflictHint') }}
          </v-tooltip>
        </template>
      </v-checkbox>
    </div>
  </div>
</template>

<style scoped>
.system-plugin-checkbox {
  flex: none;
}

.system-plugin-checkbox :deep(.v-selection-control) {
  min-height: auto;
}
</style>
