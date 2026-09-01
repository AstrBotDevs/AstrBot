<template>
  <div class="provider-select-menu" :class="`provider-select-menu--${variant}`">
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
            :placeholder="sharedTm('providerSelector.searchPlaceholder')"
            hide-details
            variant="outlined"
            density="compact"
            prepend-inner-icon="mdi-magnify"
            class="provider-search"
            clearable
          />

          <v-progress-linear
            v-if="loadingProviders"
            indeterminate
            color="primary"
            class="provider-loading"
          />

          <div
            v-if="multiple && selectedProviderIds.length > 0"
            class="selected-provider-section"
          >
            <div class="selected-provider-label">
              {{
                sharedTm('providerSelector.selectedModelCount', {
                  count: selectedProviderIds.length,
                })
              }}
            </div>
            <v-list density="compact" class="selected-provider-list">
              <v-list-item
                v-for="(providerId, index) in selectedProviderIds"
                :key="`selected-${providerId}`"
                rounded="lg"
                class="selected-provider-item"
              >
                <v-list-item-title class="provider-item-title">
                  {{ providerId }}
                </v-list-item-title>
                <template #append>
                  <div class="selected-provider-actions">
                    <v-btn
                      icon="mdi-arrow-up"
                      size="x-small"
                      variant="text"
                      :disabled="index === 0"
                      @click.stop="moveSelected(index, -1)"
                    />
                    <v-btn
                      icon="mdi-arrow-down"
                      size="x-small"
                      variant="text"
                      :disabled="index === selectedProviderIds.length - 1"
                      @click.stop="moveSelected(index, 1)"
                    />
                    <v-btn
                      icon="mdi-close"
                      size="x-small"
                      variant="text"
                      @click.stop="removeSelected(providerId)"
                    />
                  </div>
                </template>
              </v-list-item>
            </v-list>
            <v-divider class="provider-menu-divider" />
          </div>

          <v-list
            v-if="!loadingProviders"
            density="compact"
            nav
            class="provider-menu-list"
          >
            <v-list-item
              v-if="!multiple && allowEmpty && !searchQuery"
              :active="!modelValue"
              rounded="lg"
              class="provider-menu-item"
              @click="clearSelection"
            >
              <v-list-item-title class="provider-item-title">
                {{ sharedTm('providerSelector.clearSelection') }}
              </v-list-item-title>
              <v-list-item-subtitle class="provider-subtitle">
                {{ sharedTm('providerSelector.clearSelectionSubtitle') }}
              </v-list-item-subtitle>
              <template #append>
                <v-icon
                  v-if="!modelValue"
                  class="provider-selected-icon"
                  size="18"
                >
                  mdi-check
                </v-icon>
              </template>
            </v-list-item>

            <v-list-item
              v-for="provider in filteredProviders"
              :key="provider.id"
              :active="isProviderSelected(provider.id)"
              rounded="lg"
              class="provider-menu-item"
              @click="selectProvider(provider)"
            >
              <v-list-item-title class="provider-item-title">
                {{ provider.id }}
              </v-list-item-title>
              <v-list-item-subtitle class="provider-subtitle">
                <span class="model-name">
                  {{
                    provider.model || provider.type || provider.provider_type
                  }}
                </span>
                <span
                  v-if="
                    capabilityBadges(provider).length ||
                    formatContextLimit(provider, metadataForProvider(provider))
                  "
                  class="meta-icons"
                >
                  <v-tooltip
                    v-for="item in capabilityBadges(provider)"
                    :key="item.key"
                    location="top"
                    max-width="320"
                  >
                    <template #activator="{ props: badgeTooltipProps }">
                      <span
                        v-bind="badgeTooltipProps"
                        class="meta-icon-badge"
                        :class="{ 'meta-icon-badge--disabled': !item.enabled }"
                        @click.stop
                      >
                        <v-icon size="13">{{ item.icon }}</v-icon>
                      </span>
                    </template>
                    <span>{{ item.tooltip }}</span>
                  </v-tooltip>
                  <v-tooltip
                    v-if="
                      formatContextLimit(
                        provider,
                        metadataForProvider(provider),
                      )
                    "
                    location="top"
                    max-width="320"
                  >
                    <template #activator="{ props: contextTooltipProps }">
                      <span
                        v-bind="contextTooltipProps"
                        class="meta-context-badge"
                        @click.stop
                      >
                        {{
                          formatContextLimit(
                            provider,
                            metadataForProvider(provider),
                          )
                        }}
                      </span>
                    </template>
                    <span>{{
                      providerTm('models.metadata.context', {
                        tokens: formatContextLimit(
                          provider,
                          metadataForProvider(provider),
                        ),
                      })
                    }}</span>
                  </v-tooltip>
                </span>
              </v-list-item-subtitle>
              <template #append>
                <div class="provider-menu-actions" @click.stop>
                  <v-tooltip location="top">
                    <template #activator="{ props: testTooltipProps }">
                      <v-btn
                        v-bind="testTooltipProps"
                        icon="mdi-connection"
                        size="x-small"
                        variant="text"
                        :loading="testingProviderIds.includes(provider.id)"
                        :disabled="testingProviderIds.includes(provider.id)"
                        @click.stop="testProvider(provider)"
                      />
                    </template>
                    <span>{{ providerTm('models.testButton') }}</span>
                  </v-tooltip>
                  <v-icon
                    v-if="isProviderSelected(provider.id)"
                    class="provider-selected-icon"
                    size="18"
                  >
                    mdi-check
                  </v-icon>
                </div>
              </template>
            </v-list-item>
          </v-list>

          <div
            v-if="!loadingProviders && filteredProviders.length === 0"
            class="empty-hint"
          >
            {{ sharedTm('providerSelector.noProviders') }}
          </div>

          <v-divider class="provider-menu-divider" />
          <v-btn
            block
            prepend-icon="mdi-plus"
            variant="text"
            class="provider-create-button"
            @click="openProviderDrawer"
          >
            {{ sharedTm('providerSelector.createProvider') }}
          </v-btn>
        </div>
      </v-card>
    </v-menu>
  </div>

  <v-overlay
    v-model="providerDrawer"
    class="provider-drawer-overlay"
    location="right"
    transition="slide-x-reverse-transition"
    :scrim="true"
    @click:outside="closeProviderDrawer"
  >
    <v-card class="provider-drawer-card" elevation="12">
      <div class="provider-drawer-header">
        <v-btn icon variant="text" @click="closeProviderDrawer">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </div>
      <div class="provider-drawer-content">
        <ProviderChatCompletionPanel
          v-if="providerType === 'chat_completion'"
        />
        <ProviderPage v-else :default-tab="providerType" />
      </div>
    </v-card>
  </v-overlay>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue';
import { providerApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import { useToast } from '@/utils/toast';
import {
  formatContextLimit,
  providerCapabilityBadges,
  type ProviderModelMetadata,
  type ProviderMetadataSource,
} from '@/utils/providerMetadata';

const ProviderChatCompletionPanel = defineAsyncComponent(
  () => import('@/components/provider/ProviderChatCompletionPanel.vue'),
);
const ProviderPage = defineAsyncComponent(
  () => import('@/views/ProviderPage.vue'),
);

interface ProviderConfig extends ProviderMetadataSource {
  id: string;
  model?: string;
  type?: string;
  provider_type?: string;
  enable?: boolean;
}

const props = withDefaults(
  defineProps<{
    modelValue?: string | string[];
    fallbackModel?: string;
    providerType?: string;
    buttonText?: string;
    variant?: 'config' | 'input' | 'header';
    allowEmpty?: boolean;
    multiple?: boolean;
  }>(),
  {
    modelValue: '',
    fallbackModel: '',
    providerType: 'chat_completion',
    buttonText: '',
    variant: 'config',
    allowEmpty: true,
    multiple: false,
  },
);

const emit = defineEmits<{
  'update:modelValue': [value: string | string[]];
  select: [provider: ProviderConfig | null];
}>();

const { tm: sharedTm } = useModuleI18n('core.shared');
const { tm: providerTm } = useModuleI18n('features/provider');
const { success: toastSuccess, error: toastError } = useToast();

const providerConfigs = ref<ProviderConfig[]>([]);
const modelMetadata = ref<Record<string, ProviderModelMetadata>>({});
const testingProviderIds = ref<string[]>([]);
const searchQuery = ref('');
const menuOpen = ref(false);
const providerDrawer = ref(false);
const loadingProviders = ref(false);
const providersLoaded = ref(false);

const selectedProviderIds = computed(() =>
  props.multiple && Array.isArray(props.modelValue)
    ? props.modelValue.filter((value): value is string => Boolean(value))
    : [],
);

const selectedProvider = computed(() =>
  providerConfigs.value.find(
    (provider) =>
      !Array.isArray(props.modelValue) && provider.id === props.modelValue,
  ),
);

const triggerTitle = computed(() => {
  if (props.multiple) {
    return selectedProviderIds.value.length > 0
      ? sharedTm('providerSelector.selectedModelCount', {
          count: selectedProviderIds.value.length,
        })
      : sharedTm('providerSelector.notSelected');
  }
  if (props.variant === 'input') {
    return (
      selectedProvider.value?.model ||
      props.fallbackModel ||
      selectedProvider.value?.id ||
      (typeof props.modelValue === 'string' && props.modelValue) ||
      sharedTm('providerSelector.model')
    );
  }
  if (selectedProvider.value?.id) return selectedProvider.value.id;
  if (typeof props.modelValue === 'string' && props.modelValue) {
    return props.modelValue;
  }
  if (props.variant === 'header')
    return sharedTm('providerSelector.defaultModel');
  if (props.buttonText) return props.buttonText;
  return sharedTm('providerSelector.notSelected');
});

const triggerMeta = computed(() => {
  if (props.variant !== 'header') return '';
  const model = selectedProvider.value?.model || props.fallbackModel;
  if (!model || model === triggerTitle.value) return '';
  return model;
});

const menuLocation = computed(() => {
  if (props.variant === 'input') return 'top';
  return props.variant === 'header' ? 'bottom start' : 'bottom end';
});

const filteredProviders = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  if (!query) return providerConfigs.value;
  return providerConfigs.value.filter(
    (provider) =>
      provider.id.toLowerCase().includes(query) ||
      String(provider.model || '')
        .toLowerCase()
        .includes(query),
  );
});

async function loadProviderConfigs(force = false) {
  if (loadingProviders.value || (providersLoaded.value && !force)) return;
  loadingProviders.value = true;
  try {
    const response = await providerApi.listByProviderType(props.providerType);
    if (response.data.status === 'ok') {
      modelMetadata.value = (response.data.model_metadata || {}) as Record<
        string,
        ProviderModelMetadata
      >;
      providerConfigs.value = (
        (response.data.data || []) as unknown as ProviderConfig[]
      ).filter((provider) => provider.enable !== false);
      providersLoaded.value = true;
    }
  } catch (error) {
    console.error('Failed to load provider list:', error);
    providerConfigs.value = [];
  } finally {
    loadingProviders.value = false;
  }
}

function selectProvider(provider: ProviderConfig) {
  if (props.multiple) {
    const selected = [...selectedProviderIds.value];
    const index = selected.indexOf(provider.id);
    if (index >= 0) {
      selected.splice(index, 1);
    } else {
      selected.push(provider.id);
    }
    emit('update:modelValue', selected);
    return;
  }
  emit('update:modelValue', provider.id);
  emit('select', provider);
  menuOpen.value = false;
}

function clearSelection() {
  emit('update:modelValue', '');
  emit('select', null);
  menuOpen.value = false;
}

function isProviderSelected(providerId: string) {
  return props.multiple
    ? selectedProviderIds.value.includes(providerId)
    : props.modelValue === providerId;
}

function removeSelected(providerId: string) {
  emit(
    'update:modelValue',
    selectedProviderIds.value.filter((value) => value !== providerId),
  );
}

function moveSelected(index: number, delta: number) {
  const targetIndex = index + delta;
  if (targetIndex < 0 || targetIndex >= selectedProviderIds.value.length) {
    return;
  }
  const selected = [...selectedProviderIds.value];
  const [providerId] = selected.splice(index, 1);
  selected.splice(targetIndex, 0, providerId);
  emit('update:modelValue', selected);
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

async function testProvider(provider: ProviderConfig) {
  if (testingProviderIds.value.includes(provider.id)) return;
  testingProviderIds.value.push(provider.id);
  try {
    const startTime = performance.now();
    const response = await providerApi.test(provider.id);
    if (response.data.status === 'ok' && response.data.data.error === null) {
      const latency = Math.max(0, Math.round(performance.now() - startTime));
      toastSuccess(
        providerTm('models.testSuccessWithLatency', {
          id: provider.id,
          latency,
        }),
      );
    } else {
      throw new Error(
        response.data.data.error || providerTm('models.testError'),
      );
    }
  } catch (error: unknown) {
    const err = error as {
      response?: { data?: { message?: string } };
      message?: string;
    };
    toastError(
      err.response?.data?.message ||
        err.message ||
        providerTm('models.testError'),
    );
  } finally {
    testingProviderIds.value = testingProviderIds.value.filter(
      (providerId) => providerId !== provider.id,
    );
  }
}

function handleMenuToggle(isOpen: boolean) {
  if (isOpen) void loadProviderConfigs(true);
}

function openProviderDrawer() {
  menuOpen.value = false;
  providerDrawer.value = true;
}

function closeProviderDrawer() {
  providerDrawer.value = false;
}

function getCurrentSelection() {
  return {
    providerId: Array.isArray(props.modelValue) ? '' : props.modelValue,
    modelName: selectedProvider.value?.model || props.fallbackModel || '',
  };
}

watch(providerDrawer, (isOpen, wasOpen) => {
  if (!isOpen && wasOpen) void loadProviderConfigs(true);
});

defineExpose({ getCurrentSelection });
</script>

<style scoped>
.provider-select-menu {
  max-width: 100%;
}

.provider-select-menu--config {
  display: flex;
  width: 100%;
  justify-content: flex-end;
}

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

.provider-trigger--config {
  width: fit-content;
  min-height: 36px;
  justify-content: space-between;
  margin-left: auto;
  padding: 6px 8px;
  border-radius: 8px;
}

.provider-trigger--config:hover {
  background: rgba(var(--v-theme-on-surface), 0.045);
}

.provider-trigger--config .provider-trigger-title {
  font-size: 0.88rem;
  font-weight: 500;
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
  border: 1px solid rgba(var(--v-theme-on-surface), 0.09);
  border-radius: 14px !important;
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.07) !important;
}

:global(.v-overlay.v-menu .v-overlay__content > .provider-menu-card) {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.09) !important;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.07) !important;
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

.provider-loading {
  margin: 6px 0;
}

.selected-provider-section {
  margin-bottom: 2px;
}

.selected-provider-label {
  padding: 2px 8px 6px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-size: 12px;
}

.selected-provider-list {
  max-height: 184px;
  overflow-y: auto;
  padding: 0;
  background: rgba(var(--v-theme-on-surface), 0.025);
  border-radius: 10px;
}

.selected-provider-item {
  min-height: 42px !important;
}

.selected-provider-actions {
  display: inline-flex;
  align-items: center;
  gap: 1px;
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
  background: rgba(var(--v-theme-primary), 0.08);
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

.meta-icon-badge {
  display: inline-flex;
  align-items: center;
  color: rgba(var(--v-theme-on-surface), 0.72);
}

.meta-icon-badge--disabled {
  color: rgba(var(--v-theme-on-surface), 0.34);
}

.meta-context-badge {
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

.provider-menu-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
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

.provider-menu-divider {
  margin: 6px 0;
}

.provider-create-button {
  justify-content: flex-start;
  border-radius: 9px;
  text-transform: none;
}

.provider-drawer-overlay {
  align-items: stretch;
  justify-content: flex-end;
}

.provider-drawer-card {
  display: flex;
  width: clamp(360px, 70vw, 1200px);
  height: calc(100vh - 32px);
  flex-direction: column;
  margin: 16px;
  overflow: hidden;
}

.provider-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 12px;
}

.provider-drawer-content {
  flex: 1;
  overflow: hidden;
}

.provider-drawer-content > * {
  height: 100%;
  overflow: auto;
}

@media (max-width: 960px) {
  .provider-drawer-card {
    width: calc(100dvw - 24px);
    height: calc(100dvh - 24px);
    margin: 12px;
  }
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

@media (max-width: 600px) {
  .provider-drawer-overlay {
    align-items: stretch;
    justify-content: stretch;
  }

  .provider-drawer-card {
    width: 100dvw;
    height: 100dvh;
    margin: 0;
    border-radius: 0;
  }

  .provider-drawer-header {
    padding: 8px 12px;
  }

  .provider-drawer-content {
    overflow: auto;
  }

  :deep(.v-overlay__content) {
    width: 100dvw;
    max-width: 100dvw;
    margin: 0;
  }
}
</style>
