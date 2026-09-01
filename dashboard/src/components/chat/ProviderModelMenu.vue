<template>
  <ProviderSelectMenu
    ref="providerSelectMenuRef"
    :model-value="selectedProviderId"
    :fallback-model="selectedModelName"
    provider-type="chat_completion"
    :variant="variant"
    :allow-empty="false"
    @update:model-value="updateSelection"
    @select="saveSelection"
  />
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import ProviderSelectMenu from '@/components/shared/ProviderSelectMenu.vue';

interface ProviderSelection {
  id: string;
  model?: string;
}

const props = withDefaults(
  defineProps<{
    variant?: 'input' | 'header';
  }>(),
  {
    variant: 'input',
  },
);

const SELECTED_PROVIDER_KEY = 'selectedProvider';
const SELECTED_PROVIDER_MODEL_KEY = 'selectedProviderModel';
const selectedProviderId = ref('');
const selectedModelName = ref('');
const providerSelectMenuRef = ref<InstanceType<
  typeof ProviderSelectMenu
> | null>(null);
const variant = props.variant;

function updateSelection(value: string | string[]) {
  if (typeof value === 'string') selectedProviderId.value = value;
}

function saveSelection(provider: ProviderSelection | null) {
  if (!provider) return;
  selectedProviderId.value = provider.id;
  selectedModelName.value = provider.model || '';
  localStorage.setItem(SELECTED_PROVIDER_KEY, provider.id);
  localStorage.setItem(SELECTED_PROVIDER_MODEL_KEY, provider.model || '');
}

function getCurrentSelection() {
  return (
    providerSelectMenuRef.value?.getCurrentSelection() || {
      providerId: selectedProviderId.value,
      modelName: selectedModelName.value,
    }
  );
}

onMounted(() => {
  selectedProviderId.value = localStorage.getItem(SELECTED_PROVIDER_KEY) || '';
  selectedModelName.value =
    localStorage.getItem(SELECTED_PROVIDER_MODEL_KEY) || '';
});

defineExpose({ getCurrentSelection });
</script>
