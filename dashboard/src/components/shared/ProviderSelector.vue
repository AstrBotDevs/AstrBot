<template>
  <ProviderSelectMenu
    :model-value="modelValue"
    :provider-type="providerType"
    :required-modality="requiredModality"
    variant="config"
    :allow-empty="!multiple"
    :multiple="multiple"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>

<script setup>
import ProviderSelectMenu from "@/components/shared/ProviderSelectMenu.vue";

defineProps({
  modelValue: {
    type: [String, Array],
    default: "",
  },
  providerType: {
    type: String,
    default: "chat_completion",
  },
  buttonText: {
    type: String,
    default: "",
  },
  requiredModality: String,
  multiple: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["update:modelValue"]);
</script>
