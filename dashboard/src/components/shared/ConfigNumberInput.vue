<template>
  <div class="d-flex align-center ga-3 w-100">
    <template v-if="slider">
      <span>{{ slider.min ?? 0 }}</span>
      <v-slider
        :model-value="Number(modelValue) || 0"
        @update:model-value="value => { badInput = false; numericTemp = null; emit('update:modelValue', value) }"
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
      @input="event => { badInput = event.target.validity.badInput; updateValue(event.target.value) }"
      @update:model-value="value => { if (value == null) updateValue(value) }"
      @blur="() => { if (!badInput && !(required && numericTemp === '')) numericTemp = null }"
      @wheel="event => { if (event.target.matches('input[type=number]:focus:read-write')) event.preventDefault() }"
      :placeholder="placeholder"
      :aria-label="$attrs['aria-label']"
      :validation-value="badInput ? NaN : (numericTemp ?? modelValue)"
      :rules="[value => (
        value === '' || value == null
          ? !required
          : Number.isFinite(Number(value))
            && (!integer || Number.isInteger(Number(value)))
            && (min == null || Number(value) >= min)
            && (max == null || Number(value) <= max)
      ) || t('core.common.objectEditor.invalidNumber')]"
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
import { ref, watch } from 'vue'
import { useI18n } from '@/i18n/composables'

const props = defineProps({
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
const badInput = ref(false)

watch(() => props.modelValue, (value) => {
  if (value !== '' && value != null && (badInput.value || numericTemp.value === '')) {
    badInput.value = false
    numericTemp.value = null
  }
})

function updateValue(value) {
  if (value == null) badInput.value = false
  numericTemp.value = value ?? ''
  // Native number inputs expose incomplete expressions as an empty string.
  if (badInput.value && !props.required) return
  const number = Number(numericTemp.value)
  emit('update:modelValue', numericTemp.value === '' ? '' : Number.isFinite(number) ? number : numericTemp.value)
}
</script>
