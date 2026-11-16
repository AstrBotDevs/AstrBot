<template>
  <div class="d-flex align-center ga-3 w-100">
    <template v-if="slider">
      <span>{{ slider.min ?? 0 }}</span>
      <v-slider
        :model-value="Number(modelValue) || 0"
        @update:model-value="emit('update:modelValue', $event)"
        :min="slider.min ?? 0"
        :max="slider.max ?? 100"
        :step="slider.step ?? 1"
        color="primary"
        density="compact"
        hide-details
        class="flex-grow-1"
      />
      <span>{{ slider.max ?? 100 }}</span>
    </template>
    <v-text-field
      :model-value="numericTemp ?? modelValue"
      @update:model-value="updateValue"
      @blur="numericTemp = null"
      :placeholder="placeholder"
      :aria-label="$attrs['aria-label']"
      :rules="[value => !required || (value !== '' && value != null) || t('core.common.objectEditor.numberRequired'), value => value === '' || value == null || (Number.isFinite(Number(value)) && (!integer || Number.isInteger(Number(value))) && (min == null || Number(value) >= min) && (max == null || Number(value) <= max)) || t('core.common.objectEditor.invalidNumber')]"
      type="number"
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details="auto"
      clearable
      :style="slider ? 'max-width: 120px;' : 'min-width: 0;'"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from '@/i18n/composables'

defineProps({
  modelValue: { type: [Number, String], default: '' },
  slider: { type: Object, default: null },
  min: { type: Number, default: undefined },
  max: { type: Number, default: undefined },
  integer: { type: Boolean, default: false },
  required: { type: Boolean, default: false },
  placeholder: { type: String, default: undefined }
})
const emit = defineEmits(['update:modelValue'])
const { t } = useI18n()
const numericTemp = ref(null)

function updateValue(value) {
  numericTemp.value = value ?? ''
  const number = Number(numericTemp.value)
  emit('update:modelValue', numericTemp.value === '' ? '' : Number.isFinite(number) ? number : numericTemp.value)
}
</script>
