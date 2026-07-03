<template>
  <v-menu
    v-model="menuOpen"
    :close-on-content-click="false"
    :location="menuLocation"
    offset="10"
    transition="none"
    @update:model-value="handleMenuToggle"
  >
    <template #activator="{ props: menuProps }">
      <button
        v-bind="menuProps"
        class="provider-trigger"
        :class="`provider-trigger--${variant}`"
        type="button"
      >
        <span class="provider-trigger-copy">
          <span class="provider-trigger-title">{{ triggerTitle }}</span>
          <span v-if="triggerMeta" class="provider-trigger-meta">
            {{ triggerMeta }}
          </span>
        </span>
        <v-icon class="provider-trigger-chevron" size="18">
          mdi-chevron-down
        </v-icon>
      </button>
    </template>

    <v-card class="provider-menu-card" elevation="0">
      <div class="provider-menu-body">
        <v-text-field
          v-model="searchQuery"
          placeholder="Search models"
          hide-details
          variant="outlined"
          density="compact"
          prepend-inner-icon="mdi-magnify"
          class="provider-search"
          clearable
        />

        <v-list density="compact" nav class="provider-menu-list">
          <v-list-item
            v-for="provider in filteredProviders"
            :key="provider.id"
            :active="selectedProviderId === provider.id"
            rounded="lg"
            class="provider-menu-item"
            @click="selectProvider(provider)"
          >
            <v-list-item-title class="provider-item-title">
              {{ provider.id }}
            </v-list-item-title>
            <v-list-item-subtitle class="provider-subtitle">
              <span class="model-name">{{ provider.model }}</span>
              <span class="meta-icons">
                <v-icon v-if="supportsImageInput(provider)" size="13">
                  mdi-eye-outline
                </v-icon>
                <v-icon v-if="supportsAudioInput(provider)" size="13">
                  mdi-music-note-outline
                </v-icon>
                <v-icon v-if="supportsToolCall(provider)" size="13">
                  mdi-wrench
                </v-icon>
                <v-icon v-if="supportsReasoning(provider)" size="13">
                  mdi-brain
                </v-icon>
              </span>
            </v-list-item-subtitle>
            <template #append>
              <v-icon
                v-if="selectedProviderId === provider.id"
                class="provider-selected-icon"
                size="18"
              >
                mdi-check
              </v-icon>
            </template>
          </v-list-item>
        </v-list>

        <div v-if="loadingProviders" class="empty-hint">
          Loading models...
        </div>
        <div v-else-if="filteredProviders.length === 0" class="empty-hint">
          No available models
        </div>
      </div>
    </v-card>
  </v-menu>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { providerApi } from "@/api/v1";

interface ModelMetadata {
    modalities?: { input?: string[] };
    tool_call?: boolean;
    reasoning?: boolean;
}

interface ProviderConfig {
  id: string;
  model: string;
  api_base?: string;
  model_metadata?: ModelMetadata;
  enable?: boolean;
}

const props = withDefaults(
  defineProps<{
    variant?: "input" | "header";
  }>(),
  {
    variant: "input",
  },
);

const SELECTED_PROVIDER_KEY = "selectedProvider";
const SELECTED_PROVIDER_MODEL_KEY = "selectedProviderModel";
const providerConfigs = ref<ProviderConfig[]>([]);
const selectedProviderId = ref("");
const selectedModelName = ref("");
const searchQuery = ref("");
const menuOpen = ref(false);
const loadingProviders = ref(false);
const providersLoaded = ref(false);

const variant = computed(() => props.variant);
const menuLocation = computed(() =>
  props.variant === "header" ? "bottom start" : "top",
);

const selectedProvider = computed(() =>
  providerConfigs.value.find((provider) => provider.id === selectedProviderId.value),
);

const triggerTitle = computed(() => {
  if (selectedProvider.value?.id) return selectedProvider.value.id;
  if (selectedProviderId.value) return selectedProviderId.value;
  return props.variant === "header" ? "Default model" : "Model";
});

const triggerMeta = computed(() => {
  const model = selectedProvider.value?.model || selectedModelName.value;
  if (!model || model === triggerTitle.value) return "";
  return model;
});

const filteredProviders = computed(() => {
  if (!searchQuery.value) {
    return providerConfigs.value;
  }
  const query = searchQuery.value.toLowerCase();
  return providerConfigs.value.filter(
    (provider) =>
      provider.id.toLowerCase().includes(query) ||
      provider.model.toLowerCase().includes(query),
  );
});

function loadFromStorage() {
  const savedProvider = localStorage.getItem(SELECTED_PROVIDER_KEY);
  const savedModel = localStorage.getItem(SELECTED_PROVIDER_MODEL_KEY);
  if (savedProvider) {
    selectedProviderId.value = savedProvider;
  }
  if (savedModel) {
    selectedModelName.value = savedModel;
  }
}

function saveToStorage(provider: ProviderConfig) {
  localStorage.setItem(SELECTED_PROVIDER_KEY, provider.id);
  localStorage.setItem(SELECTED_PROVIDER_MODEL_KEY, provider.model || "");
}

async function loadProviderConfigs(force = false) {
  if (loadingProviders.value || (providersLoaded.value && !force)) return;
  loadingProviders.value = true;
  try {
    const response = await providerApi.listByProviderType("chat_completion");
    if (response.data.status === "ok") {
      providerConfigs.value = ((response.data.data || []) as unknown as ProviderConfig[]).filter(
        (provider: ProviderConfig) => provider.enable !== false,
      );
      providersLoaded.value = true;
      const selected = selectedProvider.value;
      if (selected) {
        selectedModelName.value = selected.model || "";
        saveToStorage(selected);
      }
    }
  } catch (error) {
    console.error("Failed to load provider list:", error);
  } finally {
    loadingProviders.value = false;
  }
}

function selectProvider(provider: ProviderConfig) {
  selectedProviderId.value = provider.id;
  selectedModelName.value = provider.model || "";
  saveToStorage(provider);
  menuOpen.value = false;
}

function supportsImageInput(provider: ProviderConfig): boolean {
  const inputs = provider.model_metadata?.modalities?.input || [];
  return inputs.includes("image");
}

function supportsAudioInput(provider: ProviderConfig): boolean {
  const inputs = provider.model_metadata?.modalities?.input || [];
  return inputs.includes("audio");
}

function supportsToolCall(provider: ProviderConfig): boolean {
  return Boolean(provider.model_metadata?.tool_call);
}

function supportsReasoning(provider: ProviderConfig): boolean {
  return Boolean(provider.model_metadata?.reasoning);
}

function getCurrentSelection() {
  return {
    providerId: selectedProviderId.value,
    modelName: selectedProvider.value?.model || selectedModelName.value || "",
  };
}

function handleMenuToggle(isOpen: boolean) {
  if (isOpen) {
    loadProviderConfigs(true);
  }
}

onMounted(() => {
  loadFromStorage();
  loadProviderConfigs();
});

defineExpose({
  getCurrentSelection,
});
</script>

<style scoped>
.provider-trigger {
  display: inline-flex;
  max-width: 100%;
  min-width: 0;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  border: 0;
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  cursor: pointer;
  font: inherit;
  letter-spacing: 0;
  text-align: left;
}

.provider-trigger-copy {
  display: inline-flex;
  min-width: 0;
  align-items: baseline;
  gap: 10px;
}

.provider-trigger-title,
.provider-trigger-meta {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.provider-trigger--header {
  height: 24px;
  margin-top: 2px;
  padding: 0;
}

.provider-trigger--header .provider-trigger-title {
  font-size: 17px;
  font-weight: 620;
  line-height: 24px;
}

.provider-trigger--header .provider-trigger-meta {
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-size: 13px;
  font-weight: 500;
  line-height: 18px;
}

.provider-trigger--input {
  height: 40px;
  max-width: min(280px, 42vw);
  padding: 0 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.18);
  border-radius: 999px;
}

.provider-trigger--input:hover {
  border-color: rgba(var(--v-theme-on-surface), 0.34);
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.provider-trigger--input .provider-trigger-title {
  font-size: 14px;
  font-weight: 500;
}

.provider-trigger--input .provider-trigger-meta {
  display: none;
}

.provider-trigger-chevron {
  flex: 0 0 auto;
  opacity: 0.64;
}

.provider-menu-card {
  width: min(420px, calc(100vw - 24px));
  overflow: hidden;
  border: 0;
  border-radius: 14px !important;
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.08) !important;
}

.provider-menu-body {
  padding: 10px;
}

.provider-search {
  margin-bottom: 8px;
}

.provider-search :deep(.v-field) {
  border-radius: 10px;
  box-shadow: none;
}

.provider-search :deep(.v-field__outline) {
  color: rgba(var(--v-theme-on-surface), 0.16);
}

.provider-menu-list {
  max-height: min(360px, 58vh);
  overflow-y: auto;
  padding: 0;
}

.provider-menu-item {
  min-height: 54px !important;
  margin-bottom: 2px;
  border-radius: 10px !important;
}

.provider-menu-item:hover {
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.provider-menu-item.v-list-item--active {
  background: #f2f2f2;
  color: rgb(var(--v-theme-on-surface));
}

.provider-item-title {
  font-size: 14px;
  font-weight: 600;
  line-height: 18px;
}

.provider-subtitle {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.model-name {
  min-width: 0;
  overflow: hidden;
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 12px;
  line-height: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta-icons {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 4px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

.provider-selected-icon {
  color: rgba(var(--v-theme-on-surface), 0.72);
}

.empty-hint {
  padding: 16px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 12px;
  text-align: center;
}

:global(.v-theme--dark) .provider-menu-item.v-list-item--active {
  background: rgba(255, 255, 255, 0.1);
}

@media (max-width: 768px) {
  .provider-trigger--header .provider-trigger-title {
    font-size: 16px;
  }

  .provider-trigger--header .provider-trigger-meta {
    display: none;
  }

  .provider-trigger--input {
    height: 38px;
    max-width: 48vw;
  }
}
</style>
