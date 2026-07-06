<template>
  <StyledMenu
    location="end"
    offset="6"
    transition="none"
    no-border
    :close-on-content-click="true"
    @update:model-value="handleMenuToggle"
  >
    <template #activator="{ props: menuProps }">
      <v-btn
        v-bind="menuProps"
        icon="mdi-refresh"
        size="x-small"
        variant="text"
      />
    </template>

    <v-list-item
      class="styled-menu-item"
      rounded="md"
      @click="emit('retry')"
    >
      <template #prepend>
        <v-icon size="18">mdi-refresh</v-icon>
      </template>
      <v-list-item-title>{{ tm("actions.retry") }}</v-list-item-title>
    </v-list-item>

    <v-menu
      location="end"
      offset="8"
      transition="none"
      open-on-hover
      :close-on-content-click="true"
      @update:model-value="handleModelMenuToggle"
    >
      <template #activator="{ props: modelMenuProps }">
        <v-list-item
          v-bind="modelMenuProps"
          class="styled-menu-item"
          rounded="md"
        >
          <template #prepend>
            <v-icon size="18">mdi-creation</v-icon>
          </template>
          <v-list-item-title>{{ tm("actions.retryWithModel") }}</v-list-item-title>
          <template #append>
            <v-progress-circular
              v-if="loadingProviders"
              indeterminate
              size="16"
              width="2"
            />
            <v-icon v-else size="18">mdi-chevron-right</v-icon>
          </template>
        </v-list-item>
      </template>

      <v-card
        class="styled-menu-card styled-menu-card-borderless regenerate-model-card"
        elevation="8"
        rounded="lg"
      >
        <v-list density="compact" class="styled-menu-list pa-1">
          <v-list-item
            v-for="provider in providerConfigs"
            :key="provider.id"
            class="styled-menu-item regenerate-model-item"
            rounded="md"
            @click="retryWithModel(provider)"
          >
            <v-list-item-title class="text-body-2">
              {{ provider.id }}
            </v-list-item-title>
            <v-list-item-subtitle class="regenerate-model-subtitle">
              <span class="regenerate-model-name">{{ provider.model }}</span>
              <span class="regenerate-model-icons">
                <v-tooltip
                  v-for="item in capabilityBadges(provider)"
                  :key="item.key"
                  location="top"
                  max-width="320"
                >
                  <template #activator="{ props: badgeTooltipProps }">
                    <span
                      v-bind="badgeTooltipProps"
                      class="regenerate-model-icon-badge"
                      :class="{
                        'regenerate-model-icon-badge--disabled': !item.enabled,
                      }"
                      @click.stop
                    >
                      <v-icon size="12">{{ item.icon }}</v-icon>
                    </span>
                  </template>
                  <span>{{ item.tooltip }}</span>
                </v-tooltip>
                <v-tooltip
                  v-if="formatContextLimit(provider, metadataForProvider(provider))"
                  location="top"
                  max-width="320"
                >
                  <template #activator="{ props: contextTooltipProps }">
                    <span
                      v-bind="contextTooltipProps"
                      class="regenerate-model-context-badge"
                      @click.stop
                    >
                      {{ formatContextLimit(provider, metadataForProvider(provider)) }}
                    </span>
                  </template>
                  <span>{{
                    providerTm("models.metadata.context", {
                      tokens: formatContextLimit(
                        provider,
                        metadataForProvider(provider),
                      ),
                    })
                  }}</span>
                </v-tooltip>
              </span>
            </v-list-item-subtitle>
          </v-list-item>

          <div v-if="!loadingProviders && !providerConfigs.length" class="regenerate-empty">
            {{ tm("actions.noAvailableModels") }}
          </div>
        </v-list>
      </v-card>
    </v-menu>
  </StyledMenu>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { providerApi } from "@/api/v1";
import StyledMenu from "@/components/shared/StyledMenu.vue";
import { useModuleI18n } from "@/i18n/composables";
import {
  formatContextLimit,
  providerCapabilityBadges,
  type ProviderModelMetadata,
  type ProviderMetadataSource,
} from "@/utils/providerMetadata";

interface ProviderConfig extends ProviderMetadataSource {
  id: string;
  model: string;
  enable?: boolean;
}

export interface RegenerateModelSelection {
  providerId: string;
  modelName: string;
}

const emit = defineEmits<{
  retry: [];
  retryWithModel: [selection: RegenerateModelSelection];
}>();

const { tm } = useModuleI18n("features/chat");
const { tm: providerTm } = useModuleI18n("features/provider");
const providerConfigs = ref<ProviderConfig[]>([]);
const loadingProviders = ref(false);
const providersLoaded = ref(false);
const modelMetadata = ref<Record<string, ProviderModelMetadata>>({});

async function loadProviderConfigs(force = false) {
  if (loadingProviders.value || (providersLoaded.value && !force)) return;
  loadingProviders.value = true;
  try {
    const response = await providerApi.listByProviderType("chat_completion");
    if (response.data.status === "ok") {
      modelMetadata.value = (
        response.data.model_metadata || {}
      ) as Record<string, ProviderModelMetadata>;
      providerConfigs.value = (
        (response.data.data || []) as unknown as ProviderConfig[]
      ).filter((provider: ProviderConfig) => provider.enable !== false);
      providersLoaded.value = true;
    }
  } catch (error) {
    console.error("Failed to load provider list:", error);
  } finally {
    loadingProviders.value = false;
  }
}

function handleMenuToggle(isOpen: boolean) {
  if (isOpen) {
    loadProviderConfigs();
  }
}

function handleModelMenuToggle(isOpen: boolean) {
  if (isOpen) {
    loadProviderConfigs();
  }
}

function retryWithModel(provider: ProviderConfig) {
  emit("retryWithModel", {
    providerId: provider.id,
    modelName: provider.model,
  });
}

function capabilityBadges(provider: ProviderConfig) {
  return providerCapabilityBadges(
    provider,
    metadataForProvider(provider),
    providerTm,
  );
}

function metadataForProvider(provider: ProviderConfig) {
  return provider.model ? modelMetadata.value[provider.model] || null : null;
}
</script>

<style scoped>
.regenerate-model-card {
  min-width: 280px;
  max-width: min(360px, 86vw);
}

.regenerate-model-card :deep(.v-list) {
  max-height: 320px;
  overflow-y: auto;
}

.regenerate-model-item {
  min-height: 46px;
}

.regenerate-model-subtitle {
  display: flex;
  align-items: center;
  gap: 8px;
}

.regenerate-model-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--chat-muted, rgba(var(--v-theme-on-surface), 0.62));
}

.regenerate-model-icons {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 4px;
  color: var(--chat-muted, rgba(var(--v-theme-on-surface), 0.62));
}

.regenerate-model-icon-badge {
  display: inline-flex;
  align-items: center;
  color: rgba(var(--v-theme-on-surface), 0.72);
}

.regenerate-model-icon-badge--disabled {
  color: rgba(var(--v-theme-on-surface), 0.34);
}

.regenerate-model-context-badge {
  display: inline-flex;
  align-items: center;
  height: 16px;
  padding: 0 5px;
  border-radius: 999px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-size: 10px;
  font-weight: 650;
  line-height: 16px;
}

.regenerate-empty {
  padding: 14px 16px;
  color: var(--chat-muted, rgba(var(--v-theme-on-surface), 0.62));
  font-size: 12px;
  text-align: center;
}
</style>
