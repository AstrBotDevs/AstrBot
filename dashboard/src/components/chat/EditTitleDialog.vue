<template>
  <v-dialog :model-value="modelValue" @update:model-value="v => emit('update:modelValue', v)" max-width="400">
    <v-card>
      <v-card-title class="dialog-title">{{ titleText }}</v-card-title>
      <v-card-text>
        <v-text-field
          v-model="internalTitle"
          :label="placeholder"
          variant="outlined"
          hide-details
          class="mt-2"
          @keyup.enter="onSave"
          autofocus
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="emit('update:modelValue', false)" color="grey-darken-1">{{ cancelText }}</v-btn>
        <v-btn variant="text" @click="onSave" color="primary">{{ saveText }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
  </template>

<script setup lang="ts">
import { computed, watch, ref } from 'vue';

const props = defineProps<{ 
  modelValue: boolean;
  title: string;
  i18n: {
    titleText: string;
    placeholder: string;
    cancelText: string;
    saveText: string;
  }
}>();
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void;
  (e: 'save', title: string): void;
}>();

const internalTitle = ref(props.title || '');

watch(() => props.title, (v) => {
  internalTitle.value = v || '';
});

const titleText = computed(() => props.i18n.titleText);
const placeholder = computed(() => props.i18n.placeholder);
const cancelText = computed(() => props.i18n.cancelText);
const saveText = computed(() => props.i18n.saveText);

function onSave() {
  emit('save', (internalTitle.value || '').trim());
}
</script>

<style scoped>
.dialog-title {
  font-size: 18px;
  font-weight: 500;
  padding-bottom: 8px;
}
</style>
