<template>
  <RouterView></RouterView>

  <!-- 全局唯一 snackbar -->
  <v-snackbar v-if="toastStore.current" v-model="snackbarShow" :color="toastStore.current.color"
    :timeout="toastStore.current.timeout" :multi-line="toastStore.current.multiLine"
    :location="toastStore.current.location" close-on-back>
    {{ toastStore.current.message }}
    <template #actions v-if="toastStore.current.closable">
      <v-btn variant="text" @click="snackbarShow = false">关闭</v-btn>
    </template>
  </v-snackbar>
</template>

<script setup>
import { RouterView } from 'vue-router';
import { computed } from 'vue'
import { useToastStore } from '@/stores/toast'

const toastStore = useToastStore()

const snackbarShow = computed({
  get: () => !!toastStore.current,
  set: (val) => {
    if (!val) toastStore.shift()
  }
})
</script>
