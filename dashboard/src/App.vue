<template>
  <RouterView></RouterView>
  <WaitingForRestart ref="globalWaitingRef" />

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
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useToastStore } from '@/stores/toast'
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue'
import { restartAstrBot } from '@/utils/restartAstrBot'

const toastStore = useToastStore()
const globalWaitingRef = ref(null)
let disposeTrayRestartListener = null

const snackbarShow = computed({
  get: () => !!toastStore.current,
  set: (val) => {
    if (!val) toastStore.shift()
  }
})

onMounted(() => {
  const desktopBridge = window.astrbotDesktop
  if (!desktopBridge?.isElectron || !desktopBridge.onTrayRestartBackend) {
    return
  }
  disposeTrayRestartListener = desktopBridge.onTrayRestartBackend(async () => {
    try {
      await restartAstrBot(globalWaitingRef.value)
    } catch (error) {
      globalWaitingRef.value?.stop?.()
      console.error('Tray restart backend failed:', error)
    }
  })
})

onBeforeUnmount(() => {
  if (disposeTrayRestartListener) {
    disposeTrayRestartListener()
    disposeTrayRestartListener = null
  }
})
</script>
