<script setup lang="ts">
import { computed } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import type { ToolItem } from '../types';

const { tm: tmTool } = useModuleI18n('features/tooluse');

const props = defineProps<{
  items: ToolItem[];
  loading?: boolean;
  deletingSavedTools: ReadonlySet<string>;
}>();

const emit = defineEmits<{
  (e: 'toggle-tool', tool: ToolItem): void;
  (e: 'update-permission', tool: ToolItem, permission: 'admin' | 'member'): void;
  (e: 'delete-saved-settings', tool: ToolItem): void;
}>();

const toolHeaders = computed(() => [
  { title: tmTool('functionTools.title'), key: 'name', minWidth: '320px' },
  { title: tmTool('functionTools.description'), key: 'description' },
  { title: tmTool('functionTools.table.originName'), key: 'origin_name', sortable: false, width: '140px' },
  { title: tmTool('functionTools.table.permission'), key: 'permission', sortable: false, width: '110px' },
  { title: tmTool('functionTools.table.actions'), key: 'actions', sortable: false, width: '100px' }
]);

const parameterEntries = (tool: ToolItem) => Object.entries(tool.parameters?.properties || {});

const getPermissionColor = (permission?: string | null): string => {
  switch (permission) {
    case 'admin':
      return 'error';
    default:
      return 'success';
  }
};

const getPermissionLabel = (permission?: string | null): string => {
  switch (permission) {
    case 'admin':
      return tmTool('functionTools.table.permissionAdmin');
    default:
      return tmTool('functionTools.table.permissionEveryone');
  }
};
</script>

<template>
  <v-card class="rounded-lg overflow-hidden elevation-1">
    <v-data-table
      :headers="toolHeaders"
      :items="items"
      :item-value="(item) => item.resource?.key || item.resource_key || item.name"
      hover
      show-expand
      class="tool-table"
      :loading="props.loading"
    >
      <template #item.name="{ item }">
        <div class="tool-name text-body-2 font-weight-medium py-2">{{ item.name }}</div>
      </template>

      <template #item.description="{ item }">
        <div class="text-body-2 text-medium-emphasis" style="max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" :title="item.description">
          {{ item.description || '-' }}
        </div>
      </template>

      <template #item.origin_name="{ item }">
        <v-chip v-if="item.registered === false" size="small" variant="tonal">
          {{ tmTool('functionTools.table.unregistered') }}
        </v-chip>
        <div v-else class="text-body-2 text-medium-emphasis" style="max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" :title="item.origin_name">
          {{ item.origin_name || '-' }}
        </div>
      </template>

      <template #item.permission="{ item }">
        <template v-if="item.registered === false">
          <v-chip v-if="item.permission_configured" :color="getPermissionColor(item.permission)" size="small">
            {{ getPermissionLabel(item.permission) }}
          </v-chip>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        <v-menu v-else location="bottom">
          <template v-slot:activator="{ props: menuProps }">
            <v-chip
              v-bind="menuProps"
              :color="getPermissionColor(item.permission)"
              size="small"
              class="font-weight-medium cursor-pointer"
              link
            >
              {{ getPermissionLabel(item.permission) }}
              <v-icon end size="14">mdi-chevron-down</v-icon>
            </v-chip>
          </template>
          <v-list density="compact">
            <v-list-item
              :value="'member'"
              @click="emit('update-permission', item, 'member')"
              :active="item.permission !== 'admin'"
            >
              <v-list-item-title>{{ tmTool('functionTools.table.permissionEveryone') }}</v-list-item-title>
            </v-list-item>
            <v-list-item
              :value="'admin'"
              @click="emit('update-permission', item, 'admin')"
              :active="item.permission === 'admin'"
            >
              <v-list-item-title>{{ tmTool('functionTools.table.permissionAdmin') }}</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-menu>
      </template>

      <template #item.actions="{ item }">
        <span v-if="item.inactive_configured && (item.registered === false || item.active)"
          class="text-caption text-medium-emphasis">
          {{ tmTool('functionTools.table.savedInactive') }}
        </span>
        <v-switch v-if="item.registered !== false" :model-value="item.active" color="primary" density="compact"
          hide-details inset @update:model-value="emit('toggle-tool', item)" />
      </template>

      <template #item.data-table-expand="{ item, internalItem, isExpanded, toggleExpand }">
        <v-btn v-if="item.registered !== false" :icon="isExpanded(internalItem) ? '$collapse' : '$expand'"
          size="small" variant="text" :aria-label="tmTool('functionTools.parameters')"
          :aria-expanded="isExpanded(internalItem)" @click.stop="toggleExpand(internalItem)" />
        <v-btn v-else icon="mdi-delete-outline" size="small" color="error" variant="text" :ripple="false"
          :title="tmTool('functionTools.table.deleteSavedSettings', { name: item.name })"
          :aria-label="tmTool('functionTools.table.deleteSavedSettings', { name: item.name })"
          :loading="deletingSavedTools.has(item.name)" @click.stop="emit('delete-saved-settings', item)" />
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

</style>
