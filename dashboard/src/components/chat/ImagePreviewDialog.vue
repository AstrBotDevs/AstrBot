<template>
  <v-dialog :model-value="modelValue" @update:model-value="v => emit('update:modelValue', v)" max-width="90vw" max-height="90vh">
    <v-card class="image-preview-card" elevation="8">
      <v-card-title class="d-flex justify-space-between align-center pa-4">
        <span>{{ title }}</span>
        <v-btn icon="mdi-close" variant="text" @click="emit('update:modelValue', false)" />
      </v-card-title>
      <v-card-text class="text-center pa-4">
        <img :src="imageUrl" class="preview-image-large" />
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
const props = defineProps<{ modelValue: boolean; title: string; imageUrl: string }>();
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>();
</script>

<style scoped>
.preview-image-large {
  max-width: 85vw;
  max-height: 80vh;
  border-radius: 8px;
}
</style>
