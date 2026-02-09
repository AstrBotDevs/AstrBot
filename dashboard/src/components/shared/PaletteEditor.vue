<template>
  <div class="palette-editor">
    <div class="d-flex align-center gap-2">
      <v-menu
        v-model="menuOpen"
        :close-on-content-click="false"
        location="bottom start"
        transition="fade-transition"
      >
        <template #activator="{ props: menuProps }">
          <div
            v-bind="menuProps"
            class="color-preview-btn"
            :style="{ backgroundColor: previewColor }"
            :title="t('core.common.palette.clickToSelect')"
          >
            <v-icon v-if="!hasColor" size="small" color="grey">mdi-palette</v-icon>
          </div>
        </template>

        <v-card class="palette-popup" width="300">
          <v-color-picker
            v-model="pickerColor"
            :modes="['hex', 'rgb', 'hsl']"
            hide-inputs
            elevation="0"
            width="300"
          />

          <v-divider />

          <v-card-text class="pa-3">
            <div class="format-row mb-2">
              <span class="format-label">{{ t('core.common.palette.formatHex') }}</span>
              <v-text-field
                v-model="hexInput"
                density="compact"
                variant="outlined"
                hide-details
                class="format-input"
                @update:model-value="onHexInput"
                @blur="syncFromPicker"
              />
              <v-btn
                icon
                size="x-small"
                variant="text"
                @click="copyToClipboard(hexInput)"
                :title="t('core.common.copy')"
              >
                <v-icon size="small">mdi-content-copy</v-icon>
              </v-btn>
            </div>

            <div class="format-row mb-2">
              <span class="format-label">{{ t('core.common.palette.formatRgb') }}</span>
              <v-text-field
                v-model="rgbInput"
                density="compact"
                variant="outlined"
                hide-details
                class="format-input"
                @update:model-value="onRgbInput"
                @blur="syncFromPicker"
              />
              <v-btn
                icon
                size="x-small"
                variant="text"
                @click="copyToClipboard(rgbInput)"
                :title="t('core.common.copy')"
              >
                <v-icon size="small">mdi-content-copy</v-icon>
              </v-btn>
            </div>

            <div class="format-row">
              <span class="format-label">{{ t('core.common.palette.formatHsv') }}</span>
              <v-text-field
                v-model="hsvInput"
                density="compact"
                variant="outlined"
                hide-details
                class="format-input"
                @update:model-value="onHsvInput"
                @blur="syncFromPicker"
              />
              <v-btn
                icon
                size="x-small"
                variant="text"
                @click="copyToClipboard(hsvInput)"
                :title="t('core.common.copy')"
              >
                <v-icon size="small">mdi-content-copy</v-icon>
              </v-btn>
            </div>
          </v-card-text>

          <v-divider />

          <v-card-actions class="justify-space-between pa-2">
            <div class="d-flex gap-1">
              <v-btn
                size="small"
                variant="text"
                prepend-icon="mdi-content-paste"
                @click="pasteFromClipboard"
              >
                {{ t('core.common.palette.paste') }}
              </v-btn>
            </div>
            <div class="d-flex gap-1">
              <v-btn
                size="small"
                variant="text"
                @click="clearColor"
              >
                {{ t('core.common.clear') }}
              </v-btn>
              <v-btn
                size="small"
                color="primary"
                variant="tonal"
                @click="confirmColor"
              >
                {{ t('core.common.confirm') }}
              </v-btn>
            </div>
          </v-card-actions>
        </v-card>
      </v-menu>

      <v-text-field
        v-model="localValue"
        @update:model-value="onInputValueChange"
        @paste="onPaste"
        density="compact"
        variant="outlined"
        class="config-field flex-grow-1"
        hide-details
        :placeholder="formatPlaceholder"
        :error="!!validationError"
        :title="validationError"
      />
      <v-icon
        v-if="validationError"
        size="small"
        color="warning"
        :title="validationError"
      >
        mdi-alert-circle-outline
      </v-icon>
    </div>

    <v-snackbar v-model="snackbar" :timeout="1500" location="top">
      {{ snackbarText }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from '@/i18n/composables'
import {
  hexToRgb,
  rgbToHex,
  rgbToHsv,
  parseAnyColor,
  ColorFormat,
  type ColorFormatType,
  type RgbColor
} from '@/utils/color'

interface Props {
  modelValue?: string
  format?: ColorFormatType
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  format: ColorFormat.HEX
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()
const { t } = useI18n()

const menuOpen = ref(false)
const localValue = ref(props.modelValue)
const pickerColor = ref('#FFFFFF')
const hexInput = ref('#FFFFFF')
const rgbInput = ref('rgb(255, 255, 255)')
const hsvInput = ref('hsv(0, 0%, 100%)')
const snackbar = ref(false)
const snackbarText = ref('')

const formatPlaceholder = computed(() => {
  switch (props.format) {
    case ColorFormat.RGB: return t('core.common.palette.placeholderRgb')
    case ColorFormat.HSV: return t('core.common.palette.placeholderHsv')
    default: return t('core.common.palette.placeholderHex')
  }
})

const hasColor = computed(() => {
  return localValue.value && localValue.value.trim() !== ''
})

const previewColor = computed(() => {
  if (!hasColor.value) return '#FFFFFF'
  const parsed = parseAnyColor(localValue.value)
  return parsed ? rgbToHex(parsed.r, parsed.g, parsed.b) : '#FFFFFF'
})

const validationError = computed(() => {
  if (!hasColor.value) return ''
  const parsed = parseAnyColor(localValue.value)
  if (!parsed) {
    return t('core.common.palette.invalidFormat')
  }
  return ''
})

function parsePickerColor(color: string | RgbColor | null | undefined): RgbColor {
  if (!color) return { r: 255, g: 255, b: 255 }
  if (typeof color === 'string') {
    return hexToRgb(color) || { r: 255, g: 255, b: 255 }
  }
  if (typeof color === 'object') {
    return { r: color.r || 0, g: color.g || 0, b: color.b || 0 }
  }
  return { r: 255, g: 255, b: 255 }
}

function formatOutput(r: number, g: number, b: number): string {
  switch (props.format) {
    case ColorFormat.RGB:
      return `rgb(${r}, ${g}, ${b})`
    case ColorFormat.HSV: {
      const hsv = rgbToHsv(r, g, b)
      return `hsv(${hsv.h}, ${hsv.s}%, ${hsv.v}%)`
    }
    default:
      return rgbToHex(r, g, b)
  }
}

function syncInputsFromColor(r: number, g: number, b: number): void {
  hexInput.value = rgbToHex(r, g, b)
  rgbInput.value = `rgb(${r}, ${g}, ${b})`
  const hsv = rgbToHsv(r, g, b)
  hsvInput.value = `hsv(${hsv.h}, ${hsv.s}%, ${hsv.v}%)`
}

function syncFromPicker() {
  const color = parsePickerColor(pickerColor.value)
  syncInputsFromColor(color.r, color.g, color.b)
}

watch(pickerColor, () => {
  syncFromPicker()
})

function syncInternalState() {
  if (hasColor.value) {
    const parsed = parseAnyColor(localValue.value)
    if (parsed) {
      const newHex = rgbToHex(parsed.r, parsed.g, parsed.b)
      if (pickerColor.value !== newHex) {
        pickerColor.value = newHex
        syncInputsFromColor(parsed.r, parsed.g, parsed.b)
      }
    }
  } else {
    pickerColor.value = '#FFFFFF'
    syncInputsFromColor(255, 255, 255)
  }
}

watch(menuOpen, (open) => {
  if (open) syncInternalState()
})

watch(() => props.modelValue, (newVal) => {
  if (newVal !== localValue.value) {
    localValue.value = newVal
    syncInternalState()
  }
})

function onHexInput(value: string): void {
  const parsed = parseAnyColor(value)
  if (parsed) {
    pickerColor.value = rgbToHex(parsed.r, parsed.g, parsed.b)
    rgbInput.value = `rgb(${parsed.r}, ${parsed.g}, ${parsed.b})`
    const hsv = rgbToHsv(parsed.r, parsed.g, parsed.b)
    hsvInput.value = `hsv(${hsv.h}, ${hsv.s}%, ${hsv.v}%)`
  }
}

function onRgbInput(value: string): void {
  const parsed = parseAnyColor(value)
  if (parsed) {
    pickerColor.value = rgbToHex(parsed.r, parsed.g, parsed.b)
    hexInput.value = rgbToHex(parsed.r, parsed.g, parsed.b)
    const hsv = rgbToHsv(parsed.r, parsed.g, parsed.b)
    hsvInput.value = `hsv(${hsv.h}, ${hsv.s}%, ${hsv.v}%)`
  }
}

function onHsvInput(value: string): void {
  const parsed = parseAnyColor(value)
  if (parsed) {
    pickerColor.value = rgbToHex(parsed.r, parsed.g, parsed.b)
    hexInput.value = rgbToHex(parsed.r, parsed.g, parsed.b)
    rgbInput.value = `rgb(${parsed.r}, ${parsed.g}, ${parsed.b})`
  }
}

function confirmColor() {
  const color = parsePickerColor(pickerColor.value)
  emit('update:modelValue', formatOutput(color.r, color.g, color.b))
  menuOpen.value = false
}

function clearColor() {
  emit('update:modelValue', '')
  menuOpen.value = false
}

function onInputValueChange(value: string): void {
  localValue.value = value
  const parsed = parseAnyColor(value)
  if (parsed) {
    // 只有当输入有效时，才向父组件发送规范化后的值
    emit('update:modelValue', formatOutput(parsed.r, parsed.g, parsed.b))
    // 同时更新内部拾色器状态，以便预览正确
    pickerColor.value = rgbToHex(parsed.r, parsed.g, parsed.b)
  }
}

async function copyToClipboard(text: string): Promise<void> {
  if (!navigator.clipboard) {
    snackbarText.value = t('core.common.palette.copyFailed')
    snackbar.value = true
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    snackbarText.value = t('core.common.copied')
    snackbar.value = true
  } catch {
    snackbarText.value = t('core.common.palette.copyFailed')
    snackbar.value = true
  }
}

async function pasteFromClipboard() {
  if (!navigator.clipboard) {
    snackbarText.value = t('core.common.palette.pasteFailed')
    snackbar.value = true
    return
  }
  try {
    const text = await navigator.clipboard.readText()
    const parsed = parseAnyColor(text.trim())
    if (parsed) {
      pickerColor.value = rgbToHex(parsed.r, parsed.g, parsed.b)
      syncInputsFromColor(parsed.r, parsed.g, parsed.b)
      snackbarText.value = t('core.common.palette.pasteSuccess')
      snackbar.value = true
    } else {
      snackbarText.value = t('core.common.palette.pasteInvalid')
      snackbar.value = true
    }
  } catch {
    snackbarText.value = t('core.common.palette.pasteFailed')
    snackbar.value = true
  }
}

function onPaste(event: ClipboardEvent): void {
  const text = event.clipboardData?.getData('text')
  if (text) {
    const parsed = parseAnyColor(text.trim())
    if (parsed) {
      event.preventDefault()
      emit('update:modelValue', formatOutput(parsed.r, parsed.g, parsed.b))
    }
  }
}
</script>

<style scoped>
.palette-editor {
  width: 100%;
}

.color-preview-btn {
  width: 36px;
  height: 36px;
  min-width: 36px;
  border-radius: 4px;
  border: 1px solid rgba(0, 0, 0, 0.2);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: box-shadow 0.2s;
}

.color-preview-btn:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.palette-popup {
  overflow: hidden;
}

.format-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.format-label {
  width: 36px;
  font-size: 12px;
  font-weight: 500;
  color: rgba(0, 0, 0, 0.6);
}

.format-input {
  flex: 1;
}

.format-input :deep(.v-field__input) {
  font-size: 12px;
  font-family: monospace;
  padding: 4px 8px;
}

.config-field {
  margin-bottom: 0;
}

:deep(.v-color-picker) {
  border-radius: 0;
}

:deep(.v-field__input) {
  font-size: 14px;
}
</style>
