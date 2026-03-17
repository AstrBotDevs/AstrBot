<script setup lang="ts">
import { computed } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import type { ToolItem } from '../types';

const { tm: tmTool } = useModuleI18n('features/tooluse');
const { tm: tmCommand } = useModuleI18n('features/command');

const props = defineProps<{
  items: ToolItem[];
  loading?: boolean;
}>();

const emit = defineEmits<{
  (e: 'toggle-tool', tool: ToolItem): void;
}>();

const toolHeaders = computed(() => [
  { title: tmTool('functionTools.title'), key: 'name', minWidth: '160px' },
  { title: tmTool('functionTools.description'), key: 'description' },
  { title: tmTool('functionTools.table.origin'), key: 'origin', sortable: false, width: '120px' },
  { title: tmTool('functionTools.table.originName'), key: 'origin_name', sortable: false, width: '160px' },
  { title: tmCommand('status.enabled'), key: 'active', sortable: false, width: '120px' },
  { title: tmTool('functionTools.table.actions'), key: 'actions', sortable: false, width: '120px' }
]);

const parameterEntries = (tool: ToolItem) => Object.entries(tool.parameters?.properties || {});
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
        <div class="d-flex align-center py-2">
          <v-icon color="primary" class="mr-2" size="18">
            {{ item.name.includes(':') ? 'mdi-server-network' : 'mdi-function-variant' }}
          </v-icon>
          <div>
            <div class="text-subtitle-1 font-weight-medium">{{ item.name }}</div>
          </div>
        </div>
      </template>

      <template #item.description="{ item }">
        <div class="text-body-2 text-medium-emphasis" style="max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          {{ item.description || '-' }}
        </div>
      </template>

      <template #item.origin="{ item }">
        <v-chip size="small" variant="tonal" color="info" class="text-caption font-weight-medium">
          {{ item.origin || '-' }}
        </v-chip>
      </template>

      <template #item.origin_name="{ item }">
        <div class="text-body-2 text-medium-emphasis" style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          {{ item.origin_name || '-' }}
        </div>
      </template>

      <template #item.active="{ item }">
        <v-chip :color="item.active ? 'success' : 'error'" size="small" class="font-weight-medium" :variant="item.active ? 'flat' : 'outlined'">
          {{ item.active ? tmCommand('status.enabled') : tmCommand('status.disabled') }}
        </v-chip>
      </template>

      <template #item.actions="{ item }">
        <v-switch
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
</style>
