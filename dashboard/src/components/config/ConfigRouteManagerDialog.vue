<template>
  <v-dialog v-model="dialogVisible" max-width="800px">
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between">
        <div>
          <div class="text-h3 pa-2">{{ props.configName }} {{ tm('routeManager.title') }}</div>
        </div>
        <v-btn icon="mdi-close" variant="text" @click="dialogVisible = false"></v-btn>
      </v-card-title>
      <v-card-text>
        <div v-if="loading" class="d-flex justify-center py-4">
          <v-progress-circular indeterminate color="primary"></v-progress-circular>
        </div>
        <div v-else>
          <div class="text-caption text-medium-emphasis mb-4">
            {{ tm('routeManager.hint') }}
          </div>

          <div v-if="groupedRoutes.length === 0" class="text-center py-4 text-medium-emphasis">
            {{ tm('routeManager.empty') }}
          </div>

          <div v-for="(group, groupIndex) in groupedRoutes" :key="group.platformId">
            <v-divider v-if="groupIndex > 0" class="my-3" />
            <div class="route-group">
              <div class="route-group-platform">
                <v-avatar size="22" rounded="sm" class="route-platform-avatar">
                  <img
                    v-if="getRoutePlatformIcon(group.platformId)"
                    :src="getRoutePlatformIcon(group.platformId)"
                    :alt="group.platformId"
                    class="route-platform-avatar__img"
                  />
                  <v-icon v-else size="14">mdi-robot-outline</v-icon>
                </v-avatar>
                <span class="text-body-2 font-weight-medium">{{ group.platformId }}</span>
                <v-chip size="x-small" variant="tonal" color="primary">
                  {{ group.routes.length }}
                </v-chip>
              </div>

              <div class="route-group-umops">
                <div
                  v-for="route in group.routes"
                  :key="route.id"
                  class="route-umop-row"
                  :class="{ 'route-umop-row--all': isAllSessionsRoute(route.umop) }"
                >
                  <span class="text-body-2 route-umop-row__text">
                    {{ isAllSessionsRoute(route.umop) ? tm('routeManager.allSessions') : route.umop }}
                  </span>
                  <div class="route-umop-row__actions">
                    <v-tooltip :text="tm('routeManager.delete')" location="top">
                      <template #activator="{ props: tooltipProps }">
                        <v-btn
                          v-bind="tooltipProps"
                          icon="mdi-delete-outline"
                          variant="text"
                          color="error"
                          size="small"
                          @click="emit('removeRoute', route.id)"
                        />
                      </template>
                    </v-tooltip>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="dialogVisible = false">
          {{ tm('buttons.cancel') }}
        </v-btn>
        <v-btn color="primary" :loading="saving" @click="emit('save')">
          {{ tm('actions.save') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { getPlatformIcon } from '@/utils/platformUtils';

interface RouteItem {
  id: string;
  platformId: string;
  umop: string;
}

const props = withDefaults(defineProps<{
  modelValue: boolean;
  configId: string;
  configName: string;
  loading: boolean;
  saving: boolean;
  items: RouteItem[];
  platformTypeMap: Record<string, string>;
}>(), {
  modelValue: false,
  configId: '',
  configName: '',
  loading: false,
  saving: false,
  items: () => [],
  platformTypeMap: () => ({})
});

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  removeRoute: [routeId: string];
  save: [];
}>();

const { tm } = useModuleI18n('features/config');

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value)
});

const groupedRoutes = computed(() => {
  const groups: Record<string, RouteItem[]> = {};
  for (const item of props.items) {
    const platformId = String(item.platformId || '').trim();
    if (!platformId) {
      continue;
    }
    if (!groups[platformId]) {
      groups[platformId] = [];
    }
    groups[platformId].push(item);
  }

  return Object.entries(groups)
    .map(([platformId, routes]) => ({
      platformId,
      routes: (() => {
        const sortedRoutes = routes.sort((a, b) => a.umop.localeCompare(b.umop));
        const allSessionsRoute = sortedRoutes.find((route) => isAllSessionsRoute(route.umop));
        if (allSessionsRoute) {
          return [allSessionsRoute];
        }
        return sortedRoutes;
      })()
    }))
    .sort((a, b) => a.platformId.localeCompare(b.platformId));
});

function getRoutePlatformIcon(platformId: string): string | undefined {
  const platformType = props.platformTypeMap[platformId] || platformId;
  return getPlatformIcon(platformType);
}

function isAllSessionsRoute(umop: string): boolean {
  return String(umop || '').endsWith(':*:*');
}
</script>

<style scoped>
.route-group-platform {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 24px;
}

.route-group-umops {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.route-umop-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-radius: 6px;
  padding: 2px 4px 2px 10px;
  gap: 10px;
  background: rgba(var(--v-theme-on-surface), 0.03);
}

.route-umop-row--all {
  background: rgba(var(--v-theme-primary), 0.08);
}

.route-umop-row__text {
  min-width: 0;
  word-break: break-all;
}

.route-umop-row__actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.route-platform-avatar {
  background: rgba(var(--v-theme-surface), 1);
}

.route-platform-avatar__img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  padding: 2px;
}

.route-group {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
}

@media (max-width: 767px) {
  .route-group {
    grid-template-columns: minmax(0, 1fr);
  }

  .route-group-platform {
    margin-bottom: 2px;
  }

  .route-umop-row {
    align-items: flex-start;
  }
}
</style>
