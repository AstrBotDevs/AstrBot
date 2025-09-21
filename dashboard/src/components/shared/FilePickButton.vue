<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ 
  accept?: string,
  multiple?: boolean,
  color?: string,
  buttonText?: string,
  icon?: string,
  loading?: boolean,
  disabled?: boolean,
  size?: string
}>()

const emit = defineEmits<{ (e: 'picked', files: File | File[] | null): void }>()

const fileInputRef = ref<any>(null)
const model = ref<any>(null)

function trigger() {
  if (fileInputRef.value?.click) fileInputRef.value.click()
}

function onPicked(val: any) {
  emit('picked', val || null)
  // reset to allow picking same file again
  model.value = null
}
</script>

<template>
  <div class="file-pick-button">
    <v-file-input
      ref="fileInputRef"
      v-model="model"
      :accept="accept"
      :multiple="multiple"
      hide-details
      hide-input
      class="d-none"
      @update:modelValue="onPicked"
    />
    <v-btn 
      :color="color || 'primary'" 
      :loading="loading" 
      :disabled="disabled"
      :size="(size as any) || 'default'"
      :prepend-icon="icon || 'mdi-upload'"
      @click="trigger"
    >
      {{ buttonText || '选择文件' }}
    </v-btn>
  </div>
  
</template>

<style scoped>
.d-none { display: none; }
</style>

