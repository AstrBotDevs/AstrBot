<template>
  <div class="d-flex flex-column ga-2 w-100">
    <v-select
      :model-value="selection"
      :items="items"
      @update:model-value="selectOption"
      aria-label="Reasoning Effort"
      density="compact"
      variant="outlined"
      hide-details
    />
    <v-text-field
      v-if="selection === customOption"
      :model-value="modelValue"
      @update:model-value="value => { lastEmittedValue = value ?? ''; emit('update:modelValue', lastEmittedValue) }"
      :aria-label="t('core.common.objectEditor.custom')"
      :placeholder="t('core.common.objectEditor.omitWhenEmpty')"
      density="compact"
      variant="outlined"
      clearable
      hide-details
    />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from '@/i18n/composables'

const props = defineProps({
  modelValue: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue'])
const { t } = useI18n()
const presets = ['none', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra']
// A distinct sentinel keeps every string available as a custom value.
const customOption = -1
const customMode = ref(false)
let lastEmittedValue
const selection = computed(() => customMode.value || (props.modelValue && !presets.includes(props.modelValue))
  ? customOption
  : props.modelValue || '')
const items = computed(() => [
  { title: 'Default', value: '' },
  { title: 'Custom', value: customOption },
  ...presets.map(value => ({ title: value, value }))
])

watch(() => props.modelValue, value => {
  // Keep the custom input open while typing, even when it matches a preset.
  if (value !== lastEmittedValue) customMode.value = false
  lastEmittedValue = undefined
})

function selectOption(value) {
  customMode.value = value === customOption
  if (!customMode.value) {
    lastEmittedValue = value
    emit('update:modelValue', value)
  }
}
</script>
