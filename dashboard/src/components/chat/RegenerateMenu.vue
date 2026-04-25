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
                <v-icon v-if="supportsImageInput(provider)" size="12">
                  mdi-eye-outline
                </v-icon>
                <v-icon v-if="supportsAudioInput(provider)" size="12">
                  mdi-music-note-outline
                </v-icon>
                <v-icon v-if="supportsToolCall(provider)" size="12">
                  mdi-wrench
                </v-icon>
                <v-icon v-if="supportsReasoning(provider)" size="12">
                  mdi-brain
                </v-icon>
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
import axios from "axios";
import StyledMenu from "@/components/shared/StyledMenu.vue";
import { useModuleI18n } from "@/i18n/composables";

interface ModelMetadata {
  modalities?: { input?: string[] };
  tool_call?: boolean;
  reasoning?: boolean;
}

interface ProviderConfig {
  id: string;
  model: string;
  model_metadata?: ModelMetadata;
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
const providerConfigs = ref<ProviderConfig[]>([]);
const loadingProviders = ref(false);
const providersLoaded = ref(false);

async function loadProviderConfigs(force = false) {
  if (loadingProviders.value || (providersLoaded.value && !force)) return;
  loadingProviders.value = true;
  try {
    const response = await axios.get("/api/config/provider/list", {
      params: { provider_type: "chat_completion" },
    });
    if (response.data.status === "ok") {
      providerConfigs.value = (response.data.data || []).filter(
        (provider: ProviderConfig) => provider.enable !== false,
      );
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

function supportsImageInput(provider: ProviderConfig): boolean {
  return Boolean(provider.model_metadata?.modalities?.input?.includes("image"));
}

function supportsAudioInput(provider: ProviderConfig): boolean {
  return Boolean(provider.model_metadata?.modalities?.input?.includes("audio"));
}

function supportsToolCall(provider: ProviderConfig): boolean {
  return Boolean(provider.model_metadata?.tool_call);
}

function supportsReasoning(provider: ProviderConfig): boolean {
  return Boolean(provider.model_metadata?.reasoning);
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

.regenerate-empty {
  padding: 14px 16px;
  color: var(--chat-muted, rgba(var(--v-theme-on-surface), 0.62));
  font-size: 12px;
  text-align: center;
}
</style>
