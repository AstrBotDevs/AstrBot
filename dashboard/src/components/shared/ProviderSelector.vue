<template>
  <ProviderSelectMenu
    :model-value="modelValue"
    :provider-type="providerType"
    :button-text="buttonText"
    variant="config"
    :allow-empty="!multiple"
    :multiple="multiple"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>

<script setup lang="ts">
import ProviderSelectMenu from '@/components/shared/ProviderSelectMenu.vue';

withDefaults(
  defineProps<{
    modelValue?: string | string[];
    providerType?: string;
    buttonText?: string;
    multiple?: boolean;
  }>(),
  {
    modelValue: '',
    providerType: 'chat_completion',
    buttonText: '',
    multiple: false,
  },
);

const emit = defineEmits<{
  'update:modelValue': [value: string | string[]];
}>();
</script>
