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
import { ref } from "vue";
import type ProviderSelectMenu from "@/components/shared/ProviderSelectMenu.vue";
import { useProviderModelSelection } from "@/composables/useProviderModelSelection";

interface ProviderSelection {
  id: string;
  model?: string;
}

const props = withDefaults(
  defineProps<{
    variant?: "input" | "header";
  }>(),
  {
    variant: "input",
  },
);

const { selectedProviderId, selectedModelName, setSelection } = useProviderModelSelection();
const providerSelectMenuRef = ref<InstanceType<typeof ProviderSelectMenu> | null>(null);
const variant = props.variant;

function updateSelection(value: string | string[]) {
  if (typeof value === "string") setSelection(value, selectedModelName.value);
}

function saveSelection(provider: ProviderSelection | null) {
  if (!provider) return;
  setSelection(provider.id, provider.model || "");
}

function getCurrentSelection() {
  return (
    providerSelectMenuRef.value?.getCurrentSelection() || {
      providerId: selectedProviderId.value,
      modelName: selectedModelName.value,
    }
  );
}

defineExpose({ getCurrentSelection });
</script>
