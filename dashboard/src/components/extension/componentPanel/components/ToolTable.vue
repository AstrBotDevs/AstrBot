<script setup lang="ts">
import { computed } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import type { BuiltinToolConfigTag, ToolConfigCondition, ToolItem } from '../types';

const { tm: tmTool } = useModuleI18n('features/tooluse');

const props = defineProps<{
  items: ToolItem[];
  loading?: boolean;
}>();

const emit = defineEmits<{
  (e: 'toggle-tool', tool: ToolItem): void;
}>();

const toolHeaders = computed(() => [
  { title: tmTool('functionTools.title'), key: 'name', minWidth: '320px' },
  { title: tmTool('functionTools.description'), key: 'description' },
  { title: tmTool('functionTools.table.origin'), key: 'origin', sortable: false, width: '120px' },
  { title: tmTool('functionTools.table.originName'), key: 'origin_name', sortable: false, width: '160px' },
  { title: tmTool('functionTools.table.actions'), key: 'actions', sortable: false, width: '120px' }
]);

const parameterEntries = (tool: ToolItem) => Object.entries(tool.parameters?.properties || {});

const formatConfigValue = (value: unknown) => {
  if (Array.isArray(value)) {
    return value.map(item => String(item)).join(', ');
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  return String(value);
};

const formatCondition = (condition: ToolConfigCondition) => {
  if (condition.message) {
    return condition.message;
  }

  switch (condition.operator) {
    case 'truthy':
      return tmTool('functionTools.configTags.conditions.truthy', {
        key: condition.key
      });
    case 'equals':
      return tmTool('functionTools.configTags.conditions.equals', {
        key: condition.key,
        expected: formatConfigValue(condition.expected)
      });
    case 'in':
      return tmTool('functionTools.configTags.conditions.in', {
        key: condition.key,
        expected: formatConfigValue(condition.expected)
      });
    default:
      return tmTool('functionTools.configTags.conditions.fallback', {
        key: condition.key,
        actual: formatConfigValue(condition.actual)
      });
  }
};

const enabledConfigTags = (tool: ToolItem): BuiltinToolConfigTag[] => {
  if (tool.origin !== 'builtin') return [];
  return (tool.builtin_config_tags || []).filter(tag => tag.enabled);
};
</script>

<template>
  <v-card class="rounded-lg overflow-hidden elevation-1">
    <v-data-table
      :headers="toolHeaders"
      :items="items"
      item-value="name"
      hover
      show-expand
      class="tool-table"
      :loading="props.loading"
    >
      <template #item.name="{ item }">
        <div class="py-2">
          <div class="d-flex flex-wrap align-center ga-1">
            <div class="tool-name text-body-2 font-weight-medium">{{ item.name }}</div>
            <v-tooltip
              v-for="tag in enabledConfigTags(item)"
              :key="`${item.name}-${tag.conf_id}`"
              location="top"
            >
              <template #activator="{ props: tooltipProps }">
                <v-chip
                  v-bind="tooltipProps"
                  size="x-small"
                  variant="tonal"
                  color="secondary"
                  class="text-caption font-weight-medium"
                >
                  {{ tag.conf_name }}
                </v-chip>
              </template>

              <div class="tool-config-tooltip">
                <div class="text-body-2 font-weight-medium mb-2">
                  {{ tmTool('functionTools.configTags.tooltipTitle', { config: tag.conf_name }) }}
                </div>
                <div
                  v-for="(condition, index) in tag.matched_conditions"
                  :key="`${tag.conf_id}-${index}-${condition.key}`"
                  class="text-body-2 text-medium-emphasis mb-1"
                >
                  {{ formatCondition(condition) }}
                </div>
              </div>
            </v-tooltip>
          </div>
        </div>
      </template>

      <template #item.description="{ item }">
        <div class="text-body-2 text-medium-emphasis" style="max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          {{ item.description || '-' }}
        </div>
      </template>

      <template #item.origin="{ item }">
        <v-chip size="x-small" variant="tonal" color="info" class="text-caption font-weight-medium">
          {{ item.origin || '-' }}
        </v-chip>
      </template>

      <template #item.origin_name="{ item }">
        <div class="text-body-2 text-medium-emphasis" style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          {{ item.origin_name || '-' }}
        </div>
      </template>

      <template #item.actions="{ item }">
        <span v-if="item.readonly" class="text-medium-emphasis">-</span>
        <v-switch
          v-else
          :model-value="item.active"
          color="primary"
          density="compact"
          hide-details
          inset
          @update:model-value="emit('toggle-tool', item)"
        />
      </template>

      <template #no-data>
        <div class="text-center pa-8">
          <v-icon size="64" color="info" class="mb-4">mdi-function-variant</v-icon>
          <div class="text-h5 mb-2">{{ tmTool('functionTools.empty') }}</div>
        </div>
      </template>

      <template #expanded-row="{ item }">
        <td :colspan="toolHeaders.length + 1" class="pa-4">
          <div class="d-flex align-start ga-4">
            <v-icon size="20" color="primary">mdi-code-json</v-icon>
            <div class="flex-1">
              <div class="text-subtitle-2 font-weight-medium mb-2">{{ tmTool('functionTools.parameters') }}</div>
              <div v-if="parameterEntries(item).length === 0" class="text-caption text-medium-emphasis">
                {{ tmTool('functionTools.noParameters') }}
              </div>
              <v-table
                v-else
                density="compact"
                class="param-table"
              >
                <thead>
                  <tr>
                    <th class="text-left text-caption text-medium-emphasis">{{ tmTool('functionTools.table.paramName') }}</th>
                    <th class="text-left text-caption text-medium-emphasis" style="width: 140px;">{{ tmTool('functionTools.table.type') }}</th>
                    <th class="text-left text-caption text-medium-emphasis">{{ tmTool('functionTools.table.description') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="([paramName, param]) in parameterEntries(item)" :key="paramName">
                    <td class="font-weight-medium text-body-2">{{ paramName }}</td>
                    <td class="text-body-2">
                      <v-chip size="x-small" color="primary" class="text-caption">
                        {{ param?.type || '-' }}
                      </v-chip>
                    </td>
                    <td class="text-body-2 text-medium-emphasis">{{ param?.description || '-' }}</td>
                  </tr>
                </tbody>
              </v-table>
            </div>
          </div>
        </td>
      </template>
    </v-data-table>
  </v-card>
</template>

<style scoped>
.param-table {
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 8px;
}

.tool-table :deep(.v-data-table__td) {
  vertical-align: middle;
}

.tool-name {
  font-size: 0.9rem;
  line-height: 1.35;
}

.tool-config-tooltip {
  max-width: 360px;
  padding: 4px 0;
  color: rgba(255, 255, 255, 0.92);
}

.tool-config-tooltip :deep(.text-body-2),
.tool-config-tooltip :deep(.text-medium-emphasis),
.tool-config-tooltip :deep(.font-weight-medium) {
  color: inherit !important;
}
</style>
