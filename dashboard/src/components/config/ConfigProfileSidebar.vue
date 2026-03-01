<template>
  <div class="config-profile-sidebar">
    <div class="d-flex align-center justify-space-between mb-3">
      <h3 class="text-subtitle-1 font-weight-bold mb-0">
        <v-icon size="18" class="mr-1">mdi-format-list-bulleted-square</v-icon>
        {{ tm('profileSidebar.title') }}
      </h3>
      <v-tooltip :text="tm('configManagement.manageConfigs')" location="top">
        <template #activator="{ props: tooltipProps }">
          <v-btn v-bind="tooltipProps" size="small" variant="text" icon="mdi-cog" :disabled="disabled"
            @click="emit('manage')" />
        </template>
      </v-tooltip>
    </div>

    <div class="config-profile-list">
      <v-card v-for="config in configs" :key="config.id" class="profile-card" :class="{
        'profile-card--active': config.id === selectedConfigId,
        'profile-card--disabled': disabled
      }" variant="outlined" @click="onSelect(config.id)">
        <div class="profile-card__name text-h4 d-flex align-center">
          <v-icon size="24" class="mr-2">mdi-file-outline</v-icon>
          {{ config.name }}
        </div>
        <div class="mt-3 d-flex" style="align-items: start; justify-content: center;">
          <v-icon size="24" class="mr-1">mdi-routes</v-icon>
          <div class="profile-card__bindings">
            <template v-if="bindingsForConfig(config.id).length > 0">
              <v-tooltip v-for="binding in visibleBindings(bindingsForConfig(config.id))"
                :key="`${config.id}-${binding.platformId}`" location="top">
                <template #activator="{ props: tooltipProps }">
                  <button v-bind="tooltipProps" type="button" class="binding-pill"
                    @click.stop="onManageRoutes(config.id)">
                    <v-avatar size="22" class="binding-avatar" rounded="sm">
                      <img v-if="getBindingIcon(binding)" :src="getBindingIcon(binding)" :alt="binding.platformId"
                        class="binding-avatar__img" />
                      <v-icon v-else size="14">mdi-robot-outline</v-icon>
                    </v-avatar>
                    <span class="binding-pill__label">
                      {{ binding.platformId }}
                    </span>
                  </button>
                </template>
                <div class="binding-tooltip-content">
                  <div class="text-caption font-weight-bold mb-1">
                    {{ tm('profileSidebar.platformId') }}: {{ binding.platformId }}
                  </div>
                  <div class="text-caption mb-1">
                    {{ tm('profileSidebar.umop') }}:
                  </div>
                  <div v-for="umop in binding.umops" :key="`${binding.platformId}-${umop}`" class="text-caption">
                    {{ umop }}
                  </div>
                </div>
              </v-tooltip>
              <v-chip v-if="bindingsForConfig(config.id).length > maxVisibleBindings" size="x-small" variant="tonal"
                color="primary">
                +{{ bindingsForConfig(config.id).length - maxVisibleBindings }}
              </v-chip>
            </template>
            <span v-else class="text-caption text-medium-emphasis">
              {{ tm('profileSidebar.noBindings') }}
            </span>
          </div>

        </div>
      </v-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useModuleI18n } from '@/i18n/composables';
import { getPlatformIcon } from '@/utils/platformUtils';

interface ConfigInfo {
  id: string;
  name: string;
}

interface ConfigBinding {
  platformId: string;
  platformType?: string;
  umops: string[];
}

const props = withDefaults(defineProps<{
  configs: ConfigInfo[];
  selectedConfigId: string | null;
  bindingsByConfigId: Record<string, ConfigBinding[]>;
  disabled?: boolean;
}>(), {
  selectedConfigId: null,
  bindingsByConfigId: () => ({}),
  disabled: false
});

const emit = defineEmits<{
  select: [configId: string];
  manage: [];
  manageRoutes: [payload: { configId: string }];
}>();

const { tm } = useModuleI18n('features/config');

const maxVisibleBindings = 6;

function onSelect(configId: string): void {
  if (props.disabled) {
    return;
  }
  emit('select', configId);
}

function onManageRoutes(configId: string): void {
  if (props.disabled) {
    return;
  }
  emit('manageRoutes', { configId });
}

function bindingsForConfig(configId: string): ConfigBinding[] {
  return props.bindingsByConfigId[configId] || [];
}

function visibleBindings(bindings: ConfigBinding[]): ConfigBinding[] {
  return bindings.slice(0, maxVisibleBindings);
}

function getBindingIcon(binding: ConfigBinding): string | undefined {
  if (binding.platformType) {
    return getPlatformIcon(binding.platformType);
  }
  return getPlatformIcon(binding.platformId);
}
</script>

<style scoped>
.config-profile-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: calc(100vh - 210px);
  overflow-y: auto;
  padding-right: 4px;
}

.profile-card {
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
  border-radius: 12px;
  cursor: pointer;
  padding: 12px;
  transition: border-color 0.15s ease, background-color 0.15s ease, transform 0.15s ease;
}


.profile-card--active {
  background: rgba(var(--v-theme-primary), 0.08);
}

.profile-card--disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.profile-card__name {
  line-height: 1.3;
}

.profile-card__bindings {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 28px;
}

.binding-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px 2px 4px;
  border-radius: 999px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.14);
  background: rgba(var(--v-theme-surface), 1);
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.binding-pill:hover {
  border-color: rgba(var(--v-theme-primary), 0.45);
  background: rgba(var(--v-theme-primary), 0.06);
}

.binding-pill__label {
  font-size: 0.78rem;
  line-height: 1.1;
  white-space: nowrap;
  color: rgba(var(--v-theme-on-surface), 0.8);
}

.binding-avatar__img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  padding: 2px;
}

.binding-tooltip-content {
  max-width: 380px;
  word-break: break-all;
}
</style>
